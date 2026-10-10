"""Test envelope structure and speech constraints across all 8 tools."""
import pytest
from business_intel.tools.registry import list_tools, call_tool
from business_intel.schemas import Envelope


def test_all_tools_return_valid_envelopes():
    tools = list_tools()
    assert len(tools) == 8

    for t in tools:
        # Call tool with default arguments
        env = call_tool(t.name, {})
        assert isinstance(env, Envelope), f"Tool {t.name} did not return Envelope"
        assert env.ok is True, f"Tool {t.name} failed: {env.error}"
        assert isinstance(env.data, dict)
        assert 0.0 <= env.confidence <= 1.0
        assert env.source in ("db", "estimate", "simulated")
        assert isinstance(env.warnings, list)
        assert env.meta is not None
        assert env.meta.tool == t.name
        assert env.meta.as_of == "2026-10-10T19:10:00+05:30"
        assert env.meta.latency_ms >= 0

        # Speech summary validation
        speech = env.data.get("speech_summary")
        assert speech is not None, f"Tool {t.name} missing speech_summary"
        assert len(speech.strip()) > 0
        word_count = len(speech.split())
        assert word_count <= 40, f"Tool {t.name} speech_summary has {word_count} words (max 40 allowed): '{speech}'"
        # Check no markdown in speech
        assert "#" not in speech
        assert "**" not in speech
        assert "[" not in speech

