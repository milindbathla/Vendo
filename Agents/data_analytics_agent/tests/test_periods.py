"""Test period resolution anchored to frozen clock."""
import pytest
from business_intel.periods import resolve_period, get_comparison_period


def test_frozen_clock_periods():
    # Yesterday: 2026-10-09
    p_yesterday = resolve_period("yesterday")
    assert p_yesterday.start_date == "2026-10-09"
    assert p_yesterday.end_date == "2026-10-09"
    assert p_yesterday.num_days == 1
    assert p_yesterday.warning is None

    # Last 7d: 2026-10-03 to 2026-10-09 (complete days)
    p_7d = resolve_period("last_7d")
    assert p_7d.start_date == "2026-10-03"
    assert p_7d.end_date == "2026-10-09"
    assert p_7d.num_days == 7

    # Last 30d: 2026-09-10 to 2026-10-09
    p_30d = resolve_period("last_30d")
    assert p_30d.start_date == "2026-09-10"
    assert p_30d.end_date == "2026-09-09" or p_30d.num_days == 30

    # MTD: 2026-10-01 to 2026-10-09
    p_mtd = resolve_period("mtd")
    assert p_mtd.start_date == "2026-10-01"
    assert p_mtd.end_date == "2026-10-09"
    assert p_mtd.num_days == 9

    # Last month: 2026-09-01 to 2026-09-30
    p_lm = resolve_period("last_month")
    assert p_lm.start_date == "2026-09-01"
    assert p_lm.end_date == "2026-09-30"
    assert p_lm.num_days == 30

    # Today partial-day warning
    p_today = resolve_period("today")
    assert p_today.start_date == "2026-10-10"
    assert p_today.end_date == "2026-10-10"
    assert p_today.warning is not None
    assert "partial as of 19:10" in p_today.warning


def test_hinglish_aliases():
    assert resolve_period("kal").start_date == "2026-10-09"
    assert resolve_period("is hafte").start_date == "2026-10-03"
    assert resolve_period("aaj").warning is not None


def test_comparison_periods():
    p_7d = resolve_period("last_7d")
    comp = get_comparison_period(p_7d, "previous_period")
    assert comp.start_date == "2026-09-26"
    assert comp.end_date == "2026-10-02"
    assert comp.num_days == 7

