"""
Unit Tests for Purchase Approval Service & State Machine
========================================================
Validates the strict two-phase purchase lifecycle:
- PENDING_APPROVAL -> APPROVED / REJECTED -> EXECUTED
- Rejection of unconfirmed execution
- Rejection of duplicate, missing, or invalid transitions
- Protection of minimum liquid cash safety reserve
"""
import pytest
from src.decision.approval_service import (
    PurchaseApprovalService,
    PlanStatus,
    PlanNotFoundError,
    InvalidPlanStateError,
    InsufficientFundsError,
)


@pytest.fixture
def service() -> PurchaseApprovalService:
    return PurchaseApprovalService()


@pytest.fixture
def sample_items():
    return [
        {
            "ingredient_name": "cooking_oil",
            "display_name": "Sunflower Oil",
            "quantity": 5.0,
            "unit": "litres",
            "unit_price": 120.0,
            "total_price": 600.0,
        },
        {
            "ingredient_name": "containers",
            "display_name": "Eco Containers",
            "quantity": 50.0,
            "unit": "units",
            "unit_price": 6.0,
            "total_price": 300.0,
        },
    ]


def test_1_create_plan_is_pending_approval(service, sample_items):
    """Created plan must start in PENDING_APPROVAL status."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Replenishing stock for 20 upcoming tiffins",
    )
    assert plan.status == PlanStatus.PENDING_APPROVAL
    assert plan.total_cost == 900.0
    assert len(plan.items) == 2
    assert plan.confirmed_at is None
    assert plan.executed_at is None


def test_2_cannot_execute_unconfirmed_plan(service, sample_items):
    """Executing an unconfirmed (PENDING_APPROVAL) plan must be strictly rejected."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    with pytest.raises(InvalidPlanStateError) as exc_info:
        service.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)
    assert "PENDING_APPROVAL" in str(exc_info.value)
    assert plan.status == PlanStatus.PENDING_APPROVAL


def test_3_confirm_approve_transitions_to_approved(service, sample_items):
    """Explicit owner approval moves plan to APPROVED."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    confirmed = service.confirm_plan(plan.plan_id, decision="APPROVE")
    assert confirmed.status == PlanStatus.APPROVED
    assert confirmed.owner_decision == "APPROVED"
    assert confirmed.confirmed_at is not None


def test_4_confirm_reject_transitions_to_rejected(service, sample_items):
    """Owner rejection moves plan to REJECTED and forbids execution."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    rejected = service.confirm_plan(plan.plan_id, decision="REJECT")
    assert rejected.status == PlanStatus.REJECTED
    assert rejected.owner_decision == "REJECTED"

    with pytest.raises(InvalidPlanStateError):
        service.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)


def test_5_execute_approved_plan_succeeds(service, sample_items):
    """Executing an approved plan with sufficient cash succeeds and transitions to EXECUTED."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    service.confirm_plan(plan.plan_id, decision="APPROVE")

    receipt = service.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)
    assert receipt["status"] == "SIMULATED_ORDER_PLACED"
    assert receipt["amount_paid"] == 900.0
    assert receipt["cash_after"] == 4100.0
    assert plan.status == PlanStatus.EXECUTED
    assert plan.executed_at is not None


def test_6_reject_duplicate_execution(service, sample_items):
    """An already EXECUTED plan cannot be executed again (prevents duplicate orders)."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    service.confirm_plan(plan.plan_id, decision="APPROVE")
    service.execute_plan(plan.plan_id, current_cash=5000.0, safety_reserve=2000.0)

    with pytest.raises(InvalidPlanStateError) as exc:
        service.execute_plan(plan.plan_id, current_cash=4100.0, safety_reserve=2000.0)
    assert "EXECUTED" in str(exc.value)


def test_7_reject_duplicate_confirmation(service, sample_items):
    """A plan cannot be re-confirmed once approved or rejected."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    service.confirm_plan(plan.plan_id, decision="APPROVE")

    with pytest.raises(InvalidPlanStateError):
        service.confirm_plan(plan.plan_id, decision="APPROVE")


def test_8_insufficient_cash_blocks_execution(service, sample_items):
    """Execution must fail if paying the order violates the safety reserve."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    service.confirm_plan(plan.plan_id, decision="APPROVE")

    # Total cash 2500, Reserve 2000 -> Usable 500 < Cost 900
    with pytest.raises(InsufficientFundsError):
        service.execute_plan(plan.plan_id, current_cash=2500.0, safety_reserve=2000.0)

    # Status remains APPROVED, not EXECUTED
    assert plan.status == PlanStatus.APPROVED


def test_9_unknown_plan_raises_not_found(service):
    """Operating on a non-existent plan ID raises PlanNotFoundError."""
    with pytest.raises(PlanNotFoundError):
        service.get_plan("PLAN-NONEXISTENT")

    with pytest.raises(PlanNotFoundError):
        service.confirm_plan("PLAN-NONEXISTENT", decision="APPROVE")

    with pytest.raises(PlanNotFoundError):
        service.execute_plan("PLAN-NONEXISTENT", current_cash=5000.0)


def test_10_invalid_decision_string_raises_value_error(service, sample_items):
    """Invalid decision string raises ValueError."""
    plan = service.create_plan(
        supplier_id="wholesale_mandi",
        supplier_name="Metro Wholesale Mandi",
        items=sample_items,
        total_cost=900.0,
        explanation="Test plan",
    )
    with pytest.raises(ValueError):
        service.confirm_plan(plan.plan_id, decision="MAYBE")
