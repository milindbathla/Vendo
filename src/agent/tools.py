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

# Singletons shared across tool calls within an agent run.
# These are lightweight in-memory objects; no DB open here.
_profiles = load_business_profiles()
_supplier_sim = SupplierCatalogueSimulator()


# ---------------------------------------------------------------------------
# Tool 1 -- get_business_overview
# Classification: read-only | source: simulation
# ---------------------------------------------------------------------------

def get_business_overview(business_type: str = "home_tiffin") -> Dict[str, Any]:
    """Return core economics for the named business profile.

    Provides selling price, unit cost, daily capacity, starting capital,
    base demand, and lead time for procurement. Use this as the first step
    when you need to understand the business context before making any
    recommendation.

    Args:
        business_type: The business profile identifier, e.g. "home_tiffin"
            (tiffin home kitchen), "retail_kirana" (general store),
            "salon_services" (beauty services). Defaults to "home_tiffin".

    Returns:
        A dict with keys: business_type, display_name, selling_price,
        unit_cost, daily_capacity, starting_capital, base_daily_demand,
        daily_fixed_cost, lead_time_days, simulation_notice.
    """
    if not isinstance(business_type, str) or not business_type.strip():
        raise ValueError("business_type must be a non-empty string.")

    prof = _profiles.get(business_type.strip(), _profiles.get("home_tiffin"))
    return {
        "business_type":     prof.business_type,
        "display_name":      prof.display_name,
        "selling_price":     prof.selling_price,
        "unit_cost":         prof.supplier_unit_cost,
        "daily_capacity":    prof.daily_capacity,
        "starting_capital":  prof.starting_capital,
        "base_daily_demand": prof.base_daily_demand,
        "daily_fixed_cost":  prof.daily_fixed_cost,
        "lead_time_days":    prof.procurement_lead_time_days,
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

    prof = _profiles.get(business_type.strip(), _profiles.get("home_tiffin"))
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


# ---------------------------------------------------------------------------
# Tool 4 -- get_supplier_quotes
# Classification: read-only | source: simulation
# ---------------------------------------------------------------------------

def get_supplier_quotes(
    supplier_id: str = "wholesale_mandi",
    needed_ingredients_json: str = "{}",
) -> Dict[str, Any]:
    """Fetch a price quote from a supplier for specified ingredient quantities.

    Use after identifying a procurement need to understand cost before
    creating any purchase plan.

    Args:
        supplier_id: Supplier identifier. Use "wholesale_mandi" for bulk
            wholesale or "quick_commerce" for express local delivery.
        needed_ingredients_json: JSON string mapping ingredient names to
            quantities needed, e.g.
            '{"rice": 5.0, "dal": 2.0, "cooking_oil": 1.0}'.

    Returns:
        A dict with supplier name, items list (ingredient, qty, unit price,
        total), total_cost, and delivery terms.
    """
    if not isinstance(supplier_id, str) or not supplier_id.strip():
        raise ValueError("supplier_id must be a non-empty string.")
    try:
        needed: Dict[str, float] = json.loads(needed_ingredients_json)
        if not isinstance(needed, dict):
            raise TypeError("needed_ingredients_json must be a JSON object.")
    except json.JSONDecodeError as exc:
        raise ValueError(f"needed_ingredients_json is not valid JSON: {exc}") from exc

    quote = _supplier_sim.get_quote(supplier_id.strip(), needed)
    result = quote.to_dict()
    result["simulation_notice"] = SIMULATION_NOTICE
    return result


# ---------------------------------------------------------------------------
# Tool 5 -- compare_procurement_channels
# Classification: read-only | source: simulation
# ---------------------------------------------------------------------------

def compare_procurement_channels(
    needed_ingredients_json: str = "{}",
) -> Dict[str, Any]:
    """Compare wholesale vs. quick-commerce procurement for a set of ingredients.

    Returns a side-by-side cost and lead-time comparison. Use this when the
    business owner is deciding whether to order in bulk (cheaper, slower) or
    use express delivery (faster, more expensive).

    Args:
        needed_ingredients_json: JSON string mapping ingredient names to
            quantities required, e.g. '{"rice": 5.0, "dal": 2.0}'.

    Returns:
        A dict with channel comparison data, recommended_channel, cost_savings,
        and lead_time information.
    """
    try:
        needed: Dict[str, float] = json.loads(needed_ingredients_json)
        if not isinstance(needed, dict):
            raise TypeError("needed_ingredients_json must be a JSON object.")
    except json.JSONDecodeError as exc:
        raise ValueError(f"needed_ingredients_json is not valid JSON: {exc}") from exc

    result = _supplier_sim.compare_procurement_channels(needed)
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
        place_types_json: JSON string list of place types to filter by.

    Returns:
        Dict with total_count, places list, and competitor analysis summary.
    """
    from src.integrations.google_places import GooglePlacesAdapter
    types = None
    if place_types_json:
        try:
            types = json.loads(place_types_json)
        except Exception:
            types = [t.strip() for t in place_types_json.split(",") if t.strip()]

    adapter = GooglePlacesAdapter()
    resp = adapter.search_nearby_places(
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        place_types=types,
    )
    return resp.to_dict()


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
}

# Ordered list for Gemini SDK (Python functions passed as tools)
TOOL_LIST = list(TOOL_REGISTRY.values())
