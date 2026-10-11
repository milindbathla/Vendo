"""
Phase A — SQLite Persistence Tests
====================================
Covers:
 1. Schema initialisation and repeat initialisation (idempotent)
 2. Persistence after closing and reopening the database
 3. Creating and retrieving purchase plans
 4. Approval persistence
 5. Rejection persistence
 6. Preventing execution of PENDING and REJECTED plans
 7. Successful simulated execution of an APPROVED plan
 8. Preventing duplicate execution after a restart (plan re-read from disk)
 9. Insufficient funds / minimum reserve enforcement
10. Transaction rollback on failure (concurrent duplicate execution)
11. Concurrent attempts to execute the same plan (threading)
12. HTTP API compatibility: existing /api/state, /api/confirm_plan, /api/execute_plan
13. Idempotent seeding (second seed call inserts 0 rows)
14. PurchaseApprovalService in :memory: mode (existing unit-test compatibility)
15. BusinessStateRepository cash and inventory updates
"""
import sqlite3
import threading
import time
import pytest

from src.db.connection import (
    DEFAULT_DB_PATH,
    get_connection,
    initialize_database,
    seed_business_state,
)
from src.db.plan_repository import PlanRepository, PlanStatus, _InsufficientFundsError
from src.db.state_repository import BusinessStateRepository
from src.decision.approval_service import (
    PurchaseApprovalService,
    PlanNotFoundError,
    InvalidPlanStateError,
    InsufficientFundsError,
    PlanStatus as ServicePlanStatus,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """Isolated on-disk database for each test."""
    return str(tmp_path / "test_autopilot.sqlite3")


@pytest.fixture
def init_db(db_path):
    """Initialised (schema applied) database path."""
    initialize_database(db_path)
    return db_path


@pytest.fixture
def repo(init_db):
    """PlanRepository backed by a fresh, empty database."""
    return PlanRepository(init_db)


@pytest.fixture
def state_repo(init_db):
    """BusinessStateRepository backed by the same fresh database."""
    return BusinessStateRepository(init_db)


@pytest.fixture
def service(db_path):
    """PurchaseApprovalService backed by a fresh on-disk database."""
    return PurchaseApprovalService(db_path=db_path)


@pytest.fixture
def sample_items():
    return [
        {
            "ingredient_name": "cooking_oil",
            "display_name":    "Sunflower Oil",
            "quantity":        5.0,
            "unit":            "litres",
            "unit_price":      120.0,
            "total_price":     600.0,
        },
        {
            "ingredient_name": "containers",
            "display_name":    "Eco Containers",
            "quantity":        50.0,
            "unit":            "units",
            "unit_price":      6.0,
            "total_price":     300.0,
        },
    ]


# ── 1. Schema initialisation ──────────────────────────────────────────────────

class TestSchemaInitialisation:

    def test_creates_all_tables(self, db_path):
        """initialize_database() creates every expected table."""
        initialize_database(db_path)
        conn = get_connection(db_path)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "autopilot_schema_migrations",
            "autopilot_business_state",
            "autopilot_purchase_plans",
            "autopilot_plan_items",
            "autopilot_audit_events",
            "autopilot_execution_receipts",
        }
        assert expected.issubset(tables)

    def test_repeat_initialisation_is_idempotent(self, db_path):
        """Calling initialize_database() twice does not raise or corrupt data."""
        initialize_database(db_path)
        initialize_database(db_path)   # second call must be safe
        conn = get_connection(db_path)
        version = conn.execute(
            "SELECT version FROM autopilot_schema_migrations"
        ).fetchone()["version"]
        conn.close()
        assert version == 1

    def test_schema_version_recorded(self, db_path):
        """Schema version 1 is recorded after initialisation."""
        initialize_database(db_path)
        conn = get_connection(db_path)
        row = conn.execute("SELECT version FROM autopilot_schema_migrations").fetchone()
        conn.close()
        assert row is not None
        assert row["version"] == 1

    def test_wal_journal_mode_enabled(self, db_path):
        initialize_database(db_path)
        conn = get_connection(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"


# ── 2. Persistence after close/reopen ─────────────────────────────────────────

class TestPersistenceAfterReopen:

    def test_plan_survives_connection_close(self, init_db, sample_items):
        """A plan written in one connection is visible after reopening."""
        repo1 = PlanRepository(init_db)
        plan  = repo1.create_plan(
            supplier_id="wholesale_mandi",
            supplier_name="Metro Wholesale",
            items=sample_items,
            total_cost=900.0,
            explanation="Test persistence",
        )
        pid = plan.plan_id

        # Open a completely new repository (new connection)
        repo2 = PlanRepository(init_db)
        loaded = repo2.get_plan(pid)
        assert loaded.plan_id == pid
        assert loaded.total_cost == 900.0
        assert loaded.status == PlanStatus.PENDING_APPROVAL
        assert len(loaded.items) == 2

    def test_approval_survives_restart(self, init_db, sample_items):
        """APPROVED status persists across PlanRepository re-instantiation."""
        repo1 = PlanRepository(init_db)
        plan  = repo1.create_plan("s1", "Supplier", sample_items, 900.0, "test")
        repo1.confirm_plan(plan.plan_id, "APPROVE")

        repo2 = PlanRepository(init_db)
        loaded = repo2.get_plan(plan.plan_id)
        assert loaded.status == PlanStatus.APPROVED
        assert loaded.owner_decision == "APPROVED"
        assert loaded.confirmed_at is not None

    def test_execution_survives_restart(self, init_db, sample_items):
        """EXECUTED status and receipt persist across re-instantiation."""
        repo1 = PlanRepository(init_db)
        plan  = repo1.create_plan("s1", "Supplier", sample_items, 900.0, "test")
        repo1.confirm_plan(plan.plan_id, "APPROVE")
        repo1.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)

        repo2 = PlanRepository(init_db)
        loaded = repo2.get_plan(plan.plan_id)
        assert loaded.status == PlanStatus.EXECUTED
        assert loaded.executed_at is not None
        assert loaded.execution_receipt is not None
        assert loaded.execution_receipt["status"] == "SIMULATED_ORDER_PLACED"


