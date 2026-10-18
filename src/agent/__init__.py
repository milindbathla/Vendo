"""
Alexa Business Autopilot — Genuine Gemini Agent Layer
======================================================
Provides a real LLM-powered, tool-calling business agent.

Public API:
    from src.agent.autopilot_agent import run_autopilot_agent, AgentResult
"""
from src.agent.autopilot_agent import run_autopilot_agent, AgentResult

__all__ = [
    "run_autopilot_agent",
    "AgentResult",
    "EmailOperationalSupervisor",
    "SupervisorExecutionResult",
    "DocumentOnboardingService",
    "DocumentParser",
    "DocumentFactExtractor",
    "DocumentEvidence",
]

from src.agent.supervisor import (
    EmailOperationalSupervisor,
    SupervisorExecutionResult,
)
from src.agent.document_onboarding import (
    DocumentOnboardingService,
    DocumentParser,
    DocumentFactExtractor,
    DocumentEvidence,
)
