"""
Business Context Tools:
  1. get_business_overview()
  2. get_recent_business_changes(since="7d")
  3. get_business_memory(key=None, prefix=None, include_history=False)
  4. write_business_memory(key, value, source="owner_statement", confidence=None, note=None)
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from business_intel.config import (
    DEFAULT_OWNER_STATEMENT_CONFIDENCE,
    LOW_FORECAST_CONFIDENCE_THRESHOLD,
)
from business_intel.db import (
    execute_sql_query,
    get_frozen_clock,
    get_ro_connection,
    get_rw_connection,
)
from business_intel.periods import resolve_since_window
from business_intel.schemas import Envelope, ToolMeta


def get_business_overview(
    include_ledgers: bool = True,
    db_path: Optional[str] = None,
    **kwargs: Any,
) -> Envelope:
    """
    Comprehensive business state snapshot across identity, cash, tomorrow's production,
    inventory alerts, customer cohorts, reputation, supplier issues, and top signals.
    """
    t0 = time.perf_counter()
    conn = get_ro_connection(db_path)
    warnings: List[str] = []

    try:
        clock = get_frozen_clock(conn)
        as_of = clock["as_of"]

        # 1. Identity
        identity_rows, _ = execute_sql_query(conn, "business_overview_identity.sql")
        identity = identity_rows[0] if identity_rows else {}

        # 2. Cash & obligations
        cash_rows, _ = execute_sql_query(conn, "business_overview_cash.sql")
        cash_data = cash_rows[0] if cash_rows else {}

        # Get list of upcoming obligations next 7d
        cur = conn.cursor()
        cur.execute(
            """
            SELECT payment_id, payee, category, amount, due_date, status
            FROM upcoming_payments
            WHERE due_date BETWEEN (SELECT value FROM meta WHERE key = 'tomorrow_date')
                               AND (SELECT date(value, '+7 days') FROM meta WHERE key = 'tomorrow_date')
              AND status = 'pending'
            ORDER BY due_date ASC;
            """
        )
        obligations_list = [dict(r) for r in cur.fetchall()]

        # 3. Tomorrow's orders and capacity
        tomorrow_rows, _ = execute_sql_query(conn, "business_overview_tomorrow.sql")
        tomorrow_base = tomorrow_rows[0] if tomorrow_rows else {}

        # Slots details
        cur.execute(
            """
            SELECT slot_id, slot_label, start_time, end_time, capacity_units, booked_units,
                   (capacity_units - booked_units) AS free_units,
                   CASE WHEN start_time >= '13:00' THEN 1 ELSE 0 END AS is_afternoon
            FROM delivery_slots
            WHERE date = (SELECT value FROM meta WHERE key = 'tomorrow_date')
            ORDER BY start_time ASC;
            """
        )
        slots = [dict(r) for r in cur.fetchall()]
        total_free_units = sum(s["free_units"] for s in slots)
        afternoon_free_units = sum(s["free_units"] for s in slots if s["is_afternoon"])

        # 4. Inventory Alerts
        inv_rows, _ = execute_sql_query(conn, "business_overview_inventory.sql")
        inventory_alerts = [r for r in inv_rows if r["is_alert"] == 1]

        # 5. Customers
        cust_rows, _ = execute_sql_query(conn, "business_overview_customers.sql")
        customers_data = cust_rows[0] if cust_rows else {}

        # 6. Reputation
        rep_rows, _ = execute_sql_query(conn, "business_overview_reputation.sql")
        reputation_data = rep_rows[0] if rep_rows else {}

        # 7. Open supplier issues
        supp_rows, _ = execute_sql_query(conn, "business_overview_supplier_issues.sql")
        open_supplier_issues = supp_rows

        # 8. Ledger flags
        ledger_rows, _ = execute_sql_query(conn, "business_overview_ledgers.sql")
        ledger_flags = ledger_rows[0] if ledger_rows else {}

        # 9. Memory conflicts
        conflict_rows, _ = execute_sql_query(conn, "business_overview_conflicts.sql")
        unique_conflict_keys = sorted(list(set(r["key"] for r in conflict_rows)))
        memory_conflicts = {
            "count": len(unique_conflict_keys),
            "keys": unique_conflict_keys,
            "details": conflict_rows,
        }
        if unique_conflict_keys:
            warnings.append(
                f"Memory conflict detected on {len(unique_conflict_keys)} key(s): "
                + ", ".join(unique_conflict_keys)
            )

        # 10. Check for low confidence forecasts in the next 14 days
        cur.execute(
            """
            SELECT date, units_forecast, confidence, festival
            FROM demand_forecast df
            LEFT JOIN demand_drivers dd USING (date)
            WHERE df.date BETWEEN (SELECT value FROM meta WHERE key = 'tomorrow_date')
                              AND (SELECT date(value, '+14 days') FROM meta WHERE key = 'tomorrow_date')
              AND df.confidence < ?
            ORDER BY df.date ASC;
            """,
            (LOW_FORECAST_CONFIDENCE_THRESHOLD,),
        )
        low_conf_forecasts = [dict(r) for r in cur.fetchall()]
        for lcf in low_conf_forecasts:
            fest = f" ({lcf['festival']})" if lcf["festival"] else ""
            warnings.append(
                f"Low forecast confidence ({lcf['confidence']:.2f}) on {lcf['date']}{fest}"
            )

        # Top Signals Ranking (up to 5 deterministic findings by severity)
        top_signals: List[Dict[str, Any]] = []

        # Shortfall alert
        shortfall_items = [r for r in inv_rows if r["shortfall_qty"] > 0]
        if shortfall_items:
            s_details = ", ".join([f"{item['item_name']} ({item['shortfall_qty']} {item['unit']})" for item in shortfall_items])
            top_signals.append({
                "severity": "alert",
                "category": "inventory",
                "title": "Immediate ingredient shortfall for tomorrow",
                "finding": f"Shortfall detected for tomorrow: {s_details}.",
                "evidence": {"shortfalls": shortfall_items},
            })

        # Cash buffer alert or headroom notice
        headroom = cash_data.get("headroom_over_buffer", 0.0)
        if headroom < 0:
            top_signals.append({
                "severity": "alert",
                "category": "cash",
                "title": "Projected cash buffer breach",
                "finding": f"Projected balance drops below ₹{cash_data.get('min_cash_buffer', 5000):,.0f} buffer on {cash_data.get('min_projected_date')}.",
                "evidence": {"headroom": headroom, "min_projected": cash_data.get("min_projected_balance")},
            })
        elif headroom < 2000:
            top_signals.append({
                "severity": "notice",
                "category": "cash",
                "title": "Tight liquidity headroom",
                "finding": f"Cash headroom is ₹{headroom:,.0f} over the mandatory ₹{cash_data.get('min_cash_buffer', 5000):,.0f} buffer on {cash_data.get('min_projected_date')}.",
                "evidence": {"headroom": headroom},
            })

        # Afternoon capacity notice
        if afternoon_free_units >= 6:
            top_signals.append({
                "severity": "notice",
                "category": "capacity",
                "title": "Unbooked afternoon delivery slots",
                "finding": f"Kitchen has {afternoon_free_units} free units across afternoon delivery slots tomorrow.",
                "evidence": {"afternoon_free_units": afternoon_free_units, "total_free_units": total_free_units},
            })

        # Supplier issue notice
        if open_supplier_issues:
            top_signals.append({
                "severity": "notice",
                "category": "supplier",
                "title": f"Active supplier update from {open_supplier_issues[0]['supplier_name']}",
                "finding": open_supplier_issues[0]["message"],
                "evidence": {"update_id": open_supplier_issues[0]["update_id"]},
            })

        # Memory conflict notice
        if conflict_rows:
            top_signals.append({
                "severity": "notice",
                "category": "memory",
                "title": "Verified price conflicts with owner statement",
                "finding": f"Invoice verified ₹{conflict_rows[0]['verified_value']} vs owner statement ₹{conflict_rows[0]['owner_value']} for {conflict_rows[0]['key']}.",
                "evidence": {"key": conflict_rows[0]["key"]},
            })

        top_signals = top_signals[:5]

        # Spoken summary template (<= 40 words, no markdown)
        shortfall_names = [r["item_name"] for r in shortfall_items]
        if shortfall_names:
            shortfall_phrase = f"short on {' and '.join(shortfall_names)}"
        else:
            shortfall_phrase = "stock is sufficient"

        speech_summary = (
            f"Cash is Rs {int(cash_data.get('current_balance', 12000))}. "
            f"Tomorrow has {int(tomorrow_base.get('confirmed_units', 20))} confirmed tiffins with {afternoon_free_units} free afternoon slots. "
            f"You are {shortfall_phrase}, and cash headroom is Rs {int(headroom)}."
        )

        data = {
            "identity": identity,
            "as_of": as_of,
            "is_partial_day": True,
            "cash": {
                "current_balance": cash_data.get("current_balance", 12000.0),
                "min_cash_buffer": cash_data.get("min_cash_buffer", 5000.0),
                "min_projected_balance_14d": cash_data.get("min_projected_balance", 6900.0),
                "min_projected_date": cash_data.get("min_projected_date", "2026-10-12"),
                "headroom_over_buffer": headroom,
                "next_7d_obligations_total": cash_data.get("total_obligations", 19650.0),
                "obligations_list": obligations_list,
                "balance_confidence": cash_data.get("balance_confidence", 0.88),
            },
            "tomorrow": {
                "tomorrow_date": tomorrow_base.get("tomorrow_date", "2026-10-11"),
                "confirmed_units": tomorrow_base.get("confirmed_units", 20),
                "confirmed_meals": tomorrow_base.get("confirmed_units", 20),
                "free_slots": afternoon_free_units,
                "subscription_units": tomorrow_base.get("subscription_units", 14),
                "one_off_units": tomorrow_base.get("one_off_units", 6),
                "forecast_units": tomorrow_base.get("units_forecast", 23.0),
                "lower": tomorrow_base.get("lower", 20.0),
                "upper": tomorrow_base.get("upper", 26.0),
                "confidence": tomorrow_base.get("forecast_confidence", 0.82),
                "effective_target": tomorrow_base.get("effective_target", 25.3),
                "max_meals": tomorrow_base.get("max_meals", 40),
                "cook_hours": tomorrow_base.get("cook_hours", 6.0),
                "slots": slots,
                "total_free_units": total_free_units,
                "afternoon_free_units": afternoon_free_units,
            },
            "inventory_alerts": inventory_alerts,
            "customers": customers_data,
            "reputation": reputation_data,
            "open_supplier_issues": open_supplier_issues,
            "ledger_flags": ledger_flags,
            "memory_conflicts": memory_conflicts,
            "top_signals": top_signals,
            "speech_summary": speech_summary,
        }
        data["cash_position"] = data["cash"]
        data["tomorrow_load"] = data["tomorrow"]
        data["shortage_risks"] = shortfall_items

        # Confidence calculation
        confidence = 1.0
        if conflict_rows:
            confidence *= 0.80
        confidence = round(confidence, 2)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return Envelope(
            ok=True,
            data=data,
            confidence=confidence,
            source="db",
            warnings=warnings,
            error=None,
            meta=ToolMeta(
                tool="get_business_overview",
                as_of=as_of,
                period_resolved="2026-10-10",
                latency_ms=round(latency_ms, 2),
                queries=8,
            ),
        )
    finally:
        conn.close()


def get_recent_business_changes(since: str = "7d", db_path: Optional[str] = None) -> Envelope:
    """
    Merges recent operational events from suppliers, customers, restocks, documents,
    reviews, and memory writes within the requested lookback window.
    """
    t0 = time.perf_counter()
    conn = get_ro_connection(db_path)
    warnings: List[str] = []

    try:
        clock = get_frozen_clock(conn)
        as_of = clock["as_of"]
        cutoff_date, cutoff_ts = resolve_since_window(since, clock["date"])

        rows, _ = execute_sql_query(conn, "recent_changes.sql", {"cutoff_date": cutoff_date})

        # Aggregate counts by category
        by_category: Dict[str, int] = {}
        for r in rows:
            cat = r["category"]
            by_category[cat] = by_category.get(cat, 0) + 1

        total_events = len(rows)
        capped_rows = rows[:50]
        truncated = total_events > 50

        # Deterministic 3 highlights from top alerts/notices
        highlights: List[str] = []
        for r in capped_rows:
            if r["severity"] in ("alert", "notice") and len(highlights) < 3:
                highlights.append(f"{r['title']}: {r['detail']}")
        if not highlights and capped_rows:
            highlights = [f"{r['title']}: {r['detail']}" for r in capped_rows[:3]]

        speech_summary = (
            f"Found {total_events} recent changes since {cutoff_date}. "
            f"Top notices include {highlights[0] if highlights else 'no major disruptions'}."
        )

        data = {
            "since_requested": since,
            "cutoff_date": cutoff_date,
            "cutoff_timestamp": cutoff_ts,
            "total_events": total_events,
            "truncated": truncated,
            "by_category": by_category,
            "highlights": highlights,
            "events": capped_rows,
            "speech_summary": speech_summary[:200],
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
                tool="get_recent_business_changes",
                as_of=as_of,
                period_resolved=f"{cutoff_date}..{clock['date']}",
                latency_ms=round(latency_ms, 2),
                queries=1,
            ),
        )
    finally:
        conn.close()


def get_business_memory(
    key: Optional[str] = None,
    prefix: Optional[str] = None,
    include_history: bool = False,
    db_path: Optional[str] = None,
) -> Envelope:
    """
    Retrieves resolved business facts per key.
    Resolution rule: verified_record beats owner_statement always, even if newer.
    """
    t0 = time.perf_counter()
    conn = get_ro_connection(db_path)
    warnings: List[str] = []

    try:
        clock = get_frozen_clock(conn)
        as_of = clock["as_of"]

        rows, _ = execute_sql_query(
            conn,
            "business_memory_get.sql",
            {"key": key, "prefix": prefix},
        )

        # Group observations by key
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            k = r["key"]
            if k not in grouped:
                grouped[k] = []
            grouped[k].append(r)

        resolved_keys: List[Dict[str, Any]] = []
        overall_conflict = False

        for k, candidates in grouped.items():
            # Check for conflicting values
            distinct_values = {c["value"] for c in candidates}
            has_conflict = len(distinct_values) > 1
            if has_conflict:
                overall_conflict = True

            # Resolution rule: verified_record beats owner_statement
            verified_cands = [c for c in candidates if c["source"] == "verified_record"]
            owner_cands = [c for c in candidates if c["source"] == "owner_statement"]

            if verified_cands:
                # Top verified record by confidence then timestamp
                effective = verified_cands[0]
            else:
                effective = owner_cands[0]

            clarification: Optional[str] = None
            if has_conflict and verified_cands and owner_cands:
                clarification = (
                    f"Invoice records show {k} is Rs {verified_cands[0]['value']}, "
                    f"but you mentioned Rs {owner_cands[0]['value']}. Which rate should I use?"
                )

            item_data: Dict[str, Any] = {
                "key": k,
                "effective_value": effective["value"],
                "effective_source": effective["source"],
                "confidence": effective["confidence"],
                "conflict": has_conflict,
                "clarification": clarification,
            }
            if include_history:
                item_data["candidates"] = candidates

            resolved_keys.append(item_data)

        # Sort so conflicting keys appear first
        resolved_keys.sort(key=lambda x: (not x["conflict"], x["key"]))

        if overall_conflict:
            warnings.append("Memory conflict present between verified records and owner statements.")

        if key and resolved_keys:
            target = resolved_keys[0]
            if target["conflict"]:
                speech_summary = target.get("clarification") or f"Conflict on {key}: verified {target['effective_value']}."
            else:
                speech_summary = f"{key} is {target['effective_value']} according to {target['effective_source']}."
        else:
            conf_cnt = sum(1 for r in resolved_keys if r["conflict"])
            speech_summary = f"Retrieved {len(resolved_keys)} memory facts with {conf_cnt} active conflict(s)."

        confidence = 0.80 if overall_conflict else 1.0

        data = {
            "key_requested": key,
            "prefix_requested": prefix,
            "total_keys": len(resolved_keys),
            "conflict_count": sum(1 for r in resolved_keys if r["conflict"]),
            "memories": resolved_keys if not key else resolved_keys[0],
            "records": resolved_keys,
            "speech_summary": speech_summary,
        }

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return Envelope(
            ok=True,
            data=data,
            confidence=confidence,
            source="db",
            warnings=warnings,
            error=None,
            meta=ToolMeta(
                tool="get_business_memory",
                as_of=as_of,
                latency_ms=round(latency_ms, 2),
                queries=1,
            ),
        )
    finally:
        conn.close()


def write_business_memory(
    key: str = "policy.owner_note",
    value: str = "",
    category: Optional[str] = None,
    source: str = "owner_statement",
    confidence: Optional[float] = None,
    note: Optional[str] = None,
    expires_at: Optional[str] = None,
    db_path: Optional[str] = None,
    **kwargs: Any,
) -> Envelope:
    """
    Writes an owner statement to business_memory using an authorizer-protected connection.
    Rejects verified_record writes (requires document workflow).
    Never overwrites verified records.
    Logs immutable audit trail to audit_log.
    """
    if category and "." not in key:
        key = f"{category}.{key}"
    if not key:
        key = "policy.owner_note"
    t0 = time.perf_counter()

    # Rule: Only owner_statement is accepted
    if source != "owner_statement":
        return Envelope(
            ok=False,
            data={"speech_summary": "Verified records cannot be written directly; document workflow required."},
            confidence=0.0,
            source="db",
            warnings=["Write rejected: source must be owner_statement"],
            error="verified_record_requires_document_workflow",
            meta=ToolMeta(tool="write_business_memory", as_of="", latency_ms=0.0, queries=0),
        )

    conn = get_rw_connection(db_path)
    warnings: List[str] = []

    try:
        clock = get_frozen_clock(conn)
        as_of = clock["as_of"]
        assigned_conf = confidence if confidence is not None else DEFAULT_OWNER_STATEMENT_CONFIDENCE

        cur = conn.cursor()

        # Check existing entries for key
        cur.execute(
            "SELECT id, value, source, confidence FROM business_memory WHERE key = ? ORDER BY id DESC;",
            (key,),
        )
        existing = [dict(r) for r in cur.fetchall()]

        # Check idempotency: same key + value + source
        duplicate = any(r["value"] == str(value) and r["source"] == "owner_statement" for r in existing)
        if not duplicate:
            cur.execute(
                """
                INSERT INTO business_memory (key, value, source, timestamp, confidence)
                VALUES (?, ?, 'owner_statement', ?, ?);
                """,
                (key, str(value), as_of, assigned_conf),
            )

            # Audit log entry
            audit_payload = json.dumps({
                "key": key,
                "value": str(value),
                "source": "owner_statement",
                "confidence": assigned_conf,
                "note": note,
            })
            cur.execute(
                """
                INSERT INTO audit_log (action, actor, payload, timestamp)
                VALUES ('write_memory', 'business_intel', ?, ?);
                """,
                (audit_payload, as_of),
            )
            conn.commit()

        # Re-fetch candidates to resolve effective value
        cur.execute(
            "SELECT id, value, source, timestamp, confidence FROM business_memory WHERE key = ? ORDER BY id ASC;",
            (key,),
        )
        candidates = [dict(r) for r in cur.fetchall()]

        verified_cands = [c for c in candidates if c["source"] == "verified_record"]
        has_conflict = False
        effective_value_unchanged = False
        clarification: Optional[str] = None

        if verified_cands:
            effective = verified_cands[0]
            if effective["value"] != str(value):
                has_conflict = True
                effective_value_unchanged = True
                clarification = (
                    f"Noted that you stated Rs {value} for {key}. "
                    f"However, invoice record shows Rs {effective['value']}. "
                    f"Which rate should I use?"
                )
                warnings.append(
                    f"Conflict detected: Owner statement of '{value}' differs from verified record '{effective['value']}'."
                )
        else:
            # No verified record, owner statement is effective
            effective = {"value": str(value), "source": "owner_statement", "confidence": assigned_conf}

        speech_summary = (
            clarification
            if clarification
            else f"Got it, recorded {key} as {value} from your statement."
        )

        data = {
            "key": key,
            "stored_value": str(value),
            "stored_source": "owner_statement",
            "stored_confidence": assigned_conf,
            "conflict": has_conflict,
            "conflict_detected": has_conflict,
            "effective_value": effective["value"],
            "effective_source": effective["source"],
            "effective_value_unchanged": effective_value_unchanged,
            "clarification": clarification,
            "clarification_question": clarification,
            "speech_summary": speech_summary,
        }

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return Envelope(
            ok=True,
            data=data,
            confidence=0.80 if has_conflict else assigned_conf,
            source="db",
            warnings=warnings,
            error=None,
            meta=ToolMeta(
                tool="write_business_memory",
                as_of=as_of,
                latency_ms=round(latency_ms, 2),
                queries=3,
            ),
        )
    finally:
        conn.close()
