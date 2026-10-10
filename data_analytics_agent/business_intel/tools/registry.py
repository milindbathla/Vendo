"""Tool registry for Business Intel Agent.

Maps tool names to callables, schemas, descriptions, and categories.
Provides call_tool and async_call_tool helpers, and exports contract documentation.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel

from business_intel.schemas import (
    AnalyzeBusinessPerformanceInput,
    AnalyzeCostTrendsInput,
    AnalyzeProductProfitabilityInput,
    Envelope,
    GenerateBusinessReportInput,
    GetBusinessMemoryInput,
    GetBusinessOverviewInput,
    GetRecentBusinessChangesInput,
    WriteBusinessMemoryInput,
)
from business_intel.tools.analytics_tools import (
    analyze_business_performance,
    analyze_cost_trends,
    analyze_product_profitability,
    generate_business_report,
)
from business_intel.tools.context_tools import (
    get_business_memory,
    get_business_overview,
    get_recent_business_changes,
    write_business_memory,
)


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: str  # "context" | "analytics"
    func: Callable[..., Envelope]
    input_model: Type[BaseModel]


TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    "get_business_overview": ToolDefinition(
        name="get_business_overview",
        description=(
            "Owner's morning/evening briefing. Returns cash position, tomorrow's load, "
            "shortage risks, customer counts, unread supplier issues, pending ledgers, "
            "and memory conflicts."
        ),
        category="context",
        func=get_business_overview,
        input_model=GetBusinessOverviewInput,
    ),
    "get_recent_business_changes": ToolDefinition(
        name="get_recent_business_changes",
        description=(
            "Chronological log of what happened across suppliers, customers, and operations "
            "over the last N days (defaults to 7)."
        ),
        category="context",
        func=get_recent_business_changes,
        input_model=GetRecentBusinessChangesInput,
    ),
    "get_business_memory": ToolDefinition(
        name="get_business_memory",
        description=(
            "Retrieve verified records, policies, and owner-stated facts stored in memory, "
            "with conflict flags when statements conflict with records."
        ),
        category="context",
        func=get_business_memory,
        input_model=GetBusinessMemoryInput,
    ),
    "write_business_memory": ToolDefinition(
        name="write_business_memory",
        description=(
            "Record an owner statement into business memory. Enforces read-only safety "
            "except for memory and audit tables. Detects conflicts with verified records."
        ),
        category="context",
        func=write_business_memory,
        input_model=WriteBusinessMemoryInput,
    ),
    "analyze_business_performance": ToolDefinition(
        name="analyze_business_performance",
        description=(
            "Analyze revenue, volume, COGS, opex, and net profit over a resolved period "
            "(yesterday, last_7d, last_30d, mtd, last_month) with period-over-period comparisons."
        ),
        category="analytics",
        func=analyze_business_performance,
        input_model=AnalyzeBusinessPerformanceInput,
    ),
    "analyze_product_profitability": ToolDefinition(
        name="analyze_product_profitability",
        description=(
            "Calculate unit economics, bill-of-materials cost, contribution margin, "
            "and daily breakeven volume for products."
        ),
        category="analytics",
        func=analyze_product_profitability,
        input_model=AnalyzeProductProfitabilityInput,
    ),
    "analyze_cost_trends": ToolDefinition(
        name="analyze_cost_trends",
        description=(
            "Analyze supplier price movements, inflation spikes, and per-unit COGS impact "
            "over a period (default last_90d)."
        ),
        category="analytics",
        func=analyze_cost_trends,
        input_model=AnalyzeCostTrendsInput,
    ),
    "generate_business_report": ToolDefinition(
        name="generate_business_report",
        description=(
            "Synthesize comprehensive markdown business reports (daily_standup, weekly_pnl, "
            "monthly_pack, executive_brief) with Obsidian frontmatter, Mermaid charts, and math."
        ),
        category="analytics",
        func=generate_business_report,
        input_model=GenerateBusinessReportInput,
    ),
}


def get_tool(name: str) -> Optional[ToolDefinition]:
    return TOOL_DEFINITIONS.get(name)


def list_tools(category: Optional[str] = None) -> List[ToolDefinition]:
    if category is None:
        return list(TOOL_DEFINITIONS.values())
    return [t for t in TOOL_DEFINITIONS.values() if t.category == category]


def call_tool(name: str, args: Optional[Dict[str, Any]] = None, db_path: Optional[str] = None) -> Envelope:
    """Synchronously call a tool by name with arguments dict."""
    tool_def = TOOL_DEFINITIONS.get(name)
    if not tool_def:
        return Envelope(
            ok=False,
            data={},
            confidence=0.0,
            source="db",
            warnings=[],
            error=f"Unknown tool: '{name}'. Available: {list(TOOL_DEFINITIONS.keys())}",
        )

    args = args or {}
    try:
        validated_input = tool_def.input_model(**args)
        kwargs = validated_input.model_dump()
        if db_path is not None:
            kwargs["db_path"] = db_path
        return tool_def.func(**kwargs)
    except Exception as exc:
        return Envelope(
            ok=False,
            data={},
            confidence=0.0,
            source="db",
            warnings=[],
            error=f"Error executing {name}: {str(exc)}",
        )


async def async_call_tool(name: str, args: Optional[Dict[str, Any]] = None, db_path: Optional[str] = None) -> Envelope:
    """Asynchronously call a tool in a worker thread."""
    return await asyncio.to_thread(call_tool, name, args, db_path)


def export_tool_contracts(output_dir: str = "docs") -> Dict[str, str]:
    """Generates docs/tool_contracts.json and docs/tool_contracts.md."""
    os.makedirs(output_dir, exist_ok=True)
    
    contracts_data = {}
    for name, tool_def in TOOL_DEFINITIONS.items():
        contracts_data[name] = {
            "name": name,
            "category": tool_def.category,
            "description": tool_def.description,
            "parameters": tool_def.input_model.model_json_schema(),
            "output_schema": Envelope.model_json_schema(),
        }

    json_path = os.path.join(output_dir, "tool_contracts.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(contracts_data, f, indent=2)

    md_lines = [
        "# Tool Contracts: Business Intel Agent",
        "",
        "This document describes the input and output contracts for the 8 deterministic tools provided by the Business Intel Agent.",
        "All tools return a standard `Envelope` structure with zero LLM dependence.",
        "",
        "## Standard Result Envelope",
        "```json",
        json.dumps(Envelope.model_json_schema(), indent=2),
        "```",
        "",
        "## Tools",
        "",
    ]

    for name, data in contracts_data.items():
        md_lines.append(f"### `{name}`")
        md_lines.append(f"**Category:** `{data['category']}`  ")
        md_lines.append(f"**Description:** {data['description']}")
        md_lines.append("")
        md_lines.append("#### Input Parameters")
        md_lines.append("```json")
        md_lines.append(json.dumps(data["parameters"], indent=2))
        md_lines.append("```")
        md_lines.append("")

    md_path = os.path.join(output_dir, "tool_contracts.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return {"json": json_path, "md": md_path}


if __name__ == "__main__":
    res = export_tool_contracts()
    print("Contracts exported:", res)

