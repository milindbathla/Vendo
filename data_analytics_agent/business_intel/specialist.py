"""Specialist Agent adapter for Alexa Business Autopilot orchestrator.

Exposes a clean SpecialistAgent interface:
- describe() -> Dict[str, Any]
- run(task: str, context: Optional[Dict[str, Any]] = None) -> Envelope
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from business_intel.agents.business_intel_agent import BusinessIntelAgent
from business_intel.schemas import AgentAnswer, Envelope, OutOfScopeResponse
from business_intel.tools.registry import TOOL_DEFINITIONS


class BusinessIntelSpecialistAgent:
    """Orchestrator-facing Specialist Agent adapter."""

    name: str = "business_intel"
    description: str = (
        "Combined Business Context & Analytics Agent for owner-operated cloud kitchens. "
        "Answers morning briefings, cash position, operational load, performance analytics, "
        "unit economics, and cost trends."
    )

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.agent = BusinessIntelAgent(db_path=db_path)

    def describe(self) -> Dict[str, Any]:
        """Describe capabilities, tools, and usage contracts for the orchestrator."""
        return {
            "name": self.name,
            "description": self.description,
            "faces": ["context", "analytics"],
            "tools": [
                {
                    "name": name,
                    "description": defn.description,
                    "category": defn.category,
                }
                for name, defn in TOOL_DEFINITIONS.items()
            ],
            "capabilities": [
                "Morning briefing and cash headroom",
                "Tomorrow's booking load and kitchen capacity",
                "Inventory shortage and supplier price hike alerts",
                "Daily/weekly/monthly P&L and contribution margin",
                "Breakeven analysis and unit economics",
                "Executive briefing report generation (Markdown / Mermaid)",
                "Owner memory recall and policy updates",
            ],
            "out_of_scope_referrals": {
                "purchasing": "finance_and_procurement_agent",
                "capacity_planning": "demand_and_capacity_agent",
                "document_auditing": "document_agent",
                "growth_campaigns": "customer_growth_agent",
                "transactions": "commerce_execution_agent",
            },
        }

    async def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Envelope:
        """Run task asynchronously and return an Envelope result for the orchestrator."""
        db_path = context.get("db_path") if context else None
        res = await self.agent.ask_async(task, db_path=db_path)

        if isinstance(res, OutOfScopeResponse):
            return Envelope(
                ok=False,
                data=res.model_dump(),
                confidence=1.0,
                source="db",
                warnings=[f"Referred to {res.suggested_agent}"],
                error="out_of_scope",
            )

        return Envelope(
            ok=True,
            data=res.model_dump(),
            confidence=res.confidence,
            source="db",
            warnings=res.warnings,
            error=None,
        )

    def run_sync(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Envelope:
        """Synchronously execute task."""
        return asyncio.run(self.run(task, context))

