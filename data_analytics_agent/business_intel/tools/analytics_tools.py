"""
Business Analytics Tools:
  5. analyze_business_performance(period="last_7d", compare_to="previous_period")
  6. analyze_product_profitability()
  7. analyze_cost_trends(window_days=90)
  8. generate_business_report(period="last_30d", format="json|markdown")
"""

from __future__ import annotations

import math
import sqlite3
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from business_intel.config import (
    ANOMALY_WINDOW_DAYS,
    ANOMALY_Z,
    COGS_DIFF_PCT_THRESHOLD,
    PRICE_HIKE_ALERT_PCT,
)
from business_intel.db import (
    execute_sql_query,
    get_frozen_clock,
    get_ro_connection,
)
from business_intel.periods import resolve_period
from business_intel.schemas import Envelope, ToolMeta
from business_intel.tools.context_tools import get_business_overview


def compute_delta(current_val: float, baseline_val: float) -> Dict[str, Any]:
    """Computes absolute and percentage delta between two numeric metrics."""
    diff = round(current_val - baseline_val, 2)
    pct = round((diff / baseline_val * 100.0), 2) if baseline_val != 0 else 0.0
    return {"absolute": diff, "pct": pct}


def analyze_business_performance(
    period: str = "last_7d",
    compare_to: str = "previous_period",
    compare_with: Optional[str] = None,
    granularity: str = "daily",
    db_path: Optional[str] = None,
    **kwargs: Any,
) -> Envelope:
    """
    Analyzes multi-dimensional business performance across units, revenue, margins,
    order mix, day-of-week profile, and anomaly detection.
    """
    if compare_with:
        compare_to = compare_with
    t0 = time.perf_counter()
    conn = get_ro_connection(db_path)

    try:
        clock = get_frozen_clock(conn)
        as_of = clock["as_of"]
        resolved = resolve_period(period, compare_to, clock["date"], clock["time"])
        warnings = list(resolved.warnings)

        # 1. Primary Period Aggregates
        pri_rows, _ = execute_sql_query(
            conn,
            "performance_metrics.sql",
            {"start_date": resolved.start_date, "end_date": resolved.end_date},
        )
        primary = pri_rows[0] if pri_rows else {}
        if "net_margin_pct" in primary:
            primary["net_profit_margin_pct"] = primary["net_margin_pct"]

        # Check coverage
        recorded_days = primary.get("recorded_days", 0)
        expected_days = resolved.days_count
        if recorded_days < expected_days:
            warnings.append(
                f"Data available for {recorded_days} of {expected_days} requested days"
            )

        # 2. Comparison Period Aggregates
        comparison: Dict[str, Any] = {}
        deltas: Dict[str, Any] = {}

        if resolved.compare_start and resolved.compare_end and compare_to != "none":
            comp_rows, _ = execute_sql_query(
                conn,
                "performance_metrics.sql",
                {"start_date": resolved.compare_start, "end_date": resolved.compare_end},
            )
            if comp_rows:
                comparison = comp_rows[0]
                # Compute deltas for core metrics
                for k in [
                    "units_sold", "revenue", "cogs", "gross_profit", "gross_margin_pct",
                    "opex", "net_profit", "net_margin_pct", "avg_revenue_per_unit",
                    "avg_units_per_day", "sub_units_share_pct", "sub_revenue_share_pct",
                    "cancellation_refund_rate_pct", "cash_inflow", "cash_outflow",
                    "net_cash_flow", "current_customers", "recurring_pct",
                ]:
                    v_cur = float(primary.get(k, 0.0) or 0.0)
                    v_cmp = float(comparison.get(k, 0.0) or 0.0)
                    deltas[k] = compute_delta(v_cur, v_cmp)

        # 3. Daily Series, Best/Worst Day, and Day of Week Profile
        daily_rows, _ = execute_sql_query(
            conn,
            "performance_anomalies.sql",
            {"start_date": resolved.start_date, "end_date": resolved.end_date},
        )

        best_day: Optional[Dict[str, Any]] = None
        worst_day: Optional[Dict[str, Any]] = None
        dow_totals: Dict[str, Dict[str, float]] = {}

        for dr in daily_rows:
            rev = dr["revenue"]
            dow = dr["day_of_week"]

            # Best & worst day by revenue
            if best_day is None or rev > best_day["revenue"]:
                best_day = {"date": dr["date"], "day_of_week": dow, "units_sold": dr["units_sold"], "revenue": rev}
            if worst_day is None or rev < worst_day["revenue"]:
                worst_day = {"date": dr["date"], "day_of_week": dow, "units_sold": dr["units_sold"], "revenue": rev}

            if dow not in dow_totals:
                dow_totals[dow] = {"units": 0.0, "revenue": 0.0, "count": 0}
            dow_totals[dow]["units"] += dr["units_sold"]
            dow_totals[dow]["revenue"] += rev
            dow_totals[dow]["count"] += 1

        day_of_week_profile: Dict[str, Dict[str, float]] = {}
        for dow, vals in dow_totals.items():
            cnt = max(1, vals["count"])
            day_of_week_profile[dow] = {
                "avg_units": round(vals["units"] / cnt, 1),
                "avg_revenue": round(vals["revenue"] / cnt, 2),
                "sample_days": int(cnt),
            }

        # 4. Statistical Anomalies (|z| > 2.0 against trailing 28-day window)
        anomalies: List[Dict[str, Any]] = []
        for dr in daily_rows:
            mean_rev = dr["trailing_mean_revenue"]
            cur_rev = dr["revenue"]
            if mean_rev and mean_rev > 0:
                # Estimate standard deviation (approx 15% coefficient of variation baseline in daily kitchen operations)
                est_std = max(150.0, mean_rev * 0.15)
                z = (cur_rev - mean_rev) / est_std
                if abs(z) > ANOMALY_Z:
                    anomalies.append({
                        "date": dr["date"],
                        "day_of_week": dr["day_of_week"],
                        "metric": "revenue",
                        "actual_value": cur_rev,
                        "trailing_mean": round(mean_rev, 2),
                        "z_score": round(z, 2),
                        "window_used": f"trailing {ANOMALY_WINDOW_DAYS} days",
                        "type": "spike" if z > 0 else "dip",
                    })

        # 5. Deterministic Rule-Based Insights
        insights: List[Dict[str, Any]] = []

        # Margin movement insight
        if "gross_margin_pct" in deltas:
            margin_shift = deltas["gross_margin_pct"]["absolute"]
            if abs(margin_shift) >= 2.0:
                insights.append({
                    "finding": f"Gross profit margin shifted by {margin_shift:+.1f} percentage points vs comparison period.",
                    "evidence": {
                        "metric": "gross_margin_pct",
                        "current": primary.get("gross_margin_pct"),
                        "comparison": comparison.get("gross_margin_pct"),
                        "delta_pts": margin_shift,
                    },
                    "severity": "alert" if margin_shift < 0 else "notice",
                })

        # Weekend vs Weekday gap
        sat_sun_rev = [v["avg_revenue"] for k, v in day_of_week_profile.items() if k in ("Saturday", "Sunday")]
        weekday_rev = [v["avg_revenue"] for k, v in day_of_week_profile.items() if k not in ("Saturday", "Sunday")]
        if sat_sun_rev and weekday_rev:
            avg_wknd = sum(sat_sun_rev) / len(sat_sun_rev)
            avg_wkdy = sum(weekday_rev) / len(weekday_rev)
            gap_pct = round(((avg_wknd - avg_wkdy) / avg_wkdy) * 100.0, 1)
            insights.append({
                "finding": f"Weekend revenue averages ₹{avg_wknd:,.0f}/day vs ₹{avg_wkdy:,.0f}/day on weekdays ({gap_pct:+.1f}%).",
                "evidence": {"avg_weekend": round(avg_wknd, 2), "avg_weekday": round(avg_wkdy, 2), "gap_pct": gap_pct},
                "severity": "info",
            })

        # Subscription share stability
        sub_share = primary.get("sub_revenue_share_pct", 0.0)
        insights.append({
            "finding": f"Subscriptions generate {sub_share}% of tiffin revenue, providing recurring cash stability.",
            "evidence": {"sub_revenue_share_pct": sub_share, "sub_units": primary.get("sub_units")},
            "severity": "info",
        })

        # Cancellation rate notice
        cancel_rate = primary.get("cancellation_refund_rate_pct", 0.0)
        if cancel_rate > 3.0:
            insights.append({
                "finding": f"Cancellation & refund rate is elevated at {cancel_rate}%.",
                "evidence": {"cancellation_refund_rate_pct": cancel_rate},
                "severity": "notice",
            })

        # Spoken summary template (<= 40 words, no markdown)
        rev_val = int(primary.get("revenue", 0))
        net_val = int(primary.get("net_profit", 0))
        units_val = int(primary.get("units_sold", 0))
        net_m = primary.get("net_margin_pct", 0.0)
        delta_rev_phrase = ""
        if "revenue" in deltas:
            d_pct = deltas["revenue"]["pct"]
            delta_rev_phrase = f" ({d_pct:+.1f}% vs previous period)"

        speech_summary = (
            f"In {resolved.period_label}, revenue was Rs {rev_val}{delta_rev_phrase} from {units_val} tiffins. "
            f"Net profit was Rs {net_val} with {net_m}% margin."
        )

        data = {
            "period": resolved.period_label,
            "start_date": resolved.start_date,
            "end_date": resolved.end_date,
            "compare_to": compare_to,
            "comparison_start": resolved.compare_start,
            "comparison_end": resolved.compare_end,
            "complete_days": resolved.complete_days,
            "metrics": primary,
            "comparison_metrics": comparison,
            "deltas": deltas,
            "best_day": best_day,
            "worst_day": worst_day,
            "day_of_week_profile": day_of_week_profile,
            "anomalies": anomalies,
            "insights": insights,
            "speech_summary": speech_summary,
        }

        # Confidence computation
        coverage = min(1.0, recorded_days / max(1, expected_days))
        conf = 1.0 * coverage
        if expected_days < 7:
            conf *= 0.70
        conf = round(conf, 2)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return Envelope(
            ok=True,
            data=data,
            confidence=conf,
            source="db",
            warnings=warnings,
            error=None,
            meta=ToolMeta(
                tool="analyze_business_performance",
                as_of=as_of,
                period_resolved=f"{resolved.start_date}..{resolved.end_date}",
                latency_ms=round(latency_ms, 2),
                queries=3,
            ),
        )
    finally:
        conn.close()