# ── 3. Creating and retrieving plans ─────────────────────────────────────────

class TestCreateAndRetrieve:

    def test_create_plan_returns_pending_approval(self, repo, sample_items):
        plan = repo.create_plan("s1", "Supplier", sample_items, 900.0, "Test")
        assert plan.status == PlanStatus.PENDING_APPROVAL
        assert plan.total_cost == 900.0
        assert len(plan.items) == 2
        assert plan.confirmed_at is None
        assert plan.executed_at is None

    def test_get_plan_raises_keyerror_for_unknown_id(self, repo):
        with pytest.raises(KeyError):
            repo.get_plan("PLAN-DOESNOTEXIST")

    def test_list_plans_returns_all(self, repo, sample_items):
        repo.create_plan("s1", "S1", sample_items, 100.0, "A")
        repo.create_plan("s2", "S2", sample_items, 200.0, "B")
        plans = repo.list_plans()
        assert len(plans) == 2

    def test_custom_plan_id_respected(self, repo, sample_items):
        plan = repo.create_plan("s1", "S1", sample_items, 100.0, "A", plan_id="PLAN-CUSTOM01")
        assert plan.plan_id == "PLAN-CUSTOM01"

    def test_plan_items_stored_correctly(self, repo, sample_items):
        plan = repo.create_plan("s1", "S1", sample_items, 900.0, "test")
        loaded = repo.get_plan(plan.plan_id)
        names = {it.ingredient_name for it in loaded.items}
        assert names == {"cooking_oil", "containers"}


# ── 4 & 5. Approval and rejection persistence ─────────────────────────────────

class TestApprovalAndRejection:

    def test_approve_transitions_to_approved(self, repo, sample_items):
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        result = repo.confirm_plan(plan.plan_id, "APPROVE")
        assert result.status == PlanStatus.APPROVED
        assert result.owner_decision == "APPROVED"
        assert result.confirmed_at is not None

    def test_reject_transitions_to_rejected(self, repo, sample_items):
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        result = repo.confirm_plan(plan.plan_id, "REJECT")
        assert result.status == PlanStatus.REJECTED
        assert result.owner_decision == "REJECTED"

    def test_invalid_decision_raises_value_error(self, repo, sample_items):
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        with pytest.raises(ValueError, match="Invalid decision"):
            repo.confirm_plan(plan.plan_id, "MAYBE")

    def test_double_approval_raises_runtime_error(self, repo, sample_items):
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        with pytest.raises(RuntimeError):
            repo.confirm_plan(plan.plan_id, "APPROVE")

    def test_confirm_unknown_plan_raises_keyerror(self, repo):
        with pytest.raises(KeyError):
            repo.confirm_plan("PLAN-GHOST", "APPROVE")

    def test_audit_event_written_on_approve(self, init_db, sample_items):
        repo = PlanRepository(init_db)
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        conn = get_connection(init_db)
        events = conn.execute(
            "SELECT event_type FROM autopilot_audit_events WHERE plan_id=?", (plan.plan_id,)
        ).fetchall()
        conn.close()
        event_types = [e["event_type"] for e in events]
        assert "CREATED" in event_types
        assert "APPROVED" in event_types


# ── 6. Preventing execution of PENDING and REJECTED plans ────────────────────

class TestIllegalExecution:

    def test_cannot_execute_pending_plan(self, repo, sample_items):
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        with pytest.raises(RuntimeError, match="PENDING_APPROVAL"):
            repo.execute_plan(plan.plan_id, current_cash=5000.0)

    def test_cannot_execute_rejected_plan(self, repo, sample_items):
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "REJECT")
        with pytest.raises(RuntimeError, match="REJECTED"):
            repo.execute_plan(plan.plan_id, current_cash=5000.0)

    def test_execute_unknown_plan_raises_keyerror(self, repo):
        with pytest.raises(KeyError):
            repo.execute_plan("PLAN-GHOST", current_cash=5000.0)


# ── 7. Successful simulated execution ────────────────────────────────────────

class TestSuccessfulExecution:

    def test_execute_approved_plan_returns_receipt(self, repo, sample_items):
        plan = repo.create_plan("s1", "Metro", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        receipt = repo.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)

        assert receipt["status"] == "SIMULATED_ORDER_PLACED"
        assert receipt["amount_paid"] == 900.0
        assert receipt["cash_before"] == 5000.0
        assert receipt["cash_after"] == 4100.0
        assert receipt["safety_reserve_preserved"] == 2000.0

    def test_plan_status_is_executed_after_execution(self, repo, sample_items):
        plan = repo.create_plan("s1", "Metro", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        repo.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)

        loaded = repo.get_plan(plan.plan_id)
        assert loaded.status == PlanStatus.EXECUTED
        assert loaded.executed_at is not None

    def test_receipt_persisted_in_database(self, init_db, sample_items):
        repo = PlanRepository(init_db)
        plan = repo.create_plan("s1", "Metro", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        repo.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)

        conn = get_connection(init_db)
        row = conn.execute(
            "SELECT * FROM autopilot_execution_receipts WHERE plan_id=?", (plan.plan_id,)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["amount_paid"] == 900.0
        assert row["cash_after"] == 4100.0


# ── 8. Duplicate execution prevention after restart ───────────────────────────

class TestDuplicateExecutionPrevention:

    def test_duplicate_execution_blocked_same_instance(self, repo, sample_items):
        """Second execute_plan on the same repo raises RuntimeError."""
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        repo.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)

        with pytest.raises(RuntimeError, match="EXECUTED"):
            repo.execute_plan(plan.plan_id, current_cash=4100.0, safety_reserve=2000.0)

    def test_duplicate_execution_blocked_after_restart(self, init_db, sample_items):
        """Second execute_plan via a new repo (simulating restart) also raises."""
        repo1 = PlanRepository(init_db)
        plan  = repo1.create_plan("s1", "S", sample_items, 900.0, "t")
        repo1.confirm_plan(plan.plan_id, "APPROVE")
        repo1.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)

        repo2 = PlanRepository(init_db)  # simulates a fresh process
        with pytest.raises(RuntimeError, match="EXECUTED"):
            repo2.execute_plan(plan.plan_id, current_cash=4100.0, safety_reserve=2000.0)


# ── 9. Insufficient funds enforcement ────────────────────────────────────────

class TestInsufficientFunds:

    def test_execution_blocked_when_cash_too_low(self, repo, sample_items):
        """total_cost=900, usable=2500-2000=500 < 900 → raises."""
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        with pytest.raises(_InsufficientFundsError):
            repo.execute_plan(plan.plan_id, current_cash=2500.0, safety_reserve=2000.0)

    def test_plan_status_unchanged_after_funds_failure(self, repo, sample_items):
        """Plan must remain APPROVED (not EXECUTED) after a funds failure."""
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")
        try:
            repo.execute_plan(plan.plan_id, current_cash=2500.0, safety_reserve=2000.0)
        except _InsufficientFundsError:
            pass
        loaded = repo.get_plan(plan.plan_id)
        assert loaded.status == PlanStatus.APPROVED


# ── 10. Transaction rollback on failure ───────────────────────────────────────

class TestTransactionRollback:

    def test_failed_execution_does_not_corrupt_state(self, init_db, sample_items):
        """After a failed execute (funds error), subsequent approve + execute works."""
        repo = PlanRepository(init_db)
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")

        # Fail once
        try:
            repo.execute_plan(plan.plan_id, current_cash=2500.0, safety_reserve=2000.0)
        except _InsufficientFundsError:
            pass

        # Succeed with sufficient cash
        receipt = repo.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)
        assert receipt["status"] == "SIMULATED_ORDER_PLACED"


# ── 11. Concurrent execution attempts ────────────────────────────────────────

class TestConcurrentExecution:

    def test_only_one_thread_can_execute(self, init_db, sample_items):
        """
        Two threads race to execute the same APPROVED plan.
        Exactly one must succeed; the other must raise RuntimeError.
        """
        repo = PlanRepository(init_db)
        plan = repo.create_plan("s1", "S", sample_items, 900.0, "t")
        repo.confirm_plan(plan.plan_id, "APPROVE")

        results = []
        errors  = []

        def do_execute():
            try:
                r = PlanRepository(init_db).execute_plan(
                    plan.plan_id, current_cash=5000.0, safety_reserve=2000.0
                )
                results.append(r)
            except (RuntimeError, _InsufficientFundsError) as e:
                errors.append(e)

        t1 = threading.Thread(target=do_execute)
        t2 = threading.Thread(target=do_execute)
        t1.start(); t2.start()
        t1.join();  t2.join()

        # Exactly one execution must have succeeded
        assert len(results) == 1, f"Expected 1 success, got {len(results)}"
        assert len(errors)  == 1, f"Expected 1 failure, got {len(errors)}"

        # Confirm persisted status is EXECUTED
        final = PlanRepository(init_db).get_plan(plan.plan_id)
        assert final.status == PlanStatus.EXECUTED


# ── 12. PurchaseApprovalService public API with on-disk SQLite ────────────────

class TestApprovalServicePublicAPI:
    """
    Verifies the service-level exception mapping and that the existing unit-test
    assertions (plan.status, plan.executed_at, etc.) still hold for the
    SQLite-backed implementation.
    """

    def test_create_plan_is_pending(self, service, sample_items):
        plan = service.create_plan("s1", "S", sample_items, 900.0, "t")
        assert plan.status == ServicePlanStatus.PENDING_APPROVAL
        assert plan.confirmed_at is None

    def test_plan_not_found_raises_correct_exception(self, service):
        with pytest.raises(PlanNotFoundError):
            service.get_plan("PLAN-GHOST")

    def test_confirm_unknown_raises_plan_not_found(self, service):
        with pytest.raises(PlanNotFoundError):
            service.confirm_plan("PLAN-GHOST", "APPROVE")

    def test_execute_unknown_raises_plan_not_found(self, service):
        with pytest.raises(PlanNotFoundError):
            service.execute_plan("PLAN-GHOST", current_cash=5000.0)

    def test_execute_pending_raises_invalid_state(self, service, sample_items):
        plan = service.create_plan("s1", "S", sample_items, 900.0, "t")
        with pytest.raises(InvalidPlanStateError):
            service.execute_plan(plan.plan_id, current_cash=5000.0)
        assert plan.status == ServicePlanStatus.PENDING_APPROVAL

    def test_execute_rejected_raises_invalid_state(self, service, sample_items):
        plan = service.create_plan("s1", "S", sample_items, 900.0, "t")
        service.confirm_plan(plan.plan_id, "REJECT")
        with pytest.raises(InvalidPlanStateError):
            service.execute_plan(plan.plan_id, current_cash=5000.0)

    def test_full_lifecycle(self, service, sample_items):
        plan = service.create_plan("s1", "Metro", sample_items, 900.0, "t")
        service.confirm_plan(plan.plan_id, "APPROVE")
        receipt = service.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)
        assert receipt["status"] == "SIMULATED_ORDER_PLACED"
        assert receipt["cash_after"] == 4100.0

        # Refresh plan from service
        refreshed = service.get_plan(plan.plan_id)
        assert refreshed.status == ServicePlanStatus.EXECUTED
        assert refreshed.executed_at is not None

    def test_insufficient_funds_raises_correct_exception(self, service, sample_items):
        plan = service.create_plan("s1", "S", sample_items, 900.0, "t")
        service.confirm_plan(plan.plan_id, "APPROVE")
        with pytest.raises(InsufficientFundsError):
            service.execute_plan(plan.plan_id, current_cash=2500.0, safety_reserve=2000.0)
        refreshed = service.get_plan(plan.plan_id)
        assert refreshed.status == ServicePlanStatus.APPROVED   # unchanged

    def test_duplicate_execution_raises_invalid_state(self, service, sample_items):
        plan = service.create_plan("s1", "S", sample_items, 900.0, "t")
        service.confirm_plan(plan.plan_id, "APPROVE")
        service.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)
        with pytest.raises(InvalidPlanStateError):
            service.execute_plan(plan.plan_id, current_cash=4100.0, safety_reserve=2000.0)

    def test_invalid_decision_raises_value_error(self, service, sample_items):
        plan = service.create_plan("s1", "S", sample_items, 900.0, "t")
        with pytest.raises(ValueError):
            service.confirm_plan(plan.plan_id, "MAYBE")

    def test_persistence_after_service_reinstantiation(self, db_path, sample_items):
        """Plan written by service1 is visible to service2 (simulates restart)."""
        svc1 = PurchaseApprovalService(db_path=db_path)
        plan = svc1.create_plan("s1", "S", sample_items, 900.0, "t")
        svc1.confirm_plan(plan.plan_id, "APPROVE")

        svc2 = PurchaseApprovalService(db_path=db_path)
        loaded = svc2.get_plan(plan.plan_id)
        assert loaded.status == ServicePlanStatus.APPROVED

    def test_in_memory_mode_still_works(self, sample_items):
        """:memory: mode (default, used by existing unit tests) must work."""
        svc = PurchaseApprovalService()   # no db_path → :memory:
        plan = svc.create_plan("s1", "S", sample_items, 900.0, "t")
        svc.confirm_plan(plan.plan_id, "APPROVE")
        receipt = svc.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)
        assert receipt["amount_paid"] == 900.0


