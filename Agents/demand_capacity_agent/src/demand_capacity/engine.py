"""Deterministic business calculation engine shared across agents."""

import math
from typing import Any, Dict, List, Optional, Tuple


def calculate_effective_units(units: float, safety_stock_pct: float) -> float:
    """Calculate effective meal demand applying safety stock percentage."""
    return round(units * (1.0 + safety_stock_pct / 100.0), 3)


def calculate_item_requirement(
    effective_units: float,
    bom_qty: float,
    unit: str,
) -> float:
    """Translate tiffin demand into stock item requirement based on BOM and unit type."""
    raw_req = effective_units * bom_qty
    if unit == "pcs":
        return float(math.ceil(raw_req))
    return round(raw_req, 3)


def calculate_pack_procurement(
    needed_qty: float,
    pack_qty: float,
    price_per_pack: float,
    delivery_fee: float,
    free_delivery_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate integer packs needed, units provided, subtotal, delivery fee, and total cost."""
    if needed_qty <= 0:
        packs_needed = 0
    else:
        packs_needed = int(math.ceil(needed_qty / pack_qty))

    total_units_provided = round(packs_needed * pack_qty, 3)
    subtotal = round(packs_needed * price_per_pack, 2)

    if free_delivery_threshold is not None and subtotal >= free_delivery_threshold:
        applicable_delivery_fee = 0.0
    else:
        applicable_delivery_fee = round(delivery_fee, 2)

    total_cost = round(subtotal + applicable_delivery_fee, 2)

    return {
        "packs_needed": packs_needed,
        "total_units_provided": total_units_provided,
        "subtotal": subtotal,
        "applicable_delivery_fee": applicable_delivery_fee,
        "total_cost": total_cost,
    }


def is_arrival_feasible(earliest_arrival: str, deadline: str) -> bool:
    """Compare ISO/timestamp arrival string against deadline string.

    Format expected: 'YYYY-MM-DD HH:MM' or comparable ISO string.
    Lexicographical string comparison works correctly on standard ISO-formatted dates.
    """
    if not earliest_arrival or not deadline:
        return False
    return earliest_arrival <= deadline


def check_cash_buffer_compliance(
    additional_cost: float,
    min_projected_balance: float,
    min_cash_buffer: float,
) -> Tuple[bool, float, float]:
    """Check whether an additional expense preserves the required cash buffer.

    Returns:
    (is_compliant, post_expense_min_balance, headroom_remaining)
    """
    post_balance = round(min_projected_balance - additional_cost, 2)
    headroom_remaining = round(post_balance - min_cash_buffer, 2)
    is_compliant = post_balance >= min_cash_buffer
    return is_compliant, post_balance, headroom_remaining

