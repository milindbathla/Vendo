"""Business Context Specialist Agent.

Handles:
- get_business_overview
- get_recent_business_changes
- get_business_memory
- write_business_memory
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from business_intel.narrator import narrate_response
from business_intel.router import route_query
from business_intel.schemas import AgentAnswer, Envelope
from business_intel.tools.registry import async_call_tool, call_tool


class ContextAgent:
    """Specialist face for business context and operational memory."""

    name: str = "business_context_agent"
    description: str = "Provides morning briefing, operational load, cash position, supplier issues, and memory."

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path

    def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentAnswer:
        """Synchronously execute context tasks."""
        return asyncio.run(self.run_async(task, context))

    async def run_async(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentAnswer:
        """Asynchronously execute context tasks."""
        decision = route_query(task)
        tools = decision.tools or [("get_business_overview", {"include_ledgers": True})]

        envelopes: List[Envelope] = []
        for tool_name, kwargs in tools[:5]:
            env = await async_call_tool(tool_name, kwargs, db_path=self.db_path)
            envelopes.append(env)

        return narrate_response(task, envelopes)

