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

from contextlib import asynccontextmanager
import urllib.parse
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request, Form
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, model_validator

from src.db.connection import DEFAULT_DB_PATH, initialize_database, seed_business_state
from src.db.state_repository import BusinessStateRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.session_repository import SessionRepository
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.models.adaptive_profile import FactStatus, FactSource
from src.server.mcp_server import create_mcp_server
from src.server.mcp_auth import MCPAuthenticationMiddleware
from src.security.auth_service import (
    create_access_token,
    verify_access_token,
    issue_authorization_code,
    exchange_authorization_code,
    refresh_access_token,
    revoke_oauth_token,
    check_business_authorization,
    AuthenticationError,
    TokenExpiredError,
    InvalidCredentialsError,
    ScopeInsufficientError,
    JWT_ISSUER,
    JWT_AUDIENCE,
)
from src.security.oauth_config import (
    get_public_base_url,
    get_mcp_resource_url,
    get_auth_issuer_url,
    is_valid_client_redirect,
    ConfigurationError,
)
from src.models.principal import TrustedPrincipal
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

# Phase 4 & Sessions services
task_repo           = TaskRepository(_DB_PATH)
email_repo          = EmailRepository(_DB_PATH)
session_repo        = SessionRepository(_DB_PATH)
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
    session_repo=session_repo,
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
    session_repo=session_repo,
)

mcp_app = mcp_server.streamable_http_app()
streamable_endpoint = mcp_app.routes[0].endpoint

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # Initializes StreamableHTTPManager task group for official FastMCP transport
    async with mcp_app.router.lifespan_context(mcp_app):
        yield

# Initialize FastAPI application with unified lifespan
app = FastAPI(
    title="Alexa Business Autopilot",
    description="Voice-first operating layer & MCP server for Indian small businesses",
    version="1.0.0",
    lifespan=app_lifespan,
)

# Mount authenticated MCP endpoints (Streamable HTTP & SSE)
app.mount("/mcp", MCPAuthenticationMiddleware(streamable_endpoint))
app.mount("/sse", mcp_server.sse_app())

# Mount OAuth connection management routes
from src.server.auth_routes import router as auth_router
app.include_router(auth_router)

# Mount frontend demo API (MCP-backed demo.db + Zoho + Claude-backed chat) and the SPA
from src.server import demo_api
from src.server.demo_api import router as demo_router
app.include_router(demo_router)
# Share the *mounted* MCP server so every frontend data fetch goes through MCP
# and registers the additive demo tools (demo_get_accounts, …) on it.
demo_api.set_mcp_server(mcp_server)

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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Explicitly corrects or updates a specific business fact with owner authorization."""
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=req.actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(business_id, principal)

    profile = adaptive_repo.get_profile(business_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Business profile '{business_id}' not found")
    fact = profile.set_fact(
        key=req.key,
        value=req.value,
        status=FactStatus(req.status.lower() if isinstance(req.status, str) else req.status),
        source=FactSource.USER_STATED,
        notes=req.notes or f"Updated by owner {principal.subject}",
    )
    adaptive_repo.save_profile(profile)
    return {"status": "SUCCESS", "fact": fact.to_dict()}


@app.delete("/api/business/{business_id}")
def delete_business_profile_endpoint(
    business_id: str,
    actor_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Deletes an adaptive business profile with owner authorization."""
    principal = resolve_principal(
        authorization=authorization,
        query_actor_id=actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(business_id, principal)

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


def resolve_principal(
    authorization: Optional[str] = None,
    body_actor_id: Optional[str] = None,
    x_autopilot_actor_id: Optional[str] = None,
    x_autopilot_owner_id: Optional[str] = None,
    query_actor_id: Optional[str] = None,
) -> TrustedPrincipal:
    """
    Resolves the server-verified TrustedPrincipal:
    1. If Authorization header with Bearer token is provided: verifies JWT signature, issuer, audience, exp.
       If invalid/expired, immediately raises HTTP 401 with RFC 6750 WWW-Authenticate header.
    2. If no Bearer token:
       In production (AUTOPILOT_ENV=production): raises HTTP 401 with WWW-Authenticate header.
       In development mode: accepts mock developer headers (X-Autopilot-Actor-Id, etc.) or actor_id.
    """
    env = os.environ.get("AUTOPILOT_ENV", "development").lower()

    if authorization and authorization.strip():
        auth_clean = authorization.strip()
        if not auth_clean.lower().startswith("bearer "):
            raise HTTPException(
                status_code=401,
                detail="Authorization header must use Bearer scheme.",
                headers={"WWW-Authenticate": 'Bearer error="invalid_request"'},
            )
        try:
            return verify_access_token(auth_clean)
        except TokenExpiredError as e:
            raise HTTPException(
                status_code=401,
                detail="Bearer token has expired.",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The access token expired"'},
            )
        except AuthenticationError as e:
            raise HTTPException(
                status_code=401,
                detail=str(e),
                headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{str(e)}"'},
            )

    if env == "production":
        raise HTTPException(
            status_code=401,
            detail="Header-based simulated authentication is strictly disabled in production mode. Verified OAuth2/JWT authentication required.",
            headers={"WWW-Authenticate": 'Bearer realm="vendo-api", error="unauthorized", error_description="Bearer token required"'},
        )

    actor = body_actor_id or x_autopilot_actor_id or x_autopilot_owner_id or query_actor_id
    if not actor or not actor.strip():
        raise HTTPException(
            status_code=401,
            detail="Authentication required: No actor or owner identity provided in request or headers.",
            headers={"WWW-Authenticate": 'Bearer realm="vendo-api"'},
        )

    actor_clean = actor.strip()
    return TrustedPrincipal(
        subject=actor_clean,
        issuer="vendo-dev",
        audience="vendo-api",
        is_authenticated=True,
        business_membership=["*"],
        roles=["owner"],
        scopes=["*"],
        auth_method="dev_mock",
    )


def resolve_actor_id(
    body_actor_id: Optional[str] = None,
    x_autopilot_actor_id: Optional[str] = None,
    x_autopilot_owner_id: Optional[str] = None,
    query_actor_id: Optional[str] = None,
    authorization: Optional[str] = None,
) -> str:
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=body_actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
        query_actor_id=query_actor_id,
    )
    return principal.subject


