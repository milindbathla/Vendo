"""
Database Connection, Schema Initialisation & Seeding
=====================================================
All persistence in this project uses Python's built-in sqlite3.
No third-party ORM is required.

Design notes
------------
* WAL journal mode – allows concurrent readers while a writer holds a lock,
  which is appropriate for a single-process FastAPI server.
* check_same_thread=False – FastAPI/Starlette dispatches requests on a
  thread pool; SQLite handles serialisation via its own locking.
* Schema versioning – a `schema_migrations` table tracks applied versions.
  initialize_database() is idempotent: safe to call on every startup.
* Seeding – seed_business_state() uses INSERT OR IGNORE so it never
  overwrites live data if the record already exists.
"""
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default paths ──────────────────────────────────────────────────────────────
# Resolved relative to the project root at import time.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH: str = str(_PROJECT_ROOT / "data" / "business_autopilot.sqlite3")
_PROFILES_JSON: Path = _PROJECT_ROOT / "data" / "business_profiles.json"

# Current schema version – bump this integer when DDL changes.
_CURRENT_SCHEMA_VERSION = 1

# ── DDL ────────────────────────────────────────────────────────────────────────
_DDL_V1 = """
-- Schema migration tracker
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Live business state per business_type (cash, inventory)
-- Seeded from data/business_profiles.json; updated when a purchase executes.
CREATE TABLE IF NOT EXISTS business_state (
    business_type   TEXT    PRIMARY KEY,
    display_name    TEXT    NOT NULL,
    cash_balance    REAL    NOT NULL,   -- Rs, floating-point; sufficient for demo scale
    inventory_units REAL    NOT NULL,
    safety_reserve  REAL    NOT NULL DEFAULT 2000.0,
    last_updated    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Purchase plan header – one row per plan
CREATE TABLE IF NOT EXISTS purchase_plans (
    plan_id         TEXT    PRIMARY KEY,
    supplier_id     TEXT    NOT NULL,
    supplier_name   TEXT    NOT NULL,
    total_cost      REAL    NOT NULL CHECK(total_cost >= 0),
    status          TEXT    NOT NULL DEFAULT 'PENDING_APPROVAL'
                            CHECK(status IN ('PENDING_APPROVAL','APPROVED','EXECUTED','REJECTED')),
    explanation     TEXT    NOT NULL,
    created_at      REAL    NOT NULL,   -- Unix epoch (time.time())
    confirmed_at    REAL,
    executed_at     REAL,
    owner_decision  TEXT
);

-- Line items belonging to a plan
CREATE TABLE IF NOT EXISTS plan_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id         TEXT    NOT NULL REFERENCES purchase_plans(plan_id) ON DELETE CASCADE,
    ingredient_name TEXT    NOT NULL,
    display_name    TEXT    NOT NULL,
    quantity        REAL    NOT NULL CHECK(quantity >= 0),
    unit            TEXT    NOT NULL,
    unit_price      REAL    NOT NULL CHECK(unit_price >= 0),
    total_price     REAL    NOT NULL CHECK(total_price >= 0)
);

-- Audit trail – append-only; never UPDATE or DELETE rows here
CREATE TABLE IF NOT EXISTS audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,   -- 'CREATED', 'APPROVED', 'REJECTED', 'EXECUTED', 'EXEC_FAILED'
    event_data  TEXT    NOT NULL,   -- JSON blob
    occurred_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Execution receipt – one row per successfully executed plan
CREATE TABLE IF NOT EXISTS execution_receipts (
    plan_id                 TEXT    PRIMARY KEY REFERENCES purchase_plans(plan_id),
    order_id                TEXT    NOT NULL,
    supplier_id             TEXT    NOT NULL,
    supplier_name           TEXT    NOT NULL,
    items_count             INTEGER NOT NULL,
    amount_paid             REAL    NOT NULL,
    cash_before             REAL    NOT NULL,
    cash_after              REAL    NOT NULL,
    safety_reserve          REAL    NOT NULL,
    status                  TEXT    NOT NULL,
    estimated_delivery      TEXT    NOT NULL,
    disclaimer              TEXT    NOT NULL,
    executed_at             TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_plan_items_plan_id  ON plan_items(plan_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_plan   ON audit_events(plan_id);
"""


# ── Connection factory ─────────────────────────────────────────────────────────

def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Opens (or creates) a SQLite database at *db_path* with:
    - WAL journal mode for concurrent read access (file-backed DBs)
    - Foreign key enforcement
    - Row factory set to sqlite3.Row for dict-like access
    - busy_timeout=5000ms

    The directory is created if it does not exist (for file paths).
    Caller is responsible for closing the connection.
    """
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")   # wait up to 5 s if locked
    return conn


# ── Schema initialisation (idempotent) ────────────────────────────────────────

def initialize_database(
    db_path: str = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
) -> sqlite3.Connection:
    """
    Applies schema DDL and records the current schema version.
    Safe to call on every application startup – all CREATE statements use
    IF NOT EXISTS and the migration insert uses INSERT OR IGNORE.
    Does NOT drop, truncate or alter existing tables.

    If *conn* is provided, DDL is executed on that connection and the connection
    remains open. If *conn* is None, a new connection is opened for *db_path*,
    DDL is applied, and the connection is closed.
    """
    should_close = False
    if conn is None:
        conn = get_connection(db_path)
        should_close = True
    try:
        conn.executescript(_DDL_V1)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
            (_CURRENT_SCHEMA_VERSION,),
        )
        conn.commit()
        logger.info("Database schema initialised at %s (version %d)", db_path, _CURRENT_SCHEMA_VERSION)
        return conn
    finally:
        if should_close:
            conn.close()


# ── Business-state seeding (idempotent) ───────────────────────────────────────

def seed_business_state(
    db_path: str = DEFAULT_DB_PATH,
    profiles_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Seeds the `business_state` table from *profiles_path* (defaults to
    ``data/business_profiles.json``).

    Uses INSERT OR IGNORE – existing rows are never overwritten.  This means
    calling seed on a database that already has live cash/inventory mutations
    is safe and will not reset the operator's current state.

    If *conn* is provided, uses that connection without closing it.

    Returns the number of rows actually inserted (0 on subsequent calls).
    """
    path = Path(profiles_path) if profiles_path else _PROFILES_JSON
    if not path.exists():
        logger.warning("Profiles JSON not found at %s – skipping seed", path)
        return 0

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    profiles = data.get("profiles", {})
    should_close = False
    if conn is None:
        conn = get_connection(db_path)
        should_close = True
    inserted = 0
    try:
        for btype, prof in profiles.items():
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO business_state
                    (business_type, display_name, cash_balance, inventory_units, safety_reserve)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    btype,
                    prof.get("display_name", btype),
                    float(prof.get("starting_capital", 10000.0)),
                    float(prof.get("starting_inventory", 0.0)),
                    2000.0,  # default safety reserve
                ),
            )
            inserted += cur.rowcount
        conn.commit()
        if inserted:
            logger.info("Seeded %d business state record(s) into %s", inserted, db_path)
        else:
            logger.debug("Business state already seeded – no rows inserted")
    finally:
        if should_close:
            conn.close()
    return inserted
