"""
Phase 0 Regression Test Suite: Business-Agnostic Routing Safety
================================================================
Verifies that all general-purpose paths (PlanRepository, ApprovalService,
SupplierSimulator, agent tools, REST API, MCP tools) cannot route through
legacy tiffin-specific defaults, recipe calculations, or food-only procurement logic.
"""
import json
import pytest
from fastapi.testclient import TestClient

from src.db.connection import get_connection, initialize_database
from src.db.plan_repository import PlanRepository, PlanStatus
from src.db.profile_repository import AdaptiveProfileRepository
from src.decision.approval_service import PurchaseApprovalService
from src.models.adaptive_profile import AdaptiveBusinessProfile
from src.services.supplier_simulator import SupplierCatalogueSimulator
from src.agent.tools import (
    get_business_overview,
    get_supplier_quotes,
    compare_procurement_channels,
    search_nearby_competitors,
    set_active_business_id,
    set_active_profile_repo,
    _active_business_id,
)
from src.server.web_app import app
from src.server.mcp_server import create_mcp_server


@pytest.fixture
def isolated_db():
    """Provides an isolated in-memory DB connection with schema initialized."""
    conn = get_connection(":memory:")
    initialize_database(conn=conn)
    yield conn
    conn.close()


@pytest.fixture
def adaptive_setup(isolated_db):
    """Sets up a clothing retail profile and an auto garage profile in an isolated DB."""
    repo = AdaptiveProfileRepository(db_path=":memory:", shared_conn=isolated_db)

    # 1. Clothing Retail
    clothing_prof = AdaptiveBusinessProfile(
        business_id="biz_regal_menswear",
        display_name="Regal Menswear",
        category="clothing_retail",
        description="Readymade garments and custom shirts",
    )
    clothing_prof.set_fact("selling_price", 850.0)
    clothing_prof.set_fact("unit_material_cost", 380.0)
    clothing_prof.set_fact("daily_capacity", 25.0)
    clothing_prof.set_fact("cash_balance", 40000.0)
    clothing_prof.set_fact("safety_reserve", 10000.0)
    clothing_prof.set_fact("daily_fixed_cost", 800.0)
    clothing_prof.set_fact("current_inventory", 15.0)
    repo.save_profile(clothing_prof)

    # 2. Mechanical Repair Garage
    garage_prof = AdaptiveBusinessProfile(
        business_id="biz_speedy_garage",
        display_name="Speedy Auto Garage",
        category="mechanical_repair",
        description="Two-wheeler and car servicing",
    )
    garage_prof.set_fact("selling_price", 500.0)
    garage_prof.set_fact("unit_material_cost", 220.0)
    garage_prof.set_fact("daily_capacity", 12.0)
    garage_prof.set_fact("cash_balance", 15000.0)
    garage_prof.set_fact("safety_reserve", 3000.0)
    garage_prof.set_fact("daily_fixed_cost", 400.0)
    repo.save_profile(garage_prof)

    # Set as active repo for tools
    set_active_profile_repo(repo)

    yield repo, clothing_prof, garage_prof

    set_active_profile_repo(None)
    set_active_business_id(None)


# -----------------------------------------------------------------------------
# 1. PlanRepository & ApprovalService Non-Food Item Support
# -----------------------------------------------------------------------------

def test_plan_repository_accepts_non_food_item_name(isolated_db):
    """PlanRepository must accept item_name without requiring 'ingredient_name'."""
    repo = PlanRepository(db_path=":memory:", shared_conn=isolated_db)
    plan = repo.create_plan(
        supplier_id="auto_parts_distributor",
        supplier_name="National Auto Spares",
        items=[
            {
                "item_name": "brake_pads",
                "display_name": "Brake Pads Set",
                "quantity": 4.0,
                "unit": "units",
                "unit_price": 220.0,
                "total_price": 880.0,
            }
        ],
        total_cost=880.0,
        explanation="Parts for vehicle servicing",
    )
    assert plan.status == PlanStatus.PENDING_APPROVAL
    loaded_plan = repo.get_plan(plan.plan_id)
    assert len(loaded_plan.items) == 1
    item = loaded_plan.items[0]
    assert item.item_name == "brake_pads"
    assert item.ingredient_name == "brake_pads"
    item_dict = item.to_dict()
    assert item_dict["item_name"] == "brake_pads"
    assert item_dict["ingredient_name"] == "brake_pads"


