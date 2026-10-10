"""
Alexa Business Autopilot — Web Application & API Server
========================================================
Serves:
- /health: Health probe endpoint
- /mcp: Streamable HTTP MCP endpoint (official MCP protocol)
- /sse: SSE MCP endpoint (official MCP protocol)
- /api/state: Real-time business, inventory, and cash state
- /api/evaluate: Voice/text decision orchestrator with tool trace & voice response
- /api/recipe: Recipe shortage calculator for meals
- /api/confirm_plan: Two-phase owner approval gate
- /api/execute_plan: Simulated order execution

Persistence
-----------
The database path is read from the DATABASE_PATH environment variable,
falling back to data/business_autopilot.sqlite3.  On startup the schema
is initialised (idempotent) and business state is seeded from
data/business_profiles.json (INSERT OR IGNORE — live data is never reset).
"""
from dataclasses import asdict
import json
import os
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.db.connection import DEFAULT_DB_PATH, initialize_database, seed_business_state
from src.db.state_repository import BusinessStateRepository
from src.server.mcp_server import create_mcp_server
from src.decision.approval_service import (
    PurchaseApprovalService,
    PlanStatus,
    PlanNotFoundError,
    InvalidPlanStateError,
    InsufficientFundsError,
)
from src.decision.business_autopilot import BusinessAutopilotV2, OpportunityDecision
from src.models.recipe import TiffinRecipeManager
from src.services.supplier_simulator import SupplierCatalogueSimulator, SIMULATION_NOTICE
from src.simulator import load_business_profiles


# ── Database initialisation ────────────────────────────────────────────────────
_DB_PATH: str = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
initialize_database(_DB_PATH)
seed_business_state(_DB_PATH)

# ── Singleton services (shared with MCP server) ────────────────────────────────
approvals_service   = PurchaseApprovalService(db_path=_DB_PATH)
business_profiles   = load_business_profiles()
recipe_manager      = TiffinRecipeManager()
supplier_simulator  = SupplierCatalogueSimulator()
state_repo          = BusinessStateRepository(_DB_PATH)

# Create official MCP server instance (shares the same approval service instance)
mcp_server = create_mcp_server(
    approval_service=approvals_service,
    profiles=business_profiles,
)

# Initialize FastAPI application
app = FastAPI(
    title="Alexa Business Autopilot",
    description="Voice-first operating layer & MCP server for Indian small businesses",
    version="1.0.0",
)

# Mount MCP endpoints (Streamable HTTP & SSE)
app.mount("/mcp", mcp_server.streamable_http_app())
app.mount("/sse", mcp_server.sse_app())


# -----------------------------------------------------------------------------
# Request & Response Models
# -----------------------------------------------------------------------------
class EvaluateRequest(BaseModel):
    user_question: str = "Can I take 20 more tiffin orders tomorrow?"
    additional_orders: float = 20.0
    business_type: str = "home_tiffin"
    current_demand: Optional[float] = 15.0
    current_inventory: Optional[float] = 18.0
    total_cash: Optional[float] = 8000.0
    daily_capacity: Optional[float] = 40.0
    safety_reserve: float = 2000.0


class ConfirmPlanRequest(BaseModel):
    plan_id: str
    decision: str  # "APPROVE" or "REJECT"


class ExecutePlanRequest(BaseModel):
    plan_id: str
    current_cash: float = 8000.0
    safety_reserve: float = 2000.0


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "alexa-business-autopilot",
        "version": "1.0.0",
        "mcp_enabled": True,
        "mcp_endpoints": ["/mcp", "/sse"],
        "db_path": _DB_PATH,
        "simulation_notice": SIMULATION_NOTICE,
    }


@app.get("/api/state")
def get_state(business_type: str = "home_tiffin"):
    prof = business_profiles.get(business_type, business_profiles["home_tiffin"])

    # Prefer persisted cash/inventory if available; fall back to profile defaults
    db_state = state_repo.get_state(business_type)
    cash_balance    = db_state["cash_balance"]    if db_state else prof.starting_capital
    inventory_units = db_state["inventory_units"] if db_state else prof.starting_inventory

    return {
        "profile": prof.to_dict(),
        "live_state": {
            "cash_balance":    round(cash_balance, 2),
            "inventory_units": round(inventory_units, 2),
        },
        "pending_plans": [p.to_dict() for p in approvals_service.list_plans()],
        "simulation_notice": SIMULATION_NOTICE,
    }


