"""
Integration Tests for FastAPI Web Server & API Endpoints
=========================================================
Validates:
- Health probe (/health)
- Business state endpoint (/api/state)
- Decision orchestrator (/api/evaluate) with recipe shortages and auto-generated plan
- Two-phase approval and execution workflow via API
- Static web interface rendering (/)
"""
import os
import tempfile
import pytest
from starlette.testclient import TestClient

# Ensure DATABASE_PATH is isolated before importing web_app
if "DATABASE_PATH" not in os.environ:
    _temp_dir = tempfile.mkdtemp(prefix="web_api_test_")
    os.environ["DATABASE_PATH"] = os.path.join(_temp_dir, "test_isolated.sqlite3")

from src.db.connection import initialize_database, seed_business_state
from src.decision.approval_service import PurchaseApprovalService
from src.db.state_repository import BusinessStateRepository
import src.server.web_app as web_app
from src.server.web_app import app


@pytest.fixture
def isolated_web_db(tmp_path, monkeypatch):
    """Provides a fresh isolated database for each web API test."""
    temp_db = str(tmp_path / "test_web_api.sqlite3")
    initialize_database(temp_db)
    seed_business_state(temp_db)
    svc = PurchaseApprovalService(db_path=temp_db)
    repo = BusinessStateRepository(temp_db)
    monkeypatch.setattr(web_app, "_DB_PATH", temp_db)
    monkeypatch.setattr(web_app, "approvals_service", svc)
    monkeypatch.setattr(web_app, "state_repo", repo)
    monkeypatch.setenv("DATABASE_PATH", temp_db)
    return temp_db


@pytest.fixture
def client(isolated_web_db):
    return TestClient(app)



def test_1_health_endpoint(client):
    """Health endpoint must confirm healthy status, version, and MCP enablement."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["mcp_enabled"] is True
    assert "simulation_notice" in data


def test_2_state_endpoint(client):
    """State endpoint returns business profile and pending plans."""
    res = client.get("/api/state?business_type=home_tiffin")
    assert res.status_code == 200
    data = res.json()
    assert data["profile"]["business_type"] == "home_tiffin"
    assert "simulation_notice" in data


def test_3_evaluate_scenario_1_generates_approval_plan(client):
    """Evaluating 20 orders generates recipe shortage and PENDING_APPROVAL purchase plan."""
    payload = {
        "user_question": "Can I take 20 more tiffin orders tomorrow?",
        "additional_orders": 20.0,
        "business_type": "home_tiffin",
        "current_demand": 15.0,
        "current_inventory": 18.0,
        "total_cash": 8000.0,
        "daily_capacity": 40.0,
        "safety_reserve": 2000.0,
    }
    res = client.post("/api/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["decision"] == "ACCEPT_WITH_PROCUREMENT"
    assert "voice_response" in data
    assert len(data["voice_response"]) > 10
    assert len(data["tool_trace"]) >= 5

    # Check multi-ingredient recipe shortage
    assert "recipe_shortages" in data
    assert data["recipe_shortages"]["has_shortage"] is True

    # Check generated purchase plan
    plan = data["purchase_plan"]
    assert plan is not None
    assert plan["status"] == "PENDING_APPROVAL"
    assert plan["total_cost"] > 0


def test_4_full_approval_and_execution_lifecycle_via_api(client):
    """Full lifecycle: evaluate -> confirm (APPROVE) -> execute -> duplicate blocked."""
    # Step 1: Evaluate
    eval_res = client.post("/api/evaluate", json={"additional_orders": 20.0})
    plan_id = eval_res.json()["purchase_plan"]["plan_id"]

    # Step 2: Try execute unapproved plan -> 400 Bad Request
    fail_exec = client.post("/api/execute_plan", json={"plan_id": plan_id, "current_cash": 8000.0})
    assert fail_exec.status_code == 400

    # Step 3: Confirm with APPROVE
    conf_res = client.post("/api/confirm_plan", json={"plan_id": plan_id, "decision": "APPROVE"})
    assert conf_res.status_code == 200
    assert conf_res.json()["plan"]["status"] == "APPROVED"

    # Step 4: Execute approved plan
    exec_res = client.post("/api/execute_plan", json={"plan_id": plan_id, "current_cash": 8000.0})
    assert exec_res.status_code == 200
    receipt = exec_res.json()["receipt"]
    assert receipt["status"] == "SIMULATED_ORDER_PLACED"
    assert receipt["cash_after"] < 8000.0

    # Step 5: Duplicate execution attempt -> 400 Bad Request
    dup_exec = client.post("/api/execute_plan", json={"plan_id": plan_id, "current_cash": 7400.0})
    assert dup_exec.status_code == 400


def test_5_backend_root_endpoint(client):
    """Root GET serves backend service status and metadata."""
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "Alexa Business Autopilot Backend"
    assert data["mode"] == "backend_only"
    assert data["mcp_enabled"] is True


def test_6_evaluate_capacity_constrained_scenario_3_api(client):
    """
    Capacity-constrained opportunity evaluation via API:
    Current demand = 30, Additional = 20, Capacity = 40, Inventory = 36.
    Ensures:
    - Only 10 additional orders accepted (fulfilled demand = 40 meals).
    - Recipe shortages calculated for 40 meals (not 50).
    - Purchase plan created for accepted orders only.
    """
    payload = {
        "user_question": "Can I take 20 more tiffin orders tomorrow?",
        "additional_orders": 20.0,
        "business_type": "home_tiffin",
        "current_demand": 30.0,
        "current_inventory": 36.0,
        "total_cash": 8000.0,
        "daily_capacity": 40.0,
        "safety_reserve": 2000.0,
    }
    res = client.post("/api/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["decision"] == "ACCEPT_PARTIALLY"
    assert data["projected_demand"] == 50.0
    assert data["fulfilled_demand"] == 40.0
    assert data["fulfillable_additional_orders"] == 10.0
    assert data["unfulfillable_additional_orders"] == 10.0
    assert data["inventory_shortage"] == 4.0
    assert data["procurement_units"] == 4.0

    # Recipe breakdown must be grounded in fulfilled meals (40), not projected (50)
    recipe = data["recipe_shortages"]
    assert recipe["meals_count"] == 40.0
    assert recipe["ingredients"]["rice"]["required"] == 6.0  # 40 * 0.15 kg
    assert recipe["ingredients"]["dal"]["required"] == 3.2   # 40 * 0.08 kg
    assert recipe["ingredients"]["cooking_oil"]["required"] == 1.6  # 40 * 0.04 L
    assert recipe["ingredients"]["containers"]["required"] == 40.0  # 40 * 1.0 units

    # Generated purchase plan must reflect the accepted orders
    plan = data["purchase_plan"]
    assert plan is not None
    assert plan["status"] == "PENDING_APPROVAL"
    assert "10 additional tiffin orders" in plan["explanation"]
    assert "40 total meals" in plan["explanation"]


def test_7_capacity_exhausted_rejects_and_creates_no_plan(client):
    """When kitchen is at 100% capacity, reject extra orders and create no purchase plan."""
    payload = {
        "user_question": "Can I take 10 more orders?",
        "additional_orders": 10.0,
        "business_type": "home_tiffin",
        "current_demand": 40.0,
        "current_inventory": 40.0,
        "total_cash": 8000.0,
        "daily_capacity": 40.0,
        "safety_reserve": 2000.0,
    }
    res = client.post("/api/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["decision"] == "REJECT"
    assert data["fulfillable_additional_orders"] == 0.0
    assert data["unfulfillable_additional_orders"] == 10.0
    assert data["purchase_plan"] is None
