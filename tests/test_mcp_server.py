"""
Tests for Official Python MCP Server
=====================================
Validates:
- Tool registration and tool schema listing
- Execution of business state, recipe, supplier, and decision tools via MCP
- Strict two-phase lifecycle enforcement through MCP tools
"""
import asyncio
import json
import pytest
from src.server.mcp_server import create_mcp_server
from src.decision.approval_service import PurchaseApprovalService


@pytest.fixture
def mcp_server():
    approvals = PurchaseApprovalService()
    return create_mcp_server(approval_service=approvals)


@pytest.mark.anyio
async def test_1_mcp_tools_registration(mcp_server):
    """Verifies that all 10 core business and procurement tools are registered."""
    tools = await mcp_server.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = [
        "get_business_state",
        "get_upcoming_orders",
        "get_financial_position",
        "get_tiffin_recipe_breakdown",
        "get_supplier_quotes",
        "compare_procurement_channels",
        "evaluate_order_opportunity",
        "create_purchase_plan",
        "confirm_purchase_plan",
        "execute_purchase_plan",
    ]
    for expected in expected_tools:
        assert expected in tool_names, f"Tool {expected} missing from registered MCP tools"


@pytest.mark.anyio
async def test_2_call_get_business_state(mcp_server):
    """Verifies calling get_business_state tool via MCP protocol."""
    res = await mcp_server.call_tool("get_business_state", {"business_type": "home_tiffin"})
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["business_type"] == "home_tiffin"
    assert data["selling_price"] == 95.0
    assert "simulation_notice" in data


@pytest.mark.anyio
async def test_3_call_evaluate_order_opportunity(mcp_server):
    """Verifies calling the end-to-end evaluate_order_opportunity tool."""
    res = await mcp_server.call_tool(
        "evaluate_order_opportunity",
        {
            "additional_orders": 20.0,
            "business_type": "home_tiffin",
            "current_demand": 15.0,
            "current_inventory": 18.0,
            "total_cash": 8000.0,
            "daily_capacity": 40.0,
        },
    )
    assert not res.is_error
    data = json.loads(res.content[0].text)
    assert data["decision"] == "ACCEPT_WITH_PROCUREMENT"
    assert "voice_response" in data
    assert len(data["tool_trace"]) >= 5


@pytest.mark.anyio
async def test_4_mcp_two_phase_purchase_lifecycle(mcp_server):
    """Verifies strict two-phase approval lifecycle executed through MCP tools."""
    # 1. Create plan -> PENDING_APPROVAL
    items = json.dumps([
        {
            "ingredient_name": "cooking_oil",
            "display_name": "Sunflower Oil",
            "quantity": 5.0,
            "unit": "litres",
            "unit_price": 120.0,
            "total_price": 600.0,
        }
    ])
    create_res = await mcp_server.call_tool(
        "create_purchase_plan",
        {
            "supplier_id": "wholesale_mandi",
            "supplier_name": "Metro Wholesale Mandi",
            "items_json": items,
            "total_cost": 600.0,
            "explanation": "Procuring 5L oil for tiffin prep",
        },
    )
    assert not create_res.is_error
    created_data = json.loads(create_res.content[0].text)
    plan_id = created_data["plan"]["plan_id"]
    assert created_data["plan"]["status"] == "PENDING_APPROVAL"

    # 2. Try executing unconfirmed plan -> MUST FAIL with structured ERROR status
    exec_fail_res = await mcp_server.call_tool(
        "execute_purchase_plan",
        {"plan_id": plan_id, "current_cash": 8000.0, "safety_reserve": 2000.0},
    )
    assert not exec_fail_res.is_error
    fail_data = json.loads(exec_fail_res.content[0].text)
    assert fail_data["status"] == "ERROR"
    assert "PENDING_APPROVAL" in fail_data["error"]

    # 3. Confirm plan with owner approval
    confirm_res = await mcp_server.call_tool(
        "confirm_purchase_plan",
        {"plan_id": plan_id, "decision": "APPROVE"},
    )
    assert not confirm_res.is_error
    confirmed_data = json.loads(confirm_res.content[0].text)
    assert confirmed_data["plan_status"] == "APPROVED"

    # 4. Execute confirmed plan -> SUCCEEDS
    exec_res = await mcp_server.call_tool(
        "execute_purchase_plan",
        {"plan_id": plan_id, "current_cash": 8000.0, "safety_reserve": 2000.0},
    )
    assert not exec_res.is_error
    exec_data = json.loads(exec_res.content[0].text)
    assert exec_data["status"] == "EXECUTION_COMPLETE"
    assert exec_data["receipt"]["status"] == "SIMULATED_ORDER_PLACED"
    assert exec_data["receipt"]["cash_after"] == 7400.0
