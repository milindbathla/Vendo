"""Test latency and performance constraints (all tools under 300ms)."""
import time
import pytest
from business_intel.tools.registry import list_tools, call_tool


def test_all_tools_sub_300ms():
    tools = list_tools()
    for t in tools:
        t0 = time.perf_counter()
        env = call_tool(t.name, {})
        dur_ms = (time.perf_counter() - t0) * 1000.0

        assert env.ok is True, f"Tool {t.name} failed: {env.error}"
        assert dur_ms < 300.0, f"Tool {t.name} exceeded 300ms limit: {dur_ms:.2f}ms"

