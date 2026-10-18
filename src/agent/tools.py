"""
Alexa Business Autopilot -- Agent Tool Registry
================================================
Declares a curated, minimal set of read-only tools that a Gemini agent can
invoke to answer a small-business owner's question.

Design principles
-----------------
* **Read-only**: No tool mutates state or commits purchases.
  Consequential actions remain gated by the existing PurchaseApprovalService.
* **Domain-agnostic**: Tools describe generic business concepts (cash position,
  inventory, capacity, supplier options) rather than tiffin-specific operations.
* **Deterministic**: Each tool wraps existing, tested application services.
  No model-generated SQL, no shell commands, no arbitrary code execution.
* **Validated**: Each callable validates its own inputs and returns a typed dict.
* **Not database-backed yet**: Tools use the existing in-process simulation
  services. The TeammateGateway integration is scoped to a future milestone
  (see Milestone B documentation in autopilot_agent.py).

Tool registry (TOOL_REGISTRY) maps a stable tool name to a Python callable.
The Gemini SDK discovers schema from type annotations and docstrings.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.simulator import load_business_profiles
from src.services.supplier_simulator import SupplierCatalogueSimulator, SIMULATION_NOTICE
from src.decision.business_autopilot import BusinessAutopilotV2
from src.db.connection import DEFAULT_DB_PATH
from src.db.profile_repository import AdaptiveProfileRepository
from src.agent.orchestrator import AdaptiveBusinessOrchestrator

# Singletons shared across tool calls within an agent run.
_profiles = load_business_profiles()
_supplier_sim = SupplierCatalogueSimulator()
_active_adaptive_repo: Optional[AdaptiveProfileRepository] = None
_active_business_id: Optional[str] = None


def set_active_profile_repo(repo: Optional[AdaptiveProfileRepository]) -> None:
    """Configures the adaptive repository for the agent session (used for test isolation)."""
    global _active_adaptive_repo
    _active_adaptive_repo = repo


def set_active_business_id(business_id: Optional[str]) -> None:
    """Configures the active business ID for the agent session."""
    global _active_business_id
    _active_business_id = business_id


def get_active_business_id() -> Optional[str]:
    """Returns the active business ID for the agent session."""
    return _active_business_id


def _get_repo() -> AdaptiveProfileRepository:
    """Returns active adaptive repository or default SQLite instance."""
    if _active_adaptive_repo is not None:
        return _active_adaptive_repo
    return AdaptiveProfileRepository(DEFAULT_DB_PATH)


# ---------------------------------------------------------------------------
# Tool 1 -- get_business_overview
# Classification: read-only | source: adaptive DB or static profiles
# ---------------------------------------------------------------------------

def get_business_overview(business_type: str = "home_tiffin") -> Dict[str, Any]:
    """Return core economics for the named business profile.

    Inspects the adaptive profile repository first. If the business was onboarded,
    returns its verified confirmed facts, capacity, cash, and category.
    If the business matches a legacy static profile (e.g. home_tiffin, salon_service),
    returns that baseline. If unknown, returns an explicit NOT_FOUND response
    instead of silently defaulting to another business.

    Args:
        business_type: The business profile identifier, e.g. "home_tiffin",
            "biz_kalyan_electronics", "biz_mohan_garments", "salon_services".

    Returns:
        A dict with business details, economics, confirmed facts, and status.
    """
    if not isinstance(business_type, str) or not business_type.strip():
        raise ValueError("business_type must be a non-empty string.")

    b_type = business_type.strip()
    if b_type == "home_tiffin" and _active_business_id:
        b_type = _active_business_id

    import sqlite3 as _sqlite3
    repo = _get_repo()

    # 1. Check adaptive repository
    try:
        adaptive_prof = repo.get_profile(b_type)
    except _sqlite3.OperationalError:
        adaptive_prof = None  # adaptive table not yet initialised in this DB
    if adaptive_prof is not None:
        selling_price = adaptive_prof.get_value("selling_price")
        unit_cost = adaptive_prof.get_value("unit_material_cost", adaptive_prof.get_value("supplier_unit_cost"))
        capacity = adaptive_prof.get_value("daily_capacity")
        cash_bal = adaptive_prof.get_value("cash_balance", adaptive_prof.get_value("starting_capital"))
        fixed_cost = adaptive_prof.get_value("daily_fixed_cost")
        confirmed_keys = [k for k, f in adaptive_prof.facts.items() if f.status.value == "confirmed"]

        return {
            "status": "SUCCESS",
            "business_type": adaptive_prof.business_id,
            "display_name": adaptive_prof.display_name,
            "category": adaptive_prof.category,
            "selling_price": selling_price,
            "unit_cost": unit_cost,
            "daily_capacity": capacity,
            "starting_capital": cash_bal,
            "cash_balance": cash_bal,
            "safety_reserve": adaptive_prof.get_value("safety_reserve"),
            "base_daily_demand": adaptive_prof.get_value("base_daily_demand", 0.0),
            "daily_fixed_cost": fixed_cost,
            "lead_time_days": adaptive_prof.get_value("procurement_lead_time_days", 1),
            "current_inventory": adaptive_prof.get_value("current_inventory"),
            "onboarding_completed": adaptive_prof.onboarding_completed,
            "confirmed_facts": confirmed_keys,
            "is_adaptive": True,
            "simulation_notice": SIMULATION_NOTICE,
        }

    # 2. Check static legacy profiles
    if b_type in _profiles:
        prof = _profiles[b_type]
        return {
            "status": "SUCCESS",
            "business_type": prof.business_type,
            "display_name": prof.display_name,
            "category": prof.business_type,
            "selling_price": prof.selling_price,
            "unit_cost": prof.supplier_unit_cost,
            "daily_capacity": prof.daily_capacity,
            "starting_capital": prof.starting_capital,
            "base_daily_demand": prof.base_daily_demand,
            "daily_fixed_cost": prof.daily_fixed_cost,
            "lead_time_days": prof.procurement_lead_time_days,
            "is_adaptive": False,
            "simulation_notice": SIMULATION_NOTICE,
        }

    # 3. Explicit NOT_FOUND -- NO silent fallback
    return {
        "status": "NOT_FOUND",
        "error": f"Business profile '{b_type}' was not found. Please onboard or create this profile first.",
        "business_type": b_type,
        "is_adaptive": False,
        "simulation_notice": SIMULATION_NOTICE,
    }


# ---------------------------------------------------------------------------
# Tool 2 -- get_financial_position
# Classification: read-only | source: simulation
# ---------------------------------------------------------------------------

def get_financial_position(
    total_cash: float = 8000.0,
    safety_reserve: float = 2000.0,
) -> Dict[str, Any]:
    """Inspect liquid cash balance, safety reserve, and spendable capital.

    Calculates how much cash is available for procurement above the mandatory
    safety buffer. Use before any purchase recommendation to avoid breaching
    the minimum liquidity reserve.

    Args:
        total_cash: Current cash or bank balance in INR (e.g. 8000.0).
        safety_reserve: Mandatory minimum cash buffer in INR that must not be
            spent (e.g. 2000.0).

    Returns:
        A dict with keys: total_cash, safety_reserve, usable_cash,
        is_cash_constrained, simulation_notice.
    """
    if not isinstance(total_cash, (int, float)):
        raise TypeError("total_cash must be a number.")
    if not isinstance(safety_reserve, (int, float)):
        raise TypeError("safety_reserve must be a number.")
    if float(total_cash) < 0:
        raise ValueError("total_cash cannot be negative.")
    if float(safety_reserve) < 0:
        raise ValueError("safety_reserve cannot be negative.")

    usable = max(0.0, float(total_cash) - float(safety_reserve))
    return {
        "total_cash":          round(total_cash, 2),
        "safety_reserve":      round(safety_reserve, 2),
        "usable_cash":         round(usable, 2),
        "is_cash_constrained": usable < 1000.0,
        "simulation_notice":   SIMULATION_NOTICE,
    }


# ---------------------------------------------------------------------------
# Tool 3 -- evaluate_order_opportunity
# Classification: read-only | source: deterministic decision engine
# ---------------------------------------------------------------------------

def evaluate_order_opportunity(
    additional_orders: float,
    business_type: str = "home_tiffin",
    current_demand: Optional[float] = None,
    current_inventory: Optional[float] = None,
    total_cash: Optional[float] = None,
    daily_capacity: Optional[float] = None,
    safety_reserve: float = 2000.0,
) -> Dict[str, Any]:
    """Evaluate whether the business can safely accept additional orders.

    Runs a multi-step analysis across demand, inventory, capacity, and cash
    constraints. Returns a structured decision (ACCEPT, ACCEPT_WITH_PROCUREMENT,
    ACCEPT_PARTIALLY, or REJECT) with supporting evidence and recommendations.

    Use this for any question about taking on more orders, fulfilling a large
    booking, or assessing overall feasibility of a new opportunity.

    Args:
        additional_orders: Number of extra units/orders being considered (> 0).
        business_type: Profile identifier (default: "home_tiffin").
        current_demand: Today's already-committed orders (units). If omitted,
            uses the profile default.
        current_inventory: On-hand stock (units). If omitted, uses profile default.
        total_cash: Current cash balance in INR. If omitted, uses profile default.
        daily_capacity: Maximum units producible per day. If omitted, uses profile.
        safety_reserve: Cash buffer in INR that must not be breached (default 2000).

    Returns:
        A dict with keys: decision, reason, fulfillable_additional_orders,
        unfulfillable_additional_orders, fulfilled_demand, procurement_units,
        procurement_cost, voice_response, recommendations, tool_trace.
    """
    if not isinstance(additional_orders, (int, float)) or additional_orders <= 0:
        raise ValueError("additional_orders must be a positive number.")
    if not isinstance(business_type, str) or not business_type.strip():
        raise ValueError("business_type must be a non-empty string.")

    b_type = business_type.strip()
    if b_type == "home_tiffin" and _active_business_id:
        b_type = _active_business_id

    import sqlite3 as _sqlite3
    repo = _get_repo()

    # 1. Check adaptive repository
    try:
        adaptive_prof = repo.get_profile(b_type)
    except _sqlite3.OperationalError:
        adaptive_prof = None  # adaptive table not yet initialised in this DB
    if adaptive_prof is not None:
        orchestrator = AdaptiveBusinessOrchestrator(repo=repo)
        return orchestrator.evaluate_opportunity(
            profile=adaptive_prof,
            additional_units=float(additional_orders),
            current_demand=current_demand,
            current_inventory=current_inventory,
            total_cash=total_cash,
            daily_capacity=daily_capacity,
            safety_reserve=safety_reserve,
        )

    # 2. Check static legacy profiles
    if b_type in _profiles:
        prof = _profiles[b_type]
        engine = BusinessAutopilotV2(profile=prof)
        decision = engine.evaluate_opportunity(
            additional_orders=float(additional_orders),
            current_demand=current_demand,
            current_inventory=current_inventory,
            total_cash=total_cash,
            daily_capacity=daily_capacity,
            cash_reserve_target=float(safety_reserve),
        )
        result = decision.to_dict()
        result["simulation_notice"] = SIMULATION_NOTICE
        return result

    # 3. Explicit NOT_FOUND -- NO silent fallback
    return {
        "status": "NOT_FOUND",
        "decision": "REJECT",
        "error": f"Business profile '{b_type}' was not found. Please onboard or select a valid profile.",
        "business_type": b_type,
        "simulation_notice": SIMULATION_NOTICE,
    }


# ---------------------------------------------------------------------------
# Tool 4 -- get_supplier_quotes
# Classification: read-only | source: simulation
# ---------------------------------------------------------------------------

def get_supplier_quotes(
    supplier_id: str = "wholesale_mandi",
    needed_ingredients_json: str = "{}",
    needed_items_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch a price quote from a supplier for specified material, part, or ingredient quantities.

    Use after identifying a procurement need to understand cost before
    creating any purchase plan.

    Args:
        supplier_id: Supplier identifier (e.g. "wholesale_mandi", "kirana_express",
            "textile_wholesaler", "auto_parts_distributor").
        needed_ingredients_json: JSON string mapping item names to quantities needed.
        needed_items_json: Alias for needed_ingredients_json for general business items.

    Returns:
        A dict with supplier name, items list (ingredient/item, qty, unit price,
        total), total_cost, and delivery terms.
    """
    sid = supplier_id.strip() if isinstance(supplier_id, str) else "wholesale_mandi"
    raw_json = needed_items_json if needed_items_json is not None else needed_ingredients_json

    # Dynamic supplier selection if caller passed default wholesale_mandi for non-food vertical
    if sid == "wholesale_mandi" and _active_business_id:
        repo = _get_repo()
        prof = repo.get_profile(_active_business_id)
        if prof:
            if prof.category in ("clothing_retail", "tailoring_boutique"):
                sid = "textile_wholesaler"
            elif prof.category in ("mechanical_repair", "electronics_repair"):
                sid = "auto_parts_distributor"

    try:
        needed: Dict[str, float] = json.loads(raw_json)
        if not isinstance(needed, dict):
            raise TypeError("needed items/ingredients must be a JSON object.")
    except json.JSONDecodeError as exc:
        raise ValueError(f"needed items/ingredients is not valid JSON: {exc}") from exc

    quote = _supplier_sim.get_quote(sid, needed)
    result = quote.to_dict()
    result["simulation_notice"] = SIMULATION_NOTICE
    return result


