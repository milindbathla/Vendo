"""Test MCP server exposure of tools."""
import pytest
from business_intel.mcp_server import (
    get_business_overview,
    analyze_business_performance,
    ask_business_intel,
)


def test_mcp_tools_callable():
    # 1. get_business_overview
    res1 = get_business_overview()
    assert isinstance(res1, dict)
    assert res1["ok"] is True
    assert "cash_position" in res1["data"]

    # 2. analyze_business_performance
    res2 = analyze_business_performance(period="last_30d")
    assert isinstance(res2, dict)
    assert res2["ok"] is True
    assert "metrics" in res2["data"]

    # 3. ask_business_intel
    res3 = ask_business_intel("Give me my morning briefing")
    assert isinstance(res3, dict)
    assert "speech" in res3
    assert len(res3["speech"].split()) <= 45

