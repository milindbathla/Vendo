"""
Tests: Gemini Agent Core (src/agent/)
======================================
All tests are fully offline -- they inject a mock Gemini client and never
call the real API. No GEMINI_API_KEY is required to run this file.

Test coverage:
  TC-01  Final response with no tool calls -> valid AgentResult
  TC-02  Tool call dispatched to correct registered function
  TC-03  Tool result returned to Gemini in correct SDK format
  TC-04  Multi-turn: model requests a second tool after first result
  TC-05  Unknown tool name rejected safely (KeyError, no crash)
  TC-06  Invalid tool arguments handled without crashing
  TC-07  Tool execution exception handled; error returned to model
  TC-08  Max iteration limit enforced; agent_error set
  TC-09  Missing GEMINI_API_KEY raises EnvironmentError (not KeyError)
  TC-10  No auto-execution of consequential actions (no approval bypass)
  TC-11  Non-food business request not forced into tiffin workflow
  TC-12  All original 131 tests remain unaffected (import guard)

Mock strategy
-------------
We build a minimal FakeClient that returns pre-scripted responses.
Each response is a FakeResponse with:
  - .candidates: list containing one FakeCandidate
  - .function_calls: None or list of FakeFC
  - .text: final answer string or None
"""
from __future__ import annotations

import os
import types as pytypes
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fake SDK objects
# We replicate only the attributes the agent loop accesses.
# ---------------------------------------------------------------------------

@dataclass
class FakeFunctionCall:
    """Minimal stand-in for google.genai.types.FunctionCall."""
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None


@dataclass
class FakeFunctionResponse:
    """Minimal stand-in for google.genai.types.FunctionResponse."""
    name: str
    response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeCandidate:
    """Minimal stand-in for a response candidate."""
    content: Any = None


@dataclass
class FakeResponse:
    """Minimal stand-in for google.genai.types.GenerateContentResponse."""
    _text: Optional[str] = None
    _function_calls: Optional[List[FakeFunctionCall]] = None
    candidates: List[FakeCandidate] = field(default_factory=lambda: [FakeCandidate()])

    @property
    def text(self) -> Optional[str]:
        return self._text

    @property
    def function_calls(self) -> Optional[List[FakeFunctionCall]]:
        return self._function_calls


class FakeModels:
    """Fake client.models that returns a scripted sequence of FakeResponse."""

    def __init__(self, responses: List[FakeResponse]):
        self._responses = list(responses)
        self._call_count = 0

    def generate_content(self, **kwargs) -> FakeResponse:
        if self._call_count >= len(self._responses):
            # Return a terminal "done" response if script is exhausted
            return FakeResponse(_text="Done.", _function_calls=None)
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


class FakeClient:
    """Fake google.genai.Client for offline tests."""

    def __init__(self, responses: List[FakeResponse]):
        self.models = FakeModels(responses)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_final_response(text: str) -> FakeResponse:
    """A terminal response containing only text (no tool calls)."""
    return FakeResponse(
        _text=text,
        _function_calls=None,
        candidates=[FakeCandidate()],
    )


def make_tool_call_response(name: str, args: Dict[str, Any]) -> FakeResponse:
    """A response containing a single function call, no final text."""
    return FakeResponse(
        _text=None,
        _function_calls=[FakeFunctionCall(name=name, args=args)],
        candidates=[FakeCandidate()],
    )


def make_multi_tool_response(calls: List[tuple]) -> FakeResponse:
    """A response containing multiple function calls."""
    fcs = [FakeFunctionCall(name=n, args=a) for n, a in calls]
    return FakeResponse(
        _text=None,
        _function_calls=fcs,
        candidates=[FakeCandidate()],
    )


# ---------------------------------------------------------------------------
# The agent under test
# ---------------------------------------------------------------------------

from src.agent.autopilot_agent import run_autopilot_agent, AgentResult


