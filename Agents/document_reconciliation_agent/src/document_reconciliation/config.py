"""Configuration and database path resolution for Document & Reconciliation Agent."""

import os
from pathlib import Path
from typing import Optional


def resolve_db_path(configured_path: Optional[str] = None) -> str:
    """Resolve SQLite database path with deterministic fallback.

    Order of precedence:
    1. Explicitly supplied path argument
    2. Environment variable BUSINESS_MCP_DB_PATH or DEMO_DB_PATH
    3. Agent-local data/demo.db
    4. Repo-wide data/demo.db
    """
    if configured_path:
        p = Path(configured_path).resolve()
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"Configured database path does not exist: {configured_path}")

    env_path = os.environ.get("BUSINESS_MCP_DB_PATH") or os.environ.get("DEMO_DB_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"Database path in environment does not exist: {env_path}")

    # 1. Check agent-local data/demo.db
    agent_root = Path(__file__).resolve().parent.parent.parent
    local_data_path = agent_root / "data" / "demo.db"
    if local_data_path.exists():
        return str(local_data_path)

    # 2. Check repo-wide data/demo.db
    repo_root = agent_root.parent.parent
    repo_data_path = repo_root / "data" / "demo.db"
    if repo_data_path.exists():
        return str(repo_data_path)

    raise FileNotFoundError(
        "Could not find demo.db. Checked local data/demo.db and repo data/demo.db"
    )
