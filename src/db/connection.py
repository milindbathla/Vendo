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
* Schema versioning – a `autopilot_schema_migrations` table tracks applied versions.
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
# Canonical database: the seeded demo.db shared with the specialist agents.
# This file is strictly protected and MUST NEVER be mutated by autopilot DDL or seeding.
CANONICAL_DEMO_DB_PATH: str = str((_PROJECT_ROOT / "data" / "demo.db").resolve())

def is_canonical_demo_db(db_path: str) -> bool:
    """Returns True if the target database path points to the protected canonical demo.db."""
    try:
        if not db_path or db_path == ":memory:":
            return False
        return Path(db_path).resolve() == Path(CANONICAL_DEMO_DB_PATH).resolve()
    except Exception:
        return False

DEFAULT_DB_PATH: str = os.environ.get(
    "DATABASE_PATH", str(_PROJECT_ROOT / "data" / "runtime_autopilot.sqlite3")
)
_PROFILES_JSON: Path = _PROJECT_ROOT / "data" / "business_profiles.json"

# Current schema version – bump this integer when DDL changes.
_CURRENT_SCHEMA_VERSION = 5

# ── DDL ────────────────────────────────────────────────────────────────────────
_DDL_V1 = """
-- Schema migration tracker
CREATE TABLE IF NOT EXISTS autopilot_schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Live business state per business_type (cash, inventory)
-- Seeded from data/business_profiles.json; updated when a purchase executes.
CREATE TABLE IF NOT EXISTS autopilot_business_state (
    business_type   TEXT    PRIMARY KEY,
    display_name    TEXT    NOT NULL,
    cash_balance    REAL    NOT NULL,   -- Rs, floating-point; sufficient for demo scale
    inventory_units REAL    NOT NULL,
    safety_reserve  REAL    NOT NULL DEFAULT 2000.0,
    last_updated    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Purchase plan header – one row per plan
CREATE TABLE IF NOT EXISTS autopilot_purchase_plans (
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
CREATE TABLE IF NOT EXISTS autopilot_plan_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id         TEXT    NOT NULL REFERENCES autopilot_purchase_plans(plan_id) ON DELETE CASCADE,
    ingredient_name TEXT    NOT NULL,
    display_name    TEXT    NOT NULL,
    quantity        REAL    NOT NULL CHECK(quantity >= 0),
    unit            TEXT    NOT NULL,
    unit_price      REAL    NOT NULL CHECK(unit_price >= 0),
    total_price     REAL    NOT NULL CHECK(total_price >= 0)
);

-- Audit trail – append-only; never UPDATE or DELETE rows here
CREATE TABLE IF NOT EXISTS autopilot_audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,   -- 'CREATED', 'APPROVED', 'REJECTED', 'EXECUTED', 'EXEC_FAILED'
    event_data  TEXT    NOT NULL,   -- JSON blob
    occurred_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Execution receipt – one row per successfully executed plan
CREATE TABLE IF NOT EXISTS autopilot_execution_receipts (
    plan_id                 TEXT    PRIMARY KEY REFERENCES autopilot_purchase_plans(plan_id),
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

CREATE INDEX IF NOT EXISTS idx_plan_items_plan_id  ON autopilot_plan_items(plan_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_plan   ON autopilot_audit_events(plan_id);
"""

_DDL_V2 = """
-- External provider connections (Google Places, Zoho Books, etc.)
CREATE TABLE IF NOT EXISTS autopilot_provider_connections (
    provider        TEXT    NOT NULL,
    business_type   TEXT    NOT NULL DEFAULT 'home_tiffin',
    org_id          TEXT,
    api_domain      TEXT,
    scopes          TEXT,
    status          TEXT    NOT NULL DEFAULT 'disconnected', -- 'connected', 'mock', 'disconnected'
    last_synced_at  TEXT,
    metadata        TEXT,   -- JSON blob for non-sensitive connection details
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (provider, business_type)
);
CREATE INDEX IF NOT EXISTS idx_provider_connections ON autopilot_provider_connections(provider, business_type);
"""

_DDL_V3 = """
-- Adaptive business profiles: multiple independent business profiles
CREATE TABLE IF NOT EXISTS autopilot_business_profiles (
    business_id          TEXT    PRIMARY KEY,
    display_name         TEXT    NOT NULL,
    category             TEXT    NOT NULL,
    description          TEXT    NOT NULL DEFAULT '',
    city                 TEXT    NOT NULL DEFAULT 'Kanpur',
    state                TEXT    NOT NULL DEFAULT 'Uttar Pradesh',
    currency             TEXT    NOT NULL DEFAULT 'INR',
    onboarding_completed INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Adaptive business facts with provenance & confidence tracking
CREATE TABLE IF NOT EXISTS autopilot_business_facts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id          TEXT    NOT NULL REFERENCES autopilot_business_profiles(business_id) ON DELETE CASCADE,
    fact_key             TEXT    NOT NULL,
    fact_value_json      TEXT    NOT NULL,
    value_type           TEXT    NOT NULL DEFAULT 'str',
    status               TEXT    NOT NULL DEFAULT 'unknown', -- 'confirmed', 'assumed', 'unknown', 'outdated'
    source               TEXT    NOT NULL DEFAULT 'user_stated', -- 'user_stated', 'inferred', 'external_api', 'system_default'
    confidence           REAL    NOT NULL DEFAULT 1.0,
    notes                TEXT    NOT NULL DEFAULT '',
    updated_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(business_id, fact_key)
);
CREATE INDEX IF NOT EXISTS idx_business_facts_biz ON autopilot_business_facts(business_id);
"""

