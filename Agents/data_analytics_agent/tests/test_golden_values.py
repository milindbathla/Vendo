"""Test golden values against Maa Ki Rasoi demo dataset."""
import pytest
from business_intel.tools.context_tools import get_business_overview
from business_intel.tools.analytics_tools import (
    analyze_business_performance,
    analyze_product_profitability,
)


def test_golden_cash_and_tomorrow_orders():
    env = get_business_overview()
    assert env.ok is True
    data = env.data

    # Cash balance ₹12,000
    assert data["cash_position"]["current_balance"] == 12000.0

    # Tomorrow's confirmed meals = 20
    assert data["tomorrow_load"]["confirmed_meals"] == 20
    assert data["tomorrow_load"]["free_slots"] == 14

    # Shortages identified
    shortages = data["shortage_risks"]
    shortage_items = [s["item_name"] for s in shortages]
    assert any("Tiffin container" in name for name in shortage_items)
    assert any("sunflower oil" in name.lower() for name in shortage_items)


def test_golden_performance_metrics_30d():
    env = analyze_business_performance(period="last_30d")
    assert env.ok is True
    metrics = env.data["metrics"]

    assert metrics["units_sold"] == 639
    assert metrics["revenue"] == 55320.0
    assert metrics["net_profit"] == 9573.74
    assert metrics["net_profit_margin_pct"] == 17.3


def test_golden_product_profitability():
    env = analyze_product_profitability(period="last_30d")
    assert env.ok is True
    data = env.data

    # Bottom-up unit economics
    assert data["realized_price"] == 86.24
    assert data["ingredient_cogs"] == 46.80
    assert data["packaging_cogs"] == 4.40
    assert data["unit_cogs"] == 51.20
    assert data["contribution_margin"] == 35.04
    assert data["breakeven_units_daily"] == 18.2

