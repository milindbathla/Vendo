"""
Tiffin Service Management & Operational Autopilot
=================================================
Complete end-to-end business service for home tiffin and cloud-kitchen operations.
Implements:
- Order management (creation, status tracking, cancellations, inventory reservations)
- Subscriptions (daily/weekday recurring, pause, skip-date, resume, meal modifications)
- BOM-based recipe requirements and multi-item stock management
- Kitchen and delivery-slot capacity validation and overbooking prevention
- Projected demand forecasting integrating recurring subscriptions and one-off bookings
- Supplier procurement optimization (MOQ, bulk tiers, lead-time urgency, price comparison)
- Cash liquidity reserve safety and financial payables validation
- Two-phase action proposal gating, cryptographic payload verification, and idempotency
- Supplier invoice reconciliation (price discrepancies, quantity discrepancies, duplicate detection)
- Cross-tenant security isolation and conversational context persistence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from src.models.recipe import TiffinRecipeManager, STANDARD_TIFFIN_RECIPE, IngredientRequirement
from src.services.supplier_simulator import SupplierCatalogueSimulator, SupplierQuote
from src.models.principal import TrustedPrincipal
from src.db.connection import get_connection

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Domain Enums & Exceptions
# -----------------------------------------------------------------------------

class OrderStatus(str, Enum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderType(str, Enum):
    SUBSCRIPTION = "subscription"
    ONE_OFF = "one_off"


class RecommendationDecision(str, Enum):
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_PROCUREMENT = "ACCEPT_WITH_PROCUREMENT"
    ACCEPT_PARTIALLY = "ACCEPT_PARTIALLY"
    REJECT = "REJECT"


class ProposalStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


class TiffinServiceError(Exception):
    """Base exception for tiffin service errors."""


class OrderNotFoundError(TiffinServiceError):
    """Raised when an order ID is not found."""


class DuplicateOrderError(TiffinServiceError):
    """Raised when attempting to insert a duplicate order."""


class SubscriptionNotFoundError(TiffinServiceError):
    """Raised when a subscription ID is not found."""


class CapacityExceededError(TiffinServiceError):
    """Raised when requested orders exceed maximum kitchen capacity."""


class InsufficientStockError(TiffinServiceError):
    """Raised when on-hand inventory is insufficient and cannot be procured."""


class InsufficientCashError(TiffinServiceError):
    """Raised when required procurement violates minimum cash reserve."""


class UnauthorizedAccessError(TiffinServiceError):
    """Raised when cross-tenant access is attempted."""


class DuplicateActionExecutionError(TiffinServiceError):
    """Raised when an action proposal is executed more than once."""


class ActionNotApprovedError(TiffinServiceError):
    """Raised when executing an unapproved action proposal."""


class InvoiceDiscrepancyError(TiffinServiceError):
    """Raised when supplier invoice fails reconciliation."""


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

@dataclass
class TiffinOrder:
    order_id: str
    customer_id: str
    date: str
    units: int
    status: OrderStatus = OrderStatus.CONFIRMED
    order_type: OrderType = OrderType.ONE_OFF
    unit_price: float = 80.0
    amount: float = 0.0
    delivery_slot_id: Optional[str] = None
    business_id: str = "home_tiffin"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def __post_init__(self):
        if self.amount <= 0.0 and self.units > 0:
            self.amount = round(self.units * self.unit_price, 2)


@dataclass
class TiffinSubscription:
    subscription_id: str
    customer_id: str
    plan_type: str  # "daily", "weekday", "weekly"
    units: int
    unit_price: float = 80.0
    active: bool = True
    paused: bool = False
    skipped_dates: Set[str] = field(default_factory=set)
    business_id: str = "home_tiffin"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def is_active_for_date(self, target_date: str) -> bool:
        if not self.active or self.paused:
            return False
        if target_date in self.skipped_dates:
            return False
        return True


@dataclass
class TiffinActionProposal:
    proposal_id: str
    business_id: str
    action_type: str
    payload: Dict[str, Any]
    status: ProposalStatus = ProposalStatus.PENDING_APPROVAL
    estimated_cost: float = 0.0
    required_reserve: float = 2000.0
    rationale: str = ""
    created_at: float = field(default_factory=time.time)
    approved_at: Optional[float] = None
    approved_by: Optional[str] = None
    executed_at: Optional[float] = None
    execution_receipt: Optional[Dict[str, Any]] = None
    payload_hash: str = ""

    def __post_init__(self):
        if not self.payload_hash:
            canonical = json.dumps(self.payload, sort_keys=True)
            self.payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Main Service Implementation
# -----------------------------------------------------------------------------

class TiffinOrderService:
    """
    Comprehensive business service for managing orders, subscriptions,
    BOM ingredient inventories, capacity, procurement, and invoicing.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        recipe_manager: Optional[TiffinRecipeManager] = None,
        supplier_simulator: Optional[SupplierCatalogueSimulator] = None,
        default_capacity_per_day: int = 40,
    ):
        self.db_path = db_path
        self.recipe_manager = recipe_manager or TiffinRecipeManager()
        self.supplier_simulator = supplier_simulator or SupplierCatalogueSimulator()
        self.default_capacity_per_day = default_capacity_per_day

        # In-memory stores (used standalone or as transactional cache)
        self._orders: Dict[str, TiffinOrder] = {}
        self._subscriptions: Dict[str, TiffinSubscription] = {}
        self._inventory: Dict[str, Dict[str, float]] = {}  # business_id -> {item_name: on_hand}
        self._reserved_inventory: Dict[str, Dict[str, float]] = {}  # business_id -> {item_name: reserved_qty}
        self._capacity: Dict[str, Dict[str, int]] = {}  # business_id -> {date: max_meals}
        self._action_proposals: Dict[str, TiffinActionProposal] = {}
        self._reconciled_invoices: Dict[str, Dict[str, Any]] = {}
        self._execution_history: List[Dict[str, Any]] = []

        # Default inventory baseline for demo/test environments
        self._init_default_inventory("home_tiffin")

    def _init_default_inventory(self, business_id: str):
        """Initializes default realistic starting inventory if none exists."""
        if business_id not in self._inventory:
            self._inventory[business_id] = {
                "rice": 5.0,        # 5 kg on hand
                "dal": 2.0,         # 2 kg on hand
                "cooking_oil": 1.5, # 1.5 L on hand
                "containers": 25.0, # 25 containers on hand
            }
        if business_id not in self._reserved_inventory:
            self._reserved_inventory[business_id] = {
                "rice": 0.0,
                "dal": 0.0,
                "cooking_oil": 0.0,
                "containers": 0.0,
            }

    # -------------------------------------------------------------------------
    # Multi-Tenant & Security Verification
    # -------------------------------------------------------------------------

    def verify_tenant_access(self, business_id: str, principal: Optional[TrustedPrincipal]):
        """Verifies that the principal has authorized access to the requested business."""
        if principal is None:
            return  # Internal or unrestricted caller
        if not principal.has_business_access(business_id):
            raise UnauthorizedAccessError(
                f"Principal '{principal.subject}' is not authorized to access business '{business_id}'."
            )

    # -------------------------------------------------------------------------
    # Order Management
    # -------------------------------------------------------------------------

    def create_order(
        self,
        order_id: str,
        customer_id: str,
        date: str,
        units: int,
        status: OrderStatus = OrderStatus.CONFIRMED,
        order_type: OrderType = OrderType.ONE_OFF,
        unit_price: float = 80.0,
        delivery_slot_id: Optional[str] = None,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinOrder:
        """Creates a new customer order, enforces validation, and reserves stock if confirmed."""
        self.verify_tenant_access(business_id, principal)

        if units <= 0:
            raise ValueError(f"Order units must be strictly positive, got {units}")

        if order_id in self._orders:
            raise DuplicateOrderError(f"Order ID '{order_id}' already exists.")

        # Check kitchen capacity before confirming
        if status == OrderStatus.CONFIRMED:
            cap_status = self.get_capacity_status(date, business_id)
            if cap_status["booked_meals"] + units > cap_status["max_meals"]:
                raise CapacityExceededError(
                    f"Adding {units} meals for {date} exceeds kitchen capacity "
                    f"({cap_status['booked_meals']}/{cap_status['max_meals']} meals already booked)."
                )

        order = TiffinOrder(
            order_id=order_id,
            customer_id=customer_id,
            date=date,
            units=units,
            status=status,
            order_type=order_type,
            unit_price=unit_price,
            amount=round(units * unit_price, 2),
            delivery_slot_id=delivery_slot_id,
            business_id=business_id,
        )

        self._orders[order_id] = order

        # If confirmed, reserve inventory based on BOM
        if status == OrderStatus.CONFIRMED:
            self._reserve_recipe_stock(units, business_id)

        return order

    def get_order(
        self,
        order_id: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinOrder:
        self.verify_tenant_access(business_id, principal)
        order = self._orders.get(order_id)
        if not order or order.business_id != business_id:
            raise OrderNotFoundError(f"Order '{order_id}' not found for business '{business_id}'.")
        return order

    def list_orders_for_date(
        self,
        date: str,
        business_id: str = "home_tiffin",
        status: Optional[OrderStatus] = None,
        principal: Optional[TrustedPrincipal] = None,
    ) -> List[TiffinOrder]:
        self.verify_tenant_access(business_id, principal)
        result = [
            o for o in self._orders.values()
            if o.business_id == business_id and o.date == date
        ]
        if status:
            result = [o for o in result if o.status == status]
        return result

    def update_order_quantity(
        self,
        order_id: str,
        new_units: int,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinOrder:
        order = self.get_order(order_id, business_id, principal)
        if new_units <= 0:
            raise ValueError(f"New units must be strictly positive, got {new_units}")

        diff = new_units - order.units
        if diff > 0 and order.status == OrderStatus.CONFIRMED:
            cap_status = self.get_capacity_status(order.date, business_id)
            if cap_status["booked_meals"] + diff > cap_status["max_meals"]:
                raise CapacityExceededError("Updated quantity exceeds kitchen capacity.")
            self._reserve_recipe_stock(diff, business_id)
        elif diff < 0 and order.status == OrderStatus.CONFIRMED:
            self._release_recipe_stock(abs(diff), business_id)

        order.units = new_units
        order.amount = round(new_units * order.unit_price, 2)
        return order

    def cancel_order(
        self,
        order_id: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinOrder:
        order = self.get_order(order_id, business_id, principal)
        if order.status == OrderStatus.CONFIRMED:
            self._release_recipe_stock(order.units, business_id)
        order.status = OrderStatus.CANCELLED
        return order

    def fulfill_order(
        self,
        order_id: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinOrder:
        order = self.get_order(order_id, business_id, principal)
        if order.status == OrderStatus.DELIVERED:
            return order  # Idempotent

        # Consume from on-hand inventory
        needs = self.recipe_manager.calculate_ingredient_needs(order.units)
        stocks = self._inventory.get(business_id, {})
        reserved = self._reserved_inventory.get(business_id, {})

        for name, req in needs.items():
            qty = req["quantity"]
            stocks[name] = max(0.0, round(stocks.get(name, 0.0) - qty, 3))
            reserved[name] = max(0.0, round(reserved.get(name, 0.0) - qty, 3))

        order.status = OrderStatus.DELIVERED
        return order

    # -------------------------------------------------------------------------
    # Subscription Management
    # -------------------------------------------------------------------------

    def create_subscription(
        self,
        subscription_id: str,
        customer_id: str,
        plan_type: str = "daily",
        units: int = 1,
        unit_price: float = 80.0,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinSubscription:
        self.verify_tenant_access(business_id, principal)
        if units <= 0:
            raise ValueError(f"Subscription units must be > 0, got {units}")

        sub = TiffinSubscription(
            subscription_id=subscription_id,
            customer_id=customer_id,
            plan_type=plan_type,
            units=units,
            unit_price=unit_price,
            business_id=business_id,
        )
        self._subscriptions[subscription_id] = sub
        return sub

    def pause_subscription(
        self,
        subscription_id: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinSubscription:
        self.verify_tenant_access(business_id, principal)
        sub = self._subscriptions.get(subscription_id)
        if not sub or sub.business_id != business_id:
            raise SubscriptionNotFoundError(f"Subscription '{subscription_id}' not found.")
        sub.paused = True
        return sub

    def resume_subscription(
        self,
        subscription_id: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinSubscription:
        self.verify_tenant_access(business_id, principal)
        sub = self._subscriptions.get(subscription_id)
        if not sub or sub.business_id != business_id:
            raise SubscriptionNotFoundError(f"Subscription '{subscription_id}' not found.")
        sub.paused = False
        return sub

    def skip_subscription_date(
        self,
        subscription_id: str,
        target_date: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinSubscription:
        self.verify_tenant_access(business_id, principal)
        sub = self._subscriptions.get(subscription_id)
        if not sub or sub.business_id != business_id:
            raise SubscriptionNotFoundError(f"Subscription '{subscription_id}' not found.")
        sub.skipped_dates.add(target_date)
        return sub

    def get_active_subscriptions_for_date(
        self,
        target_date: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> List[TiffinSubscription]:
        self.verify_tenant_access(business_id, principal)
        return [
            s for s in self._subscriptions.values()
            if s.business_id == business_id and s.is_active_for_date(target_date)
        ]

    # -------------------------------------------------------------------------
    # Recipe & Multi-Item Inventory Management
    # -------------------------------------------------------------------------

    def set_inventory_stock(
        self,
        item_name: str,
        on_hand: float,
        business_id: str = "home_tiffin",
    ):
        """Sets on-hand stock for an ingredient, preventing negative values."""
        self._init_default_inventory(business_id)
        if on_hand < 0.0:
            raise ValueError(f"Inventory cannot be negative, got {on_hand}")
        self._inventory[business_id][item_name] = round(float(on_hand), 3)

    def get_inventory_status(
        self,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> Dict[str, Dict[str, float]]:
        self.verify_tenant_access(business_id, principal)
        self._init_default_inventory(business_id)
        stocks = self._inventory[business_id]
        reserved = self._reserved_inventory[business_id]

        status = {}
        for item, on_hand in stocks.items():
            res = reserved.get(item, 0.0)
            avail = max(0.0, round(on_hand - res, 3))
            status[item] = {
                "on_hand": on_hand,
                "reserved": res,
                "available": avail,
            }
        return status

    def _reserve_recipe_stock(self, meals_count: int, business_id: str):
        """Internal helper to reserve ingredient stock for confirmed orders."""
        self._init_default_inventory(business_id)
        needs = self.recipe_manager.calculate_ingredient_needs(meals_count)
        reserved = self._reserved_inventory[business_id]
        for name, req in needs.items():
            reserved[name] = round(reserved.get(name, 0.0) + req["quantity"], 3)

    def _release_recipe_stock(self, meals_count: int, business_id: str):
        """Internal helper to release reserved stock when orders are cancelled."""
        self._init_default_inventory(business_id)
        needs = self.recipe_manager.calculate_ingredient_needs(meals_count)
        reserved = self._reserved_inventory[business_id]
        for name, req in needs.items():
            reserved[name] = max(0.0, round(reserved.get(name, 0.0) - req["quantity"], 3))

    def evaluate_ingredient_shortages(
        self,
        meals_count: float,
        business_id: str = "home_tiffin",
    ) -> Dict[str, Any]:
        """
        Calculates recipe ingredient needs for meals_count and evaluates
        shortages strictly against AVAILABLE (unreserved) inventory.
        """
        self._init_default_inventory(business_id)
        status = self.get_inventory_status(business_id)
        available_stocks = {k: v["available"] for k, v in status.items()}

        eval_result = self.recipe_manager.evaluate_shortages(meals_count, available_stocks)
        return eval_result

    # -------------------------------------------------------------------------
    # Capacity Management
    # -------------------------------------------------------------------------

    def set_daily_capacity(self, date: str, max_meals: int, business_id: str = "home_tiffin"):
        if max_meals <= 0:
            raise ValueError("Daily capacity must be > 0")
        if business_id not in self._capacity:
            self._capacity[business_id] = {}
        self._capacity[business_id][date] = max_meals

    def get_capacity_status(
        self,
        date: str,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> Dict[str, Any]:
        self.verify_tenant_access(business_id, principal)
        max_meals = self._capacity.get(business_id, {}).get(date, self.default_capacity_per_day)

        # Count confirmed orders + active subscriptions for this date
        confirmed_orders = self.list_orders_for_date(date, business_id, status=OrderStatus.CONFIRMED)
        order_units = sum(o.units for o in confirmed_orders)

        active_subs = self.get_active_subscriptions_for_date(date, business_id)
        sub_units = sum(s.units for s in active_subs)

        booked_meals = order_units + sub_units
        remaining_capacity = max(0, max_meals - booked_meals)

        return {
            "date": date,
            "max_meals": max_meals,
            "booked_meals": booked_meals,
            "remaining_capacity": remaining_capacity,
            "is_full": booked_meals >= max_meals,
        }

    # -------------------------------------------------------------------------
    # Demand Forecasting
    # -------------------------------------------------------------------------

    def forecast_demand(
        self,
        date: str,
        business_id: str = "home_tiffin",
        additional_requested_meals: int = 0,
        principal: Optional[TrustedPrincipal] = None,
    ) -> Dict[str, Any]:
        """
        Computes projected demand considering:
        - Confirmed one-off orders
        - Active subscriptions (excluding paused and skipped)
        - New requested meals
        Avoids double-counting!
        """
        self.verify_tenant_access(business_id, principal)

        confirmed_orders = self.list_orders_for_date(date, business_id, status=OrderStatus.CONFIRMED)
        order_meals = sum(o.units for o in confirmed_orders)

        active_subs = self.get_active_subscriptions_for_date(date, business_id)
        sub_meals = sum(s.units for s in active_subs)

        existing_demand = order_meals + sub_meals
        total_projected_demand = existing_demand + additional_requested_meals

        return {
            "date": date,
            "confirmed_orders_count": len(confirmed_orders),
            "confirmed_order_meals": order_meals,
            "active_subscriptions_count": len(active_subs),
            "subscription_meals": sub_meals,
            "existing_committed_demand": existing_demand,
            "additional_requested_meals": additional_requested_meals,
            "total_projected_demand": total_projected_demand,
        }

    # -------------------------------------------------------------------------
    # Comprehensive Order Opportunity Evaluation & Action Proposal
    # -------------------------------------------------------------------------

    def evaluate_order_opportunity(
        self,
        additional_meals: int,
        date: str,
        business_id: str = "home_tiffin",
        current_cash: float = 8000.0,
        min_cash_buffer: float = 2000.0,
        upcoming_obligations: float = 0.0,
        principal: Optional[TrustedPrincipal] = None,
    ) -> Dict[str, Any]:
        """
        Full 11-step evaluation scenario:
        1. Read business profile & capacity
        2. Retrieve existing commitments & demand
        3. Check capacity bottleneck
        4. Calculate BOM recipe shortages against available stock
        5. Evaluate supplier quotes (MOQ, bulk discounts, lead time)
        6. Validate cash affordability after reserve & obligations
        7. Make explainable recommendation (ACCEPT, ACCEPT_WITH_PROCUREMENT, ACCEPT_PARTIALLY, REJECT)
        8. Generate formal action proposal if procurement required
        """
        self.verify_tenant_access(business_id, principal)

        # 1. Capacity check
        cap_status = self.get_capacity_status(date, business_id)
        remaining_cap = cap_status["remaining_capacity"]

        if remaining_cap <= 0:
            return {
                "decision": RecommendationDecision.REJECT,
                "reason": f"Kitchen capacity for {date} is fully booked ({cap_status['booked_meals']}/{cap_status['max_meals']} meals).",
                "max_acceptable_meals": 0,
                "shortages": {},
                "supplier_quote": None,
                "proposal_id": None,
            }

        meals_to_evaluate = min(additional_meals, remaining_cap)
        is_partial = meals_to_evaluate < additional_meals

        # 2. Recipe & Shortage evaluation
        shortage_result = self.evaluate_ingredient_shortages(meals_to_evaluate, business_id)
        has_shortage = shortage_result["has_shortage"]

        # 3. If no shortage and capacity allows full order -> ACCEPT immediately
        if not has_shortage and not is_partial:
            return {
                "decision": RecommendationDecision.ACCEPT,
                "reason": f"Available inventory and kitchen capacity ({remaining_cap} slots) can fulfill all {additional_meals} meals without new procurement.",
                "max_acceptable_meals": additional_meals,
                "shortages": {},
                "supplier_quote": None,
                "proposal_id": None,
            }

        # 4. If shortage exists, query SupplierCatalogueSimulator
        supplier_quote: Optional[SupplierQuote] = None
        procurement_cost = 0.0

        if has_shortage:
            shortage_dict = {
                name: data["missing"]
                for name, data in shortage_result["ingredients"].items()
                if data["is_short"]
            }
            # Quote Metro Wholesale Mandi (or express if same day)
            supplier_quote = self.supplier_simulator.get_quote(
                supplier_id="wholesale_mandi",
                needed_ingredients=shortage_dict,
            )
            procurement_cost = supplier_quote.total_cost

        # 5. Financial Position & Cash Safety Reserve
        usable_cash = current_cash - min_cash_buffer - upcoming_obligations
        is_cash_constrained = usable_cash < procurement_cost

        if is_cash_constrained:
            return {
                "decision": RecommendationDecision.REJECT,
                "reason": (
                    f"Procurement cost Rs. {procurement_cost:.2f} exceeds usable cash Rs. {usable_cash:.2f} "
                    f"(Total Rs. {current_cash:.2f} - Reserve Rs. {min_cash_buffer:.2f} - Obligations Rs. {upcoming_obligations:.2f})."
                ),
                "max_acceptable_meals": 0,
                "shortages": shortage_result["ingredients"],
                "supplier_quote": supplier_quote.to_dict() if supplier_quote else None,
                "proposal_id": None,
            }

        # 6. Generate Proposal if procurement is required
        decision = (
            RecommendationDecision.ACCEPT_PARTIALLY if is_partial
            else RecommendationDecision.ACCEPT_WITH_PROCUREMENT
        )

        proposal_id = f"prop_{business_id}_{int(time.time())}_{meals_to_evaluate}"
        payload = {
            "business_id": business_id,
            "target_date": date,
            "meals_count": meals_to_evaluate,
            "supplier_id": supplier_quote.supplier_id if supplier_quote else None,
            "supplier_name": supplier_quote.supplier_name if supplier_quote else None,
            "total_procurement_cost": procurement_cost,
            "items_to_order": [
                {
                    "ingredient": it.ingredient_name,
                    "order_qty": it.order_qty,
                    "unit": it.unit,
                    "unit_price": it.unit_price,
                    "total_price": it.total_price,
                }
                for it in supplier_quote.items
            ] if supplier_quote else [],
        }

        rationale = (
            f"Accept {meals_to_evaluate} additional meals on {date}. "
            f"Procure {len(supplier_quote.items) if supplier_quote else 0} short ingredients "
            f"from {supplier_quote.supplier_name if supplier_quote else 'local market'} for Rs. {procurement_cost:.2f}. "
            f"Remaining liquid cash after order: Rs. {current_cash - procurement_cost:.2f} (Reserve: Rs. {min_cash_buffer:.2f})."
        )

        proposal = TiffinActionProposal(
            proposal_id=proposal_id,
            business_id=business_id,
            action_type="procure_tiffin_ingredients",
            payload=payload,
            status=ProposalStatus.PENDING_APPROVAL,
            estimated_cost=procurement_cost,
            required_reserve=min_cash_buffer,
            rationale=rationale,
        )
        self._action_proposals[proposal_id] = proposal

        return {
            "decision": decision,
            "reason": rationale,
            "max_acceptable_meals": meals_to_evaluate,
            "shortages": shortage_result["ingredients"],
            "supplier_quote": supplier_quote.to_dict() if supplier_quote else None,
            "proposal_id": proposal_id,
            "procurement_cost": procurement_cost,
            "usable_cash_remaining": round(usable_cash - procurement_cost, 2),
        }

    # -------------------------------------------------------------------------
    # Two-Phase Action Approval & Idempotent Execution
    # -------------------------------------------------------------------------

    def approve_proposal(
        self,
        proposal_id: str,
        approver: str = "owner_sharma",
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> TiffinActionProposal:
        """Explicit owner approval gate for an action proposal."""
        self.verify_tenant_access(business_id, principal)
        prop = self._action_proposals.get(proposal_id)
        if not prop or prop.business_id != business_id:
            raise ValueError(f"Proposal '{proposal_id}' not found.")

        if prop.status == ProposalStatus.EXECUTED:
            raise DuplicateActionExecutionError(f"Proposal '{proposal_id}' is already executed.")

        prop.status = ProposalStatus.APPROVED
        prop.approved_at = time.time()
        prop.approved_by = approver
        return prop

    def execute_procurement_action(
        self,
        proposal_id: str,
        current_cash: float,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> Dict[str, Any]:
        """
        Executes an approved procurement proposal exactly once.
        Guarantees idempotency and verifies payload hash integrity.
        """
        self.verify_tenant_access(business_id, principal)
        prop = self._action_proposals.get(proposal_id)
        if not prop or prop.business_id != business_id:
            raise ValueError(f"Proposal '{proposal_id}' not found.")

        if prop.status == ProposalStatus.EXECUTED:
            # Idempotency guarantee: return existing receipt without duplicate side-effects
            return prop.execution_receipt  # type: ignore

        if prop.status != ProposalStatus.APPROVED:
            raise ActionNotApprovedError(
                f"Cannot execute proposal '{proposal_id}' in state '{prop.status.value}'. Must be APPROVED."
            )

        # Cryptographic payload verification
        canonical = json.dumps(prop.payload, sort_keys=True)
        current_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if current_hash != prop.payload_hash:
            raise ValueError("Payload hash tampering detected. Execution aborted.")

        cost = prop.estimated_cost
        if current_cash - cost < prop.required_reserve:
            raise InsufficientCashError(
                f"Execution rejected: Remaining cash Rs. {current_cash - cost:.2f} "
                f"violates minimum safety reserve Rs. {prop.required_reserve:.2f}."
            )

        # Execute simulated restocking
        items_ordered = prop.payload.get("items_to_order", [])
        self._init_default_inventory(business_id)
        stocks = self._inventory[business_id]

        for item in items_ordered:
            ing = item["ingredient"]
            qty = item["order_qty"]
            stocks[ing] = round(stocks.get(ing, 0.0) + qty, 3)

        receipt = {
            "receipt_id": f"rcpt_{int(time.time())}_{proposal_id[-6:]}",
            "proposal_id": proposal_id,
            "business_id": business_id,
            "status": "SUCCESS",
            "cost_debited": cost,
            "updated_cash_balance": round(current_cash - cost, 2),
            "restocked_items": items_ordered,
            "timestamp": time.time(),
        }

        prop.status = ProposalStatus.EXECUTED
        prop.executed_at = time.time()
        prop.execution_receipt = receipt

        self._execution_history.append(receipt)
        return receipt

    # -------------------------------------------------------------------------
    # Supplier Invoice Reconciliation
    # -------------------------------------------------------------------------

    def reconcile_supplier_invoice(
        self,
        invoice_number: str,
        supplier_id: str,
        invoice_items: List[Dict[str, Any]],
        expected_po_items: Optional[List[Dict[str, Any]]] = None,
        business_id: str = "home_tiffin",
        principal: Optional[TrustedPrincipal] = None,
    ) -> Dict[str, Any]:
        """
        Reconciles supplier invoice against expected Purchase Order lines.
        Detects:
        - Duplicate invoices
        - Price discrepancies (overcharging)
        - Quantity discrepancies (under/over-delivery)
        """
        self.verify_tenant_access(business_id, principal)

        if invoice_number in self._reconciled_invoices:
            return {
                "invoice_number": invoice_number,
                "status": "DUPLICATE",
                "is_matched": False,
                "discrepancies": [f"Invoice '{invoice_number}' has already been processed and reconciled."],
            }

        discrepancies = []
        is_matched = True

        if expected_po_items is not None:
            po_map = {item["ingredient"]: item for item in expected_po_items}
            for inv_item in invoice_items:
                name = inv_item.get("ingredient")
                if name not in po_map:
                    discrepancies.append(f"Unexpected item in invoice: {name}")
                    is_matched = False
                    continue

                po_item = po_map[name]
                # Price check
                if abs(inv_item.get("unit_price", 0.0) - po_item.get("unit_price", 0.0)) > 0.01:
                    discrepancies.append(
                        f"Price discrepancy on '{name}': Invoiced Rs. {inv_item.get('unit_price')}, PO Rs. {po_item.get('unit_price')}"
                    )
                    is_matched = False

                # Quantity check
                if abs(inv_item.get("qty", 0.0) - po_item.get("order_qty", 0.0)) > 0.01:
                    discrepancies.append(
                        f"Quantity discrepancy on '{name}': Invoiced {inv_item.get('qty')}, PO {po_item.get('order_qty')}"
                    )
                    is_matched = False

        status = "RECONCILED" if is_matched else "DISCREPANCY_DETECTED"
        result = {
            "invoice_number": invoice_number,
            "supplier_id": supplier_id,
            "status": status,
            "is_matched": is_matched,
            "discrepancies": discrepancies,
            "reconciled_at": time.time(),
        }

        self._reconciled_invoices[invoice_number] = result
        return result

    # -------------------------------------------------------------------------
    # Conversational Multi-Turn Query Support
    # -------------------------------------------------------------------------

    def answer_conversational_follow_up(
        self,
        question: str,
        last_proposal_id: Optional[str] = None,
        date: str = "2026-10-23",
        business_id: str = "home_tiffin",
    ) -> str:
        """
        Answers follow-up conversational queries grounded in live state.
        Preserves context between proposal generation and execution.
        """
        q_lower = question.lower()

        if "status" in q_lower or "proposal" in q_lower or "order" in q_lower:
            if last_proposal_id and last_proposal_id in self._action_proposals:
                prop = self._action_proposals[last_proposal_id]
                return (
                    f"Proposal {prop.proposal_id} is currently in state '{prop.status.value}'. "
                    f"Rationale: {prop.rationale}"
                )

        if "stock" in q_lower or "inventory" in q_lower or "rice" in q_lower or "dal" in q_lower:
            stocks = self.get_inventory_status(business_id)
            details = [f"{k}: {v['on_hand']} on hand ({v['available']} available)" for k, v in stocks.items()]
            return f"Current kitchen stock: {', '.join(details)}."

        if "capacity" in q_lower or "how many" in q_lower:
            cap = self.get_capacity_status(date, business_id)
            return (
                f"On {date}, kitchen capacity is {cap['max_meals']} meals. "
                f"{cap['booked_meals']} meals are currently committed, leaving {cap['remaining_capacity']} slots available."
            )

        return (
            f"Vendo Autopilot is tracking your kitchen capacity, orders, and recipes for {business_id}. "
            "How can I help with tomorrow's prep or supplier orders?"
        )
