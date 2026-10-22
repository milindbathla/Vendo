"""
Persistent Conversation Session Repository
==========================================
Durable SQLite persistence for multi-turn conversational sessions,
actor identity binding, and safe proposal reference resolution.
Protects against process restart state-loss and cross-tenant leakage.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional
import uuid

from src.db.connection import get_connection, DEFAULT_DB_PATH
from src.models.session import ConversationSession, ConversationTurn

logger = logging.getLogger(__name__)


class SessionRepositoryError(Exception):
    """Base exception for session repository operations."""


class SessionNotFoundError(SessionRepositoryError):
    """Raised when a requested session does not exist."""


class SessionExpiredError(SessionRepositoryError):
    """Raised when an operation is attempted on an expired session."""


class SessionRevokedError(SessionRepositoryError):
    """Raised when an operation is attempted on a revoked session."""


class SessionAccessDeniedError(SessionRepositoryError):
    """Raised when an identity or tenant mismatch is detected."""


class SessionRepository:
    """
    SQLite-backed repository for persistent conversation sessions.
    Thread-safe and multi-tenant isolated.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._shared_conn = conn
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        return get_connection(self.db_path)

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        if self._shared_conn is None:
            conn.close()

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autopilot_conversation_sessions (
                    session_id                  TEXT PRIMARY KEY,
                    business_id                 TEXT NOT NULL,
                    owner_id                    TEXT NOT NULL,
                    subject                     TEXT NOT NULL,
                    status                      TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at                  REAL NOT NULL,
                    last_activity_at            REAL NOT NULL,
                    expires_at                  REAL NOT NULL,
                    referenced_action_ids_json  TEXT NOT NULL DEFAULT '[]',
                    relevant_task_ids_json      TEXT NOT NULL DEFAULT '[]',
                    context_version             INTEGER NOT NULL DEFAULT 1,
                    turn_history_json           TEXT NOT NULL DEFAULT '[]',
                    metadata_json               TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_biz_owner ON autopilot_conversation_sessions(business_id, owner_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_expires_status ON autopilot_conversation_sessions(expires_at, status);"
            )
            conn.commit()
        finally:
            self._close_conn(conn)

    def create_session(
        self,
        business_id: str,
        owner_id: str,
        subject: Optional[str] = None,
        session_id: Optional[str] = None,
        ttl_seconds: float = 86400.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationSession:
        """Creates a new durable conversation session bound to business_id and owner_id."""
        if not business_id or not business_id.strip():
            raise ValueError("business_id must not be empty")
        if not owner_id or not owner_id.strip():
            raise ValueError("owner_id must not be empty")

        sid = session_id or f"sess_{uuid.uuid4().hex}"
        now = time.time()
        sub = subject or owner_id
        session = ConversationSession(
            session_id=sid,
            business_id=business_id.strip(),
            owner_id=owner_id.strip(),
            subject=sub.strip(),
            status="ACTIVE",
            created_at=now,
            last_activity_at=now,
            expires_at=now + ttl_seconds,
            referenced_action_ids=[],
            relevant_task_ids=[],
            context_version=1,
            turns=[],
            metadata=metadata or {},
        )
        self.save_session(session)
        logger.info("Created persistent session %s for business %s (owner %s)", sid, business_id, owner_id)
        return session

    def get_session(
        self,
        session_id: str,
        business_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        check_expired: bool = True,
    ) -> Optional[ConversationSession]:
        """
        Loads an active session by ID.
        If business_id or owner_id is provided, strictly enforces identity and tenant binding.
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT session_id, business_id, owner_id, subject, status,
                       created_at, last_activity_at, expires_at,
                       referenced_action_ids_json, relevant_task_ids_json,
                       context_version, turn_history_json, metadata_json
                FROM autopilot_conversation_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            data = {
                "session_id": row["session_id"],
                "business_id": row["business_id"],
                "owner_id": row["owner_id"],
                "subject": row["subject"],
                "status": row["status"],
                "created_at": row["created_at"],
                "last_activity_at": row["last_activity_at"],
                "expires_at": row["expires_at"],
                "referenced_action_ids": json.loads(row["referenced_action_ids_json"] or "[]"),
                "relevant_task_ids": json.loads(row["relevant_task_ids_json"] or "[]"),
                "context_version": row["context_version"],
                "turns": json.loads(row["turn_history_json"] or "[]"),
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
            session = ConversationSession.from_dict(data)

            # Check expiration
            now = time.time()
            if check_expired and session.status == "ACTIVE" and now > session.expires_at:
                session.status = "EXPIRED"
                conn.execute(
                    "UPDATE autopilot_conversation_sessions SET status = 'EXPIRED' WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()

            # Enforce tenant and ownership boundaries
            if business_id and session.business_id != business_id:
                raise SessionAccessDeniedError(
                    f"Session '{session_id}' belongs to business '{session.business_id}', not '{business_id}'."
                )
            if owner_id and session.owner_id != owner_id and session.subject != owner_id:
                raise SessionAccessDeniedError(
                    f"Session '{session_id}' belongs to owner '{session.owner_id}', not '{owner_id}'."
                )

            return session
        finally:
            self._close_conn(conn)

    def save_session(self, session: ConversationSession) -> None:
        """Persists or updates the session record in SQLite."""
        conn = self._get_conn()
        try:
            turns_json = json.dumps([t.to_dict() for t in session.turns])
            ref_json = json.dumps(session.referenced_action_ids)
            tasks_json = json.dumps(session.relevant_task_ids)
            meta_json = json.dumps(session.metadata)

            conn.execute(
                """
                INSERT INTO autopilot_conversation_sessions (
                    session_id, business_id, owner_id, subject, status,
                    created_at, last_activity_at, expires_at,
                    referenced_action_ids_json, relevant_task_ids_json,
                    context_version, turn_history_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    last_activity_at = excluded.last_activity_at,
                    expires_at = excluded.expires_at,
                    referenced_action_ids_json = excluded.referenced_action_ids_json,
                    relevant_task_ids_json = excluded.relevant_task_ids_json,
                    context_version = excluded.context_version,
                    turn_history_json = excluded.turn_history_json,
                    metadata_json = excluded.metadata_json
                """,
                (
                    session.session_id,
                    session.business_id,
                    session.owner_id,
                    session.subject,
                    session.status,
                    session.created_at,
                    session.last_activity_at,
                    session.expires_at,
                    ref_json,
                    tasks_json,
                    session.context_version,
                    turns_json,
                    meta_json,
                ),
            )
            conn.commit()
        finally:
            self._close_conn(conn)

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        business_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> ConversationSession:
        """Appends a turn to an active session, verifying authorization and active state."""
        session = self.get_session(session_id, business_id=business_id, owner_id=owner_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        if session.status == "EXPIRED" or session.is_expired:
            raise SessionExpiredError(f"Session '{session_id}' has expired.")
        if session.status == "REVOKED":
            raise SessionRevokedError(f"Session '{session_id}' has been revoked.")

        session.add_turn(role=role, content=content, metadata=metadata)
        self.save_session(session)
        return session

    def update_referenced_actions(
        self,
        session_id: str,
        action_ids: List[str],
        business_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> ConversationSession:
        """Updates the ordered list of referenced action proposals for the session."""
        session = self.get_session(session_id, business_id=business_id, owner_id=owner_id)
        if not session:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        if not session.is_active:
            raise SessionExpiredError(f"Session '{session_id}' is not active (status: {session.status}).")

        session.set_referenced_actions(action_ids)
        self.save_session(session)
        return session

    def expire_session(self, session_id: str) -> bool:
        """Explicitly marks a session as EXPIRED."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "UPDATE autopilot_conversation_sessions SET status = 'EXPIRED' WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            self._close_conn(conn)

    def revoke_session(self, session_id: str) -> bool:
        """Explicitly revokes a session immediately."""
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "UPDATE autopilot_conversation_sessions SET status = 'REVOKED' WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            self._close_conn(conn)

    def cleanup_expired_sessions(self) -> int:
        """Deletes expired and revoked sessions to prevent unbound table growth."""
        now = time.time()
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM autopilot_conversation_sessions WHERE status IN ('EXPIRED', 'REVOKED') OR expires_at < ?",
                (now,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            self._close_conn(conn)

    def list_active_sessions(
        self,
        business_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> List[ConversationSession]:
        """Lists currently active sessions, optionally filtered by business or owner."""
        now = time.time()
        query = "SELECT * FROM autopilot_conversation_sessions WHERE status = 'ACTIVE' AND expires_at > ?"
        params: List[Any] = [now]
        if business_id:
            query += " AND business_id = ?"
            params.append(business_id)
        if owner_id:
            query += " AND (owner_id = ? OR subject = ?)"
            params.extend([owner_id, owner_id])
        query += " ORDER BY last_activity_at DESC"

        conn = self._get_conn()
        try:
            cur = conn.execute(query, params)
            results = []
            for row in cur.fetchall():
                data = {
                    "session_id": row["session_id"],
                    "business_id": row["business_id"],
                    "owner_id": row["owner_id"],
                    "subject": row["subject"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "last_activity_at": row["last_activity_at"],
                    "expires_at": row["expires_at"],
                    "referenced_action_ids": json.loads(row["referenced_action_ids_json"] or "[]"),
                    "relevant_task_ids": json.loads(row["relevant_task_ids_json"] or "[]"),
                    "context_version": row["context_version"],
                    "turns": json.loads(row["turn_history_json"] or "[]"),
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                }
                results.append(ConversationSession.from_dict(data))
            return results
        finally:
            self._close_conn(conn)
