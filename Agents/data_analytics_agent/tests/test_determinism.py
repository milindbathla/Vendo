"""Test determinism of tools: identical output bytes every run."""
import json
import pytest
from business_intel.tools.context_tools import get_business_overview, get_recent_business_changes
from business_intel.tools.analytics_tools import (
    analyze_business_performance,
    analyze_product_profitability,
    analyze_cost_trends,
)


def _strip_latency(env_dict: dict) -> dict:
    if "meta" in env_dict and env_dict["meta"]:
        env_dict["meta"]["latency_ms"] = 0.0
    return env_dict


def test_tools_deterministic():
    # 1. Overview
    e1 = _strip_latency(get_business_overview().model_dump())
    e2 = _strip_latency(get_business_overview().model_dump())
    assert json.dumps(e1, sort_keys=True) == json.dumps(e2, sort_keys=True)

    # 2. Performance
    p1 = _strip_latency(analyze_business_performance().model_dump())
    p2 = _strip_latency(analyze_business_performance().model_dump())
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)

    # 3. Product profitability
    pr1 = _strip_latency(analyze_product_profitability().model_dump())
    pr2 = _strip_latency(analyze_product_profitability().model_dump())
    assert json.dumps(pr1, sort_keys=True) == json.dumps(pr2, sort_keys=True)

    # 4. Cost trends
    c1 = _strip_latency(analyze_cost_trends().model_dump())
    c2 = _strip_latency(analyze_cost_trends().model_dump())
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)