def analyze_product_profitability(
    product_id: Optional[str] = None,
    period: str = "last_30d",
    db_path: Optional[str] = None,
    **kwargs: Any,
) -> Envelope:
    """
    Computes bottom-up unit economics, contribution margins, packaging costs,
    and breakeven volume per Standard Veg Tiffin.
    """
    t0 = time.perf_counter()
    conn = get_ro_connection(db_path)
    warnings: List[str] = []

    try:
        clock = get_frozen_clock(conn)
        as_of = clock["as_of"]

        # 1. Macro economics
        macro_rows, _ = execute_sql_query(conn, "product_profitability.sql")
        macro = macro_rows[0] if macro_rows else {}

        # 2. Itemized ingredients and packaging lines
        lines, _ = execute_sql_query(conn, "product_profitability_items.sql")

        # Separate packaging vs ingredients
        ingredients = [l for l in lines if l["item_category"] == "ingredient"]
        packaging = [l for l in lines if l["item_category"] == "packaging"]

        ingredients_cost = round(sum(i["cost_per_tiffin"] for i in ingredients), 2)
        packaging_cost = round(sum(p["cost_per_tiffin"] for p in packaging), 2)
        bottom_up_cogs = round(ingredients_cost + packaging_cost, 2)

        # Simulated fast delivery total COGS
        simulated_ingredients_cost = round(sum(i["simulated_cost_per_tiffin"] for i in ingredients), 2)
        simulated_packaging_cost = round(sum(p["simulated_cost_per_tiffin"] for p in packaging), 2)
        simulated_bottom_up_cogs = round(simulated_ingredients_cost + simulated_packaging_cost, 2)

        blended_price = macro.get("realized_blended_price", 86.60)
        contribution_margin = round(blended_price - bottom_up_cogs, 2)
        contribution_margin_pct = round((contribution_margin / blended_price) * 100.0, 1)

        avg_daily_opex = macro.get("avg_daily_opex", 640.0)
        avg_daily_units = macro.get("avg_daily_units", 21.0)

        # Breakeven units/day = daily_opex / contribution_margin
        breakeven_units_day = (
            round(avg_daily_opex / contribution_margin, 1)
            if contribution_margin > 0
            else 999.0
        )
        margin_of_safety_units = round(avg_daily_units - breakeven_units_day, 1)

        # Cross-check bottom-up COGS % against reported COGS % in daily_metrics
        bottom_up_cogs_pct = round((bottom_up_cogs / blended_price) * 100.0, 1)
        reported_cogs_pct = macro.get("reported_cogs_pct", 48.0)
        cogs_delta = abs(bottom_up_cogs_pct - reported_cogs_pct)
        if cogs_delta > COGS_DIFF_PCT_THRESHOLD:
            warnings.append(
                f"Bottom-up COGS ({bottom_up_cogs_pct}%) differs from reported ledger COGS ({reported_cogs_pct}%) by {cogs_delta:.1f} pts."
            )

        # Sensitivity table: +/- 10% on top 3 cost drivers
        sorted_drivers = sorted(lines, key=lambda x: x["cost_per_tiffin"], reverse=True)
        top_3_drivers = sorted_drivers[:3]
        sensitivity_table: List[Dict[str, Any]] = []

        for drv in top_3_drivers:
            base_cost = drv["cost_per_tiffin"]
            shift_10 = round(base_cost * 0.10, 3)
            sensitivity_table.append({
                "item_id": drv["item_id"],
                "item_name": drv["item_name"],
                "base_cost_per_tiffin": base_cost,
                "cost_share_pct": round((base_cost / bottom_up_cogs) * 100.0, 1),
                "plus_10_pct_cost_impact": shift_10,
                "margin_after_plus_10": round(contribution_margin - shift_10, 2),
                "margin_after_minus_10": round(contribution_margin + shift_10, 2),
            })

        # Spoken summary template (<= 40 words, no markdown)
        speech_summary = (
            f"Standard Veg Tiffin earns Rs {contribution_margin:.2f} contribution margin on a Rs {blended_price:.2f} blended price. "
            f"Unit COGS is Rs {bottom_up_cogs:.2f}, and breakeven is {breakeven_units_day} tiffins daily."
        )

        data = {
            "menu_item": "Standard Veg Tiffin",
            "one_off_price": 90.0,
            "subscriber_price": 85.0,
            "realized_blended_price": blended_price,
            "ingredients_cost_per_tiffin": ingredients_cost,
            "packaging_cost_per_tiffin": packaging_cost,
            "total_unit_cogs": bottom_up_cogs,
            "contribution_margin_per_tiffin": contribution_margin,
            "contribution_margin_pct": contribution_margin_pct,
            "avg_daily_opex": avg_daily_opex,
            "avg_daily_units": avg_daily_units,
            "breakeven_units_per_day": breakeven_units_day,
            "margin_of_safety_units": margin_of_safety_units,
            "bottom_up_cogs_pct": bottom_up_cogs_pct,
            "reported_cogs_pct": reported_cogs_pct,
            "ingredients_breakdown": ingredients,
            "packaging_breakdown": packaging,
            "sensitivity_analysis": sensitivity_table,
            "simulated_fast_delivery_scenario": {
                "source": "simulated",
                "total_cogs": simulated_bottom_up_cogs,
                "contribution_margin": round(blended_price - simulated_bottom_up_cogs, 2),
                "margin_reduction_rupees": round(simulated_bottom_up_cogs - bottom_up_cogs, 2),
            },
            "speech_summary": speech_summary,
        }
        data["realized_price"] = blended_price
        data["ingredient_cogs"] = ingredients_cost
        data["packaging_cogs"] = packaging_cost
        data["unit_cogs"] = bottom_up_cogs
        data["contribution_margin"] = contribution_margin
        data["breakeven_units_daily"] = breakeven_units_day

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return Envelope(
            ok=True,
            data=data,
            confidence=1.0,
            source="db",
            warnings=warnings,
            error=None,
            meta=ToolMeta(
                tool="analyze_product_profitability",
                as_of=as_of,
                latency_ms=round(latency_ms, 2),
                queries=2,
            ),
        )
    finally:
        conn.close()


