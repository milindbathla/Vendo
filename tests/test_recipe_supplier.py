"""
Unit Tests for Multi-Ingredient Recipe & Supplier Simulator
===========================================================
Validates:
- Deterministic tiffin ingredient breakdown (rice, dal, oil, packaging)
- Ingredient shortage detection
- Supplier catalogue pricing, volume tiers, and MOQ enforcement
- Express vs Wholesale comparison
- Presence of simulated disclaimer notices
"""
import pytest
from src.models.recipe import TiffinRecipeManager
from src.services.supplier_simulator import SupplierCatalogueSimulator, SIMULATION_NOTICE


@pytest.fixture
def recipe_mgr() -> TiffinRecipeManager:
    return TiffinRecipeManager()


@pytest.fixture
def supplier_sim() -> SupplierCatalogueSimulator:
    return SupplierCatalogueSimulator()


def test_1_recipe_breakdown_20_tiffins(recipe_mgr):
    """20 tiffins must accurately require 3.0kg rice, 1.6kg dal, 0.8L oil, 20 containers."""
    needs = recipe_mgr.calculate_ingredient_needs(20.0)
    assert needs["rice"]["quantity"] == 3.0  # 20 * 0.15 kg
    assert needs["dal"]["quantity"] == 1.6   # 20 * 0.08 kg
    assert needs["cooking_oil"]["quantity"] == 0.8  # 20 * 0.04 L
    assert needs["containers"]["quantity"] == 20.0  # 20 * 1 unit


def test_2_shortage_evaluation_detects_missing(recipe_mgr):
    """Detects missing ingredients when current stocks are below requirements."""
    current_stocks = {
        "rice": 5.0,        # Has 5.0kg, needs 3.0kg -> No shortage
        "dal": 2.0,         # Has 2.0kg, needs 1.6kg -> No shortage
        "cooking_oil": 0.2, # Has 0.2L, needs 0.8L -> Shortage 0.6L
        "containers": 5.0,  # Has 5 units, needs 20 -> Shortage 15 units
    }
    eval_res = recipe_mgr.evaluate_shortages(20.0, current_stocks)

    assert eval_res["has_shortage"] is True
    assert eval_res["ingredients"]["rice"]["is_short"] is False
    assert eval_res["ingredients"]["dal"]["is_short"] is False
    assert eval_res["ingredients"]["cooking_oil"]["is_short"] is True
    assert eval_res["ingredients"]["cooking_oil"]["missing"] == 0.6
    assert eval_res["ingredients"]["containers"]["is_short"] is True
    assert eval_res["ingredients"]["containers"]["missing"] == 15.0


def test_3_supplier_quote_enforces_moq_and_disclaimer(supplier_sim):
    """Wholesale supplier enforces MOQs on small quantities and includes simulation notice."""
    needed = {
        "cooking_oil": 0.6,  # MOQ is 5.0 L
        "containers": 15.0,  # MOQ is 50.0 units
    }
    quote = supplier_sim.get_quote("wholesale_mandi", needed)

    assert quote.simulation_notice == SIMULATION_NOTICE
    # Oil MOQ enforced
    oil_item = next(it for it in quote.items if it.ingredient_name == "cooking_oil")
    assert oil_item.order_qty == 5.0
    assert oil_item.moq_applied is True

    # Containers MOQ enforced
    cont_item = next(it for it in quote.items if it.ingredient_name == "containers")
    assert cont_item.order_qty == 50.0
    assert cont_item.moq_applied is True


def test_4_express_vs_wholesale_comparison(supplier_sim):
    """Express supplier has shorter lead time (2h vs 24h) and different cost profile."""
    needed = {"rice": 10.0, "dal": 5.0, "cooking_oil": 5.0}
    comp = supplier_sim.compare_procurement_channels(needed)

    assert comp["simulation_notice"] == SIMULATION_NOTICE
    assert comp["wholesale"]["lead_time_hours"] == 24
    assert comp["express"]["lead_time_hours"] == 2
    assert comp["lead_time_difference_hours"] == 22
    assert "cost_difference" in comp
