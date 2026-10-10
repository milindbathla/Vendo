"""Test read-only database connection guarantees."""
import sqlite3
import pytest
from business_intel.db import get_readonly_connection


def test_readonly_connection_blocks_writes():
    conn = get_readonly_connection()
    cursor = conn.cursor()

    # Verify query_only pragma is 1
    cursor.execute("PRAGMA query_only;")
    row = cursor.fetchone()
    assert row[0] == 1

    # Attempting write must raise OperationalError
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        cursor.execute("CREATE TABLE test_table (id INT);")

    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        cursor.execute("INSERT INTO business_memory (key, value, source, timestamp, confidence) VALUES ('k', 'v', 'owner_statement', '2026-10-10', 0.9);")

    conn.close()
