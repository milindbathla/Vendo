"""
Inbound Email Persistence Repository
=====================================
Manages persistent storage, deduplication, thread correlation, and retrieval
of normalized inbound emails and attachments for adaptive small businesses.
Thread-safe and supports both file-backed and in-memory SQLite instances.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from src.db.connection import get_connection
from src.models.email import (
    EmailAddress,
    EmailAttachment,
    InboundEmail,
    IngestionStatus,
    normalize_subject,
)

logger = logging.getLogger(__name__)

_EMAIL_DDL = """
CREATE TABLE IF NOT EXISTS autopilot_inbound_emails (
    message_id          TEXT NOT NULL,
    business_id         TEXT NOT NULL,
    sender_email        TEXT NOT NULL,
    sender_name         TEXT,
    to_recipients_json  TEXT NOT NULL,
    cc_recipients_json  TEXT,
    subject             TEXT,
    normalized_subject  TEXT,
    body_text           TEXT,
    body_html           TEXT,
    received_at         TEXT NOT NULL,
    thread_id           TEXT NOT NULL,
    in_reply_to         TEXT,
    references_json     TEXT,
    headers_json        TEXT,
    content_hash        TEXT NOT NULL,
    is_untrusted        INTEGER NOT NULL DEFAULT 1,
    ingestion_status    TEXT NOT NULL,
    error_message       TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (business_id, message_id)
);