def enforce_owner_authorization(business_id: str, actor_or_principal: Any) -> None:
    if isinstance(actor_or_principal, TrustedPrincipal):
        if not check_business_authorization(actor_or_principal, business_id, policy_engine):
            raise HTTPException(
                status_code=403,
                detail=f"Principal '{actor_or_principal.subject}' is not an authorized owner for business '{business_id}'. Consequential operations forbidden.",
            )
        return

    actor_id = str(actor_or_principal)
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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Approves an action proposal. Enforces authenticated owner verification and exact payload hash match.
    """
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=req.actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(req.business_id, principal)

    proposal = task_repo.get_action(action_id, business_id=req.business_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Action proposal '{action_id}' not found")

    payload = req.execution_payload if req.execution_payload is not None else proposal.payload
    try:
        approved = task_repo.approve_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=principal.subject,
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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Rejects an action proposal with documented rationale."""
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=req.actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(req.business_id, principal)

    try:
        rejected = task_repo.reject_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=principal.subject,
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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Executes an action through the controlled ActionDispatcher.
    Re-evaluates policy, validates hash binding, enforces idempotency.
    """
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=req.actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    try:
        receipt = action_dispatcher.dispatch_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=principal.subject,
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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Explicit owner-directed reconciliation for an action in EXECUTION_UNCERTAIN."""
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=req.actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(req.business_id, principal)

    try:
        receipt = action_dispatcher.reconcile_uncertain_action(
            action_id=action_id,
            business_id=req.business_id,
            actor_id=principal.subject,
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
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """Owner verification of a candidate, assumed, or outdated fact."""
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=req.actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(req.business_id, principal)

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
        notes=req.notes or f"Verified by owner {principal.subject}",
    )
    adaptive_repo.save_profile(profile)
    return {"status": "SUCCESS", "fact": updated_fact.to_dict()}


