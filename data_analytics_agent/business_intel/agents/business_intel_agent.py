"""Root Business Intel Agent.

Unified orchestrator entrypoint combining Context and Analytics faces.
Runs tools in parallel where independent, enforces max 5 tool calls,
gracefully degrades on tool errors, and checks grounding.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from business_intel.config import MAX_TOOL_CALLS_PER_TURN
from business_intel.narrator import narrate_response
from business_intel.router import route_query
from business_intel.schemas import AgentAnswer, Envelope, OutOfScopeResponse
from business_intel.tools.registry import async_call_tool


class BusinessIntelAgent:
    """Root Business Intel Agent for Alexa Business Autopilot."""

    name: str = "business_intel_agent"
    description: str = (
        "Combined Business Context & Analytics Agent for owner-operated cloud kitchens. "
        "Provides morning briefings, cash position, performance analytics, unit economics, "
        "and cost trends."
    )

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path

    def ask(
        self,
        query: str,
        db_path: Optional[str] = None,
    ) -> Union[AgentAnswer, OutOfScopeResponse]:
        """Synchronously answer an owner query."""
        return asyncio.run(self.ask_async(query, db_path=db_path))

    async def ask_async(
        self,
        query: str,
        db_path: Optional[str] = None,
    ) -> Union[AgentAnswer, OutOfScopeResponse]:
        """Asynchronously answer an owner query."""
        trace_id = f"bi_{uuid.uuid4().hex[:12]}"
        effective_db = db_path or self.db_path

        # 1. Routing
        decision = route_query(query)
        if decision.category == "out_of_scope" and decision.out_of_scope:
            return decision.out_of_scope

        tools_to_run = decision.tools or [("get_business_overview", {"include_ledgers": True})]
        # Enforce max 5 tool calls guardrail
        tools_to_run = tools_to_run[:MAX_TOOL_CALLS_PER_TURN]

        # 2. Parallel execution of independent tools
        async def _run_single(tool_name: str, kwargs: Dict[str, Any]) -> Tuple[Dict[str, Any], Envelope]:
            start_t = time.perf_counter()
            try:
                env = await async_call_tool(tool_name, kwargs, db_path=effective_db)
            except Exception as exc:
                env = Envelope(
                    ok=False,
                    data={},
                    confidence=0.0,
                    source="db",
                    warnings=[],
                    error=f"Execution failed: {str(exc)}",
                )
            dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
            meta_call = {"tool": tool_name, "args": kwargs, "latency_ms": dur_ms, "ok": env.ok}
            return meta_call, env

        results = await asyncio.gather(
            *[_run_single(name, args) for name, args in tools_to_run],
            return_exceptions=False,
        )

        tool_calls: List[Dict[str, Any]] = []
        envelopes: List[Envelope] = []
        for call_meta, env in results:
            tool_calls.append(call_meta)
            envelopes.append(env)

        # 3. Narrate response
        answer = narrate_response(query, envelopes)
        answer.trace_id = trace_id
        answer.tool_calls = tool_calls
        answer.envelopes = [env.model_dump() for env in envelopes]
        answer.intents = [decision.category]

        return answer
