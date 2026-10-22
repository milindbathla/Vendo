"""
Frontend + Backend Integration & Contract Verification Tests
============================================================
Tests end-to-end integration between the static frontend assets and FastAPI backend:
1. Static files mounting and delivery (/app/, /app/alexa.html, /app/styles.css, /app/app.js)
2. Content negotiation and root endpoint redirection
3. CORS middleware headers
4. Onboarding form submission contract (/api/onboarding/setup & /api/business/profile)
5. Archetype normalization and persistence into AdaptiveProfileRepository
6. State restoration (/api/onboarding/profile) and demo business integration (/api/demo/business)
7. Input validation error handling (empty fields, negative reserves, invalid capacities)
8. Tiffin Service REST endpoints (/api/tiffin/orders, capacity, inventory, evaluate)
9. MCP tools registration for tiffin management
"""
import pytest
from starlette.testclient import TestClient
from src.server.web_app import app, mcp_server, tiffin_service, adaptive_repo


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


# -----------------------------------------------------------------------------
# 1. Static Files & Routing Integration
# -----------------------------------------------------------------------------
def test_static_frontend_onboarding_served(client):
    """Verifies that the onboarding page is served at /app/ and /app/index.html."""
    res = client.get("/app/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "setupForm" in res.text
    assert "Activate Alexa+" in res.text


def test_static_frontend_alexa_simulator_served(client):
    """Verifies that the Alexa+ simulator page is served at /app/alexa.html."""
    res = client.get("/app/alexa.html")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "chatScroll" in res.text
    assert "Alexa+" in res.text


def test_static_frontend_assets_served(client):
    """Verifies that JavaScript and CSS assets load correctly."""
    css_res = client.get("/app/styles.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers.get("content-type", "")

    js_res = client.get("/app/app.js")
    assert js_res.status_code == 200
    assert "javascript" in js_res.headers.get("content-type", "")


def test_root_endpoint_content_negotiation(client):
    """Root GET returns JSON for API clients and redirects browsers to /app/."""
    # API client requesting JSON
    api_res = client.get("/", headers={"accept": "application/json"})
    assert api_res.status_code == 200
    data = api_res.json()
    assert data["service"] == "Alexa Business Autopilot Backend"
    assert data["mode"] == "backend_only"

    # Browser requesting HTML
    browser_res = client.get("/", headers={"accept": "text/html,application/xhtml+xml"})
    assert browser_res.status_code == 302
    assert browser_res.headers["location"] == "/app/"


def test_cors_headers_present(client):
    """Verifies CORS headers allow local multi-port or cross-origin dev servers."""
    res = client.get("/health", headers={"origin": "http://localhost:3000"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res.headers.get("access-control-allow-credentials") == "true"


# -----------------------------------------------------------------------------
# 2. Onboarding API Contract & Persistence
# -----------------------------------------------------------------------------
def test_onboarding_setup_tiffin_success(client):
    """Verifies onboarding submission for cloud-kitchen / tiffin business."""
    payload = {
        "business_name": "Maa Ki Rasoi Cloud Kitchen",
        "owner_name": "Sunita Sharma",
        "archetype": "Tiffin / cloud kitchen",
        "phone": "+91 98765 43210",
        "locality": "Kakadeo",
        "city": "Kanpur",
        "min_cash_buffer": 5000.0,
        "max_per_day": 45.0,
        "order_cutoff": "20:00",
        "cooking_start": "09:00",
        "delivery_radius_km": 6.5,
        "fast_delivery_fee": 35.0,
        "language": "Hinglish",
        "connected_services": ["Amazon Pay", "Zoho Books"],
    }
    res = client.post("/api/onboarding/setup", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["business_id"] == "home_tiffin"
    assert data["category"] == "home_tiffin"
    assert data["onboarding_completed"] is True
    assert data["profile"]["facts"]["owner_name"] == "Sunita Sharma"
    assert data["profile"]["facts"]["daily_capacity"] == 45.0


def test_onboarding_setup_alias_endpoint(client):
    """Verifies /api/business/profile alias endpoint."""
    payload = {
        "business_name": "Gupta Kirana General Store",
        "owner_name": "Ramesh Gupta",
        "archetype": "Kirana / general store",
        "min_cash_buffer": 10000.0,
        "max_per_day": 100.0,
    }
    res = client.post("/api/business/profile", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["category"] == "retail_kirana"


def test_onboarding_profile_retrieval(client):
    """Verifies profile retrieval for frontend page-refresh state restoration."""
    res = client.get("/api/onboarding/profile?business_id=home_tiffin")
    assert res.status_code == 200
    data = res.json()
    assert data["business_id"] == "home_tiffin"
    assert data["category"] == "home_tiffin"
    assert "owner_name" in data["facts"]
    assert "daily_capacity" in data["facts"]


def test_demo_business_supports_onboarded_business(client):
    """Verifies that /api/demo/business loads the onboarded profile when requested."""
    res = client.get("/api/demo/business?business_id=home_tiffin")
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "home_tiffin"


def test_onboarding_validation_errors(client):
    """Verifies that invalid onboarding payloads return 422 with meaningful details."""
    # Empty business name
    res1 = client.post("/api/onboarding/setup", json={
        "business_name": "",
        "owner_name": "Valid Owner",
        "archetype": "Bakery",
    })
    assert res1.status_code == 422

    # Negative cash reserve
    res2 = client.post("/api/onboarding/setup", json={
        "business_name": "Bakery Delights",
        "owner_name": "Valid Owner",
        "archetype": "Bakery",
        "min_cash_buffer": -500.0,
    })
    assert res2.status_code == 422

    # Zero or negative max daily capacity
    res3 = client.post("/api/onboarding/setup", json={
        "business_name": "Bakery Delights",
        "owner_name": "Valid Owner",
        "archetype": "Bakery",
        "max_per_day": 0.0,
    })
    assert res3.status_code == 422


# -----------------------------------------------------------------------------
# 3. Tiffin Service REST Endpoints
# -----------------------------------------------------------------------------
def test_tiffin_orders_and_lifecycle_api(client):
    """Verifies creating, listing, and cancelling tiffin orders via REST API."""
    order_id = "test_order_audit_101"
    # Create order
    create_res = client.post("/api/tiffin/orders", json={
        "order_id": order_id,
        "customer_id": "cust_audit_1",
        "date": "2026-10-25",
        "units": 4,
        "unit_price": 90.0,
        "business_id": "home_tiffin",
    })
    assert create_res.status_code == 200
    created = create_res.json()["order"]
    assert created["order_id"] == order_id
    assert created["units"] == 4
    assert created["amount"] == 360.0

    # List orders
    list_res = client.get("/api/tiffin/orders?date=2026-10-25&business_id=home_tiffin")
    assert list_res.status_code == 200
    orders = list_res.json()["orders"]
    assert any(o["order_id"] == order_id for o in orders)

    # Cancel order
    cancel_res = client.post(f"/api/tiffin/orders/{order_id}/cancel?business_id=home_tiffin")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["new_status"] == "cancelled"


def test_tiffin_capacity_and_inventory_endpoints(client):
    """Verifies kitchen capacity and inventory status endpoints."""
    # Capacity
    cap_res = client.get("/api/tiffin/capacity?date=2026-10-25&business_id=home_tiffin")
    assert cap_res.status_code == 200
    cap_data = cap_res.json()
    assert "max_meals" in cap_data
    assert "booked_meals" in cap_data
    assert "remaining_capacity" in cap_data

    # Inventory
    inv_res = client.get("/api/tiffin/inventory?business_id=home_tiffin")
    assert inv_res.status_code == 200
    inv_data = inv_res.json()
    assert "rice" in inv_data
    assert "dal" in inv_data
    assert "available" in inv_data["rice"]


def test_tiffin_evaluate_opportunity_endpoint(client):
    """Verifies opportunity evaluation against BOM recipes and cash safety."""
    eval_res = client.post("/api/tiffin/evaluate", json={
        "date": "2026-10-26",
        "additional_meals": 15,
        "current_cash": 8500.0,
        "min_cash_buffer": 2000.0,
        "business_id": "home_tiffin",
    })
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert "decision" in eval_data
    assert "reason" in eval_data
    assert "max_acceptable_meals" in eval_data


# -----------------------------------------------------------------------------
# 4. MCP Server Tool Registration
# -----------------------------------------------------------------------------
def test_mcp_tiffin_tools_registered():
    """Verifies that tiffin tools are registered on the FastMCP instance."""
    tool_names = [tool.name for tool in mcp_server._tool_manager.list_tools()]
    assert "tiffin_get_orders" in tool_names
    assert "tiffin_get_capacity" in tool_names
    assert "tiffin_get_inventory" in tool_names
    assert "tiffin_evaluate_opportunity" in tool_names
