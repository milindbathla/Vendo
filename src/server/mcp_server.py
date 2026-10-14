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
from typing import Dict, Any, List, Optional

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
from src.integrations.google_places import GooglePlacesAdapter
from src.integrations.zoho_books import ZohoBooksAdapter


def create_mcp_server(
    approval_service: Optional[PurchaseApprovalService] = None,
    profiles: Optional[Dict[str, BusinessProfile]] = None,
    places_adapter: Optional[GooglePlacesAdapter] = None,
    zoho_adapter: Optional[ZohoBooksAdapter] = None,
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

    # -------------------------------------------------------------------------
    # Tool 1: get_business_state
    # -------------------------------------------------------------------------
    @server.tool()
    def get_business_state(business_type: str = "home_tiffin") -> Dict[str, Any]:
        """
        Retrieves current business economics, starting inventory, daily capacity ceiling,
        and cash parameters for the specified business profile.
        """
        prof = business_profiles.get(business_type, business_profiles.get("home_tiffin"))
        return {
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
            "simulation_notice": SIMULATION_NOTICE,
        }

    # -------------------------------------------------------------------------
    # Tool 2: get_upcoming_orders
    # -------------------------------------------------------------------------
    @server.tool()
    def get_upcoming_orders(business_type: str = "home_tiffin") -> Dict[str, Any]:
        """
        Retrieves scheduled baseline customer orders for tomorrow.
        """
        prof = business_profiles.get(business_type, business_profiles.get("home_tiffin"))
        # Baseline demand represents recurring daily subscriptions/orders
        return {
            "business_type": prof.business_type,
            "scheduled_orders_tomorrow": round(prof.base_daily_demand, 0),
            "order_type": "Daily subscription tiffins",
            "capacity_ceiling": round(prof.daily_capacity, 0),
            "available_capacity_headroom": max(0.0, round(prof.daily_capacity - prof.base_daily_demand, 0)),
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
        prof = business_profiles.get(business_type, business_profiles.get("home_tiffin"))
        orchestrator = BusinessAutopilotV2(profile=prof)

        decision: OpportunityDecision = orchestrator.evaluate_opportunity(
            additional_orders=additional_orders,
            current_demand=current_demand,
            current_inventory=current_inventory,
            total_cash=total_cash,
            daily_capacity=daily_capacity,
            cash_reserve_target=safety_reserve,
            user_question=user_question,
        )
        return decision.to_dict()

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
    # Tool 11: search_nearby_competitors (Google Places API New)
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
    # Tool 12: get_zoho_organization (Zoho Books API)
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
    # Tool 13: get_zoho_invoices (Zoho Books API)
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
    # Tool 14: get_zoho_expenses_and_bills (Zoho Books API)
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
    # Tool 15: get_external_integrations_status
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

    return server
