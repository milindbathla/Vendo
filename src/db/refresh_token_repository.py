"""
SQLite Persistence Repository for OAuth 2.1 Refresh Tokens
===========================================================
Supports token rotation, family-based replay attack detection, durable revocation,
and client/tenant binding. Raw tokens are never persisted — only SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.db.connection import DEFAULT_DB_PATH, get_connection, is_canonical_demo_db

logger = logging.getLogger(__name__)

_REFRESH_TOKENS_DDL = """
CREATE TABLE IF NOT EXISTS autopilot_oauth_refresh_tokens (
    token_hash          TEXT PRIMARY KEY,
    family_id           TEXT NOT NULL,
    client_id           TEXT NOT NULL,
    subject             TEXT NOT NULL,
    business_ids_json   TEXT NOT NULL,
    scopes_json         TEXT NOT NULL,
    resource            TEXT,
    created_at          REAL NOT NULL,
    expires_at          REAL NOT NULL,
    consumed_at         REAL,
    is_revoked          INTEGER NOT NULL DEFAULT 0,
    revocation_reason   TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_family ON autopilot_oauth_refresh_tokens(family_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_subject ON autopilot_oauth_refresh_tokens(subject);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON autopilot_oauth_refresh_tokens(expires_at, is_revoked);
"""

# Default refresh token lifetime: 30 days
REFRESH_TOKEN_TTL_SECONDS = 30 * 86400


@dataclass
class RefreshTokenRecord:
    token_hash: str
    family_id: str
    client_id: str
    subject: str
    business_ids: List[str]
    scopes: List[str]
    resource: Optional[str]
    created_at: float
    expires_at: float
    consumed_at: Optional[float] = None
    is_revoked: bool = False
    revocation_reason: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_valid(self) -> bool:
        return (not self.is_revoked) and (not self.is_expired) and (not self.is_consumed)


class RefreshTokenRepository:
    """Thread-safe SQLite repository for OAuth 2.1 refresh token management."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def _ensure_table(self) -> None:
        if is_canonical_demo_db(self.db_path):
            raise PermissionError(
                "Direct mutation of canonical 'data/demo.db' is strictly forbidden. "
                "Use an isolated disposable database."
            )
        conn = self._get_conn()
        try:
            conn.executescript(_REFRESH_TOKENS_DDL)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Computes one-way SHA-256 hash of a raw refresh token."""
        return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

    def issue_refresh_token(
        self,
        subject: str,
        client_id: str,
        business_ids: List[str],
        scopes: List[str],
        resource: Optional[str] = None,
        family_id: Optional[str] = None,
        ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
    ) -> Tuple[str, RefreshTokenRecord]:
        """
        Generates a cryptographically random refresh token, stores its SHA-256 hash,
        and returns (raw_token, record). Raw token is only returned to caller once.
        """
        raw_token = f"ref_{secrets.token_urlsafe(48)}"
        token_hash = self.hash_token(raw_token)
        now = time.time()
        fam_id = family_id or f"fam_{uuid.uuid4().hex}"

        record = RefreshTokenRecord(
            token_hash=token_hash,
            family_id=fam_id,
            client_id=client_id,
            subject=subject,
            business_ids=list(business_ids),
            scopes=list(scopes),
            resource=resource,
            created_at=now,
            expires_at=now + ttl_seconds,
            consumed_at=None,
            is_revoked=False,
            revocation_reason=None,
        )

        conn = self._get_conn()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO autopilot_oauth_refresh_tokens (
                        token_hash, family_id, client_id, subject,
                        business_ids_json, scopes_json, resource,
                        created_at, expires_at, consumed_at, is_revoked, revocation_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL)
                    """,
                    (
                        record.token_hash,
                        record.family_id,
                        record.client_id,
                        record.subject,
                        json.dumps(record.business_ids),
                        json.dumps(record.scopes),
                        record.resource,
                        record.created_at,
                        record.expires_at,
                    ),
                )
            return raw_token, record
        finally:
            conn.close()

    def get_token_record(self, raw_token: str) -> Optional[RefreshTokenRecord]:
        """Looks up a token record by raw token hash."""
        token_hash = self.hash_token(raw_token)
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """
                SELECT token_hash, family_id, client_id, subject,
                       business_ids_json, scopes_json, resource,
                       created_at, expires_at, consumed_at, is_revoked, revocation_reason
                FROM autopilot_oauth_refresh_tokens
                WHERE token_hash = ?
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return RefreshTokenRecord(
                token_hash=row["token_hash"],
                family_id=row["family_id"],
                client_id=row["client_id"],
                subject=row["subject"],
                business_ids=json.loads(row["business_ids_json"]),
                scopes=json.loads(row["scopes_json"]),
                resource=row["resource"],
                created_at=float(row["created_at"]),
                expires_at=float(row["expires_at"]),
                consumed_at=float(row["consumed_at"]) if row["consumed_at"] is not None else None,
                is_revoked=bool(row["is_revoked"]),
                revocation_reason=row["revocation_reason"],
            )
        finally:
            conn.close()

    def consume_and_rotate_token(
        self,
        raw_token: str,
        client_id: str,
        ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
    ) -> Tuple[str, RefreshTokenRecord, RefreshTokenRecord]:
        """
        Atomically rotates a refresh token:
        1. Checks token validity and client_id binding.
        2. Replay check: if already consumed, revokes the ENTIRE token family.
        3. Marks old token as consumed_at = now.
        4. Issues a new refresh token in the same family preserving resource & business binding.
        Returns: (new_raw_token, new_record, old_record)
        """
        old_record = self.get_token_record(raw_token)
        if not old_record:
            raise KeyError("Invalid refresh token")

        if old_record.client_id != client_id:
            raise ValueError(f"client_id mismatch: token bound to '{old_record.client_id}', request sent '{client_id}'")

        now = time.time()

        # REPLAY ATTACK DETECTION
        if old_record.is_consumed:
            # Replay detected: revoke all tokens in this family immediately
            self.revoke_family(old_record.family_id, reason="replay_attack_detected")
            logger.critical(
                "SECURITY ALERT: Refresh token replay attack detected for family %s, subject %s. Family revoked.",
                old_record.family_id,
                old_record.subject,
            )
            raise ValueError("Refresh token replay detected. All tokens in this family have been revoked.")

        if old_record.is_revoked:
            raise ValueError(f"Refresh token has been revoked: {old_record.revocation_reason or 'revoked'}")

        if old_record.is_expired:
            raise TimeoutError("Refresh token has expired")

        # Atomic rotation
        conn = self._get_conn()
        try:
            with conn:
                # Mark old token consumed atomically
                cur = conn.execute(
                    """
                    UPDATE autopilot_oauth_refresh_tokens
                    SET consumed_at = ?
                    WHERE token_hash = ? AND consumed_at IS NULL
                    """,
                    (now, old_record.token_hash),
                )
                if cur.rowcount == 0:
                    # Race condition: another thread consumed it concurrently
                    self.revoke_family(old_record.family_id, reason="concurrent_rotation_race")
                    raise ValueError("Concurrent refresh token rotation detected. Family revoked.")

                # Issue new token in same family
                new_raw_token = f"ref_{secrets.token_urlsafe(48)}"
                new_token_hash = self.hash_token(new_raw_token)
                new_record = RefreshTokenRecord(
                    token_hash=new_token_hash,
                    family_id=old_record.family_id,
                    client_id=old_record.client_id,
                    subject=old_record.subject,
                    business_ids=old_record.business_ids,
                    scopes=old_record.scopes,
                    resource=old_record.resource,
                    created_at=now,
                    expires_at=now + ttl_seconds,
                    consumed_at=None,
                    is_revoked=False,
                    revocation_reason=None,
                )
                conn.execute(
                    """
                    INSERT INTO autopilot_oauth_refresh_tokens (
                        token_hash, family_id, client_id, subject,
                        business_ids_json, scopes_json, resource,
                        created_at, expires_at, consumed_at, is_revoked, revocation_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL)
                    """,
                    (
                        new_record.token_hash,
                        new_record.family_id,
                        new_record.client_id,
                        new_record.subject,
                        json.dumps(new_record.business_ids),
                        json.dumps(new_record.scopes),
                        new_record.resource,
                        new_record.created_at,
                        new_record.expires_at,
                    ),
                )
            return new_raw_token, new_record, old_record
        finally:
            conn.close()

    def revoke_token(self, raw_token: str, reason: str = "revoked_by_client") -> bool:
        """Revokes a specific refresh token by its hash."""
        token_hash = self.hash_token(raw_token)
        conn = self._get_conn()
        try:
            with conn:
                cur = conn.execute(
                    """
                    UPDATE autopilot_oauth_refresh_tokens
                    SET is_revoked = 1, revocation_reason = ?
                    WHERE token_hash = ?
                    """,
                    (reason, token_hash),
                )
                return cur.rowcount > 0
        finally:
            conn.close()

    def revoke_family(self, family_id: str, reason: str = "family_revocation") -> int:
        """Revokes all tokens belonging to a token family."""
        conn = self._get_conn()
        try:
            with conn:
                cur = conn.execute(
                    """
                    UPDATE autopilot_oauth_refresh_tokens
                    SET is_revoked = 1, revocation_reason = ?
                    WHERE family_id = ?
                    """,
                    (reason, family_id),
                )
                return cur.rowcount
        finally:
            conn.close()

    def revoke_subject_tokens(self, subject: str, reason: str = "subject_revocation") -> int:
        """Revokes all refresh tokens issued to a subject across all families."""
        conn = self._get_conn()
        try:
            with conn:
                cur = conn.execute(
                    """
                    UPDATE autopilot_oauth_refresh_tokens
                    SET is_revoked = 1, revocation_reason = ?
                    WHERE subject = ?
                    """,
                    (reason, subject),
                )
                return cur.rowcount
        finally:
            conn.close()
