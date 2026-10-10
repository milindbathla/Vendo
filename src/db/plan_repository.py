"""
Purchase Plan Repository
========================
All SQLite read/write operations for the purchase-plan lifecycle.

Concurrency safety
------------------
``execute_plan()`` uses ``BEGIN IMMEDIATE`` to acquire a SQLite write lock
*before* re-reading the plan status.  This prevents two concurrent HTTP
requests from executing the same plan twice – even in a multi-threaded
ASGI server – because SQLite serialises writers at the database level.

The ``busy_timeout`` set in ``get_connection()`` (5 000 ms) ensures that a
second concurrent request waits rather than immediately failing with
"database is locked".

Isolation model
---------------
All mutating helpers operate inside an explicit transaction (``BEGIN`` /
``COMMIT`` / ``ROLLBACK``).  Read-only helpers run in auto-commit mode.
"""
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.db.connection import get_connection, initialize_database

logger = logging.getLogger(__name__)


# ── Re-export lifecycle enums so callers don't import from two places ──────────

class PlanStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED         = "APPROVED"
    EXECUTED         = "EXECUTED"
    REJECTED         = "REJECTED"


# ── Typed result objects (mirrors approval_service dataclasses) ────────────────

@dataclass
class PlanItemRow:
    ingredient_name: str
    display_name: str
    quantity: float
    unit: str
    unit_price: float
    total_price: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ingredient_name": self.ingredient_name,
            "display_name":    self.display_name,
            "quantity":        round(self.quantity, 2),
            "unit":            self.unit,
            "unit_price":      round(self.unit_price, 2),
            "total_price":     round(self.total_price, 2),
        }


@dataclass
class PlanRow:
    plan_id:        str
    supplier_id:    str
    supplier_name:  str
    total_cost:     float
    status:         PlanStatus
    explanation:    str
    created_at:     float
    confirmed_at:   Optional[float]
    executed_at:    Optional[float]
    owner_decision: Optional[str]
    items:          List[PlanItemRow] = field(default_factory=list)
    execution_receipt: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id":           self.plan_id,
            "supplier_id":       self.supplier_id,
            "supplier_name":     self.supplier_name,
            "total_cost":        round(self.total_cost, 2),
            "status":            self.status.value,
            "explanation":       self.explanation,
            "created_at":        self.created_at,
            "confirmed_at":      self.confirmed_at,
            "executed_at":       self.executed_at,
            "owner_decision":    self.owner_decision,
            "items":             [it.to_dict() for it in self.items],
            "execution_receipt": self.execution_receipt,
        }


# ── Repository ─────────────────────────────────────────────────────────────────

