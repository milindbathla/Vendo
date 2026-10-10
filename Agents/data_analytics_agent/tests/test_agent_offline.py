"""Test end-to-end BusinessIntelAgent execution in offline mode (BI_LLM=off)."""
import pytest
from business_intel.agents.business_intel_agent import BusinessIntelAgent
from business_intel.schemas import AgentAnswer, OutOfScopeResponse


@pytest.fixture
def agent():
    return BusinessIntelAgent()


def test_agent_overview_query_offline(agent):
    ans = agent.ask("Give me my morning briefing")
    assert isinstance(ans, AgentAnswer)
    assert len(ans.speech.split()) <= 45
    assert ans.grounded is True
    assert len(ans.ungrounded_tokens) == 0
    assert "Rs 12000" in ans.speech or "12000" in ans.speech
    assert "get_business_overview" in ans.tools_used


def test_agent_analytics_query_offline(agent):
    ans = agent.ask("How did we perform over the last 30 days?")
    assert isinstance(ans, AgentAnswer)
    assert len(ans.speech.split()) <= 45
    assert ans.grounded is True
    assert "analyze_business_performance" in ans.tools_used
    assert ans.details_markdown is not None


def test_agent_out_of_scope_offline(agent):
    ans = agent.ask("Can I afford to purchase 30kg rice tomorrow?")
    assert isinstance(ans, OutOfScopeResponse)
    assert ans.out_of_scope is True
    assert ans.suggested_agent == "finance_and_procurement_agent"
    assert len(ans.speech_refusal.split()) <= 45


def test_agent_both_query_offline(agent):
    ans = agent.ask("How did my week go and what issues came up?")
    assert isinstance(ans, AgentAnswer)
    assert "analyze_business_performance" in ans.tools_used
    assert "get_recent_business_changes" in ans.tools_used
    assert len(ans.speech.split()) <= 45