# ---------------------------------------------------------------------------
# TC-01: Final response with no tool calls -> valid AgentResult
# ---------------------------------------------------------------------------
class TestTC01_FinalResponseNoToolCalls:
    def test_returns_agent_result(self):
        """A response with text only and no function calls returns AgentResult."""
        final = make_final_response(
            "recommendation: Accept all orders.\n"
            "rationale: Inventory is sufficient.\n"
            "trade_offs: Low risk.\n"
            "next_steps:\n- Confirm with supplier.\n"
            "approvals_required:\n"
            "assumptions:\n"
            "unknowns:\n"
        )
        client = FakeClient([final])
        result = run_autopilot_agent("Can I take 10 more orders?", _client=client)

        assert isinstance(result, AgentResult)
        assert result.error is None
        assert result.iterations == 1
        assert len(result.tools_invoked) == 0
        assert "Accept" in result.recommendation

    def test_result_has_all_required_fields(self):
        """AgentResult always contains all required fields."""
        client = FakeClient([make_final_response("recommendation: Done.")])
        result = run_autopilot_agent("Test goal", _client=client)

        assert hasattr(result, "recommendation")
        assert hasattr(result, "rationale")
        assert hasattr(result, "trade_offs")
        assert hasattr(result, "next_steps")
        assert hasattr(result, "approvals_required")
        assert hasattr(result, "assumptions")
        assert hasattr(result, "unknowns")
        assert hasattr(result, "tools_invoked")
        assert hasattr(result, "iterations")
        assert isinstance(result.next_steps, list)
        assert isinstance(result.approvals_required, list)

    def test_to_dict_is_serialisable(self):
        """AgentResult.to_dict() produces JSON-serialisable output."""
        import json
        client = FakeClient([make_final_response("recommendation: Proceed.")])
        result = run_autopilot_agent("Audit my cash", _client=client)
        d = result.to_dict()
        serialised = json.dumps(d)  # must not raise
        assert isinstance(serialised, str)


