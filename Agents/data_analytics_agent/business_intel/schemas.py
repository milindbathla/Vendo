"""
Pydantic v2 schemas and envelopes for Business Intel Agent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["db", "estimate", "simulated"]
LanguageType = Literal["en", "hi", "hinglish"]


class ToolMeta(BaseModel):
    """Execution metadata attached to tool results."""
    model_config = ConfigDict(extra="ignore")

    tool: str = Field(description="Name of the tool executed")
    as_of: str = Field(description="Frozen timestamp as of which the query ran")
    period_resolved: Optional[str] = Field(default=None, description="Resolved date window if applicable")
    latency_ms: float = Field(default=0.0, description="Execution latency in milliseconds")
    queries: int = Field(default=1, description="Number of database queries executed")


class Envelope(BaseModel):
    """Standardized response envelope returned by all tools."""
    model_config = ConfigDict(extra="ignore")

    ok: bool = Field(description="Whether the tool succeeded")
    data: Dict[str, Any] = Field(default_factory=dict, description="Precomputed structured payload including speech_summary")
    confidence: float = Field(ge=0.0, le=1.0, description="Calculated confidence score [0.0, 1.0]")
    source: SourceType = Field(description="Origin category: db, estimate, or simulated")
    warnings: List[str] = Field(default_factory=list, description="Any warnings, caveat flags, or partial day alerts")
    error: Optional[str] = Field(default=None, description="Error message if tool failed")
    meta: Optional[ToolMeta] = Field(default=None, description="Tool execution telemetry")


# Tool Input Schemas

class GetBusinessOverviewInput(BaseModel):
    """Input parameters for get_business_overview (takes no arguments)."""
    model_config = ConfigDict(extra="ignore")


class GetRecentBusinessChangesInput(BaseModel):
    """Input parameters for get_recent_business_changes."""
    model_config = ConfigDict(extra="ignore")

    since: str = Field(
        default="7d",
        description="Lookback window: '24h', '48h', '7d', '30d', 'since_yesterday', or ISO date/datetime"
    )


class GetBusinessMemoryInput(BaseModel):
    """Input parameters for get_business_memory."""
    model_config = ConfigDict(extra="ignore")

    key: Optional[str] = Field(
        default=None,
        description="Specific knowledge key (e.g. 'supplier.gupta.oil_price_per_l'). If None, lists all keys."
    )
    prefix: Optional[str] = Field(
        default=None,
        description="Filter keys by dot-separated prefix (e.g. 'supplier.', 'owner.')"
    )
    include_history: bool = Field(
        default=False,
        description="Whether to return all candidate historical observations per key"
    )


class WriteBusinessMemoryInput(BaseModel):
    """Input parameters for write_business_memory."""
    model_config = ConfigDict(extra="ignore")

    key: str = Field(default="policy.owner_note", description="Knowledge topic key (e.g. 'owner.preferred_delivery_time')")
    value: str = Field(default="noted", description="Value asserted by the owner")
    category: Optional[str] = Field(default=None, description="Optional category prefix")
    source: Literal["owner_statement", "verified_record"] = Field(
        default="owner_statement",
        description="Source of the memory. Only 'owner_statement' is accepted by this tool."
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence override. Defaults to 0.40 for owner statements."
    )
    note: Optional[str] = Field(
        default=None,
        description="Optional explanatory note or context"
    )


class AnalyzeBusinessPerformanceInput(BaseModel):
    """Input parameters for analyze_business_performance."""
    model_config = ConfigDict(extra="ignore")

    period: str = Field(
        default="last_7d",
        description="Primary period: 'today', 'yesterday', 'last_7d', 'last_30d', 'mtd', 'last_month', or 'YYYY-MM-DD..YYYY-MM-DD'"
    )
    compare_to: Literal["previous_period", "same_period_last_month", "none"] = Field(
        default="previous_period",
        description="Comparison baseline to compute deltas"
    )


class AnalyzeProductProfitabilityInput(BaseModel):
    """Input parameters for analyze_product_profitability (single-SKU tiffin economics)."""
    model_config = ConfigDict(extra="ignore")


class AnalyzeCostTrendsInput(BaseModel):
    """Input parameters for analyze_cost_trends."""
    model_config = ConfigDict(extra="ignore")

    window_days: int = Field(
        default=90,
        ge=7,
        le=365,
        description="Historical observation window in days (default 90 days)"
    )


class GenerateBusinessReportInput(BaseModel):
    """Input parameters for generate_business_report."""
    model_config = ConfigDict(extra="ignore")

    period: str = Field(
        default="last_30d",
        description="Report period: 'last_7d', 'last_30d', 'mtd', 'last_month', etc."
    )
    format: Literal["json", "markdown"] = Field(
        default="markdown",
        description="Output format: 'json' or 'markdown' (Obsidian-compatible)"
    )


class AskBusinessIntelInput(BaseModel):
    """Unified natural language question input for Business Intel Agent."""
    model_config = ConfigDict(extra="ignore")

    question: str = Field(description="Owner natural language question in English, Hindi, or Hinglish")
    language: Optional[str] = Field(default=None, description="Optional target language override ('en', 'hi', 'hinglish')")


class AgentAnswer(BaseModel):
    """End-to-end result envelope returned by the Business Intel Agent."""
    model_config = ConfigDict(extra="ignore")

    speech: str = Field(default="", description="Concise spoken reply for voice output (<= 45 words, no markdown)")
    spoken: Optional[str] = Field(default=None, description="Alias for speech")
    details_markdown: Optional[str] = Field(default=None, description="Visual detail / table for screen-enabled devices")
    display_markdown: Optional[str] = Field(default=None, description="Alias for details_markdown")
    language: str = Field(default="en", description="Detected language ('en', 'hi', 'hinglish')")
    intents: List[str] = Field(default_factory=list, description="Resolved routing intents")
    tools_used: List[str] = Field(default_factory=list, description="Tool names used")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Tools called with arguments and latency")
    envelopes: List[Dict[str, Any]] = Field(default_factory=list, description="Underlying tool envelopes returned")
    grounded: bool = Field(default=True, description="Whether all numbers in speech were strictly grounded")
    ungrounded_tokens: List[str] = Field(default_factory=list, description="Any ungrounded numeric tokens detected")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall answer confidence")
    warnings: List[str] = Field(default_factory=list, description="Aggregated warnings from tools")
    caveats: List[str] = Field(default_factory=list, description="Alias for warnings")
    trace_id: str = Field(default="", description="Unique tracing identifier for observability")

    def model_post_init(self, __context: Any) -> None:
        if not self.speech and self.spoken:
            self.speech = self.spoken
        elif not self.spoken and self.speech:
            self.spoken = self.speech
        if not self.details_markdown and self.display_markdown:
            self.details_markdown = self.display_markdown
        elif not self.display_markdown and self.details_markdown:
            self.display_markdown = self.details_markdown
        if not self.caveats and self.warnings:
            self.caveats = self.warnings
        elif not self.warnings and self.caveats:
            self.warnings = self.caveats


class OutOfScopeResponse(BaseModel):
    """Envelope returned when a user request falls outside Business Intel scope."""
    model_config = ConfigDict(extra="ignore")

    ok: bool = False
    out_of_scope: bool = True
    error: str = "out_of_scope"
    suggested_agent: str
    reason: str
    speech_summary: str = ""
    speech_refusal: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.speech_refusal and self.speech_summary:
            self.speech_refusal = self.speech_summary
        elif not self.speech_summary and self.speech_refusal:
            self.speech_summary = self.speech_refusal
