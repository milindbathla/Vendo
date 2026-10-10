"""Safe parameterized SQLite database access layer."""

import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple


class Database:
    """Encapsulates safe parameterized database operations against SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for obtaining a database connection."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for atomic database transactions with rollback on error."""
        conn = self.connect()
        try:
            conn.execute("BEGIN TRANSACTION;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Execute a read query with parameters and return list of dicts."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        """Execute a read query with parameters and return first row as dict or None."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def fetch_val(self, query: str, params: Tuple[Any, ...] = ()) -> Any:
        """Execute a read query and return the single scalar value in the first column."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return row[0] if row is not None else None

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> int:
        """Execute a write command with parameters and return rowcount."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount

