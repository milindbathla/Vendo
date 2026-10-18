"""
src.db — SQLite persistence layer for Alexa Business Autopilot
==============================================================
Provides:
- Database initialisation and schema versioning  (connection.py)
- Purchase-plan repository with atomic lifecycle  (plan_repository.py)
- Business-state repository for cash & inventory  (state_repository.py)

All modules use Python's built-in sqlite3.  No ORM dependency.
"""
from src.db.connection import (
    DEFAULT_DB_PATH,
    get_connection,
    initialize_database,
    seed_business_state,
)
from src.db.plan_repository import PlanRepository
from src.db.state_repository import BusinessStateRepository

__all__ = [
    "DEFAULT_DB_PATH",
    "get_connection",
    "initialize_database",
    "seed_business_state",
    "PlanRepository",
    "BusinessStateRepository",
    "AdaptiveProfileRepository",
    "EmailRepository",
    "TaskRepository",
    "TaskNotFoundError",
    "ActionNotFoundError",
    "InvalidStateTransitionError",
    "PayloadTamperedError",
    "UnauthorizedError",
    "ConcurrentUpdateError",
]

from src.db.profile_repository import AdaptiveProfileRepository
from src.db.email_repository import EmailRepository
from src.db.task_repository import (
    TaskRepository,
    TaskNotFoundError,
    ActionNotFoundError,
    InvalidStateTransitionError,
    PayloadTamperedError,
    UnauthorizedError,
    ConcurrentUpdateError,
)