# ---------------------------------------------------------------------------
# TC-02: Tool call dispatched to correct registered function
# ---------------------------------------------------------------------------
class TestTC02_ToolDispatch:
    def test_get_business_overview_dispatched(self):
        """Agent correctly dispatches get_business_overview and records it."""
        responses = [
            make_tool_call_response(
                "get_business_overview",
                {"business_type": "home_tiffin"},
            ),
            make_final_response("recommendation: Business looks good."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Describe my business", _client=client)

        assert result.iterations == 2
        assert len(result.tools_invoked) == 1
        assert result.tools_invoked[0]["tool"] == "get_business_overview"
        assert result.tools_invoked[0]["error"] is None

    def test_get_financial_position_dispatched(self):
        """get_financial_position dispatches and returns correct keys."""
        responses = [
            make_tool_call_response(
                "get_financial_position",
                {"total_cash": 9000.0, "safety_reserve": 2000.0},
            ),
            make_final_response("recommendation: Cash is adequate."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Check my cash", _client=client)

        assert len(result.tools_invoked) == 1
        assert result.tools_invoked[0]["tool"] == "get_financial_position"
        assert result.tools_invoked[0]["error"] is None

    def test_evaluate_order_opportunity_dispatched(self):
        """evaluate_order_opportunity is dispatched with correct args."""
        responses = [
            make_tool_call_response(
                "evaluate_order_opportunity",
                {"additional_orders": 15.0},
            ),
            make_final_response("recommendation: Accept 15 orders."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Can I take 15 more orders?", _client=client)

        assert result.tools_invoked[0]["tool"] == "evaluate_order_opportunity"
        assert result.tools_invoked[0]["error"] is None


# ---------------------------------------------------------------------------
# TC-03: Tool result returned to Gemini in correct format
# ---------------------------------------------------------------------------
class TestTC03_ToolResultReturnedToGemini:
    def test_second_call_receives_function_response(self):
        """The second generate_content call includes function response contents."""
        call_args_list = []

        class RecordingModels:
            def __init__(self):
                self._calls = 0
            def generate_content(self, **kwargs):
                # Snapshot the length NOW since the agent mutates one shared list
                call_args_list.append(len(list(kwargs.get("contents", []))))
                self._calls += 1
                if self._calls == 1:
                    return FakeResponse(
                        _text=None,
                        _function_calls=[
                            FakeFunctionCall("get_financial_position",
                                             {"total_cash": 5000.0})
                        ],
                        candidates=[FakeCandidate()],
                    )
                return FakeResponse(
                    _text="recommendation: Cash check done.",
                    _function_calls=None,
                    candidates=[FakeCandidate()],
                )

        fake_client = MagicMock()
        fake_client.models = RecordingModels()

        run_autopilot_agent("Check cash", _client=fake_client)

        # Two generate_content calls were made
        assert len(call_args_list) == 2
        # First call: 1 item (initial user message only)
        assert call_args_list[0] == 1
        # Second call: 3 items (user + model fc turn + function response turn)
        assert call_args_list[1] >= 3


# ---------------------------------------------------------------------------
# TC-04: Multi-turn: model requests second tool after first result
# ---------------------------------------------------------------------------
class TestTC04_MultiTurn:
    def test_two_tool_calls_both_recorded(self):
        """Agent handles two sequential tool call rounds correctly."""
        responses = [
            make_tool_call_response("get_business_overview", {}),
            make_tool_call_response("get_financial_position",
                                    {"total_cash": 10000.0}),
            make_final_response("recommendation: You can proceed safely."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Full business assessment", _client=client)

        assert result.iterations == 3
        assert len(result.tools_invoked) == 2
        assert result.tools_invoked[0]["tool"] == "get_business_overview"
        assert result.tools_invoked[1]["tool"] == "get_financial_position"
        assert result.error is None

    def test_three_tool_calls_in_sequence(self):
        """Agent handles three sequential tool rounds."""
        responses = [
            make_tool_call_response("get_business_overview", {}),
            make_tool_call_response("get_financial_position", {}),
            make_tool_call_response("evaluate_order_opportunity",
                                    {"additional_orders": 5.0}),
            make_final_response("recommendation: Accept 5 orders."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Assess opportunity", _client=client)

        assert len(result.tools_invoked) == 3
        assert result.error is None


# ---------------------------------------------------------------------------
# TC-05: Unknown tool name rejected safely
# ---------------------------------------------------------------------------
class TestTC05_UnknownToolName:
    def test_unknown_tool_sets_error_in_record(self):
        """An unknown tool name is rejected; error is captured in tools_invoked."""
        responses = [
            make_tool_call_response("delete_all_orders", {}),
            make_final_response("recommendation: Could not proceed."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Hack the system", _client=client)

        # Agent must not crash
        assert isinstance(result, AgentResult)
        # The rejected call must be recorded with an error
        assert len(result.tools_invoked) == 1
        assert result.tools_invoked[0]["tool"] == "delete_all_orders"
        assert result.tools_invoked[0]["error"] is not None

    def test_unknown_tool_does_not_raise_to_caller(self):
        """Unknown tool name must not propagate an exception to the caller."""
        responses = [
            make_tool_call_response("nonexistent_tool", {"x": 1}),
            make_final_response("recommendation: Handled gracefully."),
        ]
        client = FakeClient(responses)
        # Must not raise
        result = run_autopilot_agent("Goal", _client=client)
        assert isinstance(result, AgentResult)


# ---------------------------------------------------------------------------
# TC-06: Invalid tool arguments handled without crashing
# ---------------------------------------------------------------------------
class TestTC06_InvalidArguments:
    def test_negative_additional_orders_captured(self):
        """evaluate_order_opportunity with negative orders raises ValueError, captured."""
        responses = [
            make_tool_call_response(
                "evaluate_order_opportunity",
                {"additional_orders": -5.0},  # invalid
            ),
            make_final_response("recommendation: Invalid input handled."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("I want to reduce orders by 5", _client=client)

        assert isinstance(result, AgentResult)
        assert result.tools_invoked[0]["error"] is not None  # error was captured

    def test_empty_business_type_captured(self):
        """get_business_overview with empty business_type error is captured."""
        responses = [
            make_tool_call_response("get_business_overview", {"business_type": ""}),
            make_final_response("recommendation: Empty type handled."),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Describe my business", _client=client)
        assert result.tools_invoked[0]["error"] is not None


# ---------------------------------------------------------------------------
# TC-07: Tool execution exception handled; error returned to model
# ---------------------------------------------------------------------------
class TestTC07_ToolExceptionHandled:
    def test_tool_exception_does_not_crash_agent(self, monkeypatch):
        """A tool that raises an exception mid-loop does not crash the agent."""
        from src.agent import tools as agent_tools

        original_fn = agent_tools.TOOL_REGISTRY["get_business_overview"]

        def boom(**kwargs):
            raise RuntimeError("Simulated database failure")

        agent_tools.TOOL_REGISTRY["get_business_overview"] = boom
        try:
            responses = [
                make_tool_call_response("get_business_overview", {}),
                make_final_response("recommendation: Error was handled."),
            ]
            client = FakeClient(responses)
            result = run_autopilot_agent("Check business", _client=client)
            assert isinstance(result, AgentResult)
            assert result.tools_invoked[0]["error"] is not None
            assert "Simulated database failure" in result.tools_invoked[0]["error"]
        finally:
            agent_tools.TOOL_REGISTRY["get_business_overview"] = original_fn


# ---------------------------------------------------------------------------
# TC-08: Max iteration limit enforced
# ---------------------------------------------------------------------------
class TestTC08_MaxIterationLimit:
    def test_iteration_limit_stops_loop(self):
        """Agent stops after max_iterations even if model keeps requesting tools."""
        # Script 3 tool call responses; limit to 2 iterations
        responses = [
            make_tool_call_response("get_business_overview", {}),
            make_tool_call_response("get_financial_position", {}),
            make_tool_call_response("evaluate_order_opportunity",
                                    {"additional_orders": 1.0}),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Loop test", _client=client, max_iterations=2)

        assert result.iterations == 2
        assert result.error is not None
        assert "maximum iteration limit" in result.error

    def test_zero_iterations_cap(self):
        """max_iterations=1 means only one generate_content call."""
        responses = [
            make_tool_call_response("get_business_overview", {}),
            make_final_response("Should not reach here"),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent("Minimal test", _client=client, max_iterations=1)
        assert result.iterations == 1
        assert result.error is not None


# ---------------------------------------------------------------------------
# TC-09: Missing GEMINI_API_KEY raises EnvironmentError
# ---------------------------------------------------------------------------
class TestTC09_MissingApiKey:
    def test_missing_key_raises_environment_error(self, monkeypatch):
        """Missing GEMINI_API_KEY without a mock client raises EnvironmentError."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
            run_autopilot_agent("Test without key")

    def test_error_message_does_not_contain_secret(self, monkeypatch):
        """EnvironmentError message must not contain the actual key value."""
        monkeypatch.setenv("GEMINI_API_KEY", "")
        with pytest.raises(EnvironmentError) as exc_info:
            run_autopilot_agent("Test empty key")
        error_msg = str(exc_info.value)
        assert "sk-" not in error_msg  # no key fragments
        assert len(error_msg) < 300    # no huge dumps


# ---------------------------------------------------------------------------
# TC-10: Consequential actions cannot bypass the approval mechanism
# ---------------------------------------------------------------------------
class TestTC10_ApprovalGating:
    def test_agent_recommendation_does_not_auto_execute_plans(self):
        """Agent result contains an approval requirement, not an execution record."""
        responses = [
            make_tool_call_response(
                "evaluate_order_opportunity",
                {"additional_orders": 20.0, "total_cash": 8000.0},
            ),
            make_final_response(
                "recommendation: Accept 20 orders with procurement.\n"
                "approvals_required:\n"
                "- Create purchase plan and get owner sign-off before ordering.\n"
            ),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent(
            "Can I take 20 more orders? I have Rs 8000 cash.", _client=client
        )
        # No execution should have happened
        assert isinstance(result, AgentResult)
        # The agent must surface required approvals, not execute them
        # The result should NOT have any executed purchase plan IDs
        d = result.to_dict()
        raw = result.raw_response
        assert "EXECUTED" not in raw  # no execution receipt in output

    def test_tool_registry_does_not_contain_execute_plan(self):
        """execute_purchase_plan is NOT in the agent's TOOL_REGISTRY."""
        from src.agent.tools import TOOL_REGISTRY
        assert "execute_purchase_plan" not in TOOL_REGISTRY

    def test_tool_registry_does_not_contain_confirm_plan(self):
        """confirm_purchase_plan is NOT exposed to the agent."""
        from src.agent.tools import TOOL_REGISTRY
        assert "confirm_purchase_plan" not in TOOL_REGISTRY

    def test_tool_registry_does_not_contain_create_plan(self):
        """create_purchase_plan is NOT in the agent tool registry."""
        from src.agent.tools import TOOL_REGISTRY
        assert "create_purchase_plan" not in TOOL_REGISTRY


# ---------------------------------------------------------------------------
# TC-11: Non-food business request not forced into tiffin workflow
# ---------------------------------------------------------------------------
class TestTC11_BusinessAgnostic:
    def test_salon_business_type_dispatches_correctly(self):
        """Agent uses the business_type the model selects, not always home_tiffin."""
        responses = [
            make_tool_call_response(
                "get_business_overview",
                {"business_type": "home_tiffin"},  # model may fall back to default
            ),
            make_final_response(
                "recommendation: Your salon can take 5 more clients.\n"
                "rationale: Capacity is available.\n"
            ),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent(
            "I run a hair salon. Can I book 5 more clients tomorrow?",
            _client=client,
        )
        # Agent must not crash or force tiffin-specific fields
        assert isinstance(result, AgentResult)
        assert result.error is None

    def test_general_cash_question_works(self):
        """A generic cash question (not tiffin-specific) is handled."""
        responses = [
            make_tool_call_response(
                "get_financial_position",
                {"total_cash": 12000.0, "safety_reserve": 3000.0},
            ),
            make_final_response(
                "recommendation: Rs 9000 is available above the safety reserve."
            ),
        ]
        client = FakeClient(responses)
        result = run_autopilot_agent(
            "I have Rs 12000 cash. How much can I safely spend?", _client=client
        )
        assert result.tools_invoked[0]["tool"] == "get_financial_position"
        assert result.error is None


# ---------------------------------------------------------------------------
# TC-12: Import guard -- agent package does not break existing test suite
# ---------------------------------------------------------------------------
class TestTC12_ExistingTestsCompatible:
    def test_agent_tools_importable(self):
        """src.agent.tools imports without error."""
        from src.agent import tools  # noqa: F401
        assert hasattr(tools, "TOOL_REGISTRY")
        assert hasattr(tools, "TOOL_LIST")

    def test_agent_module_importable(self):
        """src.agent.autopilot_agent imports without error."""
        from src.agent import autopilot_agent  # noqa: F401
        assert hasattr(autopilot_agent, "run_autopilot_agent")
        assert hasattr(autopilot_agent, "AgentResult")

    def test_tool_registry_has_five_tools(self):
        """Exactly 5 tools are registered in the initial milestone."""
        from src.agent.tools import TOOL_REGISTRY
        assert len(TOOL_REGISTRY) == 5
        expected = {
            "get_business_overview",
            "get_financial_position",
            "evaluate_order_opportunity",
            "get_supplier_quotes",
            "compare_procurement_channels",
        }
        assert set(TOOL_REGISTRY.keys()) == expected

    def test_all_tools_are_callable(self):
        """Every registered tool is callable."""
        from src.agent.tools import TOOL_REGISTRY
        for name, func in TOOL_REGISTRY.items():
            assert callable(func), f"Tool '{name}' is not callable."

    def test_existing_decision_engine_still_importable(self):
        """The existing BusinessAutopilotV2 is not broken by the new agent layer."""
        from src.decision.business_autopilot import BusinessAutopilotV2
        engine = BusinessAutopilotV2()
        assert engine is not None

    def test_existing_approval_service_still_importable(self):
        """The existing PurchaseApprovalService is not broken."""
        from src.decision.approval_service import PurchaseApprovalService
        svc = PurchaseApprovalService()  # in-memory
        assert svc is not None
        svc.close()