CREATE TABLE IF NOT EXISTS autopilot_email_attachments (
    attachment_id       TEXT PRIMARY KEY,
    message_id          TEXT NOT NULL,
    business_id         TEXT NOT NULL,
    filename            TEXT NOT NULL,
    content_type        TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL,
    content_hash        TEXT NOT NULL,
    raw_data_hex        TEXT,
    extracted_text      TEXT,
    is_untrusted        INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (business_id, message_id) REFERENCES autopilot_inbound_emails(business_id, message_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_emails_biz_id ON autopilot_inbound_emails(business_id);
CREATE INDEX IF NOT EXISTS idx_emails_thread_id ON autopilot_inbound_emails(thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_content_hash ON autopilot_inbound_emails(business_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_emails_in_reply_to ON autopilot_inbound_emails(in_reply_to);
"""


class EmailRepository:
    """
    CRUD repository for normalized inbound emails with built-in deduplication
    and conversational thread correlation.
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
            conn.executescript(_EMAIL_DDL)
            conn.commit()
        finally:
            self._close(conn)

    def correlate_thread_id(
        self,
        business_id: str,
        in_reply_to: Optional[str],
        references: List[str],
        normalized_subject: str,
        sender_email: str,
        fallback_id: str,
    ) -> str:
        """
        Determines the appropriate thread_id based on In-Reply-To, References,
        or normalized subject correlation.
        """
        conn = self._conn()
        try:
            # 1. Direct match on In-Reply-To
            if in_reply_to:
                row = conn.execute(
                    "SELECT thread_id FROM autopilot_inbound_emails WHERE business_id = ? AND message_id = ?",
                    (business_id, in_reply_to),
                ).fetchone()
                if row:
                    return str(row["thread_id"])

            # 2. Check References list
            if references:
                placeholders = ",".join("?" for _ in references)
                query = f"""
                    SELECT thread_id FROM autopilot_inbound_emails
                    WHERE business_id = ? AND message_id IN ({placeholders})
                    ORDER BY received_at DESC LIMIT 1
                """
                params = [business_id] + references
                row = conn.execute(query, params).fetchone()
                if row:
                    return str(row["thread_id"])

            # 3. Subject-based correlation if subject is non-trivial (>= 4 chars)
            clean_sub = normalized_subject.strip()
            if len(clean_sub) >= 4:
                row = conn.execute(
                    """
                    SELECT thread_id FROM autopilot_inbound_emails
                    WHERE business_id = ? AND normalized_subject = ?
                    ORDER BY received_at DESC LIMIT 1
                    """,
                    (business_id, clean_sub),
                ).fetchone()
                if row:
                    return str(row["thread_id"])

            return fallback_id
        finally:
            self._close(conn)

    def find_by_content_hash(
        self, business_id: str, content_hash: str
    ) -> Optional[InboundEmail]:
        """Looks up an email by its deterministic content hash within the business context."""
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM autopilot_inbound_emails
                WHERE business_id = ? AND content_hash = ?
                LIMIT 1
                """,
                (business_id, content_hash),
            ).fetchone()
            if not row:
                return None
            return self._row_to_email(conn, row)
        finally:
            self._close(conn)

    def ingest_email(self, email: InboundEmail) -> InboundEmail:
        """
        Durable, idempotent ingestion of an inbound email.
        Detects duplicates by message_id and content_hash.
        Correlates thread_id across existing conversations.
        """
        conn = self._conn()
        try:
            # Check 1: Duplicate by message_id
            existing_by_id = conn.execute(
                "SELECT * FROM autopilot_inbound_emails WHERE business_id = ? AND message_id = ?",
                (email.business_id, email.message_id),
            ).fetchone()
            if existing_by_id:
                logger.info(f"Duplicate email detected by message_id: {email.message_id}")
                dup = self._row_to_email(conn, existing_by_id)
                dup.ingestion_status = IngestionStatus.DUPLICATE
                return dup

            # Check 2: Duplicate by content_hash
            existing_by_hash = conn.execute(
                "SELECT * FROM autopilot_inbound_emails WHERE business_id = ? AND content_hash = ?",
                (email.business_id, email.content_hash),
            ).fetchone()
            if existing_by_hash:
                logger.info(f"Duplicate email detected by content_hash: {email.content_hash}")
                dup = self._row_to_email(conn, existing_by_hash)
                dup.ingestion_status = IngestionStatus.DUPLICATE
                return dup

            # Thread correlation
            correlated_thread = self.correlate_thread_id(
                business_id=email.business_id,
                in_reply_to=email.in_reply_to,
                references=email.references,
                normalized_subject=email.normalized_subject,
                sender_email=email.sender.email,
                fallback_id=email.thread_id or email.message_id,
            )
            email.thread_id = correlated_thread
            email.ingestion_status = IngestionStatus.PARSED

            # Insert email record
            conn.execute(
                """
                INSERT INTO autopilot_inbound_emails (
                    message_id, business_id, sender_email, sender_name,
                    to_recipients_json, cc_recipients_json, subject,
                    normalized_subject, body_text, body_html, received_at,
                    thread_id, in_reply_to, references_json, headers_json,
                    content_hash, is_untrusted, ingestion_status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email.message_id,
                    email.business_id,
                    email.sender.email,
                    email.sender.name,
                    json.dumps([r.to_dict() for r in email.to_recipients]),
                    json.dumps([r.to_dict() for r in email.cc_recipients]),
                    email.subject,
                    email.normalized_subject,
                    email.body_text,
                    email.body_html,
                    email.received_at,
                    email.thread_id,
                    email.in_reply_to,
                    json.dumps(email.references),
                    json.dumps(email.headers),
                    email.content_hash,
                    1 if email.is_untrusted else 0,
                    email.ingestion_status.value,
                    email.error_message,
                ),
            )

            # Insert attachments
            for att in email.attachments:
                raw_hex = att.raw_data.hex() if att.raw_data else None
                conn.execute(
                    """
                    INSERT INTO autopilot_email_attachments (
                        attachment_id, message_id, business_id, filename, content_type,
                        size_bytes, content_hash, raw_data_hex, extracted_text, is_untrusted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        att.attachment_id,
                        email.message_id,
                        email.business_id,
                        att.filename,
                        att.content_type,
                        att.size_bytes,
                        att.content_hash,
                        raw_hex,
                        att.extracted_text,
                        1 if att.is_untrusted else 0,
                    ),
                )

            conn.commit()
            return email
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._close(conn)

    def get_email(self, message_id: str, business_id: Optional[str] = None) -> Optional[InboundEmail]:
        """Retrieves an email and its attachments by message_id."""
        conn = self._conn()
        try:
            if business_id:
                row = conn.execute(
                    "SELECT * FROM autopilot_inbound_emails WHERE message_id = ? AND business_id = ?",
                    (message_id, business_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM autopilot_inbound_emails WHERE message_id = ?",
                    (message_id,),
                ).fetchone()
            if not row:
                return None
            return self._row_to_email(conn, row)
        finally:
            self._close(conn)

    # API convenience aliases
    save_email = ingest_email
    get_by_id = get_email


    def list_emails(
        self,
        business_id: str,
        limit: int = 50,
        thread_id: Optional[str] = None,
    ) -> List[InboundEmail]:
        """Lists emails for a business in reverse chronological order."""
        conn = self._conn()
        try:
            if thread_id:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_inbound_emails
                    WHERE business_id = ? AND thread_id = ?
                    ORDER BY received_at ASC
                    LIMIT ?
                    """,
                    (business_id, thread_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_inbound_emails
                    WHERE business_id = ?
                    ORDER BY received_at DESC
                    LIMIT ?
                    """,
                    (business_id, limit),
                ).fetchall()
            return [self._row_to_email(conn, r) for r in rows]
        finally:
            self._close(conn)

    def get_thread_messages(
        self, thread_id: str, business_id: Optional[str] = None
    ) -> List[InboundEmail]:
        """Returns all messages in a conversational thread in chronological order."""
        conn = self._conn()
        try:
            if business_id:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_inbound_emails
                    WHERE thread_id = ? AND business_id = ?
                    ORDER BY received_at ASC
                    """,
                    (thread_id, business_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM autopilot_inbound_emails
                    WHERE thread_id = ?
                    ORDER BY received_at ASC
                    """,
                    (thread_id,),
                ).fetchall()
            return [self._row_to_email(conn, r) for r in rows]
        finally:
            self._close(conn)

    def count_emails(self, business_id: str) -> int:
        """Counts total ingested emails for a business."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM autopilot_inbound_emails WHERE business_id = ?",
                (business_id,),
            ).fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            self._close(conn)

    def _row_to_email(self, conn: sqlite3.Connection, row: sqlite3.Row) -> InboundEmail:
        message_id = row["message_id"]
        to_recipients = [
            EmailAddress.from_dict(d)
            for d in json.loads(row["to_recipients_json"] or "[]")
        ]
        cc_recipients = [
            EmailAddress.from_dict(d)
            for d in json.loads(row["cc_recipients_json"] or "[]")
        ]
        references = json.loads(row["references_json"] or "[]")
        headers = json.loads(row["headers_json"] or "{}")

        # Load attachments
        att_rows = conn.execute(
            "SELECT * FROM autopilot_email_attachments WHERE business_id = ? AND message_id = ?",
            (row["business_id"], message_id),
        ).fetchall()

        attachments = []
        for ar in att_rows:
            raw_data = None
            if ar["raw_data_hex"]:
                try:
                    raw_data = bytes.fromhex(ar["raw_data_hex"])
                except ValueError:
                    pass

            attachments.append(
                EmailAttachment(
                    attachment_id=ar["attachment_id"],
                    filename=ar["filename"],
                    content_type=ar["content_type"],
                    size_bytes=ar["size_bytes"],
                    content_hash=ar["content_hash"],
                    raw_data=raw_data,
                    extracted_text=ar["extracted_text"],
                    is_untrusted=bool(ar["is_untrusted"]),
                )
            )

        return InboundEmail(
            message_id=message_id,
            business_id=row["business_id"],
            sender=EmailAddress(
                email=row["sender_email"],
                name=row["sender_name"] or "",
            ),
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
            subject=row["subject"] or "",
            normalized_subject=row["normalized_subject"] or "",
            body_text=row["body_text"] or "",
            body_html=row["body_html"],
            received_at=row["received_at"],
            thread_id=row["thread_id"],
            in_reply_to=row["in_reply_to"],
            references=references,
            attachments=attachments,
            headers=headers,
            content_hash=row["content_hash"],
            is_untrusted=bool(row["is_untrusted"]),
            ingestion_status=IngestionStatus(row["ingestion_status"]),
            error_message=row["error_message"],
        )
