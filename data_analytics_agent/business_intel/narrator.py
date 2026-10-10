"""Narrator for Business Intel Agent.

Generates final spoken voice response and rich display markdown for the user.
Follows strict grounding rules:
- With BI_LLM=off (or no key), uses deterministic templates from tool envelopes.
- With BI_LLM=on, prompts the LLM and runs Grounding Verifier with 1-shot retry fallback.
- Spoken response is strictly <= 45 words, conversational, no markdown.
- Display markdown has structured bullet points, metrics, or tables.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from business_intel.config import BI_LLM_ENABLED, GEMINI_API_KEY
from business_intel.grounding import verify_grounding
from business_intel.schemas import AgentAnswer, Envelope


def _build_deterministic_spoken(envelopes: List[Envelope]) -> str:
    """Build speech directly from precomputed tool envelope speech_summaries."""
    if not envelopes:
        return "I could not find the relevant business information."

    valid_summaries = [
        env.data.get("speech_summary", "").strip()
        for env in envelopes
        if env.ok and env.data and env.data.get("speech_summary")
    ]
    if not valid_summaries:
        first_err = next((env.error for env in envelopes if env.error), None)
        if first_err:
            return f"I encountered an issue retrieving business data: {first_err[:50]}"
        return "I could not find the relevant business information."

    combined = " ".join(valid_summaries)
    # Ensure word count limit <= 45 words
    words = combined.split()
    if len(words) > 45:
        combined = " ".join(words[:45])
        if not combined.endswith("."):
            combined += "."
    return combined


def _build_deterministic_display(envelopes: List[Envelope], title: str = "Business Intel Briefing") -> str:
    """Build markdown report for screens/phones deterministically from tool envelopes."""
    lines = [f"## {title}\n"]

    for i, env in enumerate(envelopes):
        tool_name = env.meta.tool if env.meta else f"Tool {i+1}"
        lines.append(f"### {tool_name.replace('_', ' ').title()}")

        if not env.ok:
            lines.append(f"> **Error:** {env.error or 'Operation failed'}\n")
            continue

        if env.warnings:
            for w in env.warnings:
                lines.append(f"> ⚠️ *{w}*")
            lines.append("")

        speech = env.data.get("speech_summary")
        if speech:
            lines.append(f"**Summary:** {speech}\n")

        # Key metrics table or highlights if present
        if "metrics" in env.data and isinstance(env.data["metrics"], dict):
            m = env.data["metrics"]
            lines.append("| Metric | Value |")
            lines.append("|---|---|")
            for k, v in m.items():
                if isinstance(v, (int, float, str)):
                    lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
            lines.append("")

        if "identity" in env.data:
            ident = env.data["identity"]
            lines.append(f"- **Business:** {ident.get('business_name')} ({ident.get('city')})")
            if "cash_position" in env.data:
                cp = env.data["cash_position"]
                lines.append(f"- **Current Cash:** ₹{cp.get('current_balance', 0):,.2f}")
            lines.append("")

        if "changes" in env.data and isinstance(env.data["changes"], list):
            lines.append(f"**Recent Events ({len(env.data['changes'])} total):**")
            for ch in env.data["changes"][:5]:
                lines.append(f"- `[{ch.get('date')}]` {ch.get('category').title()}: {ch.get('title')}")
            lines.append("")

    return "\n".join(lines)


def narrate_response(
    question: str,
    envelopes: List[Envelope],
    force_deterministic: bool = False,
) -> AgentAnswer:
    """Generate final AgentAnswer with spoken voice and display markdown."""
    tools_used = [env.meta.tool for env in envelopes if env.meta]
    caveats: List[str] = []
    min_confidence = 1.0

    combined_data: Dict[str, Any] = {}
    for env in envelopes:
        if env.warnings:
            caveats.extend(env.warnings)
        if env.confidence < min_confidence:
            min_confidence = env.confidence
        if env.source in ("estimate", "simulated"):
            caveats.append(f"Contains {env.source} data from {env.meta.tool if env.meta else 'analysis'}")
        if env.data:
            combined_data.update(env.data)

    # Deduplicate caveats
    caveats = list(dict.fromkeys(caveats))

    # Deterministic speech baseline
    baseline_spoken = _build_deterministic_spoken(envelopes)
    baseline_display = _build_deterministic_display(envelopes)

    # If LLM is disabled or no key or forced deterministic, return baseline directly
    if force_deterministic or not BI_LLM_ENABLED or not GEMINI_API_KEY:
        return AgentAnswer(
            spoken=baseline_spoken,
            display_markdown=baseline_display,
            tools_used=tools_used,
            confidence=round(min_confidence, 2),
            caveats=caveats,
        )

    # LLM branch (when BI_LLM=on and GEMINI_API_KEY is available)
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
You are the voice narrator for Maa Ki Rasoi Cloud Kitchen's Alexa Business Autopilot.
User Question: "{question}"
Tool Data (JSON):
{combined_data}

Rules:
1. Spoken: Under 45 words, conversational Indian English, clear numbers (Rs / lakh / %), NO markdown, NO asterisks, NO URLs.
2. Every number in Spoken MUST come directly from the Tool Data or be a trivial rounding of it. DO NOT invent or calculate new numbers.
3. Display: Rich markdown for screen with metrics, bullets, or tables.

Respond with:
SPOKEN: <voice response>
DISPLAY:
<markdown response>
"""
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        text = response.text or ""
        spoken = baseline_spoken
        display = baseline_display

        if "SPOKEN:" in text and "DISPLAY:" in text:
            parts = text.split("DISPLAY:")
            spoken_part = parts[0].replace("SPOKEN:", "").strip()
            display_part = parts[1].strip()
            if spoken_part:
                spoken = spoken_part
            if display_part:
                display = display_part

        # Grounding check
        is_grounded, ungrounded = verify_grounding(spoken, combined_data)
        if not is_grounded:
            # Attempt 1: Re-prompt
            retry_prompt = f"""
The following spoken response had ungrounded numbers: {ungrounded}.
Tool Data: {combined_data}
Rewrite the spoken response under 45 words using ONLY the numbers from the data.
"""
            retry_resp = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=retry_prompt,
            )
            retry_text = (retry_resp.text or "").strip()
            is_grounded_retry, _ = verify_grounding(retry_text, combined_data)
            if is_grounded_retry and len(retry_text.split()) <= 45:
                spoken = retry_text
            else:
                # Fall back to deterministic speech
                spoken = baseline_spoken

        # Final word count enforcement
        if len(spoken.split()) > 45:
            spoken = " ".join(spoken.split()[:45])
            if not spoken.endswith("."):
                spoken += "."

        return AgentAnswer(
            spoken=spoken,
            display_markdown=display,
            tools_used=tools_used,
            confidence=round(min_confidence, 2),
            caveats=caveats,
        )
    except Exception:
        # Graceful fallback on LLM failure
        return AgentAnswer(
            spoken=baseline_spoken,
            display_markdown=baseline_display,
            tools_used=tools_used,
            confidence=round(min_confidence, 2),
            caveats=caveats,
        )

