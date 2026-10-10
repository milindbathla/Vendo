"""
Period parser and comparison baseline resolver relative to the frozen clock.
Never uses system clock datetime.now().
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class ResolvedPeriod:
    """Resolved date boundaries and metadata for a query period."""
    start_date: str          # YYYY-MM-DD
    end_date: str            # YYYY-MM-DD
    days_count: int
    complete_days: bool
    warnings: List[str]
    compare_start: Optional[str] = None
    compare_end: Optional[str] = None
    period_label: str = ""

    @property
    def num_days(self) -> int:
        return self.days_count

    @property
    def warning(self) -> Optional[str]:
        return self.warnings[0] if self.warnings else None


# Default frozen reference date
FROZEN_DATE_STR = "2026-10-10"
FROZEN_TIME_STR = "19:10"


def parse_iso_date(date_str: str) -> datetime.date:
    """Parses a YYYY-MM-DD string into a datetime.date object."""
    return datetime.date.fromisoformat(date_str[:10])


def resolve_period(
    period_expr: str = "last_7d",
    compare_to: str = "previous_period",
    as_of_date_str: str = FROZEN_DATE_STR,
    as_of_time_str: str = FROZEN_TIME_STR,
) -> ResolvedPeriod:
    """
    Parses a period expression relative to the frozen reference date.
    Returns ResolvedPeriod with exact ISO date boundaries and comparison window.
    """
    as_of_date = parse_iso_date(as_of_date_str)
    yesterday_date = as_of_date - datetime.timedelta(days=1)

    expr = (period_expr or "last_7d").strip().lower()
    warnings: List[str] = []
    complete_days = True

    # 1. Today / Aaj
    if expr in ("today", "aaj"):
        start_date = as_of_date
        end_date = as_of_date
        complete_days = False
        warnings.append(f"today is partial as of {as_of_time_str}")
        label = "today"

    # 2. Yesterday / Kal
    elif expr in ("yesterday", "kal", "beeta kal", "beeta_kal"):
        start_date = yesterday_date
        end_date = yesterday_date
        label = "yesterday"

    # 3. Last 7 Days / This week / Is hafte / Pichhle 7 din
    elif expr in ("last_7d", "last_7_days", "7d", "this_week", "is_hafte", "is hafte", "pichhle_7_din", "pichhle 7 din"):
        end_date = yesterday_date
        start_date = end_date - datetime.timedelta(days=6)
        label = "last_7d"

    # 4. Last 30 Days / Pichhle 30 din / 30d
    elif expr in ("last_30d", "last_30_days", "30d", "pichhle_30_din", "pichhle 30 din", "last 30 days"):
        end_date = yesterday_date
        start_date = end_date - datetime.timedelta(days=29)
        label = "last_30d"

    # 5. Month-to-date (MTD) / Is mahine / This month
    elif expr in ("mtd", "month_to_date", "this_month", "is_mahine", "is mahine"):
        start_date = datetime.date(as_of_date.year, as_of_date.month, 1)
        end_date = yesterday_date
        if end_date < start_date:
            end_date = start_date
            complete_days = False
            warnings.append(f"today is partial as of {as_of_time_str}")
        label = "mtd"

    # 6. Last Month / Pichhla mahina
    elif expr in ("last_month", "pichhla_mahina", "pichhla mahina"):
        # Prior month to October 2026 is September 2026 (30 days)
        if as_of_date.month == 1:
            prev_year = as_of_date.year - 1
            prev_month = 12
        else:
            prev_year = as_of_date.year
            prev_month = as_of_date.month - 1
        start_date = datetime.date(prev_year, prev_month, 1)
        # Last day of prev month
        if prev_month in (1, 3, 5, 7, 8, 10, 12):
            last_day = 31
        elif prev_month == 2:
            last_day = 28  # 2026 is not a leap year
        else:
            last_day = 30
        end_date = datetime.date(prev_year, prev_month, last_day)
        label = f"{prev_year}-{prev_month:02d}"

    # 7. Specific Month format 'YYYY-MM'
    elif len(expr) == 7 and expr[4] == "-" and expr[:4].isdigit() and expr[5:].isdigit():
        y = int(expr[:4])
        m = int(expr[5:])
        start_date = datetime.date(y, m, 1)
        if m in (1, 3, 5, 7, 8, 10, 12):
            ld = 31
        elif m == 2:
            ld = 28
        else:
            ld = 30
        end_date = datetime.date(y, m, ld)
        label = expr

    # 8. Date Range 'YYYY-MM-DD..YYYY-MM-DD'
    elif ".." in expr:
        parts = expr.split("..")
        start_date = parse_iso_date(parts[0])
        end_date = parse_iso_date(parts[1])
        if end_date >= as_of_date:
            complete_days = False
            warnings.append(f"today is partial as of {as_of_time_str}")
        label = f"{start_date.isoformat()}..{end_date.isoformat()}"

    # 9. Fallback to single date or default
    else:
        try:
            target_d = parse_iso_date(expr)
            start_date = target_d
            end_date = target_d
            if target_d >= as_of_date:
                complete_days = False
                warnings.append(f"today is partial as of {as_of_time_str}")
            label = target_d.isoformat()
        except ValueError:
            # Default to last 7 complete days
            end_date = yesterday_date
            start_date = end_date - datetime.timedelta(days=6)
            label = "last_7d"

    days_count = (end_date - start_date).days + 1

    # Resolve Comparison Period
    compare_start: Optional[str] = None
    compare_end: Optional[str] = None

    if compare_to == "previous_period":
        comp_end_date = start_date - datetime.timedelta(days=1)
        comp_start_date = comp_end_date - datetime.timedelta(days=days_count - 1)
        compare_start = comp_start_date.isoformat()
        compare_end = comp_end_date.isoformat()
    elif compare_to == "same_period_last_month":
        # Shift back ~30 days
        comp_start_date = start_date - datetime.timedelta(days=30)
        comp_end_date = end_date - datetime.timedelta(days=30)
        compare_start = comp_start_date.isoformat()
        compare_end = comp_end_date.isoformat()

    return ResolvedPeriod(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        days_count=days_count,
        complete_days=complete_days,
        warnings=warnings,
        compare_start=compare_start,
        compare_end=compare_end,
        period_label=label,
    )


def resolve_since_window(
    since_expr: str = "7d",
    as_of_date_str: str = FROZEN_DATE_STR,
) -> Tuple[str, str]:
    """
    Parses a `since` expression (e.g. '24h', '48h', '7d', '30d', 'since_yesterday', ISO timestamp).
    Returns (cutoff_iso_date, cutoff_iso_timestamp).
    """
    as_of_date = parse_iso_date(as_of_date_str)
    as_of_dt = datetime.datetime.fromisoformat(f"{as_of_date_str}T19:10:00+05:30")
    s = (since_expr or "7d").strip().lower()

    if s == "24h":
        cutoff_dt = as_of_dt - datetime.timedelta(hours=24)
    elif s == "48h":
        cutoff_dt = as_of_dt - datetime.timedelta(hours=48)
    elif s in ("7d", "last_7d"):
        cutoff_dt = as_of_dt - datetime.timedelta(days=7)
    elif s in ("30d", "last_30d"):
        cutoff_dt = as_of_dt - datetime.timedelta(days=30)
    elif s in ("since_yesterday", "kal_se"):
        yesterday = as_of_date - datetime.timedelta(days=1)
        cutoff_dt = datetime.datetime.fromisoformat(f"{yesterday.isoformat()}T00:00:00+05:30")
    else:
        try:
            if "t" in s:
                cutoff_dt = datetime.datetime.fromisoformat(s)
            else:
                d = parse_iso_date(s)
                cutoff_dt = datetime.datetime.fromisoformat(f"{d.isoformat()}T00:00:00+05:30")
        except Exception:
            cutoff_dt = as_of_dt - datetime.timedelta(days=7)

    return cutoff_dt.date().isoformat(), cutoff_dt.isoformat()


def get_comparison_period(
    period: ResolvedPeriod,
    compare_to: str = "previous_period",
) -> ResolvedPeriod:
    """Helper to return the comparison period as a ResolvedPeriod."""
    if period.compare_start and period.compare_end:
        start_d = parse_iso_date(period.compare_start)
        end_d = parse_iso_date(period.compare_end)
        days = (end_d - start_d).days + 1
        return ResolvedPeriod(
            start_date=period.compare_start,
            end_date=period.compare_end,
            days_count=days,
            complete_days=True,
            warnings=[],
            period_label=f"comparison_{compare_to}",
        )
    return period
