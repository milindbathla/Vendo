"""
Unit Tests for Alexa Business Autopilot V2 Orchestrator
========================================================
Validates the 8 baseline decision criteria for the agentic opportunity evaluator.
"""
import pytest
from src.models.business import BusinessProfile
from src.simulator import load_business_profiles
from src.decision.business_autopilot import (
    BusinessAutopilotV2,
    DecisionType,
    OpportunityDecision,
)


@pytest.fixture
def home_tiffin_profile() -> BusinessProfile:
    profiles = load_business_profiles()
    return profiles["home_tiffin"]


@pytest.fixture
def autopilot(home_tiffin_profile) -> BusinessAutopilotV2:
    return BusinessAutopilotV2(profile=home_tiffin_profile)


# -------------------------------------------------------------------------
# Test 1: Acceptable opportunity (inventory + capacity + cash all OK)
# -------------------------------------------------------------------------
def test_1_accept_when_all_resources_sufficient(autopilot):
    """When inventory, capacity, and cash all cover the extra demand -> ACCEPT."""
    result = autopilot.evaluate_opportunity(
        additional_orders=5,
        current_demand=15,
        current_inventory=25,
        total_cash=8000.0,
        daily_capacity=25,
    )
    assert result.decision == DecisionType.ACCEPT
    assert result.fulfillable_additional_orders == 5.0
    assert result.unfulfillable_additional_orders == 0.0
    assert result.inventory_status.shortage_units == 0.0
    assert result.capacity_status.is_bottleneck is False


# -------------------------------------------------------------------------
# Test 2: Inventory shortage detected -> ACCEPT_WITH_PROCUREMENT
# -------------------------------------------------------------------------
def test_2_accept_with_procurement_on_inventory_shortage(autopilot):
    """Inventory insufficient but cash can cover procurement -> ACCEPT_WITH_PROCUREMENT."""
    result = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=15,
        current_inventory=18,
        total_cash=8000.0,
        daily_capacity=40,
    )
    assert result.decision == DecisionType.ACCEPT_WITH_PROCUREMENT
    assert result.inventory_status.shortage_units > 0
    assert result.affordability.is_affordable is True
    assert result.fulfillable_additional_orders == 20.0
    assert result.unfulfillable_additional_orders == 0.0


# -------------------------------------------------------------------------
# Test 3: Capacity constraint detected -> ACCEPT_PARTIALLY
# -------------------------------------------------------------------------
def test_3_partial_accept_on_capacity_constraint(autopilot):
    """Demand exceeds production capacity -> ACCEPT_PARTIALLY."""
    result = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=30,
        current_inventory=36,
        total_cash=8000.0,
        daily_capacity=40,
    )
    assert result.decision == DecisionType.ACCEPT_PARTIALLY
    assert result.capacity_status.is_bottleneck is True
    assert result.fulfillable_additional_orders < 20.0
    assert result.fulfillable_additional_orders > 0.0
    assert result.unfulfillable_additional_orders > 0.0
    # Capacity allows 40, current demand 30, so max 10 additional
    assert result.fulfillable_additional_orders == 10.0


# -------------------------------------------------------------------------
# Test 4: Cash constraint detected -> ACCEPT_PARTIALLY or REJECT
# -------------------------------------------------------------------------
def test_4_cash_constraint_limits_procurement(autopilot):
    """Usable cash is too low for full procurement -> partial or reject."""
    result = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=15,
        current_inventory=18,
        total_cash=2100.0,
        daily_capacity=40,
        cash_reserve_target=2000.0,
    )
    # With only Rs.100 usable cash, full procurement is unaffordable
    assert result.decision in (DecisionType.ACCEPT_PARTIALLY, DecisionType.REJECT)
    assert result.affordability.is_affordable is False
    assert result.financial_position.usable_cash <= 200.0


# -------------------------------------------------------------------------
# Test 5: Procurement recommendation is deterministic
# -------------------------------------------------------------------------
def test_5_procurement_is_deterministic(autopilot):
    """Same inputs always yield same procurement plan."""
    r1 = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=15,
        current_inventory=18,
        total_cash=8000.0,
        daily_capacity=40,
    )
    r2 = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=15,
        current_inventory=18,
        total_cash=8000.0,
        daily_capacity=40,
    )
    assert r1.procurement_plan.recommended_procurement_units == r2.procurement_plan.recommended_procurement_units
    assert r1.procurement_plan.procurement_mode == r2.procurement_plan.procurement_mode
    assert r1.procurement_plan.estimated_cost == r2.procurement_plan.estimated_cost