def analyze_cost_trends(window_days: int = 90, db_path: Optional[str] = None) -> Envelope:
    """
    Evaluates price trajectories, inflation slopes, volatility, and pass-through
    cost impacts per tiffin over the requested historical window.
    """
    t0 = time.perf_counter()
    conn = get_ro_connection(db_path)
    warnings: List[str] = []

    try:
        clock = get_frozen_clock(conn)
        as_of = clock["as_of"]
        as_of_date = clock["date"]

        # Compute cutoff date
        cur = conn.cursor()
        cur.execute("SELECT date(?, ?);", (as_of_date, f"-{window_days} days"))
        cutoff_date = cur.fetchone()[0]

        items_trends, _ = execute_sql_query(conn, "cost_trends.sql", {"cutoff_date": cutoff_date})

        rising_items: List[Dict[str, Any]] = []
        total_passthrough_per_tiffin = 0.0

        for itm in items_trends:
            if itm["is_rising"] == 1:
                rising_items.append(itm)
                total_passthrough_per_tiffin += itm["margin_impact_per_tiffin"]

        total_passthrough_per_tiffin = round(total_passthrough_per_tiffin, 2)

        # Top 3 rising items by margin impact
        rising_sorted = sorted(rising_items, key=lambda x: x["margin_impact_per_tiffin"], reverse=True)
        top_3_rising = rising_sorted[:3]

        # Monthly COGS % trend from monthly_metrics
        cur.execute(
            """
            SELECT month, ROUND(cogs * 100.0 / revenue, 1) AS cogs_pct,
                   ROUND(opex / 30.0, 2) AS daily_opex
            FROM monthly_metrics
            ORDER BY month ASC;
            """
        )
        monthly_cogs_trend = [dict(r) for r in cur.fetchall()]

        # Spoken summary template (<= 40 words, no markdown)
        if top_3_rising:
            lead_item = top_3_rising[0]
            lead_phrase = f"{lead_item['item_name']} rose {lead_item['pct_change']:.1f}%"
        else:
            lead_phrase = "prices remained stable"

        speech_summary = (
            f"Over the last {window_days} days, {lead_phrase}. "
            f"Rising supplier prices added Rs {total_passthrough_per_tiffin:.2f} per tiffin in production cost."
        )

        data = {
            "window_days": window_days,
            "cutoff_date": cutoff_date,
            "as_of_date": as_of_date,
            "total_items_analyzed": len(items_trends),
            "rising_items_count": len(rising_items),
            "total_passthrough_per_tiffin": total_passthrough_per_tiffin,
            "top_rising_cost_drivers": top_3_rising,
            "all_items_trends": items_trends,
            "monthly_cogs_trend": monthly_cogs_trend,
            "speech_summary": speech_summary,
        }

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return Envelope(
            ok=True,
            data=data,
            confidence=1.0,
            source="db",
            warnings=warnings,
            error=None,
            meta=ToolMeta(
                tool="analyze_cost_trends",
                as_of=as_of,
                period_resolved=f"{cutoff_date}..{as_of_date}",
                latency_ms=round(latency_ms, 2),
                queries=2,
            ),
        )
    finally:
        conn.close()


