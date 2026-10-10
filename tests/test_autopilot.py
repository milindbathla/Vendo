"""
Unit and Regression Tests for Alexa Business Autopilot Baseline Decision Engine
================================================================================
Validates all 7 baseline decision criteria:
1. Sufficient inventory -> no purchase required.
2. Inventory shortage + sufficient cash -> procurement recommended.
3. Low cash -> bulk procurement rejected / cash preserved.
4. Bulk procurement wins when discount is high, cash is sufficient, holding risk low.
5. Capacity constraints are correctly reflected in shortage and warnings.
6. Determinism: identical state produces identical recommendation.
7. Explanations: structured bullets, reason, and conversational voice response.
"""
import pytest
from src.models.business import BusinessProfile
from src.simulator import load_business_profiles
from src.decision.autopilot import (
    BusinessAutopilot,
    AutopilotState,
    AutopilotRecommendation,
    AutopilotOption,
)


@pytest.fixture
def home_tiffin_profile() -> BusinessProfile:
    profiles = load_business_profiles()
    return profiles["home_tiffin"]


@pytest.fixture
def cloud_kitchen_profile() -> BusinessProfile:
    profiles = load_business_profiles()
    return profiles["cloud_kitchen"]


def test_1_enough_inventory_no_purchase_required(home_tiffin_profile):
    """Criterion 1: When available inventory >= forecast demand, recommend no purchase."""
    autopilot = BusinessAutopilot(home_tiffin_profile)
    state = AutopilotState(
        inventory_on_hand=30.0,
        total_cash=8000.0,
        forecast_demand=20.0,
        daily_capacity=25.0,
    )
    rec = autopilot.analyze(state=state)

    assert rec.shortage == 0.0
    assert rec.recommended_option.name == "no_purchase"
    assert rec.recommended_option.quantity == 0.0
    assert rec.recommended_option.total_cost == 0.0
    assert "No purchase is needed" in rec.conversational_response or "No purchase" in rec.reason
    assert len(rec.explanation_bullets) >= 2


def test_2_inventory_shortage_with_sufficient_cash_recommends_procurement(home_tiffin_profile):
    """Criterion 2: Inventory shortage + sufficient cash -> procurement is recommended."""
    autopilot = BusinessAutopilot(home_tiffin_profile)
    state = AutopilotState(
        inventory_on_hand=14.0,
        total_cash=8000.0,
        forecast_demand=20.0,
        daily_capacity=25.0,
        cash_reserve_target=2000.0,
    )
    rec = autopilot.analyze(state=state)

    assert rec.shortage == 6.0
    assert rec.recommended_option.name in ["normal_purchase", "bulk_purchase"]
    assert rec.recommended_option.quantity >= 6.0
    assert rec.recommended_option.is_feasible is True
    assert rec.recommended_option.cash_after >= 2000.0
    assert rec.recommended_option.stockout_units == 0.0


def test_3_low_cash_bulk_procurement_does_not_win(home_tiffin_profile):
    """Criterion 3: When cash is tight, bulk procurement is rejected or loses to cash preservation."""
    autopilot = BusinessAutopilot(home_tiffin_profile)
    # Total cash Rs.2,200 with reserve target Rs.2,000 -> usable cash is only Rs.200
    state = AutopilotState(
        inventory_on_hand=14.0,
        total_cash=2200.0,
        forecast_demand=20.0,
        daily_capacity=25.0,
        cash_reserve_target=2000.0,
    )
    rec = autopilot.analyze(state=state)

    # Bulk option must NOT win
    assert rec.recommended_option.name != "bulk_purchase"
    bulk_opt = next(opt for opt in rec.options if opt.name == "bulk_purchase")
    assert bulk_opt.is_feasible is False
    assert "exceeds" in bulk_opt.infeasible_reason.lower()

    # The chosen option must respect the usable cash constraint
    assert rec.recommended_option.total_cost <= 200.0


