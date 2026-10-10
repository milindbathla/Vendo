"""
Build and Verification Script for Alexa Business Autopilot Database.
Executes build order:
  1. schema.sql
  2. seed_anchor.sql
  3. seed_bulk.sql (generated via generate_bulk.py if missing)
  4. views.sql
  5. verify_demo.sql (Assertions A1..A16)

Prints:
  - Table row counts
  - Key decision numbers (shortfall, 2217 / 1675 / 2077, headroom 1900, plan balances)
  - Assertion results table
  - "ALL 16 ASSERTIONS PASS" upon 100% success.
Exits non-zero on any failure.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
from typing import List, Tuple, Dict, Any


def get_base_dir() -> str:
    """Returns the absolute path to demo_data/."""
    return os.path.dirname(os.path.abspath(__file__))


def read_sql_file(filepath: str) -> str:
    """Reads SQL content from a file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def build_database(db_path: str) -> sqlite3.Connection:
    """Builds the SQLite database from scratch using strict sequence."""
    if os.path.exists(db_path):
        os.remove(db_path)

    base_dir = get_base_dir()
    schema_sql = read_sql_file(os.path.join(base_dir, "schema.sql"))
    anchor_sql = read_sql_file(os.path.join(base_dir, "seed_anchor.sql"))

    bulk_file = os.path.join(base_dir, "seed_bulk.sql")
    if not os.path.exists(bulk_file):
        print("seed_bulk.sql not found; generating via generate_bulk.py...")
        import generate_bulk
        generate_bulk.main()

    bulk_sql = read_sql_file(bulk_file)
    views_sql = read_sql_file(os.path.join(base_dir, "views.sql"))

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    # 1. schema
    conn.executescript(schema_sql)
    # 2. anchor
    conn.executescript(anchor_sql)
    # 3. bulk
    conn.executescript(bulk_sql)
    # 4. views
    conn.executescript(views_sql)
    conn.commit()

    return conn


def get_dump_hash(conn: sqlite3.Connection) -> str:
    """Dumps all database statements deterministically and calculates SHA256."""
    dump_lines = [line for line in conn.iterdump()]
    dump_text = "\n".join(dump_lines)
    return hashlib.sha256(dump_text.encode("utf-8")).hexdigest()


def run_verifications(conn: sqlite3.Connection) -> List[Tuple[str, str, str, str]]:
    """Runs verify_demo.sql and foreign key checks."""
    base_dir = get_base_dir()

    # Foreign key check
    fk_cur = conn.cursor()
    fk_cur.execute("PRAGMA foreign_key_check;")
    fk_violations = fk_cur.fetchall()
    if fk_violations:
        print(f"ERROR: Foreign key violations detected: {fk_violations}")
        sys.exit(1)

    verify_sql = read_sql_file(os.path.join(base_dir, "verify_demo.sql"))
    cur = conn.cursor()
    cur.execute(verify_sql)
    results = cur.fetchall()
    return results


