"""Test memory authorizer and write permissions."""
import os
import shutil
import sqlite3
from pathlib import Path
import pytest

import business_intel.config as bi_config
import business_intel.db as bi_db
from business_intel.db import get_authorizer_rw_connection
from business_intel.tools.context_tools import write_business_memory, get_business_memory


@pytest.fixture(autouse=True)
def isolate_memory_authorizer_db(tmp_path, monkeypatch):
    """
    Isolate test database writes so tests never modify the canonical demo.db.
    Copies canonical demo.db to a temporary directory and rebinds DEMO_DB_PATH.
    """
    source_db = None
    for cand in [
        Path(__file__).resolve().parents[3] / "data" / "demo.db",
        Path(__file__).resolve().parents[1] / "demo_data" / "demo.db",
    ]:
        if cand.exists():
            source_db = cand
            break

    assert source_db is not None, "Canonical demo.db not found for test isolation."
    test_db = tmp_path / "test_memory_demo.db"
    shutil.copy2(source_db, test_db)

    test_db_str = str(test_db)
    monkeypatch.setattr(bi_config, "DEMO_DB_PATH", test_db_str)
    monkeypatch.setattr(bi_db, "DEMO_DB_PATH", test_db_str)
    monkeypatch.setenv("DEMO_DB_PATH", test_db_str)
    yield test_db_str



def test_authorizer_blocks_unauthorized_tables():
    conn = get_authorizer_rw_connection()
    cursor = conn.cursor()

    # Attempt to insert into items table -> must fail
    with pytest.raises(sqlite3.DatabaseError):
        cursor.execute("INSERT INTO items (item_id, name, unit) VALUES ('test', 'Test Item', 'kg')")

    # Attempt to update orders table -> must fail
    with pytest.raises(sqlite3.DatabaseError):
        cursor.execute("UPDATE orders SET units = 100 WHERE order_id = 'ORD-001'")

    # Attempt to drop table -> must fail
    with pytest.raises(sqlite3.DatabaseError):
        cursor.execute("DROP TABLE customers")

    # Attempt to delete from business_memory -> must fail (deletes are denied)
    with pytest.raises(sqlite3.DatabaseError):
        cursor.execute("DELETE FROM business_memory")

    conn.close()


def test_write_business_memory_success_and_conflict():
    # 1. Write a normal policy
    res1 = write_business_memory(
        category="policy",
        key="test.packaging_preference",
        value="Use biodegradable containers",
    )
    assert res1.ok is True
    assert res1.data["conflict_detected"] is False

    # 2. Verify write persisted
    res_get = get_business_memory(key="test.packaging_preference")
    assert res_get.ok is True
    assert len(res_get.data["records"]) >= 1

    # 3. Write a statement conflicting with verified Gupta oil price
    res_conflict = write_business_memory(
        category="supplier_rate",
        key="supplier.gupta.oil_price_per_l",
        value="130",
    )
    assert res_conflict.ok is True
    assert res_conflict.data["conflict_detected"] is True
    assert "clarification_question" in res_conflict.data
    assert "Which rate should I use" in res_conflict.data["clarification_question"]

