"""
Purchase Approval State Machine & Lifecycle Service
===================================================
Enforces strict two-phase approval for all consequential procurement decisions:
1. PENDING_APPROVAL -> Plan generated with cost, items, and trade-offs.
2. APPROVED / REJECTED -> Explicit owner confirmation gate.
3. EXECUTED -> Simulated execution ONLY after approval and fund validation.

Rejects:
- Execution of unconfirmed plans (PENDING_APPROVAL).
- Duplicate approvals or executions.
- Already consumed/rejected plans.
- Operations violating minimum liquid cash reserves.

Persistence
-----------
All plan state is stored in SQLite via PlanRepository.

- db_path=None (default) -> uses ":memory:" SQLite.
  Existing unit tests use this mode and require no changes.
- db_path="<file>" -> persistent on-disk SQLite.
  Used by the web server and MCP server for production state.

The public API (method signatures and exception types) is identical to the
previous in-memory implementation so all existing callers continue to work.
"""
import time
from dataclasses import dataclass, field
from enum import Enum
import sqlite3
from typing import Any, Dict, List, Optional

from src.db.plan_repository import (
    PlanRepository,
    PlanRow,
    PlanItemRow,
    PlanStatus,
    _InsufficientFundsError,
)
from src.db.connection import get_connection, initialize_database


# ── Re-export enum for callers that import from this module ───────────────────
__all__ = [
    "PurchaseApprovalService",
    "PlanStatus",
    "PurchaseApprovalError",
    "PlanNotFoundError",
    "InvalidPlanStateError",
    "InsufficientFundsError",
    "PurchasePlan",
    "PurchasePlanItem",
]


# ── Exception hierarchy (unchanged public API) ────────────────────────────────

class PurchaseApprovalError(Exception):
    """Base exception for purchase approval lifecycle failures."""
    pass


class PlanNotFoundError(PurchaseApprovalError):
    """Raised when the requested plan ID does not exist."""
    pass


class InvalidPlanStateError(PurchaseApprovalError):
    """Raised when attempting an illegal state transition."""
    pass


class InsufficientFundsError(PurchaseApprovalError):
    """Raised when cash balance violates liquidity reserve during execution."""
    pass


# ── Dataclass wrappers that mirror the old interface ─────────────────────────
# These adapt PlanRow / PlanItemRow to the exact shape tests and callers expect.

@dataclass
class PurchasePlanItem:
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
class PurchasePlan:
    """
    Public façade over PlanRow.  Attributes are read-write so tests that do
    ``assert plan.status == PlanStatus.EXECUTED`` after execute_plan() still
    work – the service refreshes the object from SQLite on every mutating call.
    """
    plan_id:        str
    supplier_id:    str
    supplier_name:  str
    items:          List[PurchasePlanItem]
    total_cost:     float
    status:         PlanStatus
    explanation:    str
    created_at:     float = field(default_factory=time.time)
    confirmed_at:   Optional[float] = None
    executed_at:    Optional[float] = None
    owner_decision: Optional[str] = None
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


# ── Converter ─────────────────────────────────────────────────────────────────

def _row_to_plan(row: PlanRow) -> PurchasePlan:
    items = [
        PurchasePlanItem(
            ingredient_name=it.ingredient_name,
            display_name=it.display_name,
            quantity=it.quantity,
            unit=it.unit,
            unit_price=it.unit_price,
            total_price=it.total_price,
        )
        for it in row.items
    ]
    return PurchasePlan(
        plan_id=row.plan_id,
        supplier_id=row.supplier_id,
        supplier_name=row.supplier_name,
        items=items,
        total_cost=row.total_cost,
        status=row.status,
        explanation=row.explanation,
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
        executed_at=row.executed_at,
        owner_decision=row.owner_decision,
        execution_receipt=row.execution_receipt,
    )


# ── Service ───────────────────────────────────────────────────────────────────

