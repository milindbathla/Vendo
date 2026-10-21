"""
Encrypted Token Store for per-merchant OAuth refresh tokens.
=============================================================
Stores refresh tokens encrypted at rest using Fernet symmetric
encryption (AES-128-CBC + HMAC-SHA256).

Key management:
  - Set TOKEN_ENCRYPTION_KEY in .env (generate once with token_store.generate_key())
  - If the key is absent the store falls back to base64 encoding with a warning
    (suitable for local dev only — NOT for production).

Usage:
    from src.db.token_store import TokenStore
    store = TokenStore(db_path="data/demo.db")
    store.save_token("zoho_books", "merchant_001", refresh_token)
    token = store.load_token("zoho_books", "merchant_001")
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
from typing import Optional

from src.db.connection import DEFAULT_DB_PATH, is_canonical_demo_db

logger = logging.getLogger(__name__)

_TOKEN_STORE_DDL = """
CREATE TABLE IF NOT EXISTS autopilot_oauth_tokens (
    provider        TEXT    NOT NULL,
    merchant_id     TEXT    NOT NULL DEFAULT 'default',
    token_blob      TEXT    NOT NULL,   -- encrypted (or base64) refresh token
    scopes          TEXT,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (provider, merchant_id)
);
"""


def generate_key() -> str:
    """
    Generates a new Fernet encryption key (URL-safe base64, 32 bytes).
    Run once and store in TOKEN_ENCRYPTION_KEY env var.

    Usage:
        python -c "from src.db.token_store import generate_key; print(generate_key())"
    """
    try:
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode("utf-8")
    except ImportError:
        import secrets
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8")


class TokenStore:
    """
    SQLite-backed encrypted storage for OAuth refresh tokens.

    Encryption behaviour:
    - If TOKEN_ENCRYPTION_KEY is set and cryptography is installed → Fernet AES
    - Otherwise → base64 only (warn in log; fine for local dev)
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        encryption_key: Optional[str] = None,
    ):
        self.db_path = db_path or os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
        self._key = encryption_key or os.environ.get("TOKEN_ENCRYPTION_KEY", "").strip()
        self._fernet = None

        if self._key:
            try:
                from cryptography.fernet import Fernet
                key_bytes = self._key.encode("utf-8") if isinstance(self._key, str) else self._key
                self._fernet = Fernet(key_bytes)
                logger.info("TokenStore: Fernet encryption enabled.")
            except Exception as exc:
                logger.warning("TokenStore: Could not init Fernet (%s). Using base64 fallback.", exc)
        else:
            logger.warning(
                "TokenStore: TOKEN_ENCRYPTION_KEY not set. "
                "Tokens will be base64-encoded only. Set the key for production use."
            )

        env = os.environ.get("AUTOPILOT_ENV", "development").lower()
        if env == "production" and not self._fernet:
            raise RuntimeError(
                "Insecure token storage fallback (base64) is strictly prohibited in production mode. "
                "A valid TOKEN_ENCRYPTION_KEY must be configured."
            )

        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_table(self) -> None:
        if is_canonical_demo_db(self.db_path):
            raise PermissionError(
                "Direct mutation of canonical 'data/demo.db' is strictly forbidden. "
                "Use an isolated disposable database."
            )
        conn = self._get_conn()
        try:
            conn.executescript(_TOKEN_STORE_DDL)
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Encrypt / Decrypt helpers
    # -------------------------------------------------------------------------

    def _encrypt(self, plaintext: str) -> str:
        if self._fernet:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        if os.environ.get("AUTOPILOT_ENV", "development").lower() == "production":
            raise RuntimeError("Insecure base64 token storage is forbidden in production.")
        # Fallback: base64 with a marker so we know it's not encrypted
        return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("utf-8")

    def _decrypt(self, blob: str) -> str:
        if blob.startswith("b64:"):
            return base64.b64decode(blob[4:]).decode("utf-8")
        if self._fernet:
            return self._fernet.decrypt(blob.encode("utf-8")).decode("utf-8")
        raise ValueError(
            "Token appears to be Fernet-encrypted but TOKEN_ENCRYPTION_KEY is not set. "
            "Cannot decrypt."
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def save_token(
        self,
        provider: str,
        merchant_id: str = "default",
        refresh_token: str = "",
        scopes: Optional[str] = None,
    ) -> None:
        """Encrypts and persists a refresh token for a merchant+provider pair."""
        blob = self._encrypt(refresh_token)
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO autopilot_oauth_tokens
                    (provider, merchant_id, token_blob, scopes, updated_at)
                VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                ON CONFLICT(provider, merchant_id) DO UPDATE SET
                    token_blob = excluded.token_blob,
                    scopes     = COALESCE(excluded.scopes, autopilot_oauth_tokens.scopes),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                """,
                (provider, merchant_id, blob, scopes),
            )
            conn.commit()
            logger.info("TokenStore: saved token for provider=%s merchant=%s", provider, merchant_id)
        finally:
            conn.close()

    def load_token(self, provider: str, merchant_id: str = "default") -> Optional[str]:
        """Retrieves and decrypts the refresh token for a merchant+provider pair."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT token_blob FROM autopilot_oauth_tokens WHERE provider=? AND merchant_id=?",
                (provider, merchant_id),
            ).fetchone()
            if not row:
                return None
            return self._decrypt(row["token_blob"])
        finally:
            conn.close()

    def delete_token(self, provider: str, merchant_id: str = "default") -> None:
        """Removes a stored token (e.g. on merchant disconnect)."""
        conn = self._get_conn()
        try:
            conn.execute(
                "DELETE FROM autopilot_oauth_tokens WHERE provider=? AND merchant_id=?",
                (provider, merchant_id),
            )
            conn.commit()
        finally:
            conn.close()

    def token_exists(self, provider: str, merchant_id: str = "default") -> bool:
        """Returns True if a token is stored for the given pair."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM autopilot_oauth_tokens WHERE provider=? AND merchant_id=?",
                (provider, merchant_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def list_connections(self, merchant_id: str = "default") -> list:
        """Lists all provider connections for a merchant (no token values returned)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT provider, merchant_id, scopes, created_at, updated_at "
                "FROM autopilot_oauth_tokens WHERE merchant_id=?",
                (merchant_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
