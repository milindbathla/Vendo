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
falling back to the canonical data/demo.db.  On startup the autopilot's own
runtime tables (autopilot_*) are initialised (idempotent, additive — the
teammate-owned domain tables are never touched) and the autopilot_business_state
table is seeded from data/business_profiles.json (INSERT OR IGNORE — live data
is never reset).
"""
from dataclasses import asdict
import json
import os
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from pydantic import BaseModel, Field

from src.db.connection import DEFAULT_DB_PATH, initialize_database, seed_business_state
from src.db.state_repository import BusinessStateRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.models.adaptive_profile import FactStatus, FactSource
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
from src.integrations.google_places import GooglePlacesAdapter
from src.integrations.zoho_books import ZohoBooksAdapter
from src.integrations.amazon_pay import AmazonPayAdapter
from src.integrations.base import IntegrationError, ValidationError
from src.integrations.meta import MetaAdapter

# Phase 4 persistence, decision, and agent imports
from src.db.task_repository import (
    TaskRepository,
    ActionProposal,
    OperationalTask,
    TaskState,
    ActionNotFoundError,
    TaskNotFoundError,
    PayloadTamperedError,
    UnauthorizedError,
)
from src.db.email_repository import EmailRepository
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import (
    ActionDispatcher,
    ExecutionReceipt,
    ActionNotApprovedError,
    ActionPayloadTamperedError,
    UnauthorizedExecutionError,
    ExecutionUncertainError,
    UnknownActionTypeError,
)
from src.agent.supervisor import EmailOperationalSupervisor
from src.agent.document_onboarding import DocumentOnboardingService
from src.models.email import InboundEmail, EmailAddress


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
places_adapter      = GooglePlacesAdapter()
zoho_adapter        = ZohoBooksAdapter()
adaptive_repo       = AdaptiveProfileRepository(_DB_PATH)

# Phase 4 services
task_repo           = TaskRepository(_DB_PATH)
email_repo          = EmailRepository(_DB_PATH)
policy_engine       = PermissionEngine()
action_dispatcher   = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)
supervisor          = EmailOperationalSupervisor(
    email_repo=email_repo,
    task_repo=task_repo,
    profile_repo=adaptive_repo,
    policy_engine=policy_engine,
)
doc_onboarding_service = DocumentOnboardingService(repo=adaptive_repo)

orchestrator        = AdaptiveBusinessOrchestrator(
    repo=adaptive_repo,
    approval_service=approvals_service,
    places_adapter=places_adapter,
    zoho_adapter=zoho_adapter,
    task_repo=task_repo,
    email_repo=email_repo,
    supervisor=supervisor,
    action_dispatcher=action_dispatcher,
    policy_engine=policy_engine,
)
amazon_pay_adapter = AmazonPayAdapter()
meta_adapter       = MetaAdapter()

# Create official MCP server instance (shares the same service instances)
mcp_server = create_mcp_server(
    approval_service=approvals_service,
    profiles=business_profiles,
    places_adapter=places_adapter,
    zoho_adapter=zoho_adapter,
    profile_repo=adaptive_repo,
    task_repo=task_repo,
    email_repo=email_repo,
    policy_engine=policy_engine,
    action_dispatcher=action_dispatcher,
    supervisor=supervisor,
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

# Mount OAuth connection management routes
from src.server.auth_routes import router as auth_router
app.include_router(auth_router)

# Mount frontend demo API (read-only demo.db + Gemini-backed chat) and the SPA
from src.server.demo_api import router as demo_router
app.include_router(demo_router)

from pathlib import Path as _Path
from fastapi.staticfiles import StaticFiles
_FRONTEND_DIR = _Path(__file__).resolve().parents[2] / "frontend"
if _FRONTEND_DIR.is_dir():
    # Served at /app/ (onboarding) and /app/alexa.html (Alexa+ simulator)
    app.mount("/app", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


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
    # 1. Check adaptive profile repository first
    adaptive_prof = adaptive_repo.get_profile(business_type)
    if adaptive_prof:
        cash = adaptive_prof.get_value("cash_balance", adaptive_prof.get_value("starting_capital", 10000.0))
        inv = adaptive_prof.get_value("current_inventory", 0.0)
        return {
            "profile": adaptive_prof.to_dict(),
            "live_state": {
                "cash_balance": round(float(cash), 2),
                "inventory_units": round(float(inv), 2),
            },
            "pending_plans": [p.to_dict() for p in approvals_service.list_plans()],
            "is_adaptive": True,
            "simulation_notice": SIMULATION_NOTICE,
        }

    # 2. Check legacy static profiles
    if business_type in business_profiles:
        prof = business_profiles[business_type]
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
            "is_adaptive": False,
            "simulation_notice": SIMULATION_NOTICE,
        }

    # 3. Explicit 404 NOT_FOUND -- NO silent fallback
    raise HTTPException(status_code=404, detail=f"Business profile '{business_type}' not found.")


@app.post("/api/evaluate")
def evaluate(req: EvaluateRequest):
    # 1. Check adaptive repository first
    adaptive_prof = adaptive_repo.get_profile(req.business_type)
    if adaptive_prof:
        return orchestrator.evaluate_opportunity(
            profile=adaptive_prof,
            additional_units=req.additional_orders,
            current_demand=req.current_demand,
            current_inventory=req.current_inventory,
            total_cash=req.total_cash,
            daily_capacity=req.daily_capacity,
            safety_reserve=req.safety_reserve,
        )

    # 2. Check legacy static profiles
    if req.business_type not in business_profiles:
        raise HTTPException(status_code=404, detail=f"Business profile '{req.business_type}' not found.")

    prof = business_profiles[req.business_type]
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


class PlacesNearbyRequest(BaseModel):
    latitude: float = Field(default=26.4727, description="Search latitude")
    longitude: float = Field(default=80.3015, description="Search longitude")
    radius_meters: float = Field(default=1500.0, description="Radius in meters (max 50,000m)")
    place_types: Optional[List[str]] = Field(default=None, description="Optional list of place types")


# ── Integration Endpoints ──────────────────────────────────────────────────────

@app.get("/api/integrations/status")
def get_integrations_status():
    """Returns connectivity and operational mode of external provider integrations."""
    return {
        "status": "SUCCESS",
        "google_places": {
            "provider": "google_places",
            "mode": "mock" if places_adapter.is_mock else "live",
            "api_endpoint": "https://places.googleapis.com/v1/places:searchNearby",
        },
        "zoho_books": {
            "provider": "zoho_books",
            "mode": "mock" if zoho_adapter.is_mock else "live",
            "org_id": zoho_adapter.org_id,
            "api_domain": zoho_adapter.oauth_manager.api_domain,
            "is_configured": zoho_adapter.oauth_manager.is_configured,
        },
        "amazon_pay": amazon_pay_adapter.get_status(),
        "meta": meta_adapter.get_status(),
    }


@app.post("/api/integrations/places/nearby")
def search_places_nearby(req: PlacesNearbyRequest):
    """Searches nearby commercial listings via Google Places API (New)."""
    try:
        resp = places_adapter.search_nearby_places(
            latitude=req.latitude,
            longitude=req.longitude,
            radius_meters=req.radius_meters,
            place_types=req.place_types,
        )
        return resp.to_dict()
    except (ValidationError, IntegrationError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/integrations/zoho/organization")
def get_zoho_org(organization_id: Optional[str] = None):
    """Retrieves organization metadata from Zoho Books."""
    try:
        org = zoho_adapter.get_organization(organization_id=organization_id)
        return {
            "status": "SUCCESS",
            "organization": org.to_dict(),
            "is_mock": zoho_adapter.is_mock,
        }
    except (ValidationError, IntegrationError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/integrations/zoho/invoices")
def get_zoho_invoices_endpoint(status: Optional[str] = None, page: int = 1, per_page: int = 20):
    """Retrieves paginated invoices from Zoho Books."""
    try:
        resp = zoho_adapter.get_invoices(status=status, page=page, per_page=per_page)
        return resp.to_dict()
    except (ValidationError, IntegrationError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/integrations/zoho/expenses")
def get_zoho_expenses_endpoint(page: int = 1, per_page: int = 20):
    """Retrieves bills, expenses, and accounting summary from Zoho Books."""
    try:
        bills_resp = zoho_adapter.get_bills(page=page, per_page=per_page)
        expenses_resp = zoho_adapter.get_expenses(page=page, per_page=per_page)
        summary = zoho_adapter.get_accounting_summary()
        return {
            "status": "SUCCESS",
            "accounting_summary": summary.to_dict(),
            "bills": bills_resp.to_dict(),
            "expenses": expenses_resp.to_dict(),
            "is_mock": zoho_adapter.is_mock,
        }
    except (ValidationError, IntegrationError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Adaptive Business Onboarding & Orchestration Endpoints ───────────────────────

class OnboardingChatRequest(BaseModel):
    message: str = Field(..., description="Natural language statement or answer")
    business_id: Optional[str] = Field(default=None, description="Existing business profile ID, if resuming")


class FactUpdateRequest(BaseModel):
    key: str = Field(..., description="Fact key, e.g. selling_price, unit_material_cost")
    value: Any = Field(..., description="Fact value")
    status: str = Field(default="confirmed", description="confirmed, assumed, unknown, or outdated")
    notes: str = Field(default="", description="Reason or context for update")
    actor_id: Optional[str] = Field(default=None, description="Actor performing update")


@app.post("/api/onboarding/chat")
def onboarding_chat_endpoint(req: OnboardingChatRequest):
    """
    Conversational onboarding and interaction for ANY small business.
    Accepts natural language, extracts structured facts, tracks status/provenance,
    asks follow-ups, and handles corrections.
    """
    return orchestrator.handle_user_message(message=req.message, business_id=req.business_id)


@app.get("/api/business/profiles")
def list_business_profiles_endpoint():
    """Lists all registered adaptive business profiles."""
    return {"profiles": adaptive_repo.list_profiles()}


@app.get("/api/business/{business_id}")
def get_business_profile_endpoint(business_id: str):
    """Retrieves full profile and granular facts for a specific business."""
    profile = adaptive_repo.get_profile(business_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Business profile '{business_id}' not found")
    return profile.to_dict()


@app.put("/api/business/{business_id}/facts")
def update_business_fact_endpoint(
    business_id: str,
    req: FactUpdateRequest,
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Explicitly corrects or updates a specific business fact with owner authorization."""
    actor_id = resolve_actor_id(req.actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    enforce_owner_authorization(business_id, actor_id)

    profile = adaptive_repo.get_profile(business_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Business profile '{business_id}' not found")
    fact = profile.set_fact(
        key=req.key,
        value=req.value,
        status=FactStatus(req.status.lower() if isinstance(req.status, str) else req.status),
        source=FactSource.USER_STATED,
        notes=req.notes or f"Updated by owner {actor_id}",
    )
    adaptive_repo.save_profile(profile)
    return {"status": "SUCCESS", "fact": fact.to_dict()}


@app.delete("/api/business/{business_id}")
def delete_business_profile_endpoint(
    business_id: str,
    actor_id: Optional[str] = Query(None),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Deletes an adaptive business profile with owner authorization."""
    actor = resolve_actor_id(actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    enforce_owner_authorization(business_id, actor)

    success = adaptive_repo.delete_profile(business_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Business profile '{business_id}' not found")
    return {"status": "SUCCESS", "deleted": business_id}


# -----------------------------------------------------------------------------
# Phase 4: Controlled Execution and Task Lifecycle Models & Endpoints
# -----------------------------------------------------------------------------
AUTOPILOT_ENV = os.environ.get("AUTOPILOT_ENV", "development").lower()


class EmailIngestRequest(BaseModel):
    business_id: str
    sender_email: str
    sender_name: Optional[str] = ""
    subject: str
    body_plain: str
    body_html: Optional[str] = ""
    message_id: Optional[str] = None
    process_now: bool = True


class ActionApproveRequest(BaseModel):
    business_id: str
    actor_id: Optional[str] = None
    execution_payload: Optional[Dict[str, Any]] = None


class ActionRejectRequest(BaseModel):
    business_id: str
    actor_id: Optional[str] = None
    rejection_reason: str


class ActionDispatchRequest(BaseModel):
    business_id: str
    actor_id: Optional[str] = None
    execution_payload: Optional[Dict[str, Any]] = None


class ExecutionReconcileRequest(BaseModel):
    business_id: str
    actor_id: Optional[str] = None
    resolution: str  # "CONFIRM_EXECUTED" or "CONFIRM_FAILED"
    notes: str


class DocumentOnboardRequest(BaseModel):
    business_id: str
    document_text: str
    filename: Optional[str] = "onboarding_doc.txt"
    doc_format: Optional[str] = "txt"


class FactVerifyRequest(BaseModel):
    business_id: str
    key: str
    status: str = "CONFIRMED"
    value: Optional[Any] = None
    notes: Optional[str] = None
    actor_id: Optional[str] = None


def resolve_actor_id(
    body_actor_id: Optional[str] = None,
    x_autopilot_actor_id: Optional[str] = None,
    x_autopilot_owner_id: Optional[str] = None,
) -> str:
    env = os.environ.get("AUTOPILOT_ENV", "development").lower()
    if env == "production":
        raise HTTPException(
            status_code=403,
            detail="Header-based simulated authentication is strictly disabled in production mode. Verified OAuth2/JWT authentication required.",
        )
    actor = body_actor_id or x_autopilot_actor_id or x_autopilot_owner_id
    if not actor or not actor.strip():
        raise HTTPException(
            status_code=401,
            detail="Authentication required: No actor or owner identity provided in request or headers.",
        )
    return actor.strip()


def enforce_owner_authorization(business_id: str, actor_id: str) -> None:
    if not policy_engine.is_authorized_owner(business_id, actor_id):
        raise HTTPException(
            status_code=403,
            detail=f"Actor '{actor_id}' is not an authorized owner for business '{business_id}'. Consequential operations forbidden.",
        )


@app.post("/api/emails/ingest")
def ingest_email_endpoint(req: EmailIngestRequest):
    """
    Ingests an untrusted inbound email, normalizes fields, and stores in EmailRepository.
    Optionally triggers immediate supervisor processing.
    """
    inbound = InboundEmail(
        message_id=req.message_id or f"msg_{os.urandom(8).hex()}",
        business_id=req.business_id,
        sender=EmailAddress(email=req.sender_email, name=req.sender_name or ""),
        to_recipients=[EmailAddress(email=f"{req.business_id}@autopilot.local")],
        subject=req.subject,
        body_text=req.body_plain,
        body_html=req.body_html or "",
    )
    saved_email = email_repo.save_email(inbound)

    result: Dict[str, Any] = {
        "status": "STORED",
        "email_id": saved_email.email_id,
        "business_id": req.business_id,
    }

    if req.process_now:
        try:
            outcome = supervisor.process_email(saved_email)
            result["status"] = "PROCESSED"
            result["task_id"] = outcome.task.task_id
            result["classification"] = outcome.classification.to_dict() if hasattr(outcome.classification, "to_dict") else asdict(outcome.classification)
            result["proposals_count"] = len(outcome.action_proposals)
            result["proposals"] = [p.to_dict() for p in outcome.action_proposals]
        except Exception as e:
            result["status"] = "PROCESSING_ERROR"
            result["error"] = str(e)

    return result


@app.post("/api/emails/{email_id}/process")
def process_email_endpoint(email_id: str, business_id: str = Query(...)):
    """Triggers supervisor analysis for an already ingested email."""
    email = email_repo.get_by_id(email_id, business_id=business_id)
    if not email:
        raise HTTPException(status_code=404, detail=f"Email '{email_id}' not found for business '{business_id}'")
    try:
        outcome = supervisor.process_email(email)
        return {
            "status": "PROCESSED",
            "task_id": outcome.task.task_id,
            "classification": outcome.classification.to_dict() if hasattr(outcome.classification, "to_dict") else asdict(outcome.classification),
            "proposals_count": len(outcome.action_proposals),
            "proposals": [p.to_dict() for p in outcome.action_proposals],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks")
def list_tasks_endpoint(
    business_id: str = Query(...),
    state: Optional[str] = Query(None),
    limit: int = Query(50),
):
    """Lists operational tasks for a business, strictly tenant-isolated."""
    task_state = TaskState(state) if state and state in TaskState._value2member_map_ else None
    tasks = task_repo.list_tasks(business_id=business_id, state=task_state, limit=limit)
    return {"tasks": [t.to_dict() for t in tasks]}


@app.get("/api/tasks/{task_id}")
def get_task_endpoint(task_id: str, business_id: str = Query(...)):
    """Retrieves detailed operational task state, including action proposals and audit trail."""
    task = task_repo.get_task(task_id, business_id=business_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found for business '{business_id}'")
    actions = task_repo.list_actions_for_task(task_id, business_id=business_id)
    audit_trail = task_repo.get_audit_log(task_id, business_id=business_id)
    res = task.to_dict()
    res["actions"] = [a.to_dict() for a in actions]
    res["audit_trail"] = audit_trail
    return res


@app.get("/api/tasks/{task_id}/actions")
def list_task_actions_endpoint(task_id: str, business_id: str = Query(...)):
    """Lists action proposals for a specific operational task."""
    actions = task_repo.list_actions_for_task(task_id, business_id=business_id)
    return {"actions": [a.to_dict() for a in actions]}


@app.get("/api/actions/{action_id}")
def get_action_proposal_endpoint(action_id: str, business_id: str = Query(...)):
    """Retrieves an action proposal with exact payload and SHA-256 hash."""
    proposal = task_repo.get_action(action_id, business_id=business_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Action proposal '{action_id}' not found")
    return proposal.to_dict()


@app.post("/api/actions/{action_id}/approve")
def approve_action_endpoint(
    action_id: str,
    req: ActionApproveRequest,
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Approves an action proposal. Enforces authenticated owner verification and exact payload hash match.
    """
    actor_id = resolve_actor_id(req.actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    enforce_owner_authorization(req.business_id, actor_id)

    proposal = task_repo.get_action(action_id, business_id=req.business_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Action proposal '{action_id}' not found")

    payload = req.execution_payload if req.execution_payload is not None else proposal.payload
    try:
        approved = task_repo.approve_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=actor_id,
            execution_payload=payload,
            policy_engine=policy_engine,
        )
        return {"status": "APPROVED", "action": approved.to_dict()}
    except PayloadTamperedError as e:
        raise HTTPException(status_code=400, detail=f"Payload tampering detected: {str(e)}")
    except UnauthorizedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/actions/{action_id}/reject")
def reject_action_endpoint(
    action_id: str,
    req: ActionRejectRequest,
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Rejects an action proposal with documented rationale."""
    actor_id = resolve_actor_id(req.actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    enforce_owner_authorization(req.business_id, actor_id)

    try:
        rejected = task_repo.reject_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=actor_id,
            rejection_reason=req.rejection_reason,
        )
        return {"status": "REJECTED", "action": rejected.to_dict()}
    except ActionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Action proposal '{action_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/actions/{action_id}/dispatch")
def dispatch_action_endpoint(
    action_id: str,
    req: ActionDispatchRequest,
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Executes an action through the controlled ActionDispatcher.
    Re-evaluates policy, validates hash binding, enforces idempotency.
    """
    actor_id = resolve_actor_id(req.actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    try:
        receipt = action_dispatcher.dispatch_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=actor_id,
            execution_payload=req.execution_payload,
        )
        return {"status": receipt.status, "receipt": asdict(receipt)}
    except ActionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found")
    except ActionNotApprovedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ActionPayloadTamperedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnauthorizedExecutionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ExecutionUncertainError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except UnknownActionTypeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/executions")
def list_executions_endpoint(
    business_id: str = Query(...),
    task_id: Optional[str] = Query(None),
    limit: int = Query(50),
):
    """Lists execution records and receipts for audit tracking."""
    if task_id:
        records = task_repo.list_executions_for_task(task_id=task_id, business_id=business_id)
    else:
        records = task_repo.list_executions_for_business(business_id=business_id, limit=limit)
    return {"executions": records}


@app.post("/api/executions/{action_id}/reconcile")
def reconcile_execution_endpoint(
    action_id: str,
    req: ExecutionReconcileRequest,
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Explicit owner-directed reconciliation for an action in EXECUTION_UNCERTAIN."""
    actor_id = resolve_actor_id(req.actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    enforce_owner_authorization(req.business_id, actor_id)

    try:
        receipt = action_dispatcher.reconcile_uncertain_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=actor_id,
            resolution=req.resolution,
            notes=req.notes,
        )
        return {"status": receipt.status, "receipt": asdict(receipt)}
    except ActionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found")
    except UnauthorizedExecutionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/documents/onboard")
def onboard_document_endpoint(req: DocumentOnboardRequest):
    """
    Ingests and parses document content (text/CSV/PDF), extracts evidence-backed candidate facts,
    flags contradictions against confirmed facts, and asks follow-ups without overwriting.
    """
    try:
        result = doc_onboarding_service.ingest_document(
            business_id=req.business_id,
            filename=req.filename or "onboarding_doc.txt",
            content=req.document_text,
            doc_format=req.doc_format or "txt",
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documents/verify-fact")
def verify_fact_endpoint(
    req: FactVerifyRequest,
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Owner verification of a candidate, assumed, or outdated fact."""
    actor_id = resolve_actor_id(req.actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    enforce_owner_authorization(req.business_id, actor_id)

    profile = adaptive_repo.get_profile(req.business_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Business profile '{req.business_id}' not found")

    fact = profile.get_fact(req.key)
    val = req.value if req.value is not None else (fact.value if fact else None)
    try:
        fact_status = FactStatus(req.status.lower())
    except (ValueError, AttributeError):
        fact_status = FactStatus.CONFIRMED

    updated_fact = profile.set_fact(
        key=req.key,
        value=val,
        status=fact_status,
        source=FactSource.USER_STATED,
        notes=req.notes or f"Verified by owner {actor_id}",
    )
    adaptive_repo.save_profile(profile)
    return {"status": "SUCCESS", "fact": updated_fact.to_dict()}


class OrchestratorQueryRequest(BaseModel):
    business_id: str
    message: str
    actor_id: Optional[str] = None


@app.post("/api/orchestrator/query")
def orchestrator_query_endpoint(
    req: OrchestratorQueryRequest,
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Central operational assistant endpoint.
    Processes natural-language queries, briefings, follow-ups, and operational requests.
    """
    actor_id = resolve_actor_id(req.actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    return orchestrator.handle_user_message(
        message=req.message,
        business_id=req.business_id,
        actor_id=actor_id,
    )


@app.get("/api/orchestrator/briefing")
def orchestrator_briefing_endpoint(
    business_id: str = Query(...),
    actor_id: Optional[str] = Query(None),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Returns a proactive daily operational briefing and voice-friendly summary.
    """
    actor = resolve_actor_id(actor_id, x_autopilot_actor_id, x_autopilot_owner_id)
    return orchestrator.generate_daily_briefing(business_id=business_id, actor_id=actor)


@app.get("/")
def root():
    return {
        "service": "Alexa Business Autopilot Backend",
        "version": "1.0.0",
        "status": "healthy",
        "mode": "backend_only",
        "mcp_enabled": True,
        "mcp_endpoints": ["/mcp", "/sse"],
        "adaptive_endpoints": [
            "/api/onboarding/chat",
            "/api/business/profiles",
            "/api/business/{business_id}",
            "/api/orchestrator/query",
        ],
        "db_path": _DB_PATH,
        "simulation_notice": SIMULATION_NOTICE,
    }
