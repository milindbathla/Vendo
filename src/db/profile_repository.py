"""
Adaptive Profile Repository
============================
Persists and retrieves multi-tenant, isolated adaptive business profiles and facts.
Handles fact provenance, status updates, and session isolation.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from src.db.connection import get_connection, initialize_database
from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactStatus,
    FactSource,
)

logger = logging.getLogger(__name__)


class AdaptiveProfileRepository:
    """
    CRUD repository for adaptive business profiles and granular facts.
    Thread-safe and supports both file-backed and in-memory SQLite connections.
    """

    def __init__(
        self,
        db_path: str,
        shared_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        self._db_path = db_path
        self._shared_conn: Optional[sqlite3.Connection] = shared_conn
        if db_path == ":memory:" and self._shared_conn is None:
            self._shared_conn = get_connection(":memory:")
            initialize_database(conn=self._shared_conn)

    def _conn(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        return get_connection(self._db_path)

    def _close(self, conn: sqlite3.Connection) -> None:
        if self._shared_conn is None or conn is not self._shared_conn:
            conn.close()

    def close(self) -> None:
        if self._shared_conn is not None:
            try:
                self._shared_conn.close()
            except Exception:
                pass
            self._shared_conn = None

    def save_profile(self, profile: AdaptiveBusinessProfile) -> None:
        """Upserts a business profile and all its tracked facts atomically."""
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO autopilot_business_profiles (
                    business_id, display_name, category, description,
                    city, state, currency, onboarding_completed, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(business_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    category = excluded.category,
                    description = excluded.description,
                    city = excluded.city,
                    state = excluded.state,
                    currency = excluded.currency,
                    onboarding_completed = excluded.onboarding_completed,
                    updated_at = excluded.updated_at
                """,
                (
                    profile.business_id,
                    profile.display_name,
                    profile.category,
                    profile.description,
                    profile.city,
                    profile.state,
                    profile.currency,
                    1 if profile.onboarding_completed else 0,
                    profile.created_at,
                    profile.updated_at,
                ),
            )

            # Upsert all facts
            for fact in profile.facts.values():
                val_json = json.dumps(fact.value)
                status_str = fact.status.value if isinstance(fact.status, FactStatus) else str(fact.status)
                source_str = fact.source.value if isinstance(fact.source, FactSource) else str(fact.source)
                conn.execute(
                    """
                    INSERT INTO autopilot_business_facts (
                        business_id, fact_key, fact_value_json, value_type,
                        status, source, confidence, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(business_id, fact_key) DO UPDATE SET
                        fact_value_json = excluded.fact_value_json,
                        value_type = excluded.value_type,
                        status = excluded.status,
                        source = excluded.source,
                        confidence = excluded.confidence,
                        notes = excluded.notes,
                        updated_at = excluded.updated_at
                    """,
                    (
                        profile.business_id,
                        fact.key,
                        val_json,
                        fact.value_type,
                        status_str,
                        source_str,
                        fact.confidence,
                        fact.encode_notes_with_history(),  # embeds correction_log in notes
                        fact.updated_at,
                    ),
                )

            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def get_profile(self, business_id: str) -> Optional[AdaptiveBusinessProfile]:
        """Loads a business profile and all its facts by unique business_id."""
        conn = self._conn()
        try:
            try:
                row = conn.execute(
                    "SELECT * FROM autopilot_business_profiles WHERE business_id = ?",
                    (business_id,),
                ).fetchone()
            except sqlite3.OperationalError as e:
                logger.debug(f"Table autopilot_business_profiles not found: {e}")
                return None

            if not row:
                return None

            try:
                facts_rows = conn.execute(
                    "SELECT * FROM autopilot_business_facts WHERE business_id = ?",
                    (business_id,),
                ).fetchall()
            except sqlite3.OperationalError as e:
                logger.debug(f"Table autopilot_business_facts not found: {e}")
                facts_rows = []

            facts: Dict[str, BusinessFact] = {}
            for f_row in facts_rows:
                try:
                    val = json.loads(f_row["fact_value_json"])
                except Exception:
                    val = f_row["fact_value_json"]

                fact = BusinessFact(
                    key=f_row["fact_key"],
                    value=val,
                    value_type=f_row["value_type"],
                    status=FactStatus(f_row["status"]),
                    source=FactSource(f_row["source"]),
                    confidence=float(f_row["confidence"]),
                    notes=f_row["notes"],
                    updated_at=f_row["updated_at"],
                )
                facts[fact.key] = fact

            return AdaptiveBusinessProfile(
                business_id=row["business_id"],
                display_name=row["display_name"],
                category=row["category"],
                description=row["description"],
                city=row["city"],
                state=row["state"],
                currency=row["currency"],
                onboarding_completed=bool(row["onboarding_completed"]),
                facts=facts,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        finally:
            self._close(conn)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """Returns metadata summaries of all registered business profiles."""
        conn = self._conn()
        try:
            try:
                rows = conn.execute(
                    """
                    SELECT p.*, count(f.id) as facts_count
                    FROM autopilot_business_profiles p
                    LEFT JOIN autopilot_business_facts f ON p.business_id = f.business_id
                    GROUP BY p.business_id
                    ORDER BY p.updated_at DESC
                    """
                ).fetchall()
            except sqlite3.OperationalError as e:
                logger.debug(f"Table autopilot_business_profiles not found: {e}")
                return []

            return [
                {
                    "business_id": r["business_id"],
                    "display_name": r["display_name"],
                    "category": r["category"],
                    "description": r["description"],
                    "city": r["city"],
                    "onboarding_completed": bool(r["onboarding_completed"]),
                    "facts_count": r["facts_count"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]
        finally:
            self._close(conn)

    def delete_profile(self, business_id: str) -> bool:
        """Deletes a business profile and its cascading facts."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM autopilot_business_profiles WHERE business_id = ?",
                (business_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            self._close(conn)

    def set_fact(self, business_id: str, fact: BusinessFact) -> None:
        """Upserts a single business fact for an existing profile."""
        conn = self._conn()
        try:
            val_json = json.dumps(fact.value)
            status_str = fact.status.value if isinstance(fact.status, FactStatus) else str(fact.status)
            source_str = fact.source.value if isinstance(fact.source, FactSource) else str(fact.source)
            conn.execute(
                """
                INSERT INTO autopilot_business_facts (
                    business_id, fact_key, fact_value_json, value_type,
                    status, source, confidence, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(business_id, fact_key) DO UPDATE SET
                    fact_value_json = excluded.fact_value_json,
                    value_type = excluded.value_type,
                    status = excluded.status,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    business_id,
                    fact.key,
                    val_json,
                    fact.value_type,
                    status_str,
                    source_str,
                    fact.confidence,
                    fact.notes,
                    fact.updated_at,
                ),
            )
            conn.execute(
                "UPDATE autopilot_business_profiles SET updated_at = ? WHERE business_id = ?",
                (fact.updated_at, business_id),
            )
            conn.commit()
        finally:
            self._close(conn)

    def delete_fact(self, business_id: str, fact_key: str) -> bool:
        """Removes a specific fact for a business."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM autopilot_business_facts WHERE business_id = ? AND fact_key = ?",
                (business_id, fact_key),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            self._close(conn)
