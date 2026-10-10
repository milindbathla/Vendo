"""
Alexa Business Autopilot — Genuine Gemini Agent Layer
======================================================
Provides a real LLM-powered, tool-calling business agent.

Public API:
    from src.agent.autopilot_agent import run_autopilot_agent, AgentResult
"""
from src.agent.autopilot_agent import run_autopilot_agent, AgentResult

__all__ = ["run_autopilot_agent", "AgentResult"]