# ---------------------------------------------------------------------------
# Tool 5 -- compare_procurement_channels
# Classification: read-only | source: simulation
# ---------------------------------------------------------------------------

def compare_procurement_channels(
    needed_ingredients_json: str = "{}",
    needed_items_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare procurement channels for materials, parts, or goods.

    Returns a side-by-side cost and lead-time comparison for any small business vertical.

    Args:
        needed_ingredients_json: JSON string mapping item names to quantities required.
        needed_items_json: Alias for needed_ingredients_json for general business items.

    Returns:
        A dict with channel comparison data, recommended_channel, cost_savings,
        and lead_time information.
    """
    raw_json = needed_items_json if needed_items_json is not None else needed_ingredients_json
    try:
        needed: Dict[str, float] = json.loads(raw_json)
        if not isinstance(needed, dict):
            raise TypeError("needed items/ingredients must be a JSON object.")
    except json.JSONDecodeError as exc:
        raise ValueError(f"needed items/ingredients is not valid JSON: {exc}") from exc

    cat = None
    if _active_business_id:
        repo = _get_repo()
        prof = repo.get_profile(_active_business_id)
        if prof:
            cat = prof.category

    result = _supplier_sim.compare_procurement_channels(needed_items=needed, category=cat)
    result["simulation_notice"] = SIMULATION_NOTICE
    return result


# ---------------------------------------------------------------------------
# Tool 6 -- search_nearby_competitors
# Classification: read-only | source: Google Places API (New)
# ---------------------------------------------------------------------------

def search_nearby_competitors(
    latitude: float = 26.4727,
    longitude: float = 80.3015,
    radius_meters: float = 1500.0,
    place_types_json: str = '["restaurant", "meal_delivery"]',
) -> Dict[str, Any]:
    """Search for nearby businesses and competitor density via Google Places API (New).

    Returns normalized place listings, ratings, distance in meters, and competitor metrics.
    Data limitation: Represents public commercial listings, not customer demand proof.

    Args:
        latitude: Latitude coordinate (-90.0 to 90.0). Defaults to Kanpur anchor (26.4727).
        longitude: Longitude coordinate (-180.0 to 180.0). Defaults to Kanpur anchor (80.3015).
        radius_meters: Search radius in meters (max 50,000m). Defaults to 1500m.
        place_types_json: JSON string list of place types to filter by. Defaults dynamically
            to the active business's category when set.

    Returns:
        Dict with total_count, places list, and competitor analysis summary.
    """
    from src.integrations.google_places import GooglePlacesAdapter

    # If caller used default place_types but an active profile is set, adapt place types to vertical
    pt_json = place_types_json
    if pt_json == '["restaurant", "meal_delivery"]' and _active_business_id:
        repo = _get_repo()
        prof = repo.get_profile(_active_business_id)
        if prof:
            cat_map = {
                "mechanical_repair": ["car_repair", "auto_repair"],
                "electronics_repair": ["electronics_store", "home_goods_store"],
                "clothing_retail": ["clothing_store", "shopping_mall"],
                "tailoring_boutique": ["clothing_store"],
                "salon_service": ["beauty_salon", "hair_care"],
                "small_fabrication": ["hardware_store"],
                "home_bakery": ["bakery"],
                "home_tiffin": ["restaurant", "meal_delivery"],
                "retail_kirana": ["grocery_or_supermarket"],
            }
            if prof.category in cat_map:
                pt_json = json.dumps(cat_map[prof.category])
    types = None
    if pt_json:
        try:
            types = json.loads(pt_json)
        except Exception:
            types = [t.strip() for t in pt_json.split(",") if t.strip()]

    adapter = GooglePlacesAdapter()
    resp = adapter.search_nearby_places(
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        place_types=types,
    )
    result = resp.to_dict()
    result["status"] = "SUCCESS" if resp.success else "FAILED"
    result["place_types_queried"] = types
    return result


# ---------------------------------------------------------------------------
# Tool 7 -- get_zoho_accounting_summary
# Classification: read-only | source: Zoho Books API
# ---------------------------------------------------------------------------

def get_zoho_accounting_summary(organization_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve verified accounting summary from Zoho Books API.

    Returns invoiced revenue, cash collected, outstanding receivables,
    overdue receivables, and vendor bills payable. Strictly distinguishes
    billed revenue from collected cash.

    Args:
        organization_id: Optional Zoho Organization ID. If omitted, uses default.

    Returns:
        Dict with total_invoiced_revenue, cash_collected, outstanding_receivables,
        and bills payable.
    """
    from src.integrations.zoho_books import ZohoBooksAdapter
    adapter = ZohoBooksAdapter(org_id=organization_id)
    summary = adapter.get_accounting_summary()
    return {
        "status": "SUCCESS",
        "accounting_summary": summary.to_dict(),
        "is_mock": adapter.is_mock,
    }


# ---------------------------------------------------------------------------
# Tool 8 -- get_adaptive_profile
# Classification: read-only | source: adaptive SQLite database
# ---------------------------------------------------------------------------

def get_adaptive_profile(business_id: str) -> Dict[str, Any]:
    """Retrieve full profile details and granular fact history for an onboarded business.

    Use when you need to inspect confirmed facts, assumptions, and missing prerequisites
    for a specific business.

    Args:
        business_id: The unique business identifier (e.g. "biz_kalyan_electronics").

    Returns:
        Dict with status, business metadata, confirmed facts, assumed defaults, and outdated facts.
    """
    if not isinstance(business_id, str) or not business_id.strip():
        raise ValueError("business_id must be a non-empty string.")

    repo = _get_repo()
    profile = repo.get_profile(business_id.strip())
    if not profile:
        return {
            "status": "NOT_FOUND",
            "business_id": business_id,
            "error": f"Profile '{business_id}' not found. Please onboard first.",
        }
    return {
        "status": "SUCCESS",
        "profile": profile.to_dict(),
    }


# ---------------------------------------------------------------------------
# Tool 9 -- onboard_or_update_business
# Classification: conversational state | source: adaptive onboarding engine
# ---------------------------------------------------------------------------

def onboard_or_update_business(
    message: str,
    business_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Process natural language business descriptions to extract or update facts.

    Extracts business name, category, prices, unit material costs, daily capacity,
    cash balance, and fixed overhead. Tracks fact provenance and flags missing prerequisites.

    Args:
        message: Natural language description, e.g. "I run a clothing shop selling shirts for Rs 800."
        business_id: Optional existing profile ID to update or resume.

    Returns:
        Dict with business_id, category, extracted_facts, missing_critical_facts, and follow-up question.
    """
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string.")

    repo = _get_repo()
    orchestrator = AdaptiveBusinessOrchestrator(repo=repo)
    return orchestrator.handle_user_message(message=message, business_id=business_id)


# ---------------------------------------------------------------------------
# Tool 10 -- list_registered_businesses
# Classification: read-only | source: adaptive SQLite database
# ---------------------------------------------------------------------------

def list_registered_businesses() -> Dict[str, Any]:
    """List all registered adaptive business profiles and their categories."""
    repo = _get_repo()
    profiles = repo.list_profiles()
    return {
        "status": "SUCCESS",
        "count": len(profiles),
        "profiles": profiles,
    }


# ---------------------------------------------------------------------------
# Public registry -- maps stable names to callables
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, Any] = {
    "get_business_overview":        get_business_overview,
    "get_financial_position":       get_financial_position,
    "evaluate_order_opportunity":   evaluate_order_opportunity,
    "get_supplier_quotes":          get_supplier_quotes,
    "compare_procurement_channels": compare_procurement_channels,
    "search_nearby_competitors":    search_nearby_competitors,
    "get_zoho_accounting_summary":  get_zoho_accounting_summary,
    "get_adaptive_profile":         get_adaptive_profile,
    "onboard_or_update_business":   onboard_or_update_business,
    "list_registered_businesses":   list_registered_businesses,
}

# Ordered list for Gemini SDK (Python functions passed as tools)
TOOL_LIST = list(TOOL_REGISTRY.values())
