"""
Alexa Business Autopilot V2 -- CLI Demo
========================================
Demonstrates the agentic MCP tool orchestration pipeline with 4 test scenarios.

Run with:
    python -m src.autopilot_v2_demo
"""
from src.decision.business_autopilot import BusinessAutopilotV2, DecisionType


SEPARATOR = "=" * 72
THIN_SEP = "-" * 72


def render_opportunity(result, scenario_label=""):
    """Renders a full tool-trace report for one opportunity evaluation."""
    if scenario_label:
        print(f"\n{'#' * 72}")
        print(f"  {scenario_label}")
        print(f"{'#' * 72}")

    print(f"\n{SEPARATOR}")
    print("  ALEXA BUSINESS AUTOPILOT -- V2")
    print(SEPARATOR)
    print(f'\n  USER: "{result.user_question}"')

    # Tool trace
    for t in result.tool_trace:
        print(f"\n  [{t['step']}] {t['tool'].upper().replace('_', ' ')}")
        print(f"      {t['summary']}")

    # Structured analysis summary
    print(f"\n{THIN_SEP}")
    print("  ANALYSIS SUMMARY")
    print(THIN_SEP)
    print(f"  Business           : {result.business_overview.display_name}")
    print(f"  Current Demand     : {result.demand_forecast.current_demand:.0f} orders")
    print(f"  Additional Demand  : {result.demand_forecast.additional_demand:.0f} orders")
    print(f"  Projected Demand   : {result.demand_forecast.projected_demand:.0f} orders")
    print(f"  Daily Capacity     : {result.capacity_status.daily_capacity:.0f} orders/day"
          f" {'[BOTTLENECK]' if result.capacity_status.is_bottleneck else '[OK]'}")
    print(f"  Available Inventory: {result.inventory_status.available_units:.0f} units")
    print(f"  Inventory Required : {result.inventory_status.required_units:.0f} units")
    print(f"  Inventory Shortage : {result.inventory_status.shortage_units:.0f} units")
    print(f"  Total Cash         : Rs.{result.financial_position.total_cash:,.2f}")
    print(f"  Safety Reserve     : Rs.{result.financial_position.safety_reserve:,.2f}")
    print(f"  Usable Cash        : Rs.{result.financial_position.usable_cash:,.2f}")
    if result.inventory_status.shortage_units > 0:
        print(f"  Procurement Needed : {result.procurement_plan.recommended_procurement_units:.0f} units"
              f" ({result.procurement_plan.procurement_mode})")
        print(f"  Procurement Cost   : Rs.{result.procurement_plan.estimated_cost:,.2f}")
        print(f"  Affordable         : {'YES' if result.affordability.is_affordable else 'NO'}")

    # Decision block
    print(f"\n{SEPARATOR}")
    decision_badge = result.decision.value
    print(f"  DECISION: {decision_badge}")
    print(SEPARATOR)
    print(f"\n  Reason: {result.reason}")
    print(f"\n  Fulfillable additional orders  : {result.fulfillable_additional_orders:.0f}")
    print(f"  Unfulfillable additional orders: {result.unfulfillable_additional_orders:.0f}")

    if result.recommendations:
        print(f"\n  RECOMMENDATIONS:")
        for r in result.recommendations:
            print(f"    - {r}")

    if result.explanation_bullets:
        print(f"\n  WHY?")
        for b in result.explanation_bullets:
            print(f"    - {b}")

    print(f"\n  VOICE RESPONSE (ALEXA):")
    print(f'    "{result.voice_response}"')
    print(SEPARATOR + "\n")


def run_demo():
    autopilot = BusinessAutopilotV2()  # Defaults to home_tiffin profile

    # ------------------------------------------------------------------
    # Scenario 1: NORMAL OPPORTUNITY -- small additional demand, no issues
    # ------------------------------------------------------------------
    # home_tiffin: base_daily_demand~30, starting_inventory~50,
    #              daily_capacity~25, starting_capital~10000
    # We use custom state to set up a clean scenario
    result_1 = autopilot.evaluate_opportunity(
        additional_orders=5,
        current_demand=15,
        current_inventory=25,
        total_cash=8000.0,
        daily_capacity=25,
        user_question="Can I take 5 more tiffin orders tomorrow?",
    )
    render_opportunity(result_1, "SCENARIO 1: NORMAL OPPORTUNITY (Easy Accept)")

    # ------------------------------------------------------------------
    # Scenario 2: INVENTORY SHORTAGE -- procurement needed but affordable
    # ------------------------------------------------------------------
    result_2 = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=15,
        current_inventory=18,
        total_cash=8000.0,
        daily_capacity=40,
        user_question="Can I take 20 more tiffin orders tomorrow?",
    )
    render_opportunity(result_2, "SCENARIO 2: INVENTORY SHORTAGE (Accept with Procurement)")

    # ------------------------------------------------------------------
    # Scenario 3: CAPACITY CONSTRAINT -- kitchen cannot handle all orders
    # ------------------------------------------------------------------
    result_3 = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=30,
        current_inventory=36,
        total_cash=8000.0,
        daily_capacity=40,
        user_question="Can I take 20 more tiffin orders tomorrow?",
    )
    render_opportunity(result_3, "SCENARIO 3: CAPACITY CONSTRAINT (Partial Accept)")

    # ------------------------------------------------------------------
    # Scenario 4: CASH CONSTRAINT -- can't afford full procurement
    # ------------------------------------------------------------------
    result_4 = autopilot.evaluate_opportunity(
        additional_orders=20,
        current_demand=15,
        current_inventory=18,
        total_cash=2100.0,
        daily_capacity=40,
        cash_reserve_target=2000.0,
        user_question="Can I take 20 more tiffin orders tomorrow?",
    )
    render_opportunity(result_4, "SCENARIO 4: CASH CONSTRAINT (Partial or Reject)")

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------
    print(f"\n{'=' * 95}")
    print("  SCENARIO COMPARISON SUMMARY")
    print(f"{'=' * 95}")
    header = (
        f"{'Scenario':<35} | {'Decision':<25} | {'Add. Req':>8} | {'Fulfill':>7} | {'Reject':>6}"
    )
    print(header)
    print("-" * len(header))
    for label, res in [
        ("1. Normal Opportunity", result_1),
        ("2. Inventory Shortage", result_2),
        ("3. Capacity Constraint", result_3),
        ("4. Cash Constraint", result_4),
    ]:
        print(
            f"{label:<35} | {res.decision.value:<25} | "
            f"{res.demand_forecast.additional_demand:>6.0f}  | "
            f"{res.fulfillable_additional_orders:>5.0f}  | "
            f"{res.unfulfillable_additional_orders:>4.0f}"
        )
    print("-" * len(header))
    print()


if __name__ == "__main__":
    run_demo()
