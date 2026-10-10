"""MCP server exposing Business Intel Agent tools and natural language ask endpoint.

Compatible with official mcp SDK (FastMCP / MCPServer).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from business_intel.agents.business_intel_agent import BusinessIntelAgent
from business_intel.tools.analytics_tools import (
    analyze_business_performance as _analyze_business_performance,
    analyze_cost_trends as _analyze_cost_trends,
    analyze_product_profitability as _analyze_product_profitability,
    generate_business_report as _generate_business_report,
)
from business_intel.tools.context_tools import (
    get_business_memory as _get_business_memory,
    get_business_overview as _get_business_overview,
    get_recent_business_changes as _get_recent_business_changes,
    write_business_memory as _write_business_memory,
)

server = MCPServer("business-intel-server")


@server.tool()
def get_business_overview(include_ledgers: bool = True) -> Dict[str, Any]:
    """Get the owner's morning/evening briefing including cash position, tomorrow's load, shortage risks, and customer counts."""
    return _get_business_overview(include_ledgers=include_ledgers).model_dump()


@server.tool()
def get_recent_business_changes(since_days: int = 7, min_severity: str = "all") -> Dict[str, Any]:
    """Retrieve chronological log of recent supplier, customer, and operational changes."""
    return _get_recent_business_changes(since_days=since_days, min_severity=min_severity).model_dump()


@server.tool()
def get_business_memory(
    category: Optional[str] = None,
    key: Optional[str] = None,
    include_conflicts: bool = True,
) -> Dict[str, Any]:
    """Retrieve business policies, verified records, and owner-stated facts with conflict flags."""
    return _get_business_memory(category=category, key=key, include_conflicts=include_conflicts).model_dump()


@server.tool()
def write_business_memory(
    category: str,
    key: str,
    value: str,
    source: str = "owner_statement",
    confidence: float = 0.9,
    expires_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Record an owner statement into business memory safely with audit logging and conflict detection."""
    return _write_business_memory(
        category=category,
        key=key,
        value=value,
        source=source,
        confidence=confidence,
        expires_at=expires_at,
    ).model_dump()


@server.tool()
def analyze_business_performance(
    period: str = "last_30d",
    compare_with: str = "previous_period",
    granularity: str = "daily",
) -> Dict[str, Any]:
    """Analyze revenue, volume, COGS, opex, and net profit over a resolved period with comparison metrics."""
    return _analyze_business_performance(
        period=period,
        compare_with=compare_with,
        granularity=granularity,
    ).model_dump()


@server.tool()
def analyze_product_profitability(
    product_id: Optional[str] = None,
    period: str = "last_30d",
) -> Dict[str, Any]:
    """Calculate unit economics, bill-of-materials cost, contribution margin, and daily breakeven volume."""
    return _analyze_product_profitability(product_id=product_id, period=period).model_dump()


@server.tool()
def analyze_cost_trends(
    item_id: Optional[str] = None,
    period: str = "last_90d",
) -> Dict[str, Any]:
    """Analyze supplier price movements, inflation spikes, and per-unit COGS impact."""
    return _analyze_cost_trends(item_id=item_id, period=period).model_dump()


@server.tool()
def generate_business_report(
    report_type: str = "executive_brief",
    period: str = "last_30d",
    export_format: str = "markdown",
) -> Dict[str, Any]:
    """Synthesize comprehensive markdown business reports with Obsidian frontmatter, Mermaid charts, and math."""
    return _generate_business_report(
        report_type=report_type,
        period=period,
        export_format=export_format,
    ).model_dump()


@server.tool()
def ask_business_intel(question: str) -> Dict[str, Any]:
    """Ask a natural language business question in English, Hindi, or Hinglish to the Business Intel Agent."""
    agent = BusinessIntelAgent()
    res = agent.ask(question)
    return res.model_dump()


if __name__ == "__main__":
    server.run()

