"""Pytest configuration for data_analytics_agent tests.

Ensures that tests running in the data analytics agent suite never modify
the canonical data/demo.db database by providing an isolated test database copy.
"""
import os
import shutil
from pathlib import Path
import pytest

import business_intel.config as bi_config
import business_intel.db as bi_db


@pytest.fixture(scope="session", autouse=True)
def isolate_analytics_db_session(tmp_path_factory):
    """
    Session-wide fixture that creates a temporary copy of demo.db for tests
    and rebinds DEMO_DB_PATH so all tests (including write_business_memory calls)
    run against the temporary copy.
    """
    source_db = None
    for cand in [
        Path(__file__).resolve().parents[3] / "data" / "demo.db",
        Path(__file__).resolve().parents[1] / "demo_data" / "demo.db",
    ]:
        if cand.exists():
            source_db = cand
            break

    if source_db is None:
        yield
        return

    temp_dir = tmp_path_factory.mktemp("data_analytics_db")
    temp_db = temp_dir / "demo.db"
    shutil.copy2(source_db, temp_db)

    test_db_str = str(temp_db)
    bi_config.DEMO_DB_PATH = test_db_str
    bi_db.DEMO_DB_PATH = test_db_str
    os.environ["DEMO_DB_PATH"] = test_db_str

    yield test_db_str