def print_table_counts(conn: sqlite3.Connection) -> None:
    """Prints row count per table in a formatted table."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    tables = [r[0] for r in cur.fetchall()]

    print("\n" + "=" * 65)
    print(f"{'TABLE NAME':<35} | {'ROW COUNT':>12} | {'TYPE':<12}")
    print("-" * 65)
    total_rows = 0
    for tbl in tables:
        c_cur = conn.cursor()
        c_cur.execute(f"SELECT COUNT(*) FROM {tbl};")
        cnt = c_cur.fetchone()[0]
        total_rows += cnt
        category = "Anchor/Core" if cnt < 20 else "Bulk/Ledger"
        print(f"{tbl:<35} | {cnt:>12} | {category:<12}")
    print("-" * 65)
    print(f"{'TOTAL ROWS ACROSS ALL TABLES':<35} | {total_rows:>12} |")
    print("=" * 65 + "\n")


def print_key_numbers(conn: conn) -> None:
    """Prints headline business metrics and invariant numbers."""
    cur = conn.cursor()

    # 1. Shortfall
    cur.execute("SELECT item_id, shortfall_qty, unit FROM v_shortfall_tomorrow ORDER BY item_id;")
    shortfalls = cur.fetchall()
    shortfall_str = ", ".join([f"{item}: {qty} {unit}" for item, qty, unit in shortfalls])

    # 2. Plan costs & balances
    cur.execute("SELECT plan_id, total_cost, min_balance_after_plan, buffer_compliant FROM v_plan_cost ORDER BY plan_id;")
    plans = cur.fetchall()

    # 3. Headroom
    cur.execute("SELECT current_balance, min_cash_buffer, min_projected_balance, cash_headroom FROM v_cash_headroom;")
    curr_b, min_buf, min_proj, headroom = cur.fetchone()

    print("=" * 65)
    print("KEY DECISION NUMBERS & HEADLINE INVARIANTS")
    print("=" * 65)
    print(f" Tomorrow's Shortfall Items:      {shortfall_str}")
    print(f" Cash Headroom (6900 - 5000):     ₹{headroom:,.2f}")
    print(f" Minimum Cash Buffer Required:    ₹{min_buf:,.2f}")
    print(f" Lowest Projected Cash (10-12):   ₹{min_proj:,.2f}")
    print("-" * 65)
    print(f"{'PLAN ID':<20} | {'TOTAL COST':>10} | {'MIN BAL AFTER':>13} | {'BUFFER OK':>10}")
    print("-" * 65)
    for p_id, cost, bal_after, b_ok in plans:
        status_ok = "YES (PASS)" if b_ok else "NO (FAIL)"
        print(f"{p_id:<20} | ₹{cost:>9.2f} | ₹{bal_after:>12.2f} | {status_ok:>10}")
    print("=" * 65 + "\n")


def test_determinism(db_path: str) -> None:
    """Verifies that building a second database produces identical SQL dumps."""
    conn1 = sqlite3.connect(db_path)
    hash1 = get_dump_hash(conn1)
    conn1.close()

    temp_db_path = db_path + ".verify_determinism.tmp"
    conn2 = build_database(temp_db_path)
    hash2 = get_dump_hash(conn2)
    conn2.close()

    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)

    if hash1 != hash2:
        print(f"FATAL: Determinism check failed! Hashes differ:\n 1: {hash1}\n 2: {hash2}")
        sys.exit(1)
    else:
        print(f"Determinism Verified: SHA256 = {hash1}")


def main() -> None:
    base_dir = get_base_dir()
    db_path = os.path.join(base_dir, "demo.db")

    print(f"Building Alexa Business Autopilot database at: {db_path}...")
    conn = build_database(db_path)

    # Print table row counts
    print_table_counts(conn)

    # Print headline decision metrics
    print_key_numbers(conn)

    # Run Invariant assertions A1..A16
    print("Running Invariant Assertions A1..A16 from verify_demo.sql...")
    results = run_verifications(conn)

    print("\n" + "=" * 80)
    print(f"{'ID':<4} | {'STATUS':<6} | {'ACTUAL VALUE':<38} | {'EXPECTED VALUE':<26}")
    print("-" * 80)

    all_passed = True
    for r in results:
        inv_id, expected, actual, status = r[0], r[1], r[2], r[3]
        print(f"{inv_id:<4} | {status:<6} | {str(actual):<38} | {str(expected):<26}")
        if status != "PASS":
            all_passed = False

    print("=" * 80)

    # Determinism test
    test_determinism(db_path)

    # Check file size
    db_size = os.path.getsize(db_path) / (1024 * 1024)
    print(f"\nFinal Database Size: {db_size:.2f} MB (Limit: < 5.0 MB)")

    # Also keep a copy at project root for convenience
    root_db_path = os.path.join(os.path.dirname(base_dir), "demo.db")
    if os.path.abspath(root_db_path) != os.path.abspath(db_path):
        import shutil
        shutil.copyfile(db_path, root_db_path)
        print(f"Synchronized root database copy at: {root_db_path}")

    if not all_passed:
        print("\nFATAL: One or more assertions failed!")
        sys.exit(1)

    print("\n" + "*" * 40)
    print("ALL 16 ASSERTIONS PASS")
    print("*" * 40 + "\n")
    conn.close()


if __name__ == "__main__":
    main()

