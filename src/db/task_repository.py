"""
Durable Task and Action Persistence Repository
===============================================
Manages stateful operational tasks, structured action proposals, immutable
payload verification, append-only audit trails, and multi-tenant isolation.
Supports both file-backed and in-memory SQLite instances.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.db.connection import get_connection
from src.models.task import (
    ActionProposal,
    OperationalTask,
    TaskState,
    compute_payload_hash,
)

if TYPE_CHECKING:
    # Only needed for type hints; imported at runtime inside methods to avoid circular import.
    from src.decision.policy_engine import PermissionEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TaskRepositoryError(Exception):
    """Base exception for task repository operations."""


class TaskNotFoundError(TaskRepositoryError):
    """Raised when a task cannot be found within the specified tenant context."""


class ActionNotFoundError(TaskRepositoryError):
    """Raised when an action proposal cannot be found."""


class InvalidStateTransitionError(TaskRepositoryError):
    """Raised when an illegal lifecycle state transition is attempted."""


class PayloadTamperedError(TaskRepositoryError):
    """Raised when an execution payload does not match the approved payload hash."""


class UnauthorizedError(TaskRepositoryError):
    """Raised when an actor lacks authorization to approve or execute an action."""


class ConcurrentUpdateError(TaskRepositoryError):
    """Raised when optimistic concurrency check fails on task update."""


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_TASK_DDL = """
CREATE TABLE IF NOT EXISTS autopilot_tasks (
    task_id             TEXT PRIMARY KEY,
    business_id         TEXT NOT NULL,
    inbound_email_id    TEXT,
    thread_id           TEXT,
    title               TEXT NOT NULL,
    description         TEXT,
    task_type           TEXT NOT NULL,
    state               TEXT NOT NULL,
    context_data_json   TEXT,
    version             INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS autopilot_action_proposals (
    action_id           TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL,
    business_id         TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    description         TEXT,
    payload_json        TEXT NOT NULL,
    payload_hash        TEXT NOT NULL,
    requires_approval   INTEGER NOT NULL DEFAULT 1,
    approved_by         TEXT,
    approved_at         TEXT,
    rejection_reason    TEXT,
    execution_status    TEXT NOT NULL DEFAULT 'PROPOSED',
    idempotency_key     TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES autopilot_tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS autopilot_task_audit_log (
    audit_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id             TEXT NOT NULL,
    business_id         TEXT NOT NULL,
    action_id           TEXT,
    actor               TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    details_json        TEXT,
    timestamp           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS autopilot_action_executions (
    execution_id        TEXT PRIMARY KEY,
    action_id           TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    business_id         TEXT NOT NULL,
    idempotency_key     TEXT NOT NULL,
    status              TEXT NOT NULL,
    receipt_id          TEXT,
    provider_name       TEXT NOT NULL,
    output_data_json    TEXT,
    error_message       TEXT,
    reconciliation_notes TEXT,
    reconciled_by       TEXT,
    reconciled_at       TEXT,
    created_at          TEXT NOT NULL,
    completed_at        TEXT,
    FOREIGN KEY (action_id) REFERENCES autopilot_action_proposals(action_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES autopilot_tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_biz_state ON autopilot_tasks(business_id, state);
CREATE INDEX IF NOT EXISTS idx_tasks_email ON autopilot_tasks(business_id, inbound_email_id);
CREATE INDEX IF NOT EXISTS idx_actions_task ON autopilot_action_proposals(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_idem ON autopilot_action_proposals(business_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_audit_task ON autopilot_task_audit_log(task_id);
CREATE INDEX IF NOT EXISTS idx_exec_action ON autopilot_action_executions(action_id);
CREATE INDEX IF NOT EXISTS idx_exec_idem ON autopilot_action_executions(business_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_exec_task ON autopilot_action_executions(task_id);
"""


class TaskRepository:
    """
    Persistence layer for operational tasks, action proposals, and audit records.
    Guarantees strict tenant isolation, immutable action hashing, and safe transitions.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        shared_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        self._db_path = db_path
        self._shared_conn: Optional[sqlite3.Connection] = shared_conn
        if db_path == ":memory:" and self._shared_conn is None:
            self._shared_conn = get_connection(":memory:")
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        return get_connection(self._db_path)

    def _close(self, conn: sqlite3.Connection) -> None:
        if self._shared_conn is None:
            conn.close()

    def _ensure_schema(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(_TASK_DDL)
            conn.commit()
        finally:
            self._close(conn)

    # ── Task Operations ───────────────────────────────────────────────────────

    def create_task(self, task: OperationalTask, actor: str = "system") -> OperationalTask:
        """Persists a new operational task and logs creation in audit history."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO autopilot_tasks (
                    task_id, business_id, inbound_email_id, thread_id,
                    title, description, task_type, state, context_data_json,
                    version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.business_id,
                    task.inbound_email_id,
                    task.thread_id,
                    task.title,
                    task.description,
                    task.task_type,
                    task.state.value if isinstance(task.state, TaskState) else str(task.state),
                    json.dumps(task.context_data),
                    task.version,
                    task.created_at,
                    task.updated_at,
                ),
            )

            # Append audit log
            self._insert_audit(
                conn=conn,
                task_id=task.task_id,
                business_id=task.business_id,
                action_id=None,
                actor=actor,
                event_type="TASK_CREATED",
                details={
                    "state": task.state.value if isinstance(task.state, TaskState) else str(task.state),
                    "task_type": task.task_type,
                    "title": task.title,
                },
            )

            conn.commit()
            return task
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def get_task(self, task_id: str, business_id: Optional[str] = None) -> Optional[OperationalTask]:
        """Retrieves a task by task_id with optional business_id tenant scoping."""
        conn = self._conn()
        try:
            if business_id:
                row = conn.execute(
                    "SELECT * FROM autopilot_tasks WHERE task_id = ? AND business_id = ?",
                    (task_id, business_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM autopilot_tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()

            if not row:
                return None
            return self._row_to_task(conn, row)
        finally:
            self._close(conn)

    def list_tasks(
        self,
        business_id: str,
        state: Optional[TaskState] = None,
        limit: int = 50,
    ) -> List[OperationalTask]:
        """Lists operational tasks for a given business, optionally filtered by state."""
        conn = self._conn()
        try:
            if state:
                state_val = state.value if isinstance(state, TaskState) else str(state)
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_tasks
                    WHERE business_id = ? AND state = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (business_id, state_val, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_tasks
                    WHERE business_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (business_id, limit),
                ).fetchall()
            return [self._row_to_task(conn, r) for r in rows]
        finally:
            self._close(conn)

    def transition_state(
        self,
        task_id: str,
        business_id: str,
        target_state: TaskState,
        actor: str,
        expected_version: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> OperationalTask:
        """
        Executes a validated, thread-safe lifecycle state transition.
        Enforces tenant isolation, transition permissibility, and optimistic locking.
        """
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM autopilot_tasks WHERE task_id = ? AND business_id = ?",
                (task_id, business_id),
            ).fetchone()
            if not row:
                raise TaskNotFoundError(f"Task '{task_id}' not found for business '{business_id}'.")

            current_task = self._row_to_task(conn, row)

            # Optimistic concurrency check
            if expected_version is not None and current_task.version != expected_version:
                raise ConcurrentUpdateError(
                    f"Task '{task_id}' version conflict: expected {expected_version}, found {current_task.version}."
                )

            # Valid transition check
            if not current_task.can_transition_to(target_state):
                raise InvalidStateTransitionError(
                    f"Illegal task transition from {current_task.state.value} to {target_state.value}."
                )

            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            new_version = current_task.version + 1

            conn.execute(
                """
                UPDATE autopilot_tasks
                SET state = ?, version = ?, updated_at = ?
                WHERE task_id = ? AND business_id = ?
                """,
                (target_state.value, new_version, now_str, task_id, business_id),
            )

            # Append audit entry
            self._insert_audit(
                conn=conn,
                task_id=task_id,
                business_id=business_id,
                action_id=None,
                actor=actor,
                event_type="STATE_TRANSITION",
                details={
                    "from_state": current_task.state.value,
                    "to_state": target_state.value,
                    "new_version": new_version,
                    "metadata": details or {},
                },
            )

            conn.commit()
            current_task.state = target_state
            current_task.version = new_version
            current_task.updated_at = now_str
            return current_task
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    # ── Action Proposals Operations ───────────────────────────────────────────

    def propose_action(
        self,
        task_id: str,
        business_id: str,
        proposal: ActionProposal,
        actor: str = "assistant",
    ) -> ActionProposal:
        """
        Records a structured action proposal tied to a task.
        Guarantees deterministic payload hash calculation and audit logging.
        """
        conn = self._conn()
        try:
            # Check task exists
            task_row = conn.execute(
                "SELECT task_id FROM autopilot_tasks WHERE task_id = ? AND business_id = ?",
                (task_id, business_id),
            ).fetchone()
            if not task_row:
                raise TaskNotFoundError(f"Task '{task_id}' not found for business '{business_id}'.")

            proposal.task_id = task_id
            proposal.business_id = business_id
            if not proposal.payload_hash:
                proposal.payload_hash = compute_payload_hash(proposal.payload)

            conn.execute(
                """
                INSERT INTO autopilot_action_proposals (
                    action_id, task_id, business_id, action_type, description,
                    payload_json, payload_hash, requires_approval, approved_by,
                    approved_at, rejection_reason, execution_status,
                    idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.action_id,
                    proposal.task_id,
                    proposal.business_id,
                    proposal.action_type,
                    proposal.description,
                    json.dumps(proposal.payload),
                    proposal.payload_hash,
                    1 if proposal.requires_approval else 0,
                    proposal.approved_by,
                    proposal.approved_at,
                    proposal.rejection_reason,
                    proposal.execution_status,
                    proposal.idempotency_key,
                    proposal.created_at,
                ),
            )

            # Append audit entry
            self._insert_audit(
                conn=conn,
                task_id=task_id,
                business_id=business_id,
                action_id=proposal.action_id,
                actor=actor,
                event_type="ACTION_PROPOSED",
                details={
                    "action_type": proposal.action_type,
                    "payload_hash": proposal.payload_hash,
                    "requires_approval": proposal.requires_approval,
                    "idempotency_key": proposal.idempotency_key,
                },
            )

            conn.commit()
            return proposal
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def get_action(self, action_id: str, business_id: Optional[str] = None) -> Optional[ActionProposal]:
        """Retrieves an action proposal by action_id."""
        conn = self._conn()
        try:
            if business_id:
                row = conn.execute(
                    "SELECT * FROM autopilot_action_proposals WHERE action_id = ? AND business_id = ?",
                    (action_id, business_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM autopilot_action_proposals WHERE action_id = ?",
                    (action_id,),
                ).fetchone()

            if not row:
                return None
            return self._row_to_action(row)
        finally:
            self._close(conn)

    def list_actions_for_task(self, task_id: str, business_id: Optional[str] = None) -> List[ActionProposal]:
        """Lists all action proposals for a given task."""
        conn = self._conn()
        try:
            if business_id:
                rows = conn.execute(
                    "SELECT * FROM autopilot_action_proposals WHERE task_id = ? AND business_id = ?",
                    (task_id, business_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM autopilot_action_proposals WHERE task_id = ?",
                    (task_id,),
                ).fetchall()
            return [self._row_to_action(r) for r in rows]
        finally:
            self._close(conn)

    def approve_action(
        self,
        action_id: str,
        business_id: str,
        actor_id: str,
        execution_payload: Dict[str, Any],
        policy_engine: "Optional[PermissionEngine]" = None,
    ) -> ActionProposal:
        """
        Approves an action proposal.
        Validates:
          1. Tenant isolation (action belongs to business_id).
          2. Actor authorization (actor_id must be authorized owner).
          3. Exact payload integrity (execution_payload must match proposal.payload_hash).
        """
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM autopilot_action_proposals WHERE action_id = ? AND business_id = ?",
                (action_id, business_id),
            ).fetchone()
            if not row:
                raise ActionNotFoundError(f"Action '{action_id}' not found for business '{business_id}'.")

            proposal = self._row_to_action(row)

            # Run policy engine verification if provided
            if policy_engine is not None:
                ver_res = policy_engine.verify_approval(
                    proposal=proposal,
                    execution_payload=execution_payload,
                    actor_id=actor_id,
                    business_id=business_id,
                )
                if not ver_res.is_valid:
                    if "PAYLOAD_HASH_MISMATCH" in ver_res.reason:
                        raise PayloadTamperedError(ver_res.reason)
                    if "UNAUTHORIZED_ACTOR" in ver_res.reason:
                        raise UnauthorizedError(ver_res.reason)
                    raise TaskRepositoryError(ver_res.reason)
            else:
                # Standalone check: exact payload hash verification
                if not proposal.verify_integrity(execution_payload):
                    raise PayloadTamperedError(
                        "Execution payload differs from approved proposal payload hash. Approval rejected."
                    )
                if not actor_id or not (actor_id.startswith("owner:") or actor_id.startswith("admin:")):
                    raise UnauthorizedError(f"Actor '{actor_id}' is not authorized to approve consequential actions.")

            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute(
                """
                UPDATE autopilot_action_proposals
                SET execution_status = 'APPROVED', approved_by = ?, approved_at = ?
                WHERE action_id = ? AND business_id = ?
                """,
                (actor_id, now_str, action_id, business_id),
            )

            # Append audit log
            self._insert_audit(
                conn=conn,
                task_id=proposal.task_id,
                business_id=business_id,
                action_id=action_id,
                actor=actor_id,
                event_type="ACTION_APPROVED",
                details={
                    "approved_by": actor_id,
                    "payload_hash": proposal.payload_hash,
                },
            )

            conn.commit()
            proposal.execution_status = "APPROVED"
            proposal.approved_by = actor_id
            proposal.approved_at = now_str
            return proposal
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def reject_action(
        self,
        action_id: str,
        business_id: str,
        actor_id: str,
        rejection_reason: str,
    ) -> ActionProposal:
        """Rejects an action proposal with documented rationale in the audit trail."""
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM autopilot_action_proposals WHERE action_id = ? AND business_id = ?",
                (action_id, business_id),
            ).fetchone()
            if not row:
                raise ActionNotFoundError(f"Action '{action_id}' not found for business '{business_id}'.")

            proposal = self._row_to_action(row)

            conn.execute(
                """
                UPDATE autopilot_action_proposals
                SET execution_status = 'REJECTED', rejection_reason = ?
                WHERE action_id = ? AND business_id = ?
                """,
                (rejection_reason, action_id, business_id),
            )

            # Append audit log
            self._insert_audit(
                conn=conn,
                task_id=proposal.task_id,
                business_id=business_id,
                action_id=action_id,
                actor=actor_id,
                event_type="ACTION_REJECTED",
                details={
                    "rejection_reason": rejection_reason,
                    "rejected_by": actor_id,
                },
            )

            conn.commit()
            proposal.execution_status = "REJECTED"
            proposal.rejection_reason = rejection_reason
            return proposal
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def mark_execution_uncertain(
        self,
        action_id: str,
        business_id: str,
        task_id: str,
        actor: str,
        reason: str,
    ) -> None:
        """
        Marks an action and its parent task as EXECUTION_UNCERTAIN.
        Used when an external provider returns a timeout or ambiguous result,
        preventing blind retries without reconciliation.
        """
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE autopilot_action_proposals
                SET execution_status = 'UNCERTAIN'
                WHERE action_id = ? AND business_id = ?
                """,
                (action_id, business_id),
            )
            conn.execute(
                """
                UPDATE autopilot_tasks
                SET state = 'EXECUTION_UNCERTAIN', version = version + 1, updated_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                WHERE task_id = ? AND business_id = ?
                """,
                (task_id, business_id),
            )
            self._insert_audit(
                conn=conn,
                task_id=task_id,
                business_id=business_id,
                action_id=action_id,
                actor=actor,
                event_type="EXECUTION_UNCERTAIN",
                details={"reason": reason},
            )
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    # ── Audit Trail ───────────────────────────────────────────────────────────

    def get_audit_trail(self, task_id: str, business_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns the append-only chronological audit trail for a task."""
        conn = self._conn()
        try:
            if business_id:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_task_audit_log
                    WHERE task_id = ? AND business_id = ?
                    ORDER BY audit_id ASC
                    """,
                    (task_id, business_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_task_audit_log
                    WHERE task_id = ?
                    ORDER BY audit_id ASC
                    """,
                    (task_id,),
                ).fetchall()

            audit_records = []
            for r in rows:
                details = json.loads(r["details_json"]) if r["details_json"] else {}
                audit_records.append({
                    "audit_id": r["audit_id"],
                    "task_id": r["task_id"],
                    "business_id": r["business_id"],
                    "action_id": r["action_id"],
                    "actor": r["actor"],
                    "event_type": r["event_type"],
                    "details": details,
                    "timestamp": r["timestamp"],
                })
            return audit_records
        finally:
            self._close(conn)

    # Alias for API consistency
    get_audit_log = get_audit_trail


    def _insert_audit(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        business_id: str,
        action_id: Optional[str],
        actor: str,
        event_type: str,
        details: Dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO autopilot_task_audit_log (
                task_id, business_id, action_id, actor, event_type, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                business_id,
                action_id,
                actor,
                event_type,
                json.dumps(details),
            ),
        )

    def _row_to_task(self, conn: sqlite3.Connection, row: sqlite3.Row) -> OperationalTask:
        context_data = json.loads(row["context_data_json"]) if row["context_data_json"] else {}
        action_rows = conn.execute(
            "SELECT action_id FROM autopilot_action_proposals WHERE task_id = ?",
            (row["task_id"],),
        ).fetchall()
        proposed_actions = [ar["action_id"] for ar in action_rows]

        return OperationalTask(
            task_id=row["task_id"],
            business_id=row["business_id"],
            inbound_email_id=row["inbound_email_id"],
            thread_id=row["thread_id"],
            title=row["title"],
            description=row["description"] or "",
            task_type=row["task_type"],
            state=TaskState(row["state"]),
            context_data=context_data,
            proposed_actions=proposed_actions,
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_action(self, row: sqlite3.Row) -> ActionProposal:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        return ActionProposal(
            action_id=row["action_id"],
            task_id=row["task_id"],
            business_id=row["business_id"],
            action_type=row["action_type"],
            description=row["description"] or "",
            payload=payload,
            payload_hash=row["payload_hash"],
            requires_approval=bool(row["requires_approval"]),
            approved_by=row["approved_by"],
            approved_at=row["approved_at"],
            rejection_reason=row["rejection_reason"],
            execution_status=row["execution_status"],
            idempotency_key=row["idempotency_key"],
            created_at=row["created_at"],
        )

    def list_pending_actions(self, business_id: str) -> List[ActionProposal]:
        """Lists all action proposals for a business that are awaiting owner approval."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM autopilot_action_proposals
                WHERE business_id = ? AND requires_approval = 1 AND execution_status = 'PROPOSED'
                ORDER BY created_at DESC
                """,
                (business_id,),
            ).fetchall()
            return [self._row_to_action(r) for r in rows]
        finally:
            self._close(conn)

    # ── Execution Operations ──────────────────────────────────────────────────

    def record_execution_attempt(
        self,
        execution_id: str,
        action_id: str,
        task_id: str,
        business_id: str,
        idempotency_key: str,
        provider_name: str,
        status: str = "EXECUTING",
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Records a new execution attempt for an action proposal."""
        conn = self._conn()
        try:
            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute(
                """
                INSERT INTO autopilot_action_executions (
                    execution_id, action_id, task_id, business_id,
                    idempotency_key, status, provider_name, output_data_json,
                    error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    action_id,
                    task_id,
                    business_id,
                    idempotency_key,
                    status,
                    provider_name,
                    json.dumps(output_data or {}),
                    error_message,
                    now_str,
                ),
            )
            conn.commit()
            return {
                "execution_id": execution_id,
                "action_id": action_id,
                "task_id": task_id,
                "business_id": business_id,
                "idempotency_key": idempotency_key,
                "status": status,
                "provider_name": provider_name,
                "output_data": output_data or {},
                "error_message": error_message,
                "created_at": now_str,
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def complete_execution(
        self,
        execution_id: str,
        receipt_id: str,
        output_data: Dict[str, Any],
        business_id: str,
    ) -> None:
        """Marks an execution record as COMPLETED with receipt identifier and output payload."""
        conn = self._conn()
        try:
            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute(
                """
                UPDATE autopilot_action_executions
                SET status = 'COMPLETED', receipt_id = ?, output_data_json = ?, completed_at = ?
                WHERE execution_id = ? AND business_id = ?
                """,
                (receipt_id, json.dumps(output_data), now_str, execution_id, business_id),
            )
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def fail_execution(
        self,
        execution_id: str,
        error_message: str,
        business_id: str,
    ) -> None:
        """Marks an execution record as FAILED with error details."""
        conn = self._conn()
        try:
            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute(
                """
                UPDATE autopilot_action_executions
                SET status = 'FAILED', error_message = ?, completed_at = ?
                WHERE execution_id = ? AND business_id = ?
                """,
                (error_message, now_str, execution_id, business_id),
            )
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def mark_execution_uncertain_record(
        self,
        execution_id: str,
        reason: str,
        business_id: str,
    ) -> None:
        """Marks an execution record as EXECUTION_UNCERTAIN."""
        conn = self._conn()
        try:
            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute(
                """
                UPDATE autopilot_action_executions
                SET status = 'EXECUTION_UNCERTAIN', error_message = ?, completed_at = ?
                WHERE execution_id = ? AND business_id = ?
                """,
                (reason, now_str, execution_id, business_id),
            )
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def reconcile_execution_record(
        self,
        execution_id: str,
        resolution: str,
        notes: str,
        actor_id: str,
        business_id: str,
        receipt_id: Optional[str] = None,
    ) -> None:
        """Records explicit manual reconciliation of an uncertain execution."""
        conn = self._conn()
        try:
            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute(
                """
                UPDATE autopilot_action_executions
                SET status = ?, reconciliation_notes = ?, reconciled_by = ?, reconciled_at = ?, receipt_id = COALESCE(?, receipt_id)
                WHERE execution_id = ? AND business_id = ?
                """,
                (resolution, notes, actor_id, now_str, receipt_id, execution_id, business_id),
            )
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def get_execution(self, execution_id: str, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves an execution record by execution_id."""
        conn = self._conn()
        try:
            if business_id:
                row = conn.execute(
                    "SELECT * FROM autopilot_action_executions WHERE execution_id = ? AND business_id = ?",
                    (execution_id, business_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM autopilot_action_executions WHERE execution_id = ?",
                    (execution_id,),
                ).fetchone()
            if not row:
                return None
            return self._row_to_execution(row)
        finally:
            self._close(conn)

    def get_execution_by_action(self, action_id: str, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves the latest execution record for an action."""
        conn = self._conn()
        try:
            if business_id:
                row = conn.execute(
                    """
                    SELECT * FROM autopilot_action_executions
                    WHERE action_id = ? AND business_id = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (action_id, business_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM autopilot_action_executions
                    WHERE action_id = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (action_id,),
                ).fetchone()
            if not row:
                return None
            return self._row_to_execution(row)
        finally:
            self._close(conn)

    def get_execution_by_idempotency_key(self, business_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Retrieves an execution record by business_id and idempotency_key."""
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM autopilot_action_executions
                WHERE business_id = ? AND idempotency_key = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (business_id, idempotency_key),
            ).fetchone()
            if not row:
                return None
            return self._row_to_execution(row)
        finally:
            self._close(conn)

    def list_executions_for_task(self, task_id: str, business_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists execution records for a task."""
        conn = self._conn()
        try:
            if business_id:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_action_executions
                    WHERE task_id = ? AND business_id = ?
                    ORDER BY created_at ASC
                    """,
                    (task_id, business_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_action_executions
                    WHERE task_id = ?
                    ORDER BY created_at ASC
                    """,
                    (task_id,),
                ).fetchall()
            return [self._row_to_execution(r) for r in rows]
        finally:
            self._close(conn)

    def list_executions_for_business(self, business_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists recent execution records for a business."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM autopilot_action_executions
                WHERE business_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (business_id, limit),
            ).fetchall()
            return [self._row_to_execution(r) for r in rows]
        finally:
            self._close(conn)

    def _row_to_execution(self, row: sqlite3.Row) -> Dict[str, Any]:
        output_data = json.loads(row["output_data_json"]) if row["output_data_json"] else {}
        return {
            "execution_id": row["execution_id"],
            "action_id": row["action_id"],
            "task_id": row["task_id"],
            "business_id": row["business_id"],
            "idempotency_key": row["idempotency_key"],
            "status": row["status"],
            "receipt_id": row["receipt_id"],
            "provider_name": row["provider_name"],
            "output_data": output_data,
            "error_message": row["error_message"],
            "reconciliation_notes": row["reconciliation_notes"],
            "reconciled_by": row["reconciled_by"],
            "reconciled_at": row["reconciled_at"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }
