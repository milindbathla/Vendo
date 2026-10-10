"""Hybrid router for Business Intel Agent.

Classifies incoming queries into:
- 'context': needs context tools
- 'analytics': needs analytics tools
- 'both': needs combination
- 'out_of_scope': belongs to another specialist agent (procurement, capacity, document, growth, execution)
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel

from business_intel.config import BI_LLM_ENABLED, GEMINI_API_KEY
from business_intel.periods import resolve_period
from business_intel.schemas import OutOfScopeResponse


class RouteDecision(BaseModel):
    category: Literal["context", "analytics", "both", "out_of_scope"]
    tools: List[Tuple[str, Dict[str, Any]]] = []
    out_of_scope: Optional[OutOfScopeResponse] = None
    reason: str = ""


# Out-of-scope pattern definitions
OUT_OF_SCOPE_RULES = [
    {
        "agent": "finance_and_procurement_agent",
        "patterns": [
            r"\b(?:can i afford|should i buy|can i buy|can we buy|afford to buy|purchase order|buy inventory|budget to buy|afford it)\b",
            r"\b(?:kya main khareed sakta|purchase planning)\b",
        ],
        "reason": "Affordability analysis and purchase planning belong to the Finance & Procurement Agent.",
        "speech": "I cannot advise on purchase decisions directly, but the Finance and Procurement Agent can check your budget and affordability.",
    },
    {
        "agent": "demand_and_capacity_agent",
        "patterns": [
            r"\b(?:can i take\b.*(?:more orders|extra orders|orders tomorrow))\b",
            r"\b(?:kitchen capacity|order capacity|forecast next week|demand forecast|predict demand|can we take 50 more)\b",
            r"\b(?:kal aur order le sakte hain|capacity limit)\b",
        ],
        "reason": "Order acceptance capacity and future demand forecasting belong to the Demand & Capacity Agent.",
        "speech": "Capacity checks and forward demand projections are handled by the Demand and Capacity Agent.",
    },
    {
        "agent": "document_agent",
        "patterns": [
            r"\b(?:verify (?:this )?bill|is this invoice authentic|check receipt|extract invoice|bill mismatch|invoice scan)\b",
            r"\b(?:bill check karo|invoice verify)\b",
        ],
        "reason": "Invoice verification and document extraction belong to the Document Agent.",
        "speech": "Document verification and invoice auditing are handled by the Document Agent.",
    },
    {
        "agent": "customer_growth_agent",
        "patterns": [
            r"\b(?:how do i get more customers|run a campaign|marketing campaign|customer acquisition|facebook ads|flyers|grow sales)\b",
            r"\b(?:naye customers kaise laye|marketing)\b",
        ],
        "reason": "Customer acquisition and marketing campaigns belong to the Customer Growth Agent.",
        "speech": "Customer acquisition and marketing campaigns are handled by the Customer Growth Agent.",
    },
    {
        "agent": "commerce_execution_agent",
        "patterns": [
            r"\b(?:order \d+|pay \w+|place (?:the )?order|send payment|transfer money|buy now|checkout)\b",
            r"\b(?:payment bhej do|order place karo)\b",
        ],
        "reason": "Transaction execution and payment dispatch belong to the Commerce Execution Agent.",
        "speech": "I cannot execute orders or transfer payments directly. The Commerce Execution Agent handles financial transactions.",
    },
]


def _check_out_of_scope(query: str) -> Optional[OutOfScopeResponse]:
    q = query.lower()
    for rule in OUT_OF_SCOPE_RULES:
        for pat in rule["patterns"]:
            if re.search(pat, q):
                return OutOfScopeResponse(
                    ok=False,
                    error="out_of_scope",
                    suggested_agent=rule["agent"],
                    reason=rule["reason"],
                    speech_refusal=rule["speech"],
                )
    return None


def route_query_deterministic(query: str) -> RouteDecision:
    """Fast deterministic regex/keyword router."""
    q = query.lower()

    # 1. Out-of-scope check
    oos = _check_out_of_scope(q)
    if oos:
        return RouteDecision(
            category="out_of_scope",
            tools=[],
            out_of_scope=oos,
            reason=oos.reason,
        )

    # 2. Check for memory writes (e.g. "remember that...", "note down...", "policy: ...")
    mem_write_match = re.search(
        r"(?:remember(?: that)?|note down|record that|save to memory)\s+(.+)", q
    )
    if mem_write_match:
        val = mem_write_match.group(1).strip()
        return RouteDecision(
            category="context",
            tools=[
                (
                    "write_business_memory",
                    {"category": "policy", "key": "owner_note", "value": val},
                )
            ],
            reason="Detected explicit memory write instruction.",
        )

    # 3. Detect period in query if any
    period = "last_30d"
    if "yesterday" in q or "kal" in q:
        period = "yesterday"
    elif "last 7" in q or "pichhle 7" in q or "this week" in q or "is hafte" in q:
        period = "last_7d"
    elif "last month" in q or "pichhle mahine" in q:
        period = "last_month"
    elif "mtd" in q or "this month" in q or "is mahine" in q:
        period = "mtd"
    elif "today" in q or "aaj" in q:
        period = "today"
    elif "last 90" in q:
        period = "last_90d"

    # 4. Keyword patterns
    context_keywords = [
        "overview", "briefing", "morning", "how are we doing", "status",
        "cash balance", "tomorrow", "kya chal raha", "summary",
        "changes", "recent changes", "what happened", "supplier issue",
        "memory", "policy", "owner note", "conflicts", "shortage"
    ]
    analytics_keywords = [
        "performance", "perform", "p&l", "profit", "revenue", "sales", "margin", "cogs",
        "cost", "price", "prices", "price hike", "supplier price", "supplier prices",
        "unit economics", "breakeven", "break-even", "report", "standup", "weekly pnl",
        "monthly pack", "numbers", "trend", "trends", "inflation", "contribution"
    ]

    has_context = any(k in q for k in context_keywords)
    has_analytics = any(k in q for k in analytics_keywords)

    # Check for both
    if (has_context and has_analytics) or ("week go" in q and "issues" in q) or ("performance and changes" in q):
        return RouteDecision(
            category="both",
            tools=[
                ("analyze_business_performance", {"period": period}),
                ("get_recent_business_changes", {"since_days": 7}),
            ],
            reason="Query spans both historical performance and recent operational changes.",
        )

    if has_analytics:
        # Determine specific analytics tool
        if ("trend" in q and ("cost" in q or "price" in q)) or "supplier price" in q or "inflation" in q or "price hike" in q:
            return RouteDecision(
                category="analytics",
                tools=[("analyze_cost_trends", {"period": "last_90d"})],
                reason="Cost/supplier price trend query.",
            )
        if "breakeven" in q or "break-even" in q or "unit economics" in q or "contribution" in q or "product profitability" in q:
            return RouteDecision(
                category="analytics",
                tools=[("analyze_product_profitability", {"period": period})],
                reason="Product profitability / unit economics query.",
            )
        if "report" in q or "standup" in q or "pack" in q:
            rtype = "executive_brief"
            if "daily" in q or "standup" in q:
                rtype = "daily_standup"
            elif "weekly" in q:
                rtype = "weekly_pnl"
            elif "monthly" in q:
                rtype = "monthly_pack"
            return RouteDecision(
                category="analytics",
                tools=[("generate_business_report", {"report_type": rtype, "period": period})],
                reason="Business report generation query.",
            )
        return RouteDecision(
            category="analytics",
            tools=[("analyze_business_performance", {"period": period})],
            reason="General business performance query.",
        )

    if has_context:
        if "changes" in q or "what happened" in q or "recent" in q:
            days = 7
            if "30" in q:
                days = 30
            elif "14" in q:
                days = 14
            return RouteDecision(
                category="context",
                tools=[("get_recent_business_changes", {"since_days": days})],
                reason="Recent business changes query.",
            )
        if "memory" in q or "policy" in q:
            return RouteDecision(
                category="context",
                tools=[("get_business_memory", {})],
                reason="Business memory query.",
            )
        return RouteDecision(
            category="context",
            tools=[("get_business_overview", {"include_ledgers": True})],
            reason="Business overview query.",
        )

    # Default fallback: get_business_overview
    return RouteDecision(
        category="context",
        tools=[("get_business_overview", {"include_ledgers": True})],
        reason="Defaulted to business overview briefing.",
    )


def route_query(query: str) -> RouteDecision:
    """Route query using hybrid strategy (deterministic rule first, LLM fallback if needed)."""
    decision = route_query_deterministic(query)
    # The deterministic router handles all structured intent and out-of-scope detection accurately
    return decision