class PlanRepository:
    """
    Stateless repository – every method opens and closes its own connection
    or uses the supplied one.  The db_path is fixed at construction time.
    """

    def __init__(
        self,
        db_path: str,
        shared_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        self._db_path = db_path
        # For :memory: databases every sqlite3.connect() call creates a
        # *different* blank database.  Keep one shared connection alive for
        # the lifetime of this repository so all operations see the same data.
        # For file-backed databases we open/close per operation for thread safety.
        self._shared_conn: Optional[sqlite3.Connection] = shared_conn
        if db_path == ":memory:" and self._shared_conn is None:
            self._shared_conn = get_connection(":memory:")
            initialize_database(conn=self._shared_conn)

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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_items(self, conn: sqlite3.Connection, plan_id: str) -> List[PlanItemRow]:
        rows = conn.execute(
            "SELECT ingredient_name, display_name, quantity, unit, unit_price, total_price "
            "FROM plan_items WHERE plan_id = ? ORDER BY id",
            (plan_id,),
        ).fetchall()
        return [
            PlanItemRow(
                ingredient_name=r["ingredient_name"],
                display_name=r["display_name"],
                quantity=r["quantity"],
                unit=r["unit"],
                unit_price=r["unit_price"],
                total_price=r["total_price"],
            )
            for r in rows
        ]

    def _load_receipt(
        self, conn: sqlite3.Connection, plan_id: str
    ) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            "SELECT * FROM execution_receipts WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def _row_to_plan(
        self, conn: sqlite3.Connection, row: sqlite3.Row
    ) -> PlanRow:
        items   = self._load_items(conn, row["plan_id"])
        receipt = self._load_receipt(conn, row["plan_id"])
        return PlanRow(
            plan_id=row["plan_id"],
            supplier_id=row["supplier_id"],
            supplier_name=row["supplier_name"],
            total_cost=row["total_cost"],
            status=PlanStatus(row["status"]),
            explanation=row["explanation"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
            executed_at=row["executed_at"],
            owner_decision=row["owner_decision"],
            items=items,
            execution_receipt=receipt,
        )

    def _audit(
        self,
        conn: sqlite3.Connection,
        plan_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO audit_events (plan_id, event_type, event_data) VALUES (?, ?, ?)",
            (plan_id, event_type, json.dumps(data)),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def create_plan(
        self,
        supplier_id: str,
        supplier_name: str,
        items: List[Dict[str, Any]],
        total_cost: float,
        explanation: str,
        plan_id: Optional[str] = None,
    ) -> PlanRow:
        """Inserts a new plan in PENDING_APPROVAL status atomically."""
        pid = plan_id or f"PLAN-{uuid.uuid4().hex[:8].upper()}"
        now = time.time()

        conn = self._conn()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO purchase_plans
                    (plan_id, supplier_id, supplier_name, total_cost, status,
                     explanation, created_at)
                VALUES (?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?)
                """,
                (pid, supplier_id, supplier_name, total_cost, explanation, now),
            )
            for it in items:
                conn.execute(
                    """
                    INSERT INTO plan_items
                        (plan_id, ingredient_name, display_name,
                         quantity, unit, unit_price, total_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        it["ingredient_name"],
                        it.get("display_name", it["ingredient_name"].replace("_", " ").title()),
                        float(it["quantity"]),
                        it.get("unit", "units"),
                        float(it["unit_price"]),
                        float(it["total_price"]),
                    ),
                )
            self._audit(conn, pid, "CREATED", {"total_cost": total_cost, "supplier_id": supplier_id})
            conn.execute("COMMIT")
            return self.get_plan(pid)
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def get_plan(self, plan_id: str) -> PlanRow:
        """Returns the plan or raises KeyError if not found."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM purchase_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            if row is None:
                raise KeyError(plan_id)
            return self._row_to_plan(conn, row)
        finally:
            self._close(conn)

    def list_plans(self) -> List[PlanRow]:
        """Returns all plans ordered by creation time."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM purchase_plans ORDER BY created_at DESC"
            ).fetchall()
            return [self._row_to_plan(conn, r) for r in rows]
        finally:
            self._close(conn)

    def confirm_plan(self, plan_id: str, decision: str) -> PlanRow:
        """
        Transitions PENDING_APPROVAL → APPROVED or REJECTED.
        Raises KeyError for unknown plans, ValueError for bad decision strings,
        and RuntimeError for illegal state transitions.
        """
        clean = decision.strip().upper()
        if clean not in ("APPROVE", "APPROVED", "REJECT", "REJECTED"):
            raise ValueError(f"Invalid decision '{decision}'. Must be 'APPROVE' or 'REJECT'.")

        new_status    = PlanStatus.APPROVED if clean in ("APPROVE", "APPROVED") else PlanStatus.REJECTED
        owner_decision = "APPROVED" if new_status == PlanStatus.APPROVED else "REJECTED"
        now = time.time()

        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM purchase_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise KeyError(plan_id)
            if row["status"] != PlanStatus.PENDING_APPROVAL.value:
                conn.execute("ROLLBACK")
                raise RuntimeError(
                    f"Cannot confirm plan '{plan_id}' with status '{row['status']}'. "
                    f"Only PENDING_APPROVAL plans can be confirmed."
                )
            conn.execute(
                "UPDATE purchase_plans SET status=?, owner_decision=?, confirmed_at=? WHERE plan_id=?",
                (new_status.value, owner_decision, now, plan_id),
            )
            self._audit(conn, plan_id, owner_decision, {"decision": owner_decision})
            conn.execute("COMMIT")
            return self.get_plan(plan_id)
        except (KeyError, RuntimeError, ValueError):
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            self._close(conn)

    def execute_plan(
        self,
        plan_id: str,
        current_cash: float,
        safety_reserve: float = 2000.0,
        business_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a purchase ONLY if:
        - Plan status is APPROVED (re-checked inside the write transaction)
        - current_cash − safety_reserve ≥ total_cost

        Uses BEGIN IMMEDIATE to serialise concurrent execution attempts at the
        SQLite level; the status is re-read *inside* the lock so a second
        concurrent request that arrives after the first commits will see
        status=EXECUTED and raise RuntimeError.

        Raises:
            KeyError            – unknown plan_id
            RuntimeError        – plan not in APPROVED status
            InsufficientFunds   – cash check fails (local sentinel; callers
                                  catch by message pattern or re-raise as their
                                  own exception type)
        """
        usable = max(0.0, current_cash - safety_reserve)
        now    = time.time()

        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT * FROM purchase_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise KeyError(plan_id)

            if row["status"] != PlanStatus.APPROVED.value:
                conn.execute("ROLLBACK")
                raise RuntimeError(
                    f"Cannot execute plan '{plan_id}' with status '{row['status']}'. "
                    f"Plan must be explicitly APPROVED before execution."
                )

            total_cost = row["total_cost"]
            if total_cost > usable:
                conn.execute("ROLLBACK")
                raise _InsufficientFundsError(
                    f"Cannot execute purchase of Rs.{total_cost:,.2f}. "
                    f"Available usable cash is Rs.{usable:,.2f} "
                    f"(Total Cash: Rs.{current_cash:,.2f}, "
                    f"Safety Reserve: Rs.{safety_reserve:,.2f})."
                )

            # Transition to EXECUTED
            conn.execute(
                "UPDATE purchase_plans SET status='EXECUTED', executed_at=? WHERE plan_id=?",
                (now, plan_id),
            )

            order_id   = f"SIM-ORD-{uuid.uuid4().hex[:6].upper()}"
            cash_after = current_cash - total_cost
            items_count = conn.execute(
                "SELECT COUNT(*) FROM plan_items WHERE plan_id=?", (plan_id,)
            ).fetchone()[0]

            receipt = {
                "order_id":                order_id,
                "plan_id":                 plan_id,
                "supplier_id":             row["supplier_id"],
                "supplier_name":           row["supplier_name"],
                "status":                  "SIMULATED_ORDER_PLACED",
                "items_count":             items_count,
                "amount_paid":             round(total_cost, 2),
                "cash_before":             round(current_cash, 2),
                "cash_after":              round(cash_after, 2),
                "safety_reserve_preserved": safety_reserve,
                "estimated_delivery":      "Within 24 hours (simulated lead time)",
                "disclaimer":              "Deterministic simulation. No real money or purchase executed.",
            }

            conn.execute(
                """
                INSERT OR REPLACE INTO execution_receipts
                    (plan_id, order_id, supplier_id, supplier_name,
                     items_count, amount_paid, cash_before, cash_after,
                     safety_reserve, status, estimated_delivery, disclaimer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    order_id,
                    row["supplier_id"],
                    row["supplier_name"],
                    items_count,
                    round(total_cost, 2),
                    round(current_cash, 2),
                    round(cash_after, 2),
                    safety_reserve,
                    "SIMULATED_ORDER_PLACED",
                    "Within 24 hours (simulated lead time)",
                    "Deterministic simulation. No real money or purchase executed.",
                ),
            )
            # Atomically update business_state in the exact same transaction if business_type is provided
            if business_type:
                conn.execute(
                    """
                    UPDATE business_state
                    SET cash_balance = cash_balance - ?,
                        last_updated = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                    WHERE business_type = ?
                    """,
                    (total_cost, business_type),
                )
            self._audit(conn, plan_id, "EXECUTED", receipt)
            conn.execute("COMMIT")
            return receipt
        except (KeyError, RuntimeError, _InsufficientFundsError):
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            self._close(conn)


class _InsufficientFundsError(RuntimeError):
    """Internal sentinel used by PlanRepository.execute_plan."""
    pass