def test_4_bulk_procurement_can_win_under_favorable_economics(home_tiffin_profile):
    """Criterion 4: Bulk procurement wins when wholesale discount is high, cash is abundant, and spoilage risk is low."""
    from dataclasses import replace
    # Create profile with high discount, low wastage, small bulk threshold
    bulk_fav_profile = replace(
        home_tiffin_profile,
        bulk_order_threshold=20.0,
        bulk_discount=0.40,  # 40% discount
        daily_wastage_rate=0.001,  # near-zero wastage
    )
    autopilot = BusinessAutopilot(bulk_fav_profile)
    state = AutopilotState(
        inventory_on_hand=5.0,
        total_cash=40000.0,
        forecast_demand=20.0,
        daily_capacity=50.0,
        cash_reserve_target=2000.0,
    )
    rec = autopilot.analyze(state=state)

    assert rec.recommended_option.name == "bulk_purchase"
    assert rec.recommended_option.quantity >= 20.0
    assert rec.recommended_option.is_feasible is True
    assert "wholesale discount" in rec.reason.lower()


def test_5_capacity_constraint_reflected_in_recommendation(home_tiffin_profile):
    """Criterion 5: Daily capacity constraint limits achievable demand and triggers explicit warnings."""
    autopilot = BusinessAutopilot(home_tiffin_profile)
    # Demand is 40 orders, but kitchen capacity is capped at 15 orders/day
    state = AutopilotState(
        inventory_on_hand=10.0,
        total_cash=8000.0,
        forecast_demand=40.0,
        daily_capacity=15.0,
        cash_reserve_target=2000.0,
    )
    rec = autopilot.analyze(state=state)

    assert rec.capacity_constrained is True
    assert rec.daily_capacity == 15.0
    assert rec.unfulfillable_demand_due_to_capacity == 25.0
    # Shortage should only cover achievable demand up to capacity (15 - 10 = 5 units)
    assert rec.shortage == 5.0
    assert any("capacity" in b.lower() for b in rec.explanation_bullets)
    assert "capacity" in rec.conversational_response.lower()


def test_6_determinism_identical_input_yields_identical_output(home_tiffin_profile):
    """Criterion 6: Same state and same input always produce 100% deterministic outputs."""
    autopilot = BusinessAutopilot(home_tiffin_profile)
    state = AutopilotState(
        inventory_on_hand=12.0,
        total_cash=7500.0,
        forecast_demand=22.0,
        daily_capacity=25.0,
        cash_reserve_target=2000.0,
    )

    rec1 = autopilot.analyze(state=state)
    rec2 = autopilot.analyze(state=state)

    assert rec1.to_dict() == rec2.to_dict()
    assert rec1.recommended_option.name == rec2.recommended_option.name
    assert rec1.recommended_option.net_score == rec2.recommended_option.net_score
    assert rec1.conversational_response == rec2.conversational_response


def test_7_structured_explanation_and_conversational_response(home_tiffin_profile):
    """Criterion 7: Recommendation contains clear structured reasons and natural conversational response."""
    autopilot = BusinessAutopilot(home_tiffin_profile)
    state = AutopilotState(
        inventory_on_hand=14.0,
        total_cash=8000.0,
        forecast_demand=20.0,
        daily_capacity=25.0,
        cash_reserve_target=2000.0,
    )
    rec = autopilot.analyze(state=state)
    res_dict = rec.to_dict()

    assert "forecast_demand" in res_dict
    assert "available_inventory" in res_dict
    assert "shortage" in res_dict
    assert "usable_cash" in res_dict
    assert "options" in res_dict
    assert len(res_dict["options"]) >= 3
    assert "recommendation" in res_dict
    assert "reason" in res_dict
    assert len(res_dict["explanation_bullets"]) >= 3
    assert len(res_dict["conversational_response"]) > 20

    # Also test owner voice question helper
    owner_q = "Alexa, can I fulfill tomorrow's 20 orders?"
    dialog = autopilot.answer_owner_question(owner_q, state=state)
    assert dialog["question"] == owner_q
    assert "conversational_response" in dialog
    assert dialog["structured_recommendation"]["recommendation"] == "normal_purchase"


def test_multi_profile_cloud_kitchen_what_if_scenarios(cloud_kitchen_profile):
    """Validates that autopilot works seamlessly with other business profiles like cloud_kitchen."""
    autopilot = BusinessAutopilot(cloud_kitchen_profile)
    scenarios = autopilot.run_what_if_scenarios()

    assert len(scenarios) == 4
    for sc in scenarios:
        assert "scenario_name" in sc
        assert "recommended_action" in sc
        assert "estimated_cost" in sc
        assert "cash_after" in sc
        assert sc["cash_after"] >= 0.0