def test_approval_service_accepts_non_food_item_name(isolated_db):
    """PurchaseApprovalService creates and executes non-food purchase plan."""
    service = PurchaseApprovalService(db_path=":memory:", shared_conn=isolated_db)
    plan = service.create_plan(
        supplier_id="textile_wholesaler",
        supplier_name="Surat Textile Depot",
        items=[
            {
                "item_name": "cotton_fabric_meters",
                "display_name": "Pure Cotton Fabric",
                "quantity": 20.0,
                "unit": "meters",
                "unit_price": 180.0,
                "total_price": 3600.0,
            }
        ],
        total_cost=3600.0,
        explanation="Fabric replenishment for garment store",
    )
    assert plan.status.value == "PENDING_APPROVAL"
    assert plan.items[0].item_name == "cotton_fabric_meters"

    # Confirm and execute
    service.confirm_plan(plan.plan_id, "APPROVE")
    receipt = service.execute_plan(plan.plan_id, current_cash=20000.0, safety_reserve=5000.0)
    assert receipt["status"] == "SIMULATED_ORDER_PLACED"
    assert receipt["amount_paid"] == 3600.0


# -----------------------------------------------------------------------------
# 2. SupplierSimulator Category-Aware Procurement Comparison
# -----------------------------------------------------------------------------

def test_supplier_simulator_compares_textile_for_clothing():
    """Textile goods or clothing category routes to textile_wholesaler, not mandi."""
    sim = SupplierCatalogueSimulator()
    res = sim.compare_procurement_channels(
        needed_items={"plain_shirts": 10.0, "cotton_fabric_meters": 15.0},
        category="clothing_retail",
    )
    assert res["category"] == "clothing_retail"
    assert "textile_wholesaler" in res["suppliers_evaluated"]
    assert res["wholesale"]["supplier_id"] == "textile_wholesaler"
    # Rice or dal must not be in the items
    item_names = [it["ingredient"] for it in res["wholesale"]["items"]]
    assert "plain_shirts" in item_names
    assert "rice" not in item_names


def test_supplier_simulator_compares_auto_parts_for_repair():
    """Auto parts or repair category routes to auto_parts_distributor, not mandi."""
    sim = SupplierCatalogueSimulator()
    res = sim.compare_procurement_channels(
        needed_items={"brake_pads": 4.0, "engine_oil_litre": 5.0},
        category="mechanical_repair",
    )
    assert res["category"] == "mechanical_repair"
    assert "auto_parts_distributor" in res["suppliers_evaluated"]
    assert res["wholesale"]["supplier_id"] == "auto_parts_distributor"
    item_names = [it["ingredient"] for it in res["wholesale"]["items"]]
    assert "brake_pads" in item_names
    assert "dal" not in item_names


# -----------------------------------------------------------------------------
# 3. Agent Tools Adaptive Routing & Competitor Places
# -----------------------------------------------------------------------------

def test_agent_tools_search_nearby_competitors_uses_adaptive_category(adaptive_setup):
    """When an auto repair garage is active, search_nearby_competitors filters by auto repair, not restaurants."""
    repo, clothing_prof, garage_prof = adaptive_setup
    set_active_business_id("biz_speedy_garage")

    # Run tool with default place_types_json
    result = search_nearby_competitors()
    assert result["status"] == "SUCCESS"
    assert "car_repair" in result["place_types_queried"] or "auto_repair" in result["place_types_queried"]
    assert "restaurant" not in result["place_types_queried"]


def test_agent_tools_get_supplier_quotes_routes_to_textile(adaptive_setup):
    """When a clothing store is active, default wholesale quote routes to textile wholesaler."""
    repo, clothing_prof, garage_prof = adaptive_setup
    set_active_business_id("biz_regal_menswear")

    quote = get_supplier_quotes(needed_items_json='{"plain_shirts": 10.0}')
    assert quote["supplier_id"] == "textile_wholesaler"
    assert quote["items"][0]["ingredient"] == "plain_shirts"