@app.post("/api/evaluate")
def evaluate(req: EvaluateRequest):
    prof = business_profiles.get(req.business_type, business_profiles["home_tiffin"])
    autopilot = BusinessAutopilotV2(profile=prof)

    # 1. Run baseline decision orchestration
    decision = autopilot.evaluate_opportunity(
        additional_orders=req.additional_orders,
        current_demand=req.current_demand,
        current_inventory=req.current_inventory,
        total_cash=req.total_cash,
        daily_capacity=req.daily_capacity,
        cash_reserve_target=req.safety_reserve,
        user_question=req.user_question,
    )
    decision_data = decision.to_dict()

    # 2. Compute multi-ingredient recipe shortage
    # Recipe evaluation is strictly based on the intended fulfilled demand
    fulfilled_meals = decision.fulfilled_demand
    current_stocks = {
        "rice":        round(req.current_inventory * 0.15, 2) if req.current_inventory else 0.0,
        "dal":         round(req.current_inventory * 0.08, 2) if req.current_inventory else 0.0,
        "cooking_oil": 0.2,   # deliberately low stock for realistic demo
        "containers":  5.0,   # deliberately low stock for realistic demo
    }
    shortage_eval = recipe_manager.evaluate_shortages(
        meals_count=fulfilled_meals,
        current_stocks=current_stocks,
    )
    decision_data["recipe_shortages"] = shortage_eval

    # 3. If procurement is required and affordable, generate an approval-gated PurchasePlan
    plan_data = None
    if (
        decision.procurement_plan.recommended_procurement_units > 0
        and decision.affordability.is_affordable
        and decision.fulfillable_additional_orders > 0
    ):
        # Quote from supplier simulator
        needed_ing = {
            k: v["missing"]
            for k, v in shortage_eval["ingredients"].items()
            if v["missing"] > 0
        }
        supplier_quote = supplier_simulator.get_quote("wholesale_mandi", needed_ing)

        plan_items = [
            {
                "ingredient_name": it.ingredient_name,
                "display_name":    it.display_name,
                "quantity":        it.order_qty,
                "unit":            it.unit,
                "unit_price":      it.unit_price,
                "total_price":     it.total_price,
            }
            for it in supplier_quote.items
        ]
        created_plan = approvals_service.create_plan(
            supplier_id=supplier_quote.supplier_id,
            supplier_name=supplier_quote.supplier_name,
            items=plan_items,
            total_cost=supplier_quote.total_cost,
            explanation=(
                f"Procurement for {decision.fulfillable_additional_orders:.0f} additional tiffin orders "
                f"(intended fulfillment: {fulfilled_meals:.0f} total meals)."
            ),
        )
        plan_data = created_plan.to_dict()

    decision_data["purchase_plan"] = plan_data
    decision_data["simulation_notice"] = SIMULATION_NOTICE
    return decision_data


@app.post("/api/confirm_plan")
def confirm_plan(req: ConfirmPlanRequest):
    try:
        plan = approvals_service.confirm_plan(req.plan_id, req.decision)
        return {
            "status": "SUCCESS",
            "plan": plan.to_dict(),
            "simulation_notice": SIMULATION_NOTICE,
        }
    except (PlanNotFoundError, InvalidPlanStateError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/execute_plan")
def execute_plan(req: ExecutePlanRequest):
    try:
        receipt = approvals_service.execute_plan(
            plan_id=req.plan_id,
            current_cash=req.current_cash,
            safety_reserve=req.safety_reserve,
            business_type="home_tiffin",
        )
        return {
            "status": "SUCCESS",
            "receipt": receipt,
            "simulation_notice": SIMULATION_NOTICE,
        }
    except (PlanNotFoundError, InvalidPlanStateError, InsufficientFundsError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/")
def root():
    return {
        "service": "Alexa Business Autopilot Backend",
        "version": "1.0.0",
        "status": "healthy",
        "mode": "backend_only",
        "mcp_enabled": True,
        "mcp_endpoints": ["/mcp", "/sse"],
        "db_path": _DB_PATH,
        "simulation_notice": SIMULATION_NOTICE,
    }
