"""Test router classification across in-scope and out-of-scope queries."""
import pytest
from business_intel.router import route_query


def test_out_of_scope_categories():
    queries = [
        ("Can I afford to buy 50kg rice tomorrow?", "finance_and_procurement_agent"),
        ("Can I take 50 more orders tomorrow for dinner?", "demand_and_capacity_agent"),
        ("Is this invoice authentic? Check receipt.", "document_agent"),
        ("How do I get more customers using social media ads?", "customer_growth_agent"),
        ("Pay Sharma ₹5000 and place order for flour.", "commerce_execution_agent"),
    ]

    for q, expected_agent in queries:
        decision = route_query(q)
        assert decision.category == "out_of_scope", f"Failed for query: {q}"
        assert decision.out_of_scope is not None
        assert decision.out_of_scope.suggested_agent == expected_agent
        assert len(decision.out_of_scope.speech_refusal) > 0


def test_in_scope_categories():
    # Context
    d1 = route_query("Give me my morning overview and cash balance")
    assert d1.category == "context"
    assert any(t[0] == "get_business_overview" for t in d1.tools)

    # Analytics
    d2 = route_query("How was my business performance over the last 30 days?")
    assert d2.category == "analytics"
    assert any(t[0] == "analyze_business_performance" for t in d2.tools)

    # Both
    d3 = route_query("How did my week go and what issues came up?")
    assert d3.category == "both"
    tool_names = [t[0] for t in d3.tools]
    assert "analyze_business_performance" in tool_names
    assert "get_recent_business_changes" in tool_names

    # Memory write
    d4 = route_query("Remember that we do not deliver beyond 5km")
    assert d4.category == "context"
    assert any(t[0] == "write_business_memory" for t in d4.tools)