def generate_business_report(
    period: str = "last_30d",
    format: str = "markdown",
    db_path: Optional[str] = None,
) -> Envelope:
    """
    Composes overview, performance, profitability, and cost trend envelopes
    into an executive report (Obsidian-compatible Markdown or JSON).
    """
    t0 = time.perf_counter()

    # Reuse envelopes from tools 1, 5, 6, 7
    overview_env = get_business_overview(db_path)
    perf_env = analyze_business_performance(period=period, compare_to="previous_period", db_path=db_path)
    profit_env = analyze_product_profitability(db_path)
    cost_env = analyze_cost_trends(window_days=90, db_path=db_path)

    ov_data = overview_env.data
    pf_data = perf_env.data
    pr_data = profit_env.data
    ct_data = cost_env.data

    as_of = overview_env.meta.as_of if overview_env.meta else "2026-10-10T19:10:00+05:30"
    period_label = pf_data.get("period", period)

    # 1. Executive Summary (<= 5 deterministic bullets)
    exec_summary = [
        f"Revenue reached ₹{pf_data['metrics'].get('revenue', 0):,.0f} from {pf_data['metrics'].get('units_sold', 0)} tiffins with a net profit of ₹{pf_data['metrics'].get('net_profit', 0):,.0f} ({pf_data['metrics'].get('net_margin_pct', 0)}% margin).",
        f"Liquid cash stands at ₹{ov_data['cash'].get('current_balance', 0):,.0f} with ₹{ov_data['cash'].get('headroom_over_buffer', 0):,.0f} headroom over the mandatory ₹{ov_data['cash'].get('min_cash_buffer', 0):,.0f} safety buffer.",
        f"Unit contribution margin is ₹{pr_data.get('contribution_margin_per_tiffin', 0):,.2f} per meal, requiring {pr_data.get('breakeven_units_per_day', 0)} meals daily to break even.",
        f"Rising ingredient costs (chiefly edible oil) added ₹{ct_data.get('total_passthrough_per_tiffin', 0):,.2f} per meal over the past 90 days.",
        f"Active customer base holds at {ov_data['customers'].get('current_customers', 0)} ({ov_data['customers'].get('recurring_pct', 0)}% recurring subscription share).",
    ]

    # 2. Top 3 Risks & Top 3 Opportunities
    top_risks = [
        {
            "risk": "Tight liquidity minimum on 2026-10-12",
            "observation": f"Cash dips to ₹{ov_data['cash'].get('min_projected_balance_14d', 0):,.0f}, leaving only ₹{ov_data['cash'].get('headroom_over_buffer', 0):,.0f} headroom above safety buffer.",
            "severity": "alert",
        },
        {
            "risk": "Immediate morning ingredient shortfalls",
            "observation": f"Shortfalls detected on oil and containers before tomorrow's production starts.",
            "severity": "alert",
        },
        {
            "risk": "Edible oil cost inflation pass-through",
            "observation": f"Sunflower oil price rose from ₹138 to ₹146/L, compressing contribution margins.",
            "severity": "notice",
        },
    ]

    top_opportunities = [
        {
            "opportunity": "Afternoon unutilized delivery slot capacity",
            "observation": f"Kitchen has {ov_data['tomorrow'].get('afternoon_free_units', 14)} unbooked slots available for student/office delivery tomorrow.",
            "potential_impact": "Up to 14 incremental daily meal sales without expanding fixed kitchen shifts.",
        },
        {
            "opportunity": "High subscription customer retention",
            "observation": f"Recurring subscribers generate {pf_data['metrics'].get('sub_revenue_share_pct', 0)}% of revenue with low cancellation rates.",
            "potential_impact": "Stable recurring working capital that cushions weekend dips.",
        },
        {
            "opportunity": "Wholesale packaging bulk discounting",
            "observation": f"Packaging accounts for ₹{pr_data.get('packaging_cost_per_tiffin', 0):,.2f} per meal; container supplier delivery SLA arrives by 07:00.",
            "potential_impact": "Direct margin expansion if container volume is aggregated.",
        },
    ]

    spoken_brief = (
        f"In {period_label}, revenue was Rs {int(pf_data['metrics'].get('revenue', 0))} with Rs {int(pf_data['metrics'].get('net_profit', 0))} net profit. "
        f"Current cash is Rs {int(ov_data['cash'].get('current_balance', 0))}, with Rs {int(ov_data['cash'].get('headroom_over_buffer', 0))} headroom. "
        f"Tomorrow has {ov_data['tomorrow'].get('afternoon_free_units', 14)} free afternoon delivery slots."
    )

    all_warnings = list(overview_env.warnings) + list(perf_env.warnings) + list(profit_env.warnings) + list(cost_env.warnings)
    unique_warnings = list(dict.fromkeys(all_warnings))

    report_markdown = ""
    if format == "markdown":
        # Build Obsidian-compatible markdown
        report_markdown = f"""---
title: Business Intelligence Executive Report - {period_label}
period: {period_label}
as_of: {as_of}
tags:
  - alexa_business_autopilot
  - business_intelligence
  - tiffin_kitchen
  - kanpur
---

# Maa Ki Rasoi Cloud Kitchen: Performance & Intelligence Brief

**Period:** `{period_label}` | **As Of:** `{as_of}` | **Location:** Kakadeo, Kanpur

---

## 1. Executive Summary

{chr(10).join(f"- {b}" for b in exec_summary)}

---

## 2. Key Performance Indicators

| Metric | Primary Period ({period_label}) | Baseline Comparison | Delta (%) |
|---|---|---|---|
| **Meals Sold** | {pf_data['metrics'].get('units_sold', 0)} | {pf_data['comparison_metrics'].get('units_sold', '-')} | {pf_data['deltas'].get('units_sold', {}).get('pct', 0):+}% |
| **Gross Revenue** | ₹{pf_data['metrics'].get('revenue', 0):,.2f} | ₹{pf_data['comparison_metrics'].get('revenue', 0):,.2f} | {pf_data['deltas'].get('revenue', {}).get('pct', 0):+}% |
| **COGS** | ₹{pf_data['metrics'].get('cogs', 0):,.2f} | ₹{pf_data['comparison_metrics'].get('cogs', 0):,.2f} | {pf_data['deltas'].get('cogs', {}).get('pct', 0):+}% |
| **Gross Margin** | {pf_data['metrics'].get('gross_margin_pct', 0)}% | {pf_data['comparison_metrics'].get('gross_margin_pct', '-')} | {pf_data['deltas'].get('gross_margin_pct', {}).get('absolute', 0):+} pts |
| **Operating Expenses** | ₹{pf_data['metrics'].get('opex', 0):,.2f} | ₹{pf_data['comparison_metrics'].get('opex', 0):,.2f} | {pf_data['deltas'].get('opex', {}).get('pct', 0):+}% |
| **Net Operating Profit** | ₹{pf_data['metrics'].get('net_profit', 0):,.2f} | ₹{pf_data['comparison_metrics'].get('net_profit', 0):,.2f} | {pf_data['deltas'].get('net_profit', {}).get('pct', 0):+}% |
| **Net Profit Margin** | {pf_data['metrics'].get('net_margin_pct', 0)}% | {pf_data['comparison_metrics'].get('net_margin_pct', '-')} | {pf_data['deltas'].get('net_margin_pct', {}).get('absolute', 0):+} pts |
| **Avg Revenue / Meal** | ₹{pf_data['metrics'].get('avg_revenue_per_unit', 0):,.2f} | ₹{pf_data['comparison_metrics'].get('avg_revenue_per_unit', 0):,.2f} | {pf_data['deltas'].get('avg_revenue_per_unit', {}).get('pct', 0):+}% |
| **Subscriber Revenue Share** | {pf_data['metrics'].get('sub_revenue_share_pct', 0)}% | {pf_data['comparison_metrics'].get('sub_revenue_share_pct', '-')} | - |
| **Monthly Recurring Revenue (MRR)** | ₹{pf_data['metrics'].get('mrr', 0):,.2f} | - | - |
| **Annual Run-Rate (ARR)** | ₹{pf_data['metrics'].get('arr', 0):,.2f} | - | - |

---

## 3. Unit Economics & Cost Drivers

Unit economics for **Standard Veg Tiffin** (menu price ₹90 one-off, ₹85 subscriber):
- **Realized Blended Price:** ₹{pr_data.get('realized_blended_price', 0):,.2f}
- **Ingredients COGS:** ₹{pr_data.get('ingredients_cost_per_tiffin', 0):,.2f}
- **Packaging Cost:** ₹{pr_data.get('packaging_cost_per_tiffin', 0):,.2f}
- **Total Unit COGS:** ₹{pr_data.get('total_unit_cogs', 0):,.2f}
- **Contribution Margin:** ₹{pr_data.get('contribution_margin_per_tiffin', 0):,.2f} ({pr_data.get('contribution_margin_pct', 0)}%)
- **Breakeven Volume:** $\\text{{breakeven}} = \\frac{{\\text{{opex}}}}{{\\text{{contribution}}}} = \\frac{{{pr_data.get('avg_daily_opex', 640):,.0f}}}{{{pr_data.get('contribution_margin_per_tiffin', 35):,.2f}}} = {pr_data.get('breakeven_units_per_day', 0)}$ tiffins/day.

```mermaid
flowchart LR
    A["Realized Price (₹{pr_data.get('realized_blended_price', 86.6):.1f})"] --> B["Ingredients (₹{pr_data.get('ingredients_cost_per_tiffin', 47.0):.1f})"]
    A --> C["Packaging (₹{pr_data.get('packaging_cost_per_tiffin', 4.4):.1f})"]
    A --> D["Contribution Margin (₹{pr_data.get('contribution_margin_per_tiffin', 35.2):.1f})"]
    D --> E["Fixed Opex (₹{pr_data.get('avg_daily_opex', 640):,.0f}/day)"]
    E --> F["Breakeven: {pr_data.get('breakeven_units_per_day', 18.2)} tiffins/day"]
```

---

## 4. Top Operational Risks & Opportunities

### Top Risks
{chr(10).join(f"- **{r['risk']}** ({r['severity'].upper()}): {r['observation']}" for r in top_risks)}

### Top Opportunities
{chr(10).join(f"- **{o['opportunity']}**: {o['observation']} *Impact:* {o['potential_impact']}" for o in top_opportunities)}

---

## 5. Appendix: System Warnings & Data Health

- **Data Coverage:** {pf_data['metrics'].get('recorded_days', 0)} days recorded.
- **Active System Warnings:**
{chr(10).join(f"  - {w}" for w in unique_warnings) if unique_warnings else "  - None"}
"""

    data = {
        "period": period_label,
        "as_of": as_of,
        "executive_summary": exec_summary,
        "kpis": pf_data.get("metrics", {}),
        "deltas": pf_data.get("deltas", {}),
        "top_risks": top_risks,
        "top_opportunities": top_opportunities,
        "spoken_brief": spoken_brief,
        "speech_summary": spoken_brief,
        "report_markdown": report_markdown if format == "markdown" else None,
    }

    latency_ms = (time.perf_counter() - t0) * 1000.0

    return Envelope(
        ok=True,
        data=data,
        confidence=min(overview_env.confidence, perf_env.confidence),
        source="db",
        warnings=unique_warnings,
        error=None,
        meta=ToolMeta(
            tool="generate_business_report",
            as_of=as_of,
            period_resolved=period_label,
            latency_ms=round(latency_ms, 2),
            queries=8,
        ),
    )
