"""Pytest configuration and global test isolation fixtures.

Ensures that tests running in the test suite never touch or mutate
the canonical data/demo.db database.
"""
import os
import tempfile
import pytest

# Set DATABASE_PATH to an isolated temporary database before web_app or any other module is imported
_temp_dir = tempfile.mkdtemp(prefix="autopilot_tests_")
_test_db_file = os.path.join(_temp_dir, "isolated_test_demo.sqlite3")
os.environ.setdefault("DATABASE_PATH", _test_db_file)


@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_db():
    yield
    try:
        import shutil
        shutil.rmtree(_temp_dir, ignore_errors=True)
    except Exception:
        pass