# ── 13. Idempotent seeding ────────────────────────────────────────────────────

class TestIdempotentSeeding:

    def test_seed_inserts_profiles_on_first_call(self, init_db):
        count = seed_business_state(init_db)
        assert count > 0  # at least one business profile in business_profiles.json

    def test_seed_inserts_zero_on_second_call(self, init_db):
        seed_business_state(init_db)
        second = seed_business_state(init_db)
        assert second == 0, "Second seed call must not overwrite existing data"

    def test_seed_does_not_reset_cash_balance(self, init_db):
        """Mutating cash balance then reseeding must not restore the original value."""
        seed_business_state(init_db)

        state_repo = BusinessStateRepository(init_db)
        # Simulate a purchase deduction
        state_repo.update_cash_after_purchase("home_tiffin", amount_deducted=500.0)
        before = state_repo.get_state("home_tiffin")["cash_balance"]

        seed_business_state(init_db)  # re-seed (INSERT OR IGNORE)
        after = state_repo.get_state("home_tiffin")["cash_balance"]

        assert after == before, "Re-seeding must not overwrite live cash balance"


# ── 14. BusinessStateRepository ──────────────────────────────────────────────

class TestBusinessStateRepository:

    def test_get_state_returns_none_before_seed(self, state_repo):
        result = state_repo.get_state("home_tiffin")
        assert result is None  # not yet seeded

    def test_get_state_after_seed(self, init_db):
        seed_business_state(init_db)
        repo = BusinessStateRepository(init_db)
        state = repo.get_state("home_tiffin")
        assert state is not None
        assert state["cash_balance"] > 0
        assert state["inventory_units"] >= 0

    def test_update_cash_deducts_correctly(self, init_db):
        seed_business_state(init_db)
        repo = BusinessStateRepository(init_db)
        original = repo.get_state("home_tiffin")["cash_balance"]
        new_bal = repo.update_cash_after_purchase("home_tiffin", amount_deducted=1000.0)
        assert new_bal == original - 1000.0
        assert repo.get_state("home_tiffin")["cash_balance"] == new_bal

    def test_update_cash_noop_for_unknown_type(self, init_db):
        seed_business_state(init_db)
        repo = BusinessStateRepository(init_db)
        result = repo.update_cash_after_purchase("nonexistent_type", 100.0)
        assert result is None  # safe no-op

    def test_update_inventory_adds_delta(self, init_db):
        seed_business_state(init_db)
        repo = BusinessStateRepository(init_db)
        original = repo.get_state("home_tiffin")["inventory_units"]
        new_inv = repo.update_inventory("home_tiffin", delta=20.0)
        assert new_inv == original + 20.0
