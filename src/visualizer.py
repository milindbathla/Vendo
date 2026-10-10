"""
Visualizer and Plotting Utility for Small Business Simulator
Generates high-resolution dashboard charts for simulation runs and scenario comparisons.
"""
import os
from typing import Dict, List, Optional
import matplotlib.pyplot as plt

from src.models.simulation import SimulationResult
from src.scenarios.scenario_engine import ScenarioConfig


def plot_simulation_dashboard(
    result: SimulationResult,
    output_path: str = "results/simulation_dashboard.png",
):
    """
    Plots a 5-panel comprehensive dashboard of the simulation timeline.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    days = [m.day for m in result.daily_records]
    cash = [m.ending_cash for m in result.daily_records]
    revenue = [m.revenue for m in result.daily_records]
    profit = [m.daily_profit for m in result.daily_records]
    demand = [m.orders_placed for m in result.daily_records]
    fulfilled = [m.orders_fulfilled for m in result.daily_records]
    capacity = [m.production_capacity for m in result.daily_records]
    inventory = [m.ending_inventory for m in result.daily_records]
    customers = [m.active_customers for m in result.daily_records]

    fig, axes = plt.subplots(5, 1, figsize=(12, 16), sharex=True)
    fig.suptitle(
        f"Value-Chain Simulation Dashboard: {result.display_name} ({result.simulation_days} Days)",
        fontsize=15,
        fontweight="bold",
        y=0.99,
    )

    # 1. Cash Balance & Liquidity
    axes[0].plot(days, cash, color="#2b5c8f", lw=2, label="Ending Cash (Rs.)")
    axes[0].axhline(y=result.starting_cash, color="#888888", linestyle="--", label="Starting Capital")
    axes[0].axhline(y=2000, color="#d9534f", linestyle=":", label="Min Safety Reserve")
    axes[0].set_ylabel("Cash (Rs.)", fontweight="bold")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="upper left")

    # 2. Demand vs. Fulfilled vs. Capacity (Stockouts)
    axes[1].plot(days, demand, color="#e67e22", lw=1.5, label="Customer Orders Demanded")
    axes[1].plot(days, fulfilled, color="#27ae60", lw=2, label="Orders Fulfilled")
    axes[1].plot(days, capacity, color="#c0392b", linestyle="--", label="Daily Capacity Limit")
    axes[1].fill_between(days, fulfilled, demand, where=[d > f for d, f in zip(demand, fulfilled)],
                         color="#e74c3c", alpha=0.3, label="Unfulfilled (Stockout)")
    axes[1].set_ylabel("Units / Orders", fontweight="bold")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="upper left")

    # 3. Inventory Level
    axes[2].plot(days, inventory, color="#8e44ad", lw=2, label="On-Hand Inventory")
    axes[2].set_ylabel("Inventory Units", fontweight="bold")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(loc="upper left")

    # 4. Daily Revenue & Profit
    axes[3].plot(days, revenue, color="#2980b9", lw=1.5, label="Daily Revenue (Rs.)")
    axes[3].plot(days, profit, color="#16a085", lw=1.5, label="Daily Profit (Rs.)")
    axes[3].axhline(y=0, color="#333333", linestyle="-", alpha=0.5)
    axes[3].set_ylabel("Financials (Rs.)", fontweight="bold")
    axes[3].grid(True, alpha=0.3)
    axes[3].legend(loc="upper left")

    # 5. Active Customer Base
    axes[4].plot(days, customers, color="#d35400", lw=2, label="Active Customer Base")
    axes[4].set_xlabel("Simulation Day", fontweight="bold")
    axes[4].set_ylabel("Customers", fontweight="bold")
    axes[4].grid(True, alpha=0.3)
    axes[4].legend(loc="upper left")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    return output_path


def plot_scenario_comparison(
    scenarios: List[ScenarioConfig],
    results: Dict[str, SimulationResult],
    output_path: str = "results/scenario_comparison.png",
):
    """
    Plots side-by-side comparative bars for Revenue, Profit, and Ending Cash.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    names = [s.name.split(":")[0] for s in scenarios if s.scenario_id in results]
    labels = [s.name for s in scenarios if s.scenario_id in results]
    profits = [results[s.scenario_id].net_profit for s in scenarios if s.scenario_id in results]
    cash = [results[s.scenario_id].ending_cash for s in scenarios if s.scenario_id in results]
    revenue = [results[s.scenario_id].total_revenue for s in scenarios if s.scenario_id in results]

    x = range(len(names))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 6))

    rects1 = ax.bar([i - width for i in x], revenue, width, label="Total Revenue (Rs.)", color="#3498db")
    rects2 = ax.bar(x, profits, width, label="Net Profit (Rs.)", color="#2ecc71")
    rects3 = ax.bar([i + width for i in x], cash, width, label="Ending Cash (Rs.)", color="#f39c12")

    ax.set_ylabel("Amount (Rs.)", fontweight="bold")
    ax.set_title("What-If Scenario Comparison (90 Days)", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()
    return output_path