class PurchaseApprovalService:
    """
    Manages the SQLite-backed lifecycle of purchase plans.

    Parameters
    ----------
    db_path : str or None
        Path to the SQLite database file.
        Defaults to ``:memory:`` so that unit tests (which call
        ``PurchaseApprovalService()`` with no arguments) continue to work
        unchanged without touching the filesystem.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path: str = db_path or ":memory:"
        self._shared_conn: Optional[sqlite3.Connection] = None
        self._plans: Dict[str, PurchasePlan] = {}
        if self._db_path == ":memory:":
            self._shared_conn = get_connection(":memory:")
            initialize_database(conn=self._shared_conn)
            self._repo = PlanRepository(":memory:", shared_conn=self._shared_conn)
        else:
            initialize_database(self._db_path)
            self._repo = PlanRepository(self._db_path)

    def close(self) -> None:
        """Closes the underlying repository and any shared connection."""
        if hasattr(self, "_repo") and self._repo:
            self._repo.close()
        if self._shared_conn is not None:
            try:
                self._shared_conn.close()
            except Exception:
                pass
            self._shared_conn = None

    # ── Public API ────────────────────────────────────────────────────────────

    def create_plan(
        self,
        supplier_id: str,
        supplier_name: str,
        items: List[Dict[str, Any]],
        total_cost: float,
        explanation: str,
        plan_id: Optional[str] = None,
    ) -> PurchasePlan:
        """Creates a purchase plan in PENDING_APPROVAL status."""
        row = self._repo.create_plan(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            items=items,
            total_cost=total_cost,
            explanation=explanation,
            plan_id=plan_id,
        )
        plan = _row_to_plan(row)
        self._plans[plan.plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> PurchasePlan:
        """Retrieves plan by ID or raises PlanNotFoundError."""
        try:
            row = self._repo.get_plan(plan_id)
            if plan_id in self._plans:
                plan = self._plans[plan_id]
                plan.status = row.status
                plan.confirmed_at = row.confirmed_at
                plan.executed_at = row.executed_at
                plan.owner_decision = row.owner_decision
                plan.execution_receipt = row.execution_receipt
                return plan
            plan = _row_to_plan(row)
            self._plans[plan_id] = plan
            return plan
        except KeyError:
            raise PlanNotFoundError(f"Purchase plan '{plan_id}' does not exist.")

    def list_plans(self) -> List[PurchasePlan]:
        """Returns all managed purchase plans."""
        return [_row_to_plan(r) for r in self._repo.list_plans()]

    def confirm_plan(self, plan_id: str, decision: str) -> PurchasePlan:
        """
        Transitions plan from PENDING_APPROVAL to APPROVED or REJECTED.
        Raises PlanNotFoundError, ValueError, or InvalidPlanStateError.
        """
        try:
            row = self._repo.confirm_plan(plan_id, decision)
            if plan_id in self._plans:
                plan = self._plans[plan_id]
                plan.status = row.status
                plan.confirmed_at = row.confirmed_at
                plan.owner_decision = row.owner_decision
                return plan
            plan = _row_to_plan(row)
            self._plans[plan_id] = plan
            return plan
        except KeyError:
            raise PlanNotFoundError(f"Purchase plan '{plan_id}' does not exist.")
        except RuntimeError as exc:
            raise InvalidPlanStateError(str(exc)) from exc

    def execute_plan(
        self,
        plan_id: str,
        current_cash: float,
        safety_reserve: float = 2000.0,
        business_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a simulated purchase ONLY after explicit approval and
        liquidity check.  Rejects unapproved, already-executed, or
        cash-deficient plans.
        """
        try:
            receipt = self._repo.execute_plan(
                plan_id=plan_id,
                current_cash=current_cash,
                safety_reserve=safety_reserve,
                business_type=business_type,
            )
            if plan_id in self._plans:
                plan = self._plans[plan_id]
                plan.status = PlanStatus.EXECUTED
                plan.executed_at = time.time()
                plan.execution_receipt = receipt
            return receipt
        except KeyError:
            raise PlanNotFoundError(f"Purchase plan '{plan_id}' does not exist.")
        except _InsufficientFundsError as exc:
            raise InsufficientFundsError(str(exc)) from exc
        except RuntimeError as exc:
            raise InvalidPlanStateError(str(exc)) from exc