_DDL_V4 = """
-- Durable conversation sessions bound to authenticated identities and tenant boundaries
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
CREATE INDEX IF NOT EXISTS idx_sessions_biz_owner ON autopilot_conversation_sessions(business_id, owner_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_status ON autopilot_conversation_sessions(expires_at, status);
"""

_DDL_V5 = """
-- Secure OAuth 2.1 refresh token storage with token rotation, family tracking, and replay detection
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
    if is_canonical_demo_db(db_path):
        raise PermissionError(
            f"Direct schema mutation of canonical '{CANONICAL_DEMO_DB_PATH}' is strictly forbidden. "
            "Use an isolated disposable database by setting DATABASE_PATH."
        )

    should_close = False
    if conn is None:
        conn = get_connection(db_path)
        should_close = True
    try:
        conn.executescript(_DDL_V1)
        conn.execute(
            "INSERT OR IGNORE INTO autopilot_schema_migrations (version) VALUES (?)",
            (1,),
        )
        conn.executescript(_DDL_V2)
        conn.execute(
            "INSERT OR IGNORE INTO autopilot_schema_migrations (version) VALUES (?)",
            (2,),
        )
        conn.executescript(_DDL_V3)
        conn.execute(
            "INSERT OR IGNORE INTO autopilot_schema_migrations (version) VALUES (?)",
            (3,),
        )
        conn.executescript(_DDL_V4)
        conn.execute(
            "INSERT OR IGNORE INTO autopilot_schema_migrations (version) VALUES (?)",
            (4,),
        )
        conn.executescript(_DDL_V5)
        conn.execute(
            "INSERT OR IGNORE INTO autopilot_schema_migrations (version) VALUES (?)",
            (5,),
        )
        conn.commit()
        logger.info("Database schema initialised at %s (version %d)", db_path, _CURRENT_SCHEMA_VERSION)
        return conn
    finally:
        if should_close:
            conn.close()


def upsert_provider_connection(
    provider: str,
    business_type: str = "home_tiffin",
    status: str = "connected",
    org_id: Optional[str] = None,
    api_domain: Optional[str] = None,
    scopes: Optional[str] = None,
    last_synced_at: Optional[str] = None,
    metadata: Optional[dict] = None,
    db_path: str = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Records or updates external provider connection state (without storing secrets)."""
    meta_json = json.dumps(metadata) if metadata else None
    should_close = False
    if conn is None:
        conn = get_connection(db_path)
        should_close = True
    try:
        conn.execute(
            """
            INSERT INTO autopilot_provider_connections
                (provider, business_type, org_id, api_domain, scopes, status, last_synced_at, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(provider, business_type) DO UPDATE SET
                org_id = COALESCE(excluded.org_id, autopilot_provider_connections.org_id),
                api_domain = COALESCE(excluded.api_domain, autopilot_provider_connections.api_domain),
                scopes = COALESCE(excluded.scopes, autopilot_provider_connections.scopes),
                status = excluded.status,
                last_synced_at = COALESCE(excluded.last_synced_at, autopilot_provider_connections.last_synced_at),
                metadata = COALESCE(excluded.metadata, autopilot_provider_connections.metadata),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            """,
            (provider, business_type, org_id, api_domain, scopes, status, last_synced_at, meta_json),
        )
        conn.commit()
    finally:
        if should_close:
            conn.close()


def get_provider_connection(
    provider: str,
    business_type: str = "home_tiffin",
    db_path: str = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict]:
    """Retrieves external provider connection state for a business."""
    should_close = False
    if conn is None:
        conn = get_connection(db_path)
        should_close = True
    try:
        cur = conn.execute(
            """
            SELECT provider, business_type, org_id, api_domain, scopes, status, last_synced_at, metadata, created_at, updated_at
            FROM autopilot_provider_connections
            WHERE provider = ? AND business_type = ?
            """,
            (provider, business_type),
        )
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("metadata"):
            try:
                res["metadata"] = json.loads(res["metadata"])
            except Exception:
                pass
        return res
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
    Seeds the `autopilot_business_state` table from *profiles_path* (defaults to
    ``data/business_profiles.json``).

    Uses INSERT OR IGNORE – existing rows are never overwritten.  This means
    calling seed on a database that already has live cash/inventory mutations
    is safe and will not reset the operator's current state.

    If *conn* is provided, uses that connection without closing it.

    Returns the number of rows actually inserted (0 on subsequent calls).
    """
    if is_canonical_demo_db(db_path):
        raise PermissionError(
            f"Direct seeding of canonical '{CANONICAL_DEMO_DB_PATH}' is strictly forbidden. "
            "Use an isolated disposable database by setting DATABASE_PATH."
        )

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
                INSERT OR IGNORE INTO autopilot_business_state
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
