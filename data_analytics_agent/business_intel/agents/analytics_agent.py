"""Business Analytics Specialist Agent.

Handles:
- analyze_business_performance
- analyze_product_profitability
- analyze_cost_trends
- generate_business_report
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from business_intel.narrator import narrate_response
from business_intel.router import route_query
from business_intel.schemas import AgentAnswer, Envelope
from business_intel.tools.registry import async_call_tool, call_tool


class AnalyticsAgent:
    """Specialist face for sales, P&L, contribution margin, and cost trends."""

    name: str = "business_analytics_agent"
    description: str = "Analyzes business performance, product profitability, cost trends, and generates markdown reports."

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path

    def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentAnswer:
        """Synchronously execute analytics tasks."""
        return asyncio.run(self.run_async(task, context))

    async def run_async(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentAnswer:
        """Asynchronously execute analytics tasks."""
        decision = route_query(task)
        tools = decision.tools or [("analyze_business_performance", {"period": "last_30d"})]

        envelopes: List[Envelope] = []
        for tool_name, kwargs in tools[:5]:
            env = await async_call_tool(tool_name, kwargs, db_path=self.db_path)
            envelopes.append(env)

        return narrate_response(task, envelopes)