# -------------------------------------------------------------------------
# Test 6: Final decision is deterministic
# -------------------------------------------------------------------------
def test_6_final_decision_is_deterministic(autopilot):
    """Same state always returns identical decision and voice response."""
    r1 = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=30,
        current_inventory=36,
        total_cash=8000.0,
        daily_capacity=40,
    )
    r2 = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=30,
        current_inventory=36,
        total_cash=8000.0,
        daily_capacity=40,
    )
    assert r1.to_dict() == r2.to_dict()


# -------------------------------------------------------------------------
# Test 7: Voice response is generated and non-empty
# -------------------------------------------------------------------------
def test_7_voice_response_generated(autopilot):
    """Every decision produces a non-trivial voice response string."""
    for add_orders, inv, cash, cap in [
        (5, 25, 8000, 25),    # ACCEPT
        (20, 18, 8000, 40),   # ACCEPT_WITH_PROCUREMENT
        (20, 36, 8000, 40),   # ACCEPT_PARTIALLY (capacity)
        (20, 18, 2100, 40),   # ACCEPT_PARTIALLY / REJECT (cash)
    ]:
        result = autopilot.evaluate_opportunity(
            additional_orders=add_orders,
            current_demand=15,
            current_inventory=inv,
            total_cash=cash,
            daily_capacity=cap,
        )
        assert len(result.voice_response) > 20, f"Voice response too short for scenario add={add_orders}"
        assert len(result.explanation_bullets) >= 2, f"Too few explanation bullets for scenario add={add_orders}"
        assert len(result.recommendations) >= 1, f"No recommendations for scenario add={add_orders}"


# -------------------------------------------------------------------------
# Test 8: Tool trace has all 7 steps
# -------------------------------------------------------------------------
def test_8_tool_trace_has_all_seven_steps(autopilot):
    """Tool trace records all 7 conceptual MCP tool calls."""
    result = autopilot.evaluate_opportunity(
        additional_orders=10,
        current_demand=15,
        current_inventory=20,
        total_cash=5000.0,
        daily_capacity=30,
    )
    assert len(result.tool_trace) == 7
    tool_names = [t["tool"] for t in result.tool_trace]
    assert "get_business_overview" in tool_names
    assert "forecast_demand" in tool_names
    assert "analyze_inventory" in tool_names
    assert "get_capacity_status" in tool_names
    assert "get_financial_position" in tool_names
    assert "analyze_purchase_affordability" in tool_names
    assert "optimize_procurement_plan" in tool_names


# -------------------------------------------------------------------------
# Test 9: REJECT when capacity fully utilized
# -------------------------------------------------------------------------
def test_9_reject_when_capacity_fully_utilized(autopilot):
    """When current demand already equals capacity, reject all additional."""
    result = autopilot.evaluate_opportunity(
        additional_orders=10,
        current_demand=40,
        current_inventory=50,
        total_cash=8000.0,
        daily_capacity=40,
    )
    assert result.decision == DecisionType.REJECT
    assert result.fulfillable_additional_orders == 0.0
    assert result.unfulfillable_additional_orders == 10.0


# -------------------------------------------------------------------------
# Test 10: to_dict serialization
# -------------------------------------------------------------------------
def test_10_to_dict_serialization(autopilot):
    """to_dict() returns a complete, JSON-serializable dictionary."""
    result = autopilot.evaluate_opportunity(
        additional_orders=5,
        current_demand=15,
        current_inventory=25,
        total_cash=8000.0,
        daily_capacity=25,
    )
    d = result.to_dict()
    required_keys = [
        "decision", "user_question", "business", "current_demand",
        "additional_demand", "projected_demand", "available_inventory",
        "inventory_shortage", "daily_capacity", "capacity_shortage",
        "total_cash", "usable_cash", "procurement_units", "procurement_cost",
        "fulfillable_additional_orders", "unfulfillable_additional_orders",
        "reason", "recommendations", "explanation_bullets", "voice_response",
        "tool_trace",
    ]
    for key in required_keys:
        assert key in d, f"Missing key: {key}"
