"""
Alexa Business Autopilot -- Genuine Gemini Agent Orchestrator
=============================================================
Implements a real LLM-driven, tool-calling agent using the google-genai SDK.

The agent:
1. Receives a natural-language business goal from the owner.
2. Sends the goal + tool definitions to a real Gemini model.
3. Receives model-selected function calls (one per iteration).
4. Validates the function name against an explicit allowlist (TOOL_REGISTRY).
5. Validates and executes only the registered Python function.
6. Returns the actual result to Gemini in the correct SDK format.
7. Loops until the model returns a final text answer or max_iterations reached.
8. Returns a structured AgentResult with the recommendation, tool trace,
   evidence, assumptions, and approval requirements.

Safety guarantees
-----------------
* NO consequential mutations. All tools are read-only.
  If a purchase plan is needed, the agent recommends it -- the PurchaseApprovalService
  must still gate every execution through the two-phase approval flow.
* NO arbitrary code execution. TOOL_REGISTRY is the only dispatch table.
* NO model-generated SQL. Tools wrap deterministic Python services.
* API key is read exclusively from the GEMINI_API_KEY environment variable.
  It is never printed, logged, or stored.

Configuration
-------------
GEMINI_MODEL (env var): Gemini model name, default "gemini-2.0-flash-001".
GEMINI_API_KEY (env var): Required for live calls. Not required for unit tests
    that mock the client.
MAX_AGENT_ITERATIONS (env var): Max tool-call rounds, default 10.

Milestone B note (database integration)
----------------------------------------
The TeammateGateway (src/db/teammate_gateway.py) is proposed for a future
milestone. It will expose the 12 parameterised queries from
data/tool_queries.sql against data/demo.db in read-only mode, and inject
them into TOOL_LIST alongside the simulation tools declared in tools.py.

Before integration the following questions must be answered:
  Q1: Should the runtime agent query data/demo.db (which matches
      data/tool_queries.sql) or data/business.db (generic schema)?
  Q2: Do the :name labels in tool_queries.sql (e.g. -- :name get_inventory)
      indicate an aiosql/named-queries parser, or are they SQL comments?
      If the former, which parser version is in use?
  Q3: When a purchase plan is executed (PurchaseApprovalService.execute_plan),
      should a purchase_orders row be written to data/demo.db, or is the
      application-managed receipt in business_autopilot.sqlite3 sufficient?
"""
from __future__ import annotations

import json
import logging
import os
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-2.0-flash-001"
_MODEL = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
_MAX_ITER = int(os.environ.get("MAX_AGENT_ITERATIONS", "10"))

