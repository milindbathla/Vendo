"""
Deterministic Supplier & Catalogue Simulator
=============================================
Simulates supplier catalog pricing, minimum order quantities (MOQ),
bulk tiers, and delivery lead times for Indian micro-enterprises.

DISCLAIMER:
All catalog data, pricing, delivery estimates, and fulfillment are
simulated deterministically for hackathon evaluation and testing.
This service is NOT connected to live Amazon retail or Amazon Now APIs.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


SIMULATION_NOTICE = (
    "Deterministic Local Supplier Simulator. "
    "Simulated data for hackathon demonstration. "
    "Not connected to live Amazon retail or Amazon Now."
)


@dataclass
class SupplierItemQuote:
    ingredient_name: str
    display_name: str
    requested_qty: float
    order_qty: float  # Adjusted for MOQ / package sizes
    unit: str
    unit_price: float
    total_price: float
    is_bulk_discount_applied: bool
    moq_applied: bool

    @property
    def item_name(self) -> str:
        return self.ingredient_name


@dataclass
class SupplierQuote:
    supplier_id: str
    supplier_name: str
    is_express: bool
    lead_time_hours: int
    lead_time_days: int
    delivery_fee: float
    items: List[SupplierItemQuote]
    subtotal: float
    total_cost: float
    simulation_notice: str = SIMULATION_NOTICE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "is_express": self.is_express,
            "lead_time_hours": self.lead_time_hours,
            "lead_time_days": self.lead_time_days,
            "delivery_fee": round(self.delivery_fee, 2),
            "subtotal": round(self.subtotal, 2),
            "total_cost": round(self.total_cost, 2),
            "simulation_notice": self.simulation_notice,
            "items": [
                {
                    "ingredient": it.ingredient_name,
                    "display_name": it.display_name,
                    "requested_qty": round(it.requested_qty, 2),
                    "order_qty": round(it.order_qty, 2),
                    "unit": it.unit,
                    "unit_price": round(it.unit_price, 2),
                    "total_price": round(it.total_price, 2),
                    "bulk_discount": it.is_bulk_discount_applied,
                    "moq_enforced": it.moq_applied,
                }
                for it in self.items
            ],
        }


class SupplierCatalogueSimulator:
    """Deterministic pricing and quote engine for supplier options."""

    # Deterministic supplier catalogue
    CATALOGUE = {
        "wholesale_mandi": {
            "id": "wholesale_mandi",
            "name": "Metro Wholesale Mandi",
            "is_express": False,
            "lead_time_hours": 24,
            "lead_time_days": 1,
            "delivery_fee": 60.0,
            "free_delivery_above": 1000.0,
            "pricing": {
                "rice": {"unit_price": 46.0, "bulk_price": 42.0, "bulk_threshold": 25.0, "moq": 10.0},
                "dal": {"unit_price": 130.0, "bulk_price": 120.0, "bulk_threshold": 15.0, "moq": 5.0},
                "cooking_oil": {"unit_price": 120.0, "bulk_price": 110.0, "bulk_threshold": 15.0, "moq": 5.0},
                "containers": {"unit_price": 6.0, "bulk_price": 5.2, "bulk_threshold": 100.0, "moq": 50.0},
            },
        },
        "kirana_express": {
            "id": "kirana_express",
            "name": "Local Kirana Express (Rapid 2-Hour)",
            "is_express": True,
            "lead_time_hours": 2,
            "lead_time_days": 0,
            "delivery_fee": 35.0,
            "free_delivery_above": 500.0,
            "pricing": {
                "rice": {"unit_price": 52.0, "bulk_price": 50.0, "bulk_threshold": 10.0, "moq": 1.0},
                "dal": {"unit_price": 145.0, "bulk_price": 140.0, "bulk_threshold": 5.0, "moq": 0.5},
                "cooking_oil": {"unit_price": 135.0, "bulk_price": 130.0, "bulk_threshold": 5.0, "moq": 1.0},
                "containers": {"unit_price": 7.5, "bulk_price": 7.0, "bulk_threshold": 50.0, "moq": 10.0},
            },
        },
        "textile_wholesaler": {
            "id": "textile_wholesaler",
            "name": "Surat & Delhi Textile Wholesalers",
            "is_express": False,
            "lead_time_hours": 48,
            "lead_time_days": 2,
            "delivery_fee": 120.0,
            "free_delivery_above": 5000.0,
            "pricing": {
                "plain_shirts": {"unit_price": 380.0, "bulk_price": 340.0, "bulk_threshold": 20.0, "moq": 5.0},
                "cotton_fabric_meters": {"unit_price": 180.0, "bulk_price": 150.0, "bulk_threshold": 30.0, "moq": 10.0},
                "buttons_threads": {"unit_price": 25.0, "bulk_price": 20.0, "bulk_threshold": 50.0, "moq": 10.0},
                "garment_packaging": {"unit_price": 12.0, "bulk_price": 9.0, "bulk_threshold": 50.0, "moq": 20.0},
            },
        },
        "auto_parts_distributor": {
            "id": "auto_parts_distributor",
            "name": "National Auto Spares & Parts Depot",
            "is_express": False,
            "lead_time_hours": 24,
            "lead_time_days": 1,
            "delivery_fee": 80.0,
            "free_delivery_above": 3000.0,
            "pricing": {
                "brake_pads": {"unit_price": 220.0, "bulk_price": 190.0, "bulk_threshold": 10.0, "moq": 2.0},
                "engine_oil_litre": {"unit_price": 320.0, "bulk_price": 290.0, "bulk_threshold": 10.0, "moq": 3.0},
                "air_filters": {"unit_price": 150.0, "bulk_price": 130.0, "bulk_threshold": 10.0, "moq": 2.0},
                "spark_plugs": {"unit_price": 95.0, "bulk_price": 80.0, "bulk_threshold": 20.0, "moq": 4.0},
            },
        },
    }

    def get_suppliers_for_category(self, category: str) -> List[Dict[str, Any]]:
        """Returns compatible suppliers for the given business category."""
        if category in ("clothing_retail", "tailoring_boutique"):
            return [self.CATALOGUE["textile_wholesaler"]]
        elif category in ("mechanical_repair", "electronics_repair"):
            return [self.CATALOGUE["auto_parts_distributor"]]
        elif category in ("home_tiffin", "food_catering", "home_bakery"):
            return [self.CATALOGUE["wholesale_mandi"], self.CATALOGUE["kirana_express"]]
        return list(self.CATALOGUE.values())

    def get_quote(
        self,
        supplier_id: str,
        needed_ingredients: Dict[str, float],
    ) -> SupplierQuote:
        """
        Calculates a deterministic quote for the requested ingredient quantities.
        Enforces supplier MOQ and applies volume discounts where threshold is met.
        """
        supplier = self.CATALOGUE.get(supplier_id)
        if not supplier:
            raise ValueError(f"Unknown supplier '{supplier_id}'. Available: {list(self.CATALOGUE.keys())}")

        item_quotes: List[SupplierItemQuote] = []
        subtotal = 0.0

        for ing_name, qty in needed_ingredients.items():
            if qty <= 0:
                continue

            pricing_info = supplier["pricing"].get(ing_name, {
                "unit_price": 50.0, "bulk_price": 45.0, "bulk_threshold": 20.0, "moq": 1.0
            })

            moq = pricing_info.get("moq", 1.0)
            order_qty = max(qty, moq)
            moq_applied = order_qty > qty

            bulk_thresh = pricing_info.get("bulk_threshold", 999.0)
            bulk_price = pricing_info.get("bulk_price", pricing_info["unit_price"])
            unit_price = pricing_info["unit_price"]

            if order_qty >= bulk_thresh:
                effective_price = bulk_price
                is_bulk = True
            else:
                effective_price = unit_price
                is_bulk = False

            item_total = order_qty * effective_price
            subtotal += item_total

            item_unit = pricing_info.get(
                "unit",
                "kg" if ing_name in ("rice", "dal") else ("litres" if ing_name == "cooking_oil" else "units")
            )

            item_quotes.append(
                SupplierItemQuote(
                    ingredient_name=ing_name,
                    display_name=ing_name.replace("_", " ").title(),
                    requested_qty=qty,
                    order_qty=order_qty,
                    unit=item_unit,
                    unit_price=effective_price,
                    total_price=item_total,
                    is_bulk_discount_applied=is_bulk,
                    moq_applied=moq_applied,
                )
            )

        delivery_fee = 0.0 if subtotal >= supplier["free_delivery_above"] else supplier["delivery_fee"]
        total_cost = subtotal + (delivery_fee if item_quotes else 0.0)

        return SupplierQuote(
            supplier_id=supplier["id"],
            supplier_name=supplier["name"],
            is_express=supplier["is_express"],
            lead_time_hours=supplier["lead_time_hours"],
            lead_time_days=supplier["lead_time_days"],
            delivery_fee=delivery_fee if item_quotes else 0.0,
            items=item_quotes,
            subtotal=subtotal,
            total_cost=total_cost,
        )

    def compare_procurement_channels(
        self,
        needed_ingredients: Optional[Dict[str, float]] = None,
        needed_items: Optional[Dict[str, float]] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compares regular wholesale delivery against urgent local delivery for any vertical."""
        items = needed_items if needed_items is not None else (needed_ingredients or {})

        # Determine best supplier pair based on category or items
        is_textile = (
            category in ("clothing_retail", "tailoring_boutique")
            or any(k in self.CATALOGUE["textile_wholesaler"]["pricing"] for k in items)
        )
        is_auto = (
            category in ("mechanical_repair", "electronics_repair")
            or any(k in self.CATALOGUE["auto_parts_distributor"]["pricing"] for k in items)
        )

        if is_textile:
            primary_quote = self.get_quote("textile_wholesaler", items)
            return {
                "simulation_notice": SIMULATION_NOTICE,
                "category": "clothing_retail",
                "wholesale": primary_quote.to_dict(),
                "primary_supplier": primary_quote.to_dict(),
                "suppliers_evaluated": ["textile_wholesaler"],
                "cost_difference": 0.0,
                "lead_time_difference_hours": 0,
            }
        elif is_auto:
            primary_quote = self.get_quote("auto_parts_distributor", items)
            return {
                "simulation_notice": SIMULATION_NOTICE,
                "category": "mechanical_repair",
                "wholesale": primary_quote.to_dict(),
                "primary_supplier": primary_quote.to_dict(),
                "suppliers_evaluated": ["auto_parts_distributor"],
                "cost_difference": 0.0,
                "lead_time_difference_hours": 0,
            }

        wholesale_quote = self.get_quote("wholesale_mandi", items)
        express_quote = self.get_quote("kirana_express", items)

        return {
            "simulation_notice": SIMULATION_NOTICE,
            "wholesale": wholesale_quote.to_dict(),
            "express": express_quote.to_dict(),
            "cost_difference": round(express_quote.total_cost - wholesale_quote.total_cost, 2),
            "lead_time_difference_hours": wholesale_quote.lead_time_hours - express_quote.lead_time_hours,
        }