class OrchestratorQueryRequest(BaseModel):
    business_id: str
    message: Optional[str] = None
    query: Optional[str] = None
    actor_id: Optional[str] = None
    session_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_message(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("message") and data.get("query"):
                data["message"] = data["query"]
            elif not data.get("message") and not data.get("query"):
                data["message"] = ""
        return data


@app.post("/api/orchestrator/query")
def orchestrator_query_endpoint(
    req: OrchestratorQueryRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Central operational assistant endpoint.
    Processes natural-language queries, briefings, follow-ups, and operational requests.
    Enforces server-verified principal and strict tenant isolation.
    """
    principal = resolve_principal(
        authorization=authorization,
        body_actor_id=req.actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(req.business_id, principal)

    return orchestrator.handle_user_message(
        message=req.message,
        business_id=req.business_id,
        actor_id=principal.subject,
        session_id=req.session_id,
    )


@app.get("/api/orchestrator/briefing")
def orchestrator_briefing_endpoint(
    business_id: str = Query(...),
    actor_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_autopilot_actor_id: Optional[str] = Header(None, alias="X-Autopilot-Actor-Id"),
    x_autopilot_owner_id: Optional[str] = Header(None, alias="X-Autopilot-Owner-Id"),
):
    """
    Returns a proactive daily operational briefing and voice-friendly summary.
    Enforces verified owner identity.
    """
    principal = resolve_principal(
        authorization=authorization,
        query_actor_id=actor_id,
        x_autopilot_actor_id=x_autopilot_actor_id,
        x_autopilot_owner_id=x_autopilot_owner_id,
    )
    enforce_owner_authorization(business_id, principal)
    return orchestrator.generate_daily_briefing(business_id=business_id, actor_id=principal.subject)


# -----------------------------------------------------------------------------
# OAuth 2.1 & RFC 8414 / RFC 9728 / RFC 9207 Metadata & Account Linking Endpoints
# -----------------------------------------------------------------------------
@app.get("/.well-known/oauth-authorization-server")
def oauth_authorization_server_metadata(request: Request):
    """RFC 8414 OAuth 2.0 Authorization Server Metadata."""
    base_url = get_public_base_url()
    issuer_url = get_auth_issuer_url()
    return {
        "issuer": issuer_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "revocation_endpoint": f"{base_url}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "scopes_supported": [
            "business:read",
            "business:write",
            "approvals:read",
            "approvals:execute",
            "tasks:read",
            "tasks:write",
        ],
        "authorization_response_iss_parameter_supported": True,
    }


@app.get("/.well-known/oauth-protected-resource")
def oauth_protected_resource_metadata(request: Request):
    """RFC 9728 OAuth 2.0 Protected Resource Metadata."""
    resource_url = get_mcp_resource_url()
    issuer_url = get_auth_issuer_url()
    return {
        "resource": resource_url,
        "authorization_servers": [issuer_url],
        "scopes_supported": [
            "business:read",
            "business:write",
            "approvals:read",
            "approvals:execute",
            "tasks:read",
            "tasks:write",
        ],
        "bearer_methods_supported": ["header"],
    }


@app.get("/oauth/authorize")
def oauth_authorize_endpoint(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query("code"),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    state: Optional[str] = Query(None),
    scope: Optional[str] = Query("business:read business:write approvals:read approvals:execute"),
    resource: Optional[str] = Query(None),
    owner_id: Optional[str] = Query("owner_sharma"),
    business_id: Optional[str] = Query("biz_kirana"),
):
    """
    OAuth 2.1 Authorization Code grant endpoint with PKCE (RFC 7636).
    Enforces redirect_uri registration to prevent open redirects.
    Includes RFC 9207 authorization server issuer identification parameter (iss).
    """
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Unsupported response_type. Only 'code' is supported.")
    if code_challenge_method.upper() != "S256":
        raise HTTPException(status_code=400, detail="Only PKCE code_challenge_method 'S256' is supported.")

    if not is_valid_client_redirect(client_id, redirect_uri):
        raise HTTPException(
            status_code=400,
            detail=f"Redirect URI '{redirect_uri}' is not allowlisted for registered client '{client_id}'.",
        )

    env = os.environ.get("AUTOPILOT_ENV", "development").lower()
    if env == "production" and (not owner_id or owner_id == "owner_sharma"):
        raise HTTPException(
            status_code=403,
            detail="Production authorization code issuance requires a verified authenticated business owner session.",
        )

    granted_scopes = scope.split() if scope else ["business:read", "approvals:read", "approvals:execute"]
    try:
        code = issue_authorization_code(
            client_id=client_id,
            redirect_uri=redirect_uri,
            subject=owner_id or "owner_sharma",
            business_ids=[business_id] if business_id else ["biz_kirana"],
            scopes=granted_scopes,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=resource,
        )
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=400, detail=str(e))

    query_params = {
        "code": code,
        "iss": get_auth_issuer_url(),  # RFC 9207 Issuer Identification
    }
    if state:
        query_params["state"] = state
    redirect_url = f"{redirect_uri}?{urllib.parse.urlencode(query_params)}"
    return RedirectResponse(url=redirect_url, status_code=302)


class TokenExchangeRequest(BaseModel):
    grant_type: str = "authorization_code"
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    client_id: str
    code_verifier: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    resource: Optional[str] = None


@app.post("/oauth/token")
async def oauth_token_endpoint(request: Request):
    """
    OAuth 2.1 token endpoint supporting:
    1. grant_type=authorization_code (exchanges code + PKCE verifier for access token and refresh token)
    2. grant_type=refresh_token (rotates refresh token, detects replay, and issues fresh access token)
    Accepts both standard form-encoded (application/x-www-form-urlencoded) and JSON bodies.
    """
    content_type = request.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            data = {}

    eff_grant_type = data.get("grant_type")
    eff_client_id = data.get("client_id")

    if not eff_client_id:
        raise HTTPException(status_code=400, detail="Missing required client_id parameter")

    if eff_grant_type == "authorization_code":
        eff_code = data.get("code")
        eff_redirect_uri = data.get("redirect_uri")
        eff_verifier = data.get("code_verifier")
        eff_resource = data.get("resource")

        if not eff_code or not eff_redirect_uri or not eff_verifier:
            raise HTTPException(status_code=400, detail="Missing required OAuth 2.1 token exchange parameters")

        try:
            return exchange_authorization_code(
                code=eff_code,
                client_id=eff_client_id,
                redirect_uri=eff_redirect_uri,
                code_verifier=eff_verifier,
                resource=eff_resource,
                db_path=_DB_PATH,
            )
        except InvalidCredentialsError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
                headers={"WWW-Authenticate": 'Bearer error="invalid_grant"'},
            )

    elif eff_grant_type == "refresh_token":
        eff_refresh_token = data.get("refresh_token")
        eff_scope = data.get("scope")

        if not eff_refresh_token:
            raise HTTPException(status_code=400, detail="Missing required refresh_token parameter")

        requested_scopes = eff_scope.split() if eff_scope else None

        try:
            return refresh_access_token(
                refresh_token=eff_refresh_token,
                client_id=eff_client_id,
                requested_scopes=requested_scopes,
                policy_engine=policy_engine,
                db_path=_DB_PATH,
            )
        except TokenExpiredError as e:
            raise HTTPException(
                status_code=400,
                detail="Refresh token has expired",
                headers={"WWW-Authenticate": 'Bearer error="invalid_grant", error_description="The refresh token expired"'},
            )
        except (InvalidCredentialsError, ScopeInsufficientError) as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
                headers={"WWW-Authenticate": 'Bearer error="invalid_grant"'},
            )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported grant_type '{eff_grant_type}'. Supported grant types: 'authorization_code', 'refresh_token'.",
        )


@app.post("/oauth/revoke")
async def oauth_revoke_endpoint(request: Request):
    """
    RFC 7009 Token Revocation Endpoint.
    Revokes either an access token or a refresh token.
    """
    content_type = request.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            data = {}

    token = data.get("token")
    token_type_hint = data.get("token_type_hint")

    if not token:
        raise HTTPException(status_code=400, detail="Missing required 'token' parameter to revoke.")

    revoke_oauth_token(token=token, token_type_hint=token_type_hint, db_path=_DB_PATH)
    return {"status": "SUCCESS", "revoked": True}


@app.get("/")
def root():
    return {
        "service": "Alexa Business Autopilot Backend",
        "version": "1.0.0",
        "status": "healthy",
        "mode": "backend_only",
        "mcp_enabled": True,
        "mcp_endpoints": ["/mcp", "/sse"],
        "oauth_discovery": [
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource",
            "/oauth/authorize",
            "/oauth/token",
        ],
        "adaptive_endpoints": [
            "/api/onboarding/chat",
            "/api/business/profiles",
            "/api/business/{business_id}",
            "/api/orchestrator/query",
        ],
        "db_path": _DB_PATH,
        "simulation_notice": SIMULATION_NOTICE,
    }