_SYSTEM_INSTRUCTIONS = """\
You are the Alexa Business Autopilot, a cautious and accurate financial and
operational copilot for Indian micro and small businesses. You serve business
owners across diverse verticals: home kitchens, retail kirana stores, salons,
bakeries, tailors, food catering, and light manufacturing.

Your role:
- Help owners understand whether an opportunity is safe to accept.
- Identify the binding constraint (capacity, cash, inventory, lead time).
- Use the available tools to gather evidence before drawing conclusions.
- Distinguish clearly between tool-provided facts, model inferences, and
  assumptions made due to missing data.
- Never fabricate inventory counts, cash balances, customer details, or
  business records. If data is absent, state this explicitly.
- Keep recommendations actionable and grounded in the tool results.
- For any consequential action (purchase, cash commitment, external message),
  specify that owner approval is required through the formal approval workflow.
  Do not claim that approval has been granted.

Response format (always structured):
  recommendation: A clear, direct recommendation.
  rationale: The evidence chain from tool results.
  trade_offs: Key risks and benefits.
  next_steps: Specific actions the owner should take.
  approvals_required: List any consequential actions awaiting owner approval.
  assumptions: Explicitly list any assumptions made.
  unknowns: Data that was missing or estimated.
"""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Structured output of a single agent run."""

    recommendation: str
    """The model's final natural-language recommendation."""

    rationale: str
    """Evidence chain extracted from tool results."""

    trade_offs: str
    """Key trade-offs and risks identified."""

    next_steps: List[str]
    """Concrete actions the owner should take."""

    approvals_required: List[str]
    """Consequential actions that are approval-gated (must not auto-execute)."""

    assumptions: List[str]
    """Explicit assumptions made due to missing information."""

    unknowns: List[str]
    """Data that was absent or estimated."""

    tools_invoked: List[Dict[str, Any]]
    """Ordered list of tool calls made, with args and summary output."""

    raw_response: str
    """The model's final text output before structured parsing."""

    iterations: int
    """Total tool-call rounds consumed."""

    error: Optional[str] = None
    """Set if the run ended due to a recoverable error."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation":    self.recommendation,
            "rationale":         self.rationale,
            "trade_offs":        self.trade_offs,
            "next_steps":        self.next_steps,
            "approvals_required": self.approvals_required,
            "assumptions":       self.assumptions,
            "unknowns":          self.unknowns,
            "tools_invoked":     self.tools_invoked,
            "iterations":        self.iterations,
            "error":             self.error,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_structured_response(text: str) -> Dict[str, Any]:
    """Best-effort extraction of structured fields from model text.

    The model is instructed to use specific section headers. This parser
    extracts them without requiring strict JSON output from the model.
    Falls back to returning the full text as the recommendation.
    """
    sections: Dict[str, Any] = {
        "recommendation": "",
        "rationale": "",
        "trade_offs": "",
        "next_steps": [],
        "approvals_required": [],
        "assumptions": [],
        "unknowns": [],
    }

    current_key: Optional[str] = None
    lines: List[str] = []

    key_map = {
        "recommendation":    "recommendation",
        "rationale":         "rationale",
        "trade_offs":        "trade_offs",
        "trade-offs":        "trade_offs",
        "next_steps":        "next_steps",
        "next steps":        "next_steps",
        "approvals_required": "approvals_required",
        "approvals required": "approvals_required",
        "assumptions":       "assumptions",
        "unknowns":          "unknowns",
    }

    list_keys = {"next_steps", "approvals_required", "assumptions", "unknowns"}

    def _flush():
        if current_key is None:
            return
        content = " ".join(lines).strip()
        if current_key in list_keys:
            items = [l.strip().lstrip("-* ").strip() for l in "\n".join(lines).splitlines() if l.strip()]
            sections[current_key] = [i for i in items if i]
        else:
            sections[current_key] = content

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        # Detect section headers like "**recommendation:**" or "Recommendation:"
        lower = stripped.lower().rstrip(":").strip("*_ ")
        if lower in key_map:
            _flush()
            current_key = key_map[lower]
            lines = []
        elif current_key is not None:
            lines.append(stripped)

    _flush()

    # If parsing found nothing useful, put the whole text as recommendation
    if not sections["recommendation"]:
        sections["recommendation"] = text.strip()

    return sections


def _dispatch_tool(name: str, args: Dict[str, Any]) -> Any:
    """Execute a registered tool by name with validated arguments.

    Args:
        name: The tool function name. Must exist in TOOL_REGISTRY.
        args: Raw argument dict from the model's FunctionCall.

    Returns:
        The tool's return value (always a dict in this registry).

    Raises:
        KeyError: If the name is not in TOOL_REGISTRY.
        Exception: Re-raised from the tool itself (captured by caller).
    """
    from src.agent.tools import TOOL_REGISTRY  # deferred to avoid circular imports

    if name not in TOOL_REGISTRY:
        raise KeyError(
            f"Unknown tool '{name}'. Allowed: {sorted(TOOL_REGISTRY.keys())}"
        )
    func = TOOL_REGISTRY[name]
    return func(**args)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_autopilot_agent(
    user_goal: str,
    *,
    business_id: Optional[str] = None,
    profile_repo: Optional[Any] = None,
    allow_offline: bool = False,
    model: Optional[str] = None,
    max_iterations: Optional[int] = None,
    api_key: Optional[str] = None,
    _client: Optional[Any] = None,   # injected in tests to avoid live API calls
) -> AgentResult:
    """Run the Gemini-powered business autopilot for a user's goal.

    Executes the full tool-calling loop:
      user_goal -> Gemini -> [function_call -> tool result -> Gemini]* -> final answer

    Args:
        user_goal: Natural-language description of what the business owner
            wants to evaluate or accomplish.
        business_id: Optional business ID to anchor context to an adaptive profile.
        profile_repo: Optional AdaptiveProfileRepository instance for isolation.
        allow_offline: When True, if GEMINI_API_KEY is absent and no _client is provided,
            runs deterministically via AdaptiveBusinessOrchestrator without crashing.
        model: Gemini model name override (default: GEMINI_MODEL env var or
            "gemini-2.0-flash-001").
        max_iterations: Maximum number of tool-call rounds (default: 10).
        api_key: API key override for testing. In production, read from
            GEMINI_API_KEY env var.
        _client: Injected mock client for offline unit tests. When provided,
            no real API call is made and no API key is required.

    Returns:
        AgentResult with the final recommendation and tool evidence.

    Raises:
        EnvironmentError: If GEMINI_API_KEY is absent, no _client is injected, and allow_offline is False.
        RuntimeError: For unrecoverable SDK errors after all retries.
    """
    from google import genai
    from google.genai import types
    from src.agent.tools import (
        TOOL_LIST,
        set_active_profile_repo,
        set_active_business_id,
        _active_adaptive_repo,
    )

    if profile_repo is not None:
        set_active_profile_repo(profile_repo)
    if business_id is not None:
        set_active_business_id(business_id)

    chosen_model = model or _MODEL
    chosen_max = max_iterations if max_iterations is not None else _MAX_ITER

    # -- Resolve active business context for instructions -------------------
    active_profile_context = ""
    if business_id:
        repo = profile_repo or _active_adaptive_repo
        if repo:
            prof = repo.get_profile(business_id)
            if prof:
                _confirmed = {
                    k: f.value for k, f in prof.facts.items()
                    if f.status.value == "confirmed"
                }
                _assumed = {
                    k: f.value for k, f in prof.facts.items()
                    if f.status.value == "assumed"
                }
                _missing = [
                    k for k, f in prof.facts.items()
                    if f.status.value == "unknown"
                ]
                active_profile_context = (
                    f"\n\nActive Business Context:\n"
                    f"- Business ID: {prof.business_id}\n"
                    f"- Name: {prof.display_name}\n"
                    f"- Category: {prof.category}\n"
                    f"- Onboarding Completed: {prof.onboarding_completed}\n"
                    f"- Confirmed Facts: {json.dumps(_confirmed)}\n"
                    f"- Missing Critical Fields: {', '.join(_missing)}\n"
                    f"- Assumptions: {json.dumps(_assumed)}\n"
                )
            else:
                active_profile_context = (
                    f"\n\nActive Business Context:\n"
                    f"- Business ID: '{business_id}' (Profile not yet registered. Ask the owner about their business or prompt onboarding.)\n"
                )

    # -- Build client --------------------------------------------------------
    if _client is None:
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            if allow_offline:
                from src.agent.orchestrator import AdaptiveBusinessOrchestrator
                repo = profile_repo or _active_adaptive_repo
                orchestrator = AdaptiveBusinessOrchestrator(repo=repo)
                offline_resp = orchestrator.handle_user_message(
                    business_id=business_id or "default",
                    message=user_goal,
                )
                return AgentResult(
                    recommendation=offline_resp.get("reply", ""),
                    rationale="Deterministic execution via AdaptiveBusinessOrchestrator (offline mode without Gemini API key).",
                    trade_offs="No generative LLM reasoning applied; structured rule-based responses only.",
                    next_steps=offline_resp.get("suggested_actions", []),
                    approvals_required=[],
                    assumptions=["Executed in offline mode without Gemini LLM."],
                    unknowns=[],
                    tools_invoked=[{
                        "tool": "offline_orchestrator",
                        "args": {"business_id": business_id, "user_goal": user_goal},
                        "summary": f"intent={offline_resp.get('intent', 'unknown')}",
                        "error": None,
                    }],
                    raw_response=offline_resp.get("reply", ""),
                    iterations=1,
                    error=None,
                )
            raise EnvironmentError(
                "GEMINI_API_KEY environment variable is not set. "
                "Set it before running the agent. Never pass the key in source code."
            )
        client = genai.Client(api_key=key)
    else:
        client = _client

    # -- Initialise conversation context -------------------------------------
    contents: List[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part(text=user_goal)],
        )
    ]

    tools_invoked: List[Dict[str, Any]] = []
    iterations = 0
    final_text = ""
    agent_error: Optional[str] = None

    # -- Agent loop ----------------------------------------------------------
    while iterations < chosen_max:
        iterations += 1
        logger.debug("Agent iteration %d/%d", iterations, chosen_max)

        try:
            response = client.models.generate_content(
                model=chosen_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTIONS + active_profile_context,
                    tools=TOOL_LIST,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True  # Manual loop so we control dispatch & logging
                    ),
                ),
            )
        except Exception as exc:
            # SDK or network error -- surface cleanly
            logger.error("Gemini API error on iteration %d: %s", iterations, exc)
            agent_error = f"Gemini API error: {exc}"
            break

        # -- Inspect response candidates -------------------------------------
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None:
            agent_error = "Gemini returned no candidates."
            break

        # Check for function calls in this response turn
        function_calls = response.function_calls  # List[FunctionCall] | None

        if not function_calls:
            # Model is done -- collect final text
            final_text = response.text or ""
            break

        # -- Execute each function call the model requested ------------------
        # Append the model's assistant turn (containing function call parts)
        contents.append(
            types.Content(
                role="model",
                parts=[types.Part(function_call=fc) for fc in function_calls],
            )
        )

        # Build function response parts for all calls in this turn
        function_response_parts: List[types.Part] = []

        for fc in function_calls:
            tool_name: str = fc.name
            tool_args: Dict[str, Any] = dict(fc.args) if fc.args else {}

            logger.debug("Tool call requested: %s(%s)", tool_name, tool_args)

            try:
                tool_result = _dispatch_tool(tool_name, tool_args)
                result_summary = str(tool_result)[:400]  # Truncate for log safety
                error_flag = None
            except KeyError as exc:
                # Unknown tool -- reject safely
                tool_result = {"error": f"Unknown tool: {exc}", "ok": False}
                result_summary = str(tool_result)
                error_flag = str(exc)
                logger.warning("Unknown tool requested by model: %s", tool_name)
            except Exception as exc:
                # Tool execution error -- return error result to model so it can adapt
                tool_result = {
                    "error": f"Tool execution failed: {type(exc).__name__}: {exc}",
                    "ok": False,
                }
                result_summary = str(tool_result)
                error_flag = str(exc)
                logger.warning(
                    "Tool '%s' raised %s: %s",
                    tool_name, type(exc).__name__, exc,
                    exc_info=False,
                )

            # Record for AgentResult
            tools_invoked.append({
                "tool":    tool_name,
                "args":    tool_args,
                "summary": result_summary[:200],
                "error":   error_flag,
            })

            # Build SDK function response part
            function_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response={"result": tool_result},
                    )
                )
            )

        # Append tool results as a user turn (required by Gemini protocol)
        contents.append(
            types.Content(
                role="user",
                parts=function_response_parts,
            )
        )

    else:
        # Iteration limit reached without a final answer
        agent_error = (
            f"Agent reached maximum iteration limit ({chosen_max}) without "
            "producing a final answer."
        )
        logger.warning(agent_error)

    # -- Parse structured fields from final text -----------------------------
    parsed = _parse_structured_response(final_text)

    return AgentResult(
        recommendation=parsed.get("recommendation", final_text),
        rationale=parsed.get("rationale", ""),
        trade_offs=parsed.get("trade_offs", ""),
        next_steps=parsed.get("next_steps", []),
        approvals_required=parsed.get("approvals_required", []),
        assumptions=parsed.get("assumptions", []),
        unknowns=parsed.get("unknowns", []),
        tools_invoked=tools_invoked,
        raw_response=final_text,
        iterations=iterations,
        error=agent_error,
    )
