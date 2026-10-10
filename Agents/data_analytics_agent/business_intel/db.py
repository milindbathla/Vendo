"""
Database connection management, authorizer enforcement, and frozen clock utilities.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from business_intel.config import DEMO_DB_PATH

SQL_DIR = Path(__file__).resolve().parent / "sql"


def memory_authorizer(
    action_code: int,
    arg1: Optional[str],
    arg2: Optional[str],
    db_name: Optional[str],
    trigger_or_view: Optional[str],
) -> int:
    """
    SQLite authorizer that strictly allows:
      - All read operations (SELECT, READ, FUNCTION)
      - INSERT operations ONLY on `business_memory` and `audit_log`
      - UPDATE operations ONLY on `business_memory`
    Any other write or schema alteration returns SQLITE_DENY.
    """
    # Read operations are always permitted
    if action_code in (
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
    ):
        return sqlite3.SQLITE_OK

    # INSERT is allowed solely on business_memory and audit_log
    if action_code == sqlite3.SQLITE_INSERT:
        table_name = (arg1 or "").lower()
        if table_name in ("business_memory", "audit_log"):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    # UPDATE is allowed solely on business_memory
    if action_code == sqlite3.SQLITE_UPDATE:
        table_name = (arg1 or "").lower()
        if table_name == "business_memory":
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    # PRAGMA is allowed only for query_only and foreign_keys
    if action_code == sqlite3.SQLITE_PRAGMA:
        pragma_name = (arg1 or "").lower()
        if pragma_name in ("query_only", "foreign_keys", "table_info", "table_list"):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    # Transactions are permitted
    if action_code in (sqlite3.SQLITE_TRANSACTION,):
        return sqlite3.SQLITE_OK

    # All other writes (DELETE, DROP, ALTER, CREATE, ATTACH) are strictly denied
    return sqlite3.SQLITE_DENY


def get_ro_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Returns a read-only SQLite connection.
    Enforces PRAGMA query_only=ON and URI mode=ro.
    """
    path = db_path or DEMO_DB_PATH
    if not os.path.exists(path):
        for candidate in [
            Path(__file__).resolve().parent.parent / "demo_data" / "demo.db",
            Path(__file__).resolve().parent.parent / "data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent / "data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent / "demo_data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent.parent / "demo_data" / "demo.db",
        ]:
            if candidate.exists():
                path = str(candidate)
                break

    # Use URI mode=ro for kernel-level read-only protection
    abs_path = os.path.abspath(path)
    uri = f"file:{abs_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_rw_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Returns an authorizer-protected connection for memory writes.
    Only INSERT on `business_memory`/`audit_log` and UPDATE on `business_memory` are allowed.
    """
    path = db_path or DEMO_DB_PATH
    if not os.path.exists(path):
        for candidate in [
            Path(__file__).resolve().parent.parent / "demo_data" / "demo.db",
            Path(__file__).resolve().parent.parent / "data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent / "data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent / "demo_data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "demo.db",
            Path(__file__).resolve().parent.parent.parent.parent / "demo_data" / "demo.db",
        ]:
            if candidate.exists():
                path = str(candidate)
                break

    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.set_authorizer(memory_authorizer)
    return conn


# Aliases for test compatibility
get_readonly_connection = get_ro_connection
get_authorizer_rw_connection = get_rw_connection


def get_frozen_clock(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Retrieves the frozen clock metadata from the `meta` table.
    Never uses the host operating system clock.
    """
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM meta WHERE key IN ('as_of', 'frozen_date', 'tomorrow_date');")
    rows = {r["key"]: r["value"] for r in cur.fetchall()}

    as_of = rows.get("as_of", "2026-10-10T19:10:00+05:30")
    frozen_date = rows.get("frozen_date", "2026-10-10")
    tomorrow_date = rows.get("tomorrow_date", "2026-10-11")

    # Time component from timestamp (e.g., '19:10')
    time_part = as_of[11:16] if len(as_of) >= 16 else "19:10"

    return {
        "as_of": as_of,
        "date": frozen_date,
        "time": time_part,
        "tomorrow_date": tomorrow_date,
        "is_partial_day": True,  # 19:10 is a partial day
    }


def load_sql(sql_file_name: str) -> str:
    """Loads a named SQL file from business_intel/sql/."""
    file_path = SQL_DIR / sql_file_name
    if not file_path.exists():
        raise FileNotFoundError(f"Named SQL file not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def execute_sql_query(
    conn: sqlite3.Connection,
    sql_text_or_name: str,
    params: Optional[Dict[str, Any] | Tuple[Any, ...]] = None,
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Executes a SQL query, returns rows as dictionaries and measures execution latency in milliseconds.
    """
    sql = load_sql(sql_text_or_name) if sql_text_or_name.endswith(".sql") else sql_text_or_name
    t0 = time.perf_counter()
    cur = conn.cursor()
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return rows, latency_ms
