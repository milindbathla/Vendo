"""
Multi-Ingredient Recipe & Inventory Models
==========================================
Deterministic recipe requirements and multi-item inventory tracking
for the Home Tiffin & Meal Service MVP.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class IngredientRequirement:
    """Requirement of a single ingredient per finished unit (meal)."""
    name: str
    display_name: str
    quantity_per_meal: float  # e.g., 0.15 kg
    unit: str  # "kg", "litres", "pieces"
    base_unit_cost: float  # Rs per unit in standard wholesale


@dataclass
class IngredientStock:
    """Current stock and reorder parameters for an ingredient."""
    name: str
    display_name: str
    unit: str
    on_hand: float
    reorder_point: float
    target_stock: float
    unit_cost: float
    safety_stock: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "unit": self.unit,
            "on_hand": round(self.on_hand, 2),
            "reorder_point": round(self.reorder_point, 2),
            "target_stock": round(self.target_stock, 2),
            "unit_cost": round(self.unit_cost, 2),
        }


# Standard Indian Home Tiffin Recipe (Meal Breakdown)
# 1 Meal = 150g Rice + 80g Dal + 40ml Cooking Oil + 1 Tiffin Container Pack
STANDARD_TIFFIN_RECIPE: List[IngredientRequirement] = [
    IngredientRequirement(
        name="rice",
        display_name="Kolam / Sona Masoori Rice",
        quantity_per_meal=0.15,  # 150g = 0.15 kg
        unit="kg",
        base_unit_cost=48.0,  # Rs. 48/kg
    ),
    IngredientRequirement(
        name="dal",
        display_name="Toor Dal (Lentils)",
        quantity_per_meal=0.08,  # 80g = 0.08 kg
        unit="kg",
        base_unit_cost=135.0,  # Rs. 135/kg
    ),
    IngredientRequirement(
        name="cooking_oil",
        display_name="Sunflower Cooking Oil",
        quantity_per_meal=0.04,  # 40ml = 0.04 L
        unit="litres",
        base_unit_cost=125.0,  # Rs. 125/L
    ),
    IngredientRequirement(
        name="containers",
        display_name="Eco Meal Container & Foil Pack",
        quantity_per_meal=1.0,  # 1 set
        unit="units",
        base_unit_cost=6.5,  # Rs. 6.50/pack
    ),
]


class TiffinRecipeManager:
    """Calculates recipe requirements and checks ingredient shortages."""

    def __init__(self, recipe: Optional[List[IngredientRequirement]] = None):
        self.recipe = recipe or STANDARD_TIFFIN_RECIPE

    def calculate_ingredient_needs(self, meals_count: float) -> Dict[str, Dict[str, Any]]:
        """Calculates exact ingredient quantities needed for a given number of meals."""
        needs = {}
        for ing in self.recipe:
            total_qty = round(meals_count * ing.quantity_per_meal, 3)
            needs[ing.name] = {
                "name": ing.name,
                "display_name": ing.display_name,
                "quantity": total_qty,
                "unit": ing.unit,
                "unit_cost": ing.base_unit_cost,
                "estimated_cost": round(total_qty * ing.base_unit_cost, 2),
            }
        return needs

    def evaluate_shortages(
        self,
        meals_count: float,
        current_stocks: Dict[str, float],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compares requirements against on-hand stocks to identify missing quantities.
        Returns detailed shortage breakdown per ingredient.
        """
        needs = self.calculate_ingredient_needs(meals_count)
        shortages = {}
        total_shortage_cost = 0.0

        for name, req in needs.items():
            on_hand = current_stocks.get(name, 0.0)
            required = req["quantity"]
            missing = max(0.0, round(required - on_hand, 3))
            est_cost = round(missing * req["unit_cost"], 2)
            total_shortage_cost += est_cost

            shortages[name] = {
                "name": name,
                "display_name": req["display_name"],
                "unit": req["unit"],
                "required": required,
                "on_hand": on_hand,
                "missing": missing,
                "is_short": missing > 0.0,
                "unit_cost": req["unit_cost"],
                "shortage_cost": est_cost,
            }

        return {
            "meals_count": meals_count,
            "ingredients": shortages,
            "total_shortage_cost": round(total_shortage_cost, 2),
            "has_shortage": any(item["is_short"] for item in shortages.values()),
        }
