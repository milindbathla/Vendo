"""
Alexa Business Autopilot — Baseline CLI Demo
============================================
Demonstrates the voice-first decision loop:
Demand -> Business State -> Financial Constraints -> Procurement Options -> Explainable Recommendation.

Run with:
    python -m src.autopilot_demo
"""
import os
import matplotlib.pyplot as plt

from src.models.business import BusinessProfile
from src.simulator import load_business_profiles
from src.decision.autopilot import BusinessAutopilot, AutopilotState, AutopilotRecommendation


def render_cli_recommendation(rec: AutopilotRecommendation):
    """Prints a structured, human-readable terminal output matching the product concept."""
    print("\n" + "=" * 65)
    print("        ALEXA BUSINESS AUTOPILOT -- BASELINE DECISION MODEL")
    print("=" * 65)
    print(f" Business Category   : {rec.display_name}")
    print(f" Tomorrow's Demand   : {rec.forecast_demand:.0f} orders")
    print(f" Available Inventory : {rec.available_inventory:.0f} units")
    print(f" Daily Capacity Limit: {rec.daily_capacity:.0f} orders/day {'[BOTTLENECK!]' if rec.capacity_constrained else '[ADEQUATE]'}")
    print(f" Inventory Shortage  : {rec.shortage:.0f} units")
    print(f" Total Liquid Cash   : Rs.{rec.total_cash:,.2f}")
    print(f" Usable Cash Buffer  : Rs.{rec.usable_cash:,.2f} (above Rs.{rec.cash_reserve_target:,.0f} safety reserve)")
    print("-" * 65)
    print(" EVALUATED PROCUREMENT OPTIONS")
    print("-" * 65)

    for idx, opt in enumerate(rec.options, 1):
        feasible_badge = "[FEASIBLE]" if opt.is_feasible else f"[BLOCKED: {opt.infeasible_reason}]"
        print(f" [{idx}] {opt.display_name} {feasible_badge}")
        print(f"     Order Quantity   : {opt.quantity:.0f} units @ Rs.{opt.unit_cost:.2f}/unit")
        print(f"     Procurement Cost : Rs.{opt.total_cost:,.2f}")
        print(f"     Cash Remaining   : Rs.{opt.cash_after:,.2f}")
        print(f"     Unfulfilled Risk : {opt.stockout_units:.0f} units ({opt.stockout_risk_pct:.1f}% risk)")
        print(f"     Cash Stress      : {opt.cash_stress_pct:.1f}% of usable budget")
        print(f"     Notes            : {opt.description}")
        print()

    print("=" * 65)
    print(" AUTOPILOT RECOMMENDATION")
    print("=" * 65)
    rec_opt = rec.recommended_option
    print(f" ACTION: {rec_opt.display_name.upper()} ({rec_opt.quantity:.0f} UNITS for Rs.{rec_opt.total_cost:,.2f})")
    print(f" STATUS: {rec.reason}")
    print("\n WHY?")
    for bullet in rec.explanation_bullets:
        print(f"  - {bullet}")
    print("-" * 65)
    print(" VOICE RESPONSE (ALEXA):")
    print(f'  "{rec.conversational_response}"')
    print("=" * 65 + "\n")


def render_what_if_table(scenarios_data):
    """Renders a clean comparison table of baseline what-if scenarios."""
    print("=" * 105)
    print(" WHAT-IF SENSITIVITY ANALYSIS (How Autopilot Adapts to Business Shocks)")
    print("=" * 105)
    header = (
        f"{'Scenario':<28} | {'Demand':<7} | {'Stock':<6} | {'Shortage':<9} | "
        f"{'Action Recommended':<24} | {'Cost (Rs)':<10} | {'Cash After':<11}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)
    for sc in scenarios_data:
        line = (
            f"{sc['scenario_name']:<28} | "
            f"{sc['forecast_demand']:>5.0f} o | "
            f"{sc['available_inventory']:>4.0f} u | "
            f"{sc['shortage']:>6.0f} u | "
            f"{sc['recommended_action']:<24} | "
            f"Rs.{sc['estimated_cost']:>7,.0f} | "
            f"Rs.{sc['cash_after']:>8,.0f}"
        )
        print(line)
    print(sep)
    print()


def plot_autopilot_dashboard(rec: AutopilotRecommendation, output_path: str = "results/autopilot_dashboard.png"):
    """Generates an intuitive chart visualizing Demand vs Inventory vs Capacity and procurement cost."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel 1: Demand vs Inventory vs Capacity
    labels = ["Available\nInventory", "Forecast\nDemand", "Daily\nCapacity", "Shortage\nto Cover"]
    values = [rec.available_inventory, rec.forecast_demand, rec.daily_capacity, rec.shortage]
    colors = ["#2b5c8f", "#e67e22", "#27ae60", "#e74c3c"]
    bars = ax1.bar(labels, values, color=colors, width=0.55)
    ax1.set_title("Operational Feasibility Check (Tomorrow)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Units / Orders", fontweight="bold")
    ax1.grid(axis="y", linestyle="--", alpha=0.3)
    for bar in bars:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2.0, h + 0.5, f"{h:.0f}", ha="center", va="bottom", fontweight="bold")

    # Panel 2: Procurement Options Comparison
    opt_names = [opt.display_name.replace(" ", "\n") for opt in rec.options]
    costs = [opt.total_cost for opt in rec.options]
    cash_left = [opt.cash_after for opt in rec.options]

    x = range(len(opt_names))
    width = 0.35
    ax2.bar([i - width / 2 for i in x], costs, width=width, label="Procurement Cost (Rs.)", color="#d9534f")
    ax2.bar([i + width / 2 for i in x], cash_left, width=width, label="Remaining Cash (Rs.)", color="#5bc0de")
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(opt_names, fontsize=9)
    ax2.set_title("Financial Options Tradeoff (Spend vs Cash Left)", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Rupees (Rs.)", fontweight="bold")
    ax2.grid(axis="y", linestyle="--", alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    return output_path


def run_demo():
    profiles = load_business_profiles()
    # Flagship demo business: home_tiffin
    profile = profiles["home_tiffin"]
    autopilot = BusinessAutopilot(profile)

    # 1. Baseline Single-Day Decision Demo
    # Scenario: 20 tiffin orders expected tomorrow, currently 14 units available, Rs.8,000 cash
    demo_state = AutopilotState(
        inventory_on_hand=14.0,
        total_cash=8000.0,
        forecast_demand=20.0,
        daily_capacity=25.0, # 25 orders/day
        cash_reserve_target=2000.0,
    )

    recommendation = autopilot.analyze(state=demo_state)
    render_cli_recommendation(recommendation)

    # 2. Simulated Alexa Owner Voice Question
    print("=" * 65)
    print(" SIMULATED OWNER VOICE INTERACTION")
    print("=" * 65)
    owner_q = "Alexa, I have 20 tiffin orders tomorrow. Can I fulfill them?"
    print(f'Owner: "{owner_q}"')
    voice_dialog = autopilot.answer_owner_question(owner_q, state=demo_state)
    print(f'Alexa: "{voice_dialog["conversational_response"]}"')
    print("=" * 65 + "\n")

    # 3. What-If Scenarios
    what_if_results = autopilot.run_what_if_scenarios(base_state=demo_state)
    render_what_if_table(what_if_results)

    # 4. Generate Visual Chart
    plot_path = plot_autopilot_dashboard(recommendation, "results/autopilot_dashboard.png")
    print(f"[OK] Generated Decision Chart: {plot_path}\n")


if __name__ == "__main__":
    run_demo()