# -----------------------------------------------------------------------------
# 4. Web Application Endpoints: Fail-Closed & Adaptive Non-Food Handling
# -----------------------------------------------------------------------------

def test_web_app_state_adaptive_no_tiffin_fallback(adaptive_setup, monkeypatch):
    """GET /api/state for an adaptive profile returns its state; unknown profile returns 404."""
    repo, clothing_prof, garage_prof = adaptive_setup
    monkeypatch.setattr("src.server.web_app.adaptive_repo", repo)

    client = TestClient(app)

    # 1. Known adaptive profile
    resp = client.get("/api/state?business_type=biz_regal_menswear")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_adaptive"] is True
    assert data["profile"]["display_name"] == "Regal Menswear"
    assert data["profile"]["category"] == "clothing_retail"

    # 2. Unknown business profile must fail closed with 404, NEVER defaulting to home_tiffin
    resp_unknown = client.get("/api/state?business_type=biz_completely_unknown_999")
    assert resp_unknown.status_code == 404
    assert "not found" in resp_unknown.json()["detail"].lower()


def test_web_app_evaluate_adaptive_excludes_recipe_shortages(adaptive_setup, monkeypatch):
    """POST /api/evaluate for clothing retail routes through adaptive orchestrator without recipe/food fields."""
    repo, clothing_prof, garage_prof = adaptive_setup
    monkeypatch.setattr("src.server.web_app.adaptive_repo", repo)

    client = TestClient(app)

    payload = {
        "user_question": "Can I take 5 more shirt orders tomorrow?",
        "additional_orders": 5.0,
        "business_type": "biz_regal_menswear",
        "current_demand": 10.0,
        "current_inventory": 15.0,
        "total_cash": 40000.0,
        "daily_capacity": 25.0,
        "safety_reserve": 10000.0,
    }
    resp = client.post("/api/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Must NOT contain recipe shortages (rice, dal, cooking oil)
    assert "recipe_shortages" not in data
    assert data["decision"] == "ACCEPT"
    assert "garments" in data["voice_response"] or "units" in data["voice_response"]

    # Unknown profile must 404
    payload["business_type"] = "biz_nonexistent_xyz"
    resp_unknown = client.post("/api/evaluate", json=payload)
    assert resp_unknown.status_code == 404


# -----------------------------------------------------------------------------
# 5. FastMCP Server: Adaptive-First and Fail-Closed
# -----------------------------------------------------------------------------

def test_mcp_server_adaptive_tools_and_fail_closed(adaptive_setup):
    """MCP server tools check adaptive repo and return NOT_FOUND for unknown businesses."""
    repo, clothing_prof, garage_prof = adaptive_setup
    server = create_mcp_server(profile_repo=repo)

    # 1. get_business_state for clothing store
    fn_state = server._tool_manager._tools["get_business_state"].fn
    state_res = fn_state(business_type="biz_regal_menswear")
    assert state_res["status"] == "SUCCESS"
    assert state_res["category"] == "clothing_retail"
    assert state_res["selling_price"] == 850.0

    # 2. get_business_state for unknown business returns NOT_FOUND
    unknown_state = fn_state(business_type="biz_unregistered_id")
    assert unknown_state["status"] == "NOT_FOUND"

    # 3. get_upcoming_orders for auto repair garage returns job units, not tiffins
    fn_orders = server._tool_manager._tools["get_upcoming_orders"].fn
    orders_res = fn_orders(business_type="biz_speedy_garage")
    assert orders_res["status"] == "SUCCESS"
    assert "jobs" in orders_res["order_type"].lower()
    assert "tiffin" not in orders_res["order_type"].lower()

    # 4. evaluate_order_opportunity for unknown returns REJECT + NOT_FOUND
    fn_eval = server._tool_manager._tools["evaluate_order_opportunity"].fn
    eval_unknown = fn_eval(additional_orders=5.0, business_type="biz_unregistered_id")
    assert eval_unknown["decision"] == "REJECT"
    assert eval_unknown["status"] == "NOT_FOUND"
