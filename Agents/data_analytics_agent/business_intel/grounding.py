"""Grounding verifier for Business Intel Agent.

Inspects every number in generated speech/text before returning it to the user.
Extracts integers, floats, currency, percentages, Indian numbering (lakh, crore),
normalizes them, and verifies that every number originated from the tool envelope data.
Zero ungrounded numbers policy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ExtractedNumber:
    raw: str
    value: float
    is_percentage: bool
    is_multiplier: bool  # k, lakh, crore


# Regex patterns
# Match patterns like: ₹12,000, Rs 55.3k, 1.2 lakh, 64.6%, -1.7%, 14, 55320
NUMBER_PATTERN = re.compile(
    r"""
    (?P<prefix>(?:₹|rs\.?|inr)\s*)?
    (?P<sign>[+-])?
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*
    (?P<suffix>%|percent|k|lakhs?|lacs?|crores?|cr)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Date/time patterns to exclude from grounding check (e.g. 2026-10-10, 19:10, 2026)
DATE_TIME_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}:\d{2}(?::\d{2})?|(?:19|20)\d{2})\b"
)


def _collect_data_numbers(obj: Any, collected: Set[float]) -> None:
    """Recursively collect all numeric values from dicts, lists, and primitives."""
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        val = float(obj)
        collected.add(val)
        # If it could be a ratio (e.g. 0.173), also add the 0-100 percentage equivalent
        if -1.0 <= val <= 1.0:
            collected.add(round(val * 100.0, 4))
    elif isinstance(obj, str):
        # Try parsing strings that might contain numbers (e.g. '12000' or '₹12000')
        cleaned = re.sub(r"[^\d.-]", "", obj)
        if cleaned:
            try:
                collected.add(float(cleaned))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_data_numbers(v, collected)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            _collect_data_numbers(item, collected)


def extract_numbers(text: str) -> List[ExtractedNumber]:
    """Extract and normalize all numbers from speech/text."""
    # Find and mask out ISO dates and timestamps so they aren't parsed as standalone numbers
    masked_text = text
    for match in DATE_TIME_PATTERN.finditer(text):
        masked_text = (
            masked_text[: match.start()]
            + " " * (match.end() - match.start())
            + masked_text[match.end() :]
        )

    results: List[ExtractedNumber] = []
    for match in NUMBER_PATTERN.finditer(masked_text):
        num_str = match.group("num")
        if not num_str:
            continue

        raw = match.group(0).strip()
        # Filter out empty or single punctuation
        if not any(c.isdigit() for c in raw):
            continue

        # Clean number part
        num_clean = num_str.replace(",", "")
        try:
            base_val = float(num_clean)
        except ValueError:
            continue

        sign = -1.0 if match.group("sign") == "-" else 1.0
        suffix = (match.group("suffix") or "").lower()

        is_percentage = suffix in ("%", "percent")
        is_multiplier = False
        multiplier = 1.0

        if suffix == "k":
            multiplier = 1_000.0
            is_multiplier = True
        elif suffix in ("lakh", "lakhs", "lac", "lacs"):
            multiplier = 100_000.0
            is_multiplier = True
        elif suffix in ("crore", "crores", "cr"):
            multiplier = 10_000_000.0
            is_multiplier = True

        final_val = sign * base_val * multiplier
        results.append(
            ExtractedNumber(
                raw=raw,
                value=final_val,
                is_percentage=is_percentage,
                is_multiplier=is_multiplier,
            )
        )

    return results


def is_number_grounded(
    extracted: ExtractedNumber,
    ground_truth_numbers: Set[float],
    tolerances: Optional[Dict[str, float]] = None,
) -> bool:
    """Check if an extracted number matches any ground truth value.
    
    Accepts exact matches, rounded values (integer, 1 decimal place),
    k/lakh approximations, or percentage conversions.
    """
    ext_val = extracted.value

    for gt in ground_truth_numbers:
        # 1. Exact match within tiny epsilon
        if abs(ext_val - gt) < 1e-4:
            return True

        # 2. Rounded matches for integer speech (e.g. 17.3% -> 17%, or 18.2 -> 18)
        if abs(round(gt) - ext_val) < 1e-4:
            return True
        if abs(round(gt, 1) - ext_val) < 1e-4:
            return True
        if abs(round(gt, 2) - ext_val) < 1e-4:
            return True

        # 3. Percentage conversions: gt is 0.173, ext is 17.3 or 17
        if extracted.is_percentage:
            if abs(gt * 100.0 - ext_val) < 0.2:  # within 0.2% tolerance
                return True
            if abs(round(gt * 100.0) - ext_val) < 1e-4:
                return True

        # 4. Multiplier approximations (e.g. 55320 -> 55.3k = 55300, relative error <= 1%)
        if extracted.is_multiplier and abs(gt) > 100:
            rel_err = abs(ext_val - gt) / abs(gt)
            if rel_err <= 0.015:  # within 1.5%
                return True

    return False


def verify_grounding(
    text: str,
    data: Dict[str, Any],
    allowed_numbers: Optional[Set[float]] = None,
) -> Tuple[bool, List[str]]:
    """Verify that all numbers in `text` are grounded in `data`.
    
    Returns:
        (True, []) if all numbers are grounded.
        (False, [list of ungrounded raw number strings]) if any hallucination is found.
    """
    gt_numbers: Set[float] = set()
    _collect_data_numbers(data, gt_numbers)
    if allowed_numbers:
        gt_numbers.update(allowed_numbers)

    # Common contextual constants (e.g., periods: 7, 30, 90, 14; hours: 24)
    # These are structural invariants of cloud kitchen queries
    structural_constants = {0.0, 1.0, 7.0, 14.0, 30.0, 60.0, 90.0, 100.0}
    gt_numbers.update(structural_constants)

    extracted = extract_numbers(text)
    ungrounded: List[str] = []

    for item in extracted:
        if not is_number_grounded(item, gt_numbers):
            ungrounded.append(item.raw)

    return len(ungrounded) == 0, ungrounded
