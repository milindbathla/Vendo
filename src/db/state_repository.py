"""
Business State Repository
=========================
Reads and writes cash balance and inventory per business_type.

The business_state table is seeded from data/business_profiles.json via
seed_business_state().  After a purchase is executed the caller should
call update_cash_after_purchase() so the stored balance reflects reality.
"""
import logging
import sqlite3
from typing import Any, Dict, Optional

from src.db.connection import get_connection, initialize_database, seed_business_state

logger = logging.getLogger(__name__)


class BusinessStateRepository:
    """
    Thin repository for the business_state table.
    All methods open and close their own connection for file-backed DBs,
    or use a shared connection for :memory: databases.
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
            seed_business_state(conn=self._shared_conn)

    def _conn(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        return get_connection(self._db_path)

    def _close(self, conn: sqlite3.Connection) -> None:
        """Close only if this is not the shared in-memory connection."""
        if self._shared_conn is None or conn is not self._shared_conn:
            conn.close()

    def close(self) -> None:
        """Explicitly closes the shared in-memory connection if one was opened."""
        if self._shared_conn is not None:
            try:
                self._shared_conn.close()
            except Exception:
                pass
            self._shared_conn = None

    def get_state(self, business_type: str) -> Optional[Dict[str, Any]]:
        """
        Returns the current persisted cash/inventory for *business_type*,
        or None if the record has not been seeded yet.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM business_state WHERE business_type = ?",
                (business_type,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            self._close(conn)

    def update_cash_after_purchase(
        self,
        business_type: str,
        amount_deducted: float,
    ) -> Optional[float]:
        """
        Deducts *amount_deducted* from the stored cash_balance atomically.
        Returns the new cash_balance, or None if the business_type row
        does not exist (safe no-op).
        """
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT cash_balance FROM business_state WHERE business_type = ?",
                (business_type,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                logger.warning(
                    "update_cash_after_purchase: business_type '%s' not found", business_type
                )
                return None
            new_balance = row["cash_balance"] - amount_deducted
            conn.execute(
                "UPDATE business_state "
                "SET cash_balance = ?, last_updated = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                "WHERE business_type = ?",
                (new_balance, business_type),
            )
            conn.execute("COMMIT")
            return new_balance
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def update_inventory(
        self,
        business_type: str,
        delta: float,
    ) -> Optional[float]:
        """
        Adds *delta* (positive = restock, negative = consumption) to
        inventory_units atomically.  Returns the new value.
        """
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT inventory_units FROM business_state WHERE business_type = ?",
                (business_type,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return None
            new_inv = row["inventory_units"] + delta
            conn.execute(
                "UPDATE business_state "
                "SET inventory_units = ?, last_updated = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                "WHERE business_type = ?",
                (new_inv, business_type),
            )
            conn.execute("COMMIT")
            return new_inv
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)
