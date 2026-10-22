"""
Alexa Business Autopilot — Official Python MCP Server
======================================================
Exposes business state, causal demand/inventory reasoning, multi-ingredient
tiffin recipes, supplier quotes, and the two-phase purchase approval lifecycle
as Model Context Protocol (MCP) tools.

Compliant with the MCP 2025-11-25+ standard using the official Python MCP SDK.
"""
from dataclasses import asdict
import json
from typing import Dict, Any, List, Optional, Tuple

from mcp.server.fastmcp import FastMCP

from src.models.business import BusinessProfile
from src.models.recipe import TiffinRecipeManager, STANDARD_TIFFIN_RECIPE
from src.simulator import load_business_profiles
from src.decision.business_autopilot import (
    BusinessAutopilotV2,
    DecisionType,
    OpportunityDecision,
)
from src.decision.approval_service import (
    PurchaseApprovalService,
    PlanStatus,
    PlanNotFoundError,
    InvalidPlanStateError,
    InsufficientFundsError,
)
from src.services.supplier_simulator import (
    SupplierCatalogueSimulator,
    SIMULATION_NOTICE,
)
from Agents.finance_agent import FinanceAgent
from Agents.supplier_intelligence import SupplierIntelligenceAgent
from src.integrations.google_places import GooglePlacesAdapter
from src.integrations.zoho_books import ZohoBooksAdapter
from src.db.connection import DEFAULT_DB_PATH
from src.db.profile_repository import AdaptiveProfileRepository
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.db.task_repository import TaskRepository, ActionProposal, OperationalTask, TaskState
from src.db.email_repository import EmailRepository
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import ActionDispatcher, ExecutionReceipt
from src.agent.supervisor import EmailOperationalSupervisor
from src.models.email import InboundEmail, EmailAddress


import os
from src.server.mcp_auth import get_current_mcp_principal
from src.db.session_repository import SessionRepository


def create_mcp_server(
    approval_service: Optional[PurchaseApprovalService] = None,
    profiles: Optional[Dict[str, BusinessProfile]] = None,
    places_adapter: Optional[GooglePlacesAdapter] = None,
    zoho_adapter: Optional[ZohoBooksAdapter] = None,
    profile_repo: Optional[AdaptiveProfileRepository] = None,
    task_repo: Optional[TaskRepository] = None,
    email_repo: Optional[EmailRepository] = None,
    policy_engine: Optional[PermissionEngine] = None,
    action_dispatcher: Optional[ActionDispatcher] = None,
    supervisor: Optional[EmailOperationalSupervisor] = None,
    session_repo: Optional[SessionRepository] = None,
) -> FastMCP:
    """Factory to create and configure the Alexa Business Autopilot MCP Server."""

    server = FastMCP(
        name="alexa-business-autopilot",
        instructions=(
            "Voice-first operating layer & MCP server for Indian micro-enterprises. "
            "Version 1.0.0."
        ),
    )

    business_profiles = profiles or load_business_profiles()
    approvals = approval_service or PurchaseApprovalService()
    recipe_manager = TiffinRecipeManager()
    supplier_simulator = SupplierCatalogueSimulator()
    places = places_adapter or GooglePlacesAdapter()
    zoho = zoho_adapter or ZohoBooksAdapter()
    adaptive_repo = profile_repo or AdaptiveProfileRepository(DEFAULT_DB_PATH)
    # Phase 4: Task lifecycle and controlled execution services
    _task_repo = task_repo or TaskRepository(db_path=DEFAULT_DB_PATH)
    _email_repo = email_repo or EmailRepository(db_path=DEFAULT_DB_PATH)
    _policy_engine = policy_engine or PermissionEngine()
    _dispatcher = action_dispatcher or ActionDispatcher(
        task_repo=_task_repo,
        policy_engine=_policy_engine,
    )
    _supervisor = supervisor or EmailOperationalSupervisor(
        email_repo=_email_repo,
        task_repo=_task_repo,
        profile_repo=adaptive_repo,
        policy_engine=_policy_engine,
    )
    _session_repo = session_repo or SessionRepository(db_path=DEFAULT_DB_PATH)

    orchestrator = AdaptiveBusinessOrchestrator(
        repo=adaptive_repo,
        approval_service=approvals,
        places_adapter=places,
        zoho_adapter=zoho,
        task_repo=_task_repo,
        email_repo=_email_repo,
        supervisor=_supervisor,
        action_dispatcher=_dispatcher,
        policy_engine=_policy_engine,
        session_repo=_session_repo,
    )

    def _authorize_mcp_call(
        business_id: Optional[str] = None,
        supplied_actor_id: Optional[str] = None,
        required_scope: Optional[str] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Safely authorizes an MCP tool invocation and determines the verified actor:
        1. Context principal takes absolute precedence; supplied actor_id is never trusted blindly.
        2. Validates tenant authorization: caller must belong to business_id.
        3. Validates OAuth scope when provided.
        4. In production mode (AUTOPILOT_ENV=production), blocks unauthenticated requests.
        """
        principal = get_current_mcp_principal()
        env = os.environ.get("AUTOPILOT_ENV", "development").lower()

        if principal:
            if required_scope and not principal.has_scope(required_scope):
                return principal.subject, {
                    "status": "UNAUTHORIZED",
                    "error": f"Security principal lacks required scope '{required_scope}'.",
                }
            if business_id and not principal.has_business_access(business_id):
                if not (_policy_engine and _policy_engine.is_authorized_owner(business_id, principal.subject)):
                    return principal.subject, {
                        "status": "UNAUTHORIZED",
                        "error": f"Security principal '{principal.subject}' is not authorized for business '{business_id}'.",
                    }
            return principal.subject, None

        if env == "production":
            return "", {
                "status": "UNAUTHORIZED",
                "error": "Unauthenticated MCP tool execution strictly forbidden in production mode.",
            }

        # Development / stdio execution fallback
        actor = supplied_actor_id or (f"owner:{business_id}" if business_id else "owner")
        if business_id and _policy_engine and not _policy_engine.is_authorized_owner(business_id, actor):
            return actor, {
                "status": "UNAUTHORIZED",
                "error": f"Actor '{actor}' is not an authorized owner for business '{business_id}'.",
            }
        return actor, None


    # -------------------------------------------------------------------------
    # Tool 1: get_business_state
    # -------------------------------------------------------------------------
    @server.tool()
    def get_business_state(business_type: str = "home_tiffin") -> Dict[str, Any]:
        """
        Retrieves current business economics, starting inventory, daily capacity ceiling,
        and cash parameters for any specified business profile.
        """
        # 1. Check static profiles first for predefined profiles
        if business_type in business_profiles:
            prof = business_profiles[business_type]
            return {
                "status": "SUCCESS",
                "business_type": prof.business_type,
                "display_name": prof.display_name,
                "selling_price": prof.selling_price,
                "supplier_unit_cost": prof.supplier_unit_cost,
                "daily_capacity": prof.daily_capacity,
                "starting_inventory": prof.starting_inventory,
                "starting_capital": prof.starting_capital,
                "base_daily_demand": prof.base_daily_demand,
                "daily_fixed_cost": prof.daily_fixed_cost,
                "lead_time_days": prof.procurement_lead_time_days,
                "is_adaptive": False,
                "simulation_notice": SIMULATION_NOTICE,
            }

        # 2. Check adaptive profile repository
        adaptive_prof = adaptive_repo.get_profile(business_type)
        if adaptive_prof:
            selling_price = adaptive_prof.get_value("selling_price", 0.0)
            unit_cost = adaptive_prof.get_value("unit_material_cost", adaptive_prof.get_value("supplier_unit_cost", 0.0))
            capacity = adaptive_prof.get_value("daily_capacity", 0.0)
            cash_bal = adaptive_prof.get_value("cash_balance", adaptive_prof.get_value("starting_capital", 10000.0))
            return {
                "status": "SUCCESS",
                "business_type": adaptive_prof.business_id,
                "display_name": adaptive_prof.display_name,
                "category": adaptive_prof.category,
                "selling_price": selling_price,
                "supplier_unit_cost": unit_cost,
                "daily_capacity": capacity,
                "starting_inventory": adaptive_prof.get_value("current_inventory", 0.0),
                "starting_capital": cash_bal,
                "base_daily_demand": adaptive_prof.get_value("base_daily_demand", 0.0),
                "daily_fixed_cost": adaptive_prof.get_value("daily_fixed_cost", 0.0),
                "lead_time_days": adaptive_prof.get_value("procurement_lead_time_days", 1),
                "is_adaptive": True,
                "simulation_notice": SIMULATION_NOTICE,
            }

        return {
            "status": "NOT_FOUND",
            "error": f"Business profile '{business_type}' was not found. Please onboard first.",
            "business_type": business_type,
            "simulation_notice": SIMULATION_NOTICE,
        }

    # -------------------------------------------------------------------------
    # Tool 2: get_upcoming_orders
    # -------------------------------------------------------------------------
    @server.tool()
    def get_upcoming_orders(business_type: str = "home_tiffin") -> Dict[str, Any]:
        """
        Retrieves scheduled baseline customer orders or bookings for tomorrow.
        """
        adaptive_prof = adaptive_repo.get_profile(business_type)
        if adaptive_prof:
            base_demand = float(adaptive_prof.get_value("base_daily_demand", 0.0))
            capacity = float(adaptive_prof.get_value("daily_capacity", 0.0))
            unit_label = orchestrator._get_unit_label(adaptive_prof.category)
            return {
                "status": "SUCCESS",
                "business_type": adaptive_prof.business_id,
                "display_name": adaptive_prof.display_name,
                "category": adaptive_prof.category,
                "scheduled_orders_tomorrow": round(base_demand, 0),
                "order_type": f"Scheduled daily {unit_label}",
                "capacity_ceiling": round(capacity, 0),
                "available_capacity_headroom": max(0.0, round(capacity - base_demand, 0)),
                "is_adaptive": True,
            }

        if business_type in business_profiles:
            prof = business_profiles[business_type]
            return {
                "status": "SUCCESS",
                "business_type": prof.business_type,
                "scheduled_orders_tomorrow": round(prof.base_daily_demand, 0),
                "order_type": "Daily subscription orders",
                "capacity_ceiling": round(prof.daily_capacity, 0),
                "available_capacity_headroom": max(0.0, round(prof.daily_capacity - prof.base_daily_demand, 0)),
                "is_adaptive": False,
            }

        return {
            "status": "NOT_FOUND",
            "error": f"Business profile '{business_type}' was not found. Please onboard first.",
            "business_type": business_type,
        }

    # -------------------------------------------------------------------------
    # Tool 3: get_financial_position
    # -------------------------------------------------------------------------
    @server.tool()
    def get_financial_position(
        total_cash: float = 8000.0,
        safety_reserve: float = 2000.0,
    ) -> Dict[str, Any]:
        """
        Inspects liquid cash balance, safety reserve threshold, and usable capital.
        """
        usable = max(0.0, total_cash - safety_reserve)
        return {
            "total_cash": round(total_cash, 2),
            "safety_reserve": round(safety_reserve, 2),
            "usable_cash": round(usable, 2),
            "is_cash_constrained": usable < 1000.0,
        }

    # -------------------------------------------------------------------------
    # Tool 4: get_tiffin_recipe_breakdown
    # -------------------------------------------------------------------------
    @server.tool()
    def get_tiffin_recipe_breakdown(
        meals_count: float = 20.0,
        current_stocks_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates exact multi-ingredient recipe requirements (rice, dal, cooking oil,
        containers) for a given meal count and checks shortages against current stock.
        """
        stocks = {}
        if current_stocks_json:
            try:
                stocks = json.loads(current_stocks_json)
            except Exception:
                stocks = {}

        return recipe_manager.evaluate_shortages(meals_count, stocks)

    # -------------------------------------------------------------------------
    # Tool 5: get_supplier_quotes
    # -------------------------------------------------------------------------
    @server.tool()
    def get_supplier_quotes(
        supplier_id: str = "wholesale_mandi",
        needed_ingredients_json: str = "{}",
    ) -> Dict[str, Any]:
        """
        Fetches deterministic pricing quote from a simulated local supplier.
        Enforces supplier MOQ and bulk discount tiers.
        """
        try:
            needed = json.loads(needed_ingredients_json)
        except Exception:
            needed = {}

        quote = supplier_simulator.get_quote(supplier_id, needed)
        return quote.to_dict()

    # -------------------------------------------------------------------------
    # Tool 6: compare_procurement_channels
    # -------------------------------------------------------------------------
    @server.tool()
    def compare_procurement_channels(
        needed_ingredients_json: str = "{}",
    ) -> Dict[str, Any]:
        """
        Compares wholesale procurement (low unit price, 24h lead time) against
        urgent local delivery (higher price, 2h rapid delivery).
        """
        try:
            needed = json.loads(needed_ingredients_json)
        except Exception:
            needed = {}

        return supplier_simulator.compare_procurement_channels(needed)

    # -------------------------------------------------------------------------
    # Tool 7: evaluate_order_opportunity
    # -------------------------------------------------------------------------
    @server.tool()
    def evaluate_order_opportunity(
        additional_orders: float,
        business_type: str = "home_tiffin",
        current_demand: Optional[float] = None,
        current_inventory: Optional[float] = None,
        total_cash: Optional[float] = None,
        daily_capacity: Optional[float] = None,
        safety_reserve: float = 2000.0,
        user_question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end multi-step reasoning across demand, inventory, capacity,
        and cash constraints. Returns decision (ACCEPT, ACCEPT_WITH_PROCUREMENT,
        ACCEPT_PARTIALLY, REJECT), tool trace, and natural voice response.
        """
        # 1. Check static profiles first for predefined profiles
        if business_type in business_profiles:
            v2_engine = BusinessAutopilotV2(profile=business_profiles[business_type])
            decision: OpportunityDecision = v2_engine.evaluate_opportunity(
                additional_orders=additional_orders,
                current_demand=current_demand,
                current_inventory=current_inventory,
                total_cash=total_cash,
                daily_capacity=daily_capacity,
                cash_reserve_target=safety_reserve,
                user_question=user_question,
            )
            return decision.to_dict()

        # 2. Check adaptive profile repository
        adaptive_prof = adaptive_repo.get_profile(business_type)
        if adaptive_prof:
            return orchestrator.evaluate_opportunity(
                profile=adaptive_prof,
                additional_units=additional_orders,
                current_demand=current_demand,
                current_inventory=current_inventory,
                total_cash=total_cash,
                daily_capacity=daily_capacity,
                safety_reserve=safety_reserve,
                user_question=user_question,
            )

        # 3. Fail closed if not found
        return {
            "status": "NOT_FOUND",
            "decision": "REJECT",
            "error": f"Business profile '{business_type}' was not found. Please onboard first.",
            "business_type": business_type,
            "simulation_notice": SIMULATION_NOTICE,
        }

    # -------------------------------------------------------------------------
    # Tool 8: create_purchase_plan
    # -------------------------------------------------------------------------
    @server.tool()
    def create_purchase_plan(
        supplier_id: str,
        supplier_name: str,
        items_json: str,
        total_cost: float,
        explanation: str,
    ) -> Dict[str, Any]:
        """
        Prepares a formal purchase plan in PENDING_APPROVAL status.
        Requires explicit owner confirmation before any order execution.
        """
        try:
            items = json.loads(items_json)
        except Exception as e:
            raise ValueError(f"Invalid items_json: {e}")

        plan = approvals.create_plan(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            items=items,
            total_cost=total_cost,
            explanation=explanation,
        )
        return {
            "status": "PLAN_CREATED",
            "plan": plan.to_dict(),
            "simulation_notice": SIMULATION_NOTICE,
            "next_step": "Awaiting explicit owner approval via confirm_purchase_plan()",
        }

    # -------------------------------------------------------------------------
    # Tool 9: confirm_purchase_plan
    # -------------------------------------------------------------------------
    @server.tool()
    def confirm_purchase_plan(
        plan_id: str,
        decision: str,  # "APPROVE" or "REJECT"
    ) -> Dict[str, Any]:
        """
        Owner confirmation gate: transitions plan from PENDING_APPROVAL to
        APPROVED or REJECTED.
        """
        try:
            plan = approvals.confirm_plan(plan_id, decision)
            return {
                "status": "DECISION_RECORDED",
                "plan_id": plan.plan_id,
                "plan_status": plan.status.value,
                "owner_decision": plan.owner_decision,
                "simulation_notice": SIMULATION_NOTICE,
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "plan_id": plan_id,
                "simulation_notice": SIMULATION_NOTICE,
            }

    # -------------------------------------------------------------------------
    # Tool 10: execute_purchase_plan
    # -------------------------------------------------------------------------
    @server.tool()
    def execute_purchase_plan(
        plan_id: str,
        current_cash: float,
        safety_reserve: float = 2000.0,
    ) -> Dict[str, Any]:
        """
        Executes simulated purchase ONLY after explicit approval and liquidity check.
        Rejects unapproved, already-executed, or cash-deficient plans.
        """
        try:
            receipt = approvals.execute_plan(
                plan_id=plan_id,
                current_cash=current_cash,
                safety_reserve=safety_reserve,
            )
            return {
                "status": "EXECUTION_COMPLETE",
                "receipt": receipt,
                "simulation_notice": SIMULATION_NOTICE,
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "plan_id": plan_id,
                "simulation_notice": SIMULATION_NOTICE,
            }

    # -------------------------------------------------------------------------
    # Tool 11: get_profitability_analysis (Finance Specialist Agent)
    # -------------------------------------------------------------------------
    @server.tool()
    def get_profitability_analysis(business_type: str = "home_tiffin") -> Dict[str, Any]:
        """
        Computes contribution margin, break-even volume, and profit at
        current demand vs full capacity using the Finance Specialist Agent.
        """
        agent = FinanceAgent(business_type=business_type)
        return agent.analyze_profitability()

    # -------------------------------------------------------------------------
    # Tool 12: forecast_cash_flow (Finance Specialist Agent)
    # -------------------------------------------------------------------------
    @server.tool()
    def forecast_cash_flow(
        days: int = 7,
        business_type: str = "home_tiffin",
        planned_procurement_cost: float = 0.0,
        planned_procurement_day: int = 1,
    ) -> Dict[str, Any]:
        """
        Projects rolling cash flow over N days based on current demand
        and cost structure using the Finance Specialist Agent.
        """
        agent = FinanceAgent(business_type=business_type)
        return agent.forecast_cash_flow(
            days=days,
            planned_procurement_cost=planned_procurement_cost,
            planned_procurement_day=planned_procurement_day,
        )

    # -------------------------------------------------------------------------
    # Tool 13: get_supplier_profile (Supplier Intelligence Specialist Agent)
    # -------------------------------------------------------------------------
    @server.tool()
    def get_supplier_profile(supplier_id: str) -> Dict[str, Any]:
        """
        Retrieves full supplier profile, contact details, lead times,
        and rating using the Supplier Intelligence Specialist Agent.
        """
        supplier_intel_agent = SupplierIntelligenceAgent()
        try:
            return supplier_intel_agent.get_supplier_profile(supplier_id=supplier_id)
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "supplier_id": supplier_id,
            }

    # -------------------------------------------------------------------------
    # Tool 14: evaluate_supplier (Supplier Intelligence Specialist Agent)
    # -------------------------------------------------------------------------
    @server.tool()
    def evaluate_supplier(supplier_id: str) -> Dict[str, Any]:
        """
        Scores a supplier across quality, cost, speed, reliability, and relationship
        dimensions using the Supplier Intelligence Specialist Agent.
        """
        supplier_intel_agent = SupplierIntelligenceAgent()
        try:
            return supplier_intel_agent.evaluate_supplier(supplier_id=supplier_id)
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "supplier_id": supplier_id,
            }

    # -------------------------------------------------------------------------
    # Tool 15: search_nearby_competitors (Google Places API New)
    # -------------------------------------------------------------------------
    @server.tool()
    def search_nearby_competitors(
        latitude: float = 26.4727,
        longitude: float = 80.3015,
        radius_meters: float = 1500.0,
        place_types_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Discovers nearby commercial businesses and potential competitors using Google Places API (New).
        Returns normalized listings, distance in meters, user ratings, and competitor summary.
        Data limitation: Represents public commercial listings, not proof of customer demand.
        """
        types = None
        if place_types_json:
            try:
                types = json.loads(place_types_json)
            except Exception:
                types = [t.strip() for t in place_types_json.split(",") if t.strip()]
        resp = places.search_nearby_places(
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            place_types=types,
        )
        return resp.to_dict()

    # -------------------------------------------------------------------------
    # Tool 16: get_zoho_organization (Zoho Books API)
    # -------------------------------------------------------------------------
    @server.tool()
    def get_zoho_organization(organization_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves company details, currency settings, and tax status from Zoho Books.
        """
        org = zoho.get_organization(organization_id=organization_id)
        return {
            "status": "SUCCESS",
            "organization": org.to_dict(),
            "is_mock": zoho.is_mock,
        }

    # -------------------------------------------------------------------------
    # Tool 17: get_zoho_invoices (Zoho Books API)
    # -------------------------------------------------------------------------
    @server.tool()
    def get_zoho_invoices(
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """
        Retrieves paginated sales invoices and accounts receivable balances from Zoho Books.
        Preserves distinction between invoiced revenue and collected cash.
        """
        resp = zoho.get_invoices(status=status, page=page, per_page=per_page)
        return resp.to_dict()

    # -------------------------------------------------------------------------
    # Tool 18: get_zoho_expenses_and_bills (Zoho Books API)
    # -------------------------------------------------------------------------
    @server.tool()
    def get_zoho_expenses_and_bills(
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """
        Retrieves operating expenses and accounts payable vendor bills from Zoho Books.
        """
        bills_resp = zoho.get_bills(page=page, per_page=per_page)
        expenses_resp = zoho.get_expenses(page=page, per_page=per_page)
        summary = zoho.get_accounting_summary()
        return {
            "status": "SUCCESS",
            "accounting_summary": summary.to_dict(),
            "bills": bills_resp.to_dict(),
            "expenses": expenses_resp.to_dict(),
            "is_mock": zoho.is_mock,
        }

    # -------------------------------------------------------------------------
    # Tool 19: get_external_integrations_status
    # -------------------------------------------------------------------------
    @server.tool()
    def get_external_integrations_status() -> Dict[str, Any]:
        """
        Reports operational and connectivity status of external API providers (Google Places & Zoho Books).
        """
        return {
            "google_places": {
                "provider": "google_places",
                "mode": "mock" if places.is_mock else "live",
                "api_endpoint": "https://places.googleapis.com/v1/places:searchNearby",
            },
            "zoho_books": {
                "provider": "zoho_books",
                "mode": "mock" if zoho.is_mock else "live",
                "api_domain": zoho.oauth_manager.api_domain,
                "accounts_url": zoho.oauth_manager.accounts_url,
                "org_id": zoho.org_id,
                "is_configured": zoho.oauth_manager.is_configured,
            },
            "amazon_pay": {
                "provider": "amazon_pay",
                "status": "EXPLICITLY_OUT_OF_SCOPE",
            },
        }

    # -------------------------------------------------------------------------
    # Tool 20: onboard_or_chat_business (Adaptive Business Onboarding & Chat)
    # -------------------------------------------------------------------------
    @server.tool()
    def onboard_or_chat_business(
        message: str,
        business_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Conversational onboarding and interaction for ANY Indian micro-enterprise.
        Extracts facts (prices, materials, capacity, cash, overhead), tracks provenance,
        identifies missing fields, handles corrections, and answers business queries.
        """
        return orchestrator.handle_user_message(message=message, business_id=business_id)

    # -------------------------------------------------------------------------
    # Tool 21: get_adaptive_business_profile
    # -------------------------------------------------------------------------
    @server.tool()
    def get_adaptive_business_profile(business_id: str) -> Dict[str, Any]:
        """
        Retrieves the complete profile and granular fact breakdown (confirmed,
        assumed, outdated) for an onboarded business.
        """
        profile = adaptive_repo.get_profile(business_id)
        if not profile:
            return {"status": "NOT_FOUND", "business_id": business_id, "error": "Profile not found"}
        return {
            "status": "SUCCESS",
            "profile": profile.to_dict(),
        }

    # -------------------------------------------------------------------------
    # Tool 22: list_adaptive_business_profiles
    # -------------------------------------------------------------------------
    @server.tool()
    def list_adaptive_business_profiles() -> List[Dict[str, Any]]:
        """
        Lists all onboarded business profiles with their categories and fact counts.
        """
        return adaptive_repo.list_profiles()

    # -------------------------------------------------------------------------
    # Tool 23: evaluate_adaptive_opportunity
    # -------------------------------------------------------------------------
    @server.tool()
    def evaluate_adaptive_opportunity(
        business_id: str,
        additional_orders: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Evaluates whether an onboarded business can take on additional demand.
        Uses universal constraints (capacity, materials, usable cash) without
        assuming food/tiffin recipes for non-food businesses.
        """
        profile = adaptive_repo.get_profile(business_id)
        if not profile:
            return {"status": "NOT_FOUND", "business_id": business_id, "error": "Profile not found"}
        return orchestrator.evaluate_opportunity(profile=profile, additional_units=additional_orders)

    # -------------------------------------------------------------------------
    # Tool 24: list_operational_tasks
    # -------------------------------------------------------------------------
    @server.tool()
    def list_operational_tasks(
        business_id: str,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        """
        Lists operational tasks for a business, optionally filtered by lifecycle state.
        Strictly tenant-isolated.
        """
        _, err = _authorize_mcp_call(business_id=business_id, required_scope="tasks:read")
        if err:
            return err
        task_state = TaskState(state) if state and state in TaskState._value2member_map_ else None
        tasks = _task_repo.list_tasks(business_id=business_id, state=task_state, limit=limit)
        return [t.to_dict() for t in tasks]

    # -------------------------------------------------------------------------
    # Tool 25: get_operational_task
    # -------------------------------------------------------------------------
    @server.tool()
    def get_operational_task(task_id: str, business_id: str) -> Dict[str, Any]:
        """
        Retrieves detailed operational task state, including action proposals and audit trail.
        """
        _, err = _authorize_mcp_call(business_id=business_id, required_scope="tasks:read")
        if err:
            return err
        task = _task_repo.get_task(task_id, business_id=business_id)
        if not task:
            return {"status": "NOT_FOUND", "error": f"Task '{task_id}' not found for business '{business_id}'."}
        actions = _task_repo.list_actions_for_task(task_id, business_id=business_id)
        audit_log = _task_repo.get_audit_log(task_id, business_id=business_id)
        result = task.to_dict()
        result["actions"] = [a.to_dict() for a in actions]
        result["audit_trail"] = audit_log
        return {"status": "SUCCESS", "task": result}

    # -------------------------------------------------------------------------
    # Tool 26: list_pending_approvals
    # -------------------------------------------------------------------------
    @server.tool()
    def list_pending_approvals(business_id: str) -> Any:
        """
        Lists all action proposals currently awaiting owner approval for a business.
        """
        _, err = _authorize_mcp_call(business_id=business_id, required_scope="approvals:read")
        if err:
            return err
        actions = _task_repo.list_pending_actions(business_id=business_id)
        return [a.to_dict() for a in actions]

    # -------------------------------------------------------------------------
    # Tool 27: get_action_proposal
    # -------------------------------------------------------------------------
    @server.tool()
    def get_action_proposal(action_id: str, business_id: str) -> Dict[str, Any]:
        """
        Retrieves a structured action proposal with its immutable payload hash and approval status.
        """
        _, err = _authorize_mcp_call(business_id=business_id, required_scope="approvals:read")
        if err:
            return err
        proposal = _task_repo.get_action(action_id, business_id=business_id)
        if not proposal:
            return {"status": "NOT_FOUND", "error": f"Action proposal '{action_id}' not found."}
        return {"status": "SUCCESS", "action": proposal.to_dict()}

    # -------------------------------------------------------------------------
    # Tool 28: approve_action_proposal
    # -------------------------------------------------------------------------
    @server.tool()
    def approve_action_proposal(
        action_id: str,
        business_id: str,
        actor_id: str = "owner",
        execution_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Approves an action proposal. Requires authenticated owner authorization.
        Validates exact payload hash binding to prevent tampering.
        """
        effective_actor, err = _authorize_mcp_call(
            business_id=business_id, supplied_actor_id=actor_id, required_scope="approvals:execute"
        )
        if err:
            return err

        proposal = _task_repo.get_action(action_id, business_id=business_id)
        if not proposal:
            return {"status": "NOT_FOUND", "error": f"Action proposal '{action_id}' not found."}

        payload = execution_payload if execution_payload is not None else proposal.payload
        try:
            approved = _task_repo.approve_action(
                action_id=action_id,
                business_id=business_id,
                actor_id=effective_actor,
                execution_payload=payload,
                policy_engine=_policy_engine,
            )
            return {"status": "APPROVED", "action": approved.to_dict()}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # -------------------------------------------------------------------------
    # Tool 29: reject_action_proposal
    # -------------------------------------------------------------------------
    @server.tool()
    def reject_action_proposal(
        action_id: str,
        business_id: str,
        actor_id: str = "owner",
        rejection_reason: str = "Rejected by business owner during operational review.",
    ) -> Dict[str, Any]:
        """
        Rejects an action proposal with documented rationale. Requires authenticated owner.
        """
        effective_actor, err = _authorize_mcp_call(
            business_id=business_id, supplied_actor_id=actor_id, required_scope="approvals:execute"
        )
        if err:
            return err
        try:
            rejected = _task_repo.reject_action(
                action_id=action_id,
                business_id=business_id,
                actor_id=effective_actor,
                rejection_reason=rejection_reason,
            )
            return {"status": "REJECTED", "action": rejected.to_dict()}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # -------------------------------------------------------------------------
    # Tool 30: dispatch_action
    # -------------------------------------------------------------------------
    @server.tool()
    def dispatch_action(
        action_id: str,
        business_id: str,
        actor_id: str = "owner",
        execution_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes an action proposal through the controlled ActionDispatcher.
        Enforces policy re-evaluation, hash verification, approval check, durable idempotency,
        and failure recovery. Never calls live external services.
        """
        effective_actor, err = _authorize_mcp_call(
            business_id=business_id, supplied_actor_id=actor_id, required_scope="approvals:execute"
        )
        if err:
            return err
        try:
            receipt = _dispatcher.dispatch_action(
                action_id=action_id,
                business_id=business_id,
                actor_id=effective_actor,
                execution_payload=execution_payload,
            )
            return {"status": receipt.status, "receipt": asdict(receipt)}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # -------------------------------------------------------------------------
    # Tool 31: list_execution_history
    # -------------------------------------------------------------------------
    @server.tool()
    def list_execution_history(
        business_id: str,
        task_id: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        """
        Lists execution receipts and records for a business or specific task.
        """
        _, err = _authorize_mcp_call(business_id=business_id, required_scope="tasks:read")
        if err:
            return err
        if task_id:
            return _task_repo.list_executions_for_task(task_id, business_id=business_id)
        return _task_repo.list_executions_for_business(business_id=business_id, limit=limit)

    # -------------------------------------------------------------------------
    # Tool 32: reconcile_uncertain_execution
    # -------------------------------------------------------------------------
    @server.tool()
    def reconcile_uncertain_execution(
        action_id: str,
        business_id: str,
        actor_id: str = "owner",
        resolution: str = "CONFIRM_FAILED",
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Explicit owner-directed reconciliation for an action in EXECUTION_UNCERTAIN state.
        Never retries automatically. Resolution must be 'CONFIRM_EXECUTED' or 'CONFIRM_FAILED'.
        """
        effective_actor, err = _authorize_mcp_call(
            business_id=business_id, supplied_actor_id=actor_id, required_scope="approvals:execute"
        )
        if err:
            return err
        try:
            receipt = _dispatcher.reconcile_uncertain_action(
                action_id=action_id,
                business_id=business_id,
                actor_id=effective_actor,
                resolution=resolution,
                notes=notes,
            )
            return {"status": receipt.status, "receipt": asdict(receipt)}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # -------------------------------------------------------------------------
    # Tool 33: process_incoming_email
    # -------------------------------------------------------------------------
    @server.tool()
    def process_incoming_email(
        email_id: str,
        business_id: str,
    ) -> Dict[str, Any]:
        """
        Triggers supervisor analysis for an ingested email.
        Creates/links operational task, classifies intent, retrieves business knowledge,
        and proposes authorized actions.
        """
        _, err = _authorize_mcp_call(business_id=business_id, required_scope="tasks:write")
        if err:
            return err
        email = _email_repo.get_by_id(email_id, business_id=business_id)
        if not email:
            return {"status": "NOT_FOUND", "error": f"Email '{email_id}' not found for business '{business_id}'."}
        try:
            outcome = _supervisor.process_email(email)
            return {
                "status": "PROCESSED",
                "task_id": outcome.task.task_id,
                "classification": outcome.classification.to_dict() if hasattr(outcome.classification, "to_dict") else asdict(outcome.classification),
                "proposals_count": len(outcome.action_proposals),
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # -------------------------------------------------------------------------
    # Tool 34: get_daily_operational_briefing (Voice-friendly Alexa+ briefing)
    # -------------------------------------------------------------------------
    @server.tool()
    def get_daily_operational_briefing(
        business_id: str,
        actor_id: str = "owner",
    ) -> Dict[str, Any]:
        """
        Generates a concise, voice-friendly daily operational briefing for the business owner.
        Summarizes pending approvals, prioritized operational tasks, cash state, and suggested actions.
        """
        effective_actor, err = _authorize_mcp_call(
            business_id=business_id, supplied_actor_id=actor_id, required_scope="business:read"
        )
        if err:
            return err
        try:
            return orchestrator.generate_daily_briefing(business_id=business_id, actor_id=effective_actor)
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    # -------------------------------------------------------------------------
    # Tool 35: query_business_orchestrator (Natural Language Assistant)
    # -------------------------------------------------------------------------
    @server.tool()
    def query_business_orchestrator(
        business_id: str,
        message: str,
        actor_id: str = "owner",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes natural language instructions, follow-ups, and queries for the business.
        Handles focus queries ('What should I focus on?'), multi-turn approval follow-ups
        ('explain the first one', 'approve it'), and urgent task reviews.
        """
        effective_actor, err = _authorize_mcp_call(
            business_id=business_id, supplied_actor_id=actor_id, required_scope="business:read"
        )
        if err:
            return err
        principal = get_current_mcp_principal()
        eff_session = session_id or (principal.session_id if principal else None)
        try:
            return orchestrator.handle_user_message(
                business_id=business_id,
                user_message=message,
                actor_id=effective_actor,
                session_id=eff_session,
            )
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    return server



# Default server instance for module-level import
server: FastMCP = create_mcp_server()


if __name__ == "__main__":
    server.run("stdio")
