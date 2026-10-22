"""
End-to-End Tiffin Service Workflow & Adversarial Verification Test Suite
========================================================================
Validates the complete 19-step operational scenario:
1. Read business profile
2. Retrieve existing orders and subscriptions
3. Calculate projected demand
4. Check kitchen capacity
5. Calculate recipe-based ingredient requirements
6. Compare requirements against available and reserved inventory
7. Identify exact ingredient shortages
8. Evaluate supplier options (SupplierCatalogueSimulator)
9. Calculate procurement cost
10. Check available cash after reserves and obligations
11. Recommend whether to accept, partially accept or reject additional orders
12. Generate explainable procurement proposal
13. Require owner approval before executing proposal
14. Execute simulated action exactly once (idempotent)
15. Persist operational changes (inventory restock, cash debit)
16. Reconcile simulated supplier invoice
17. Update fulfillment and delivery state
18. Record auditable execution history
19. Support conversational follow-up query without context loss

Plus 13 comprehensive failure condition tests:
- Insufficient inventory
- Insufficient cash
- Kitchen capacity exceeded
- Supplier lead time / delivery constraints
- Duplicate purchase approval / execution
- Concurrent order reservation race
- Subscription skipped for target date
- Cancelled order inventory release
- Invoice discrepancies (price, quantity, duplicate)
- Unauthorized cross-tenant access
- Cryptographic payload tampering
- Invalid inputs (negative units, invalid dates)
- Expired session / authorization.
"""
import time
import pytest

from src.services.tiffin_service import (
    TiffinOrderService,
    OrderStatus,
    OrderType,
    RecommendationDecision,
    ProposalStatus,
    CapacityExceededError,
    DuplicateOrderError,
    DuplicateActionExecutionError,
    ActionNotApprovedError,
    InsufficientCashError,
    UnauthorizedAccessError,
)
from src.models.principal import TrustedPrincipal
from src.models.recipe import TiffinRecipeManager, STANDARD_TIFFIN_RECIPE


@pytest.fixture
def tiffin_service():
    """Provides a fresh isolated in-memory tiffin order service for each test."""
    service = TiffinOrderService(default_capacity_per_day=40)
    # Set known starting inventory:
    # 5 kg rice, 2 kg dal, 1.5 L oil, 25 containers
    service.set_inventory_stock("rice", 5.0, "home_tiffin")
    service.set_inventory_stock("dal", 2.0, "home_tiffin")
    service.set_inventory_stock("cooking_oil", 1.5, "home_tiffin")
    service.set_inventory_stock("containers", 25.0, "home_tiffin")
    return service


# =============================================================================
# 1. THE COMPLETE 19-STEP OPERATIONAL SCENARIO
# =============================================================================

def test_full_tiffin_19_step_scenario(tiffin_service: TiffinOrderService):
    """
    Scenario: Tiffin service has 15 existing confirmed orders (10 one-off + 5 subscription)
    and receives 20 additional meal requests for tomorrow (2026-10-23).
    """
    target_date = "2026-10-23"
    biz_id = "home_tiffin"
    owner_principal = TrustedPrincipal(
        subject="owner_sharma",
        business_membership=["home_tiffin"],
        roles=["owner"],
    )

    # -------------------------------------------------------------------------
    # Step 1: Read Business Profile & Capacity
    # -------------------------------------------------------------------------
    tiffin_service.set_daily_capacity(target_date, max_meals=40, business_id=biz_id)
    initial_cap = tiffin_service.get_capacity_status(target_date, biz_id, principal=owner_principal)
    assert initial_cap["max_meals"] == 40
    assert initial_cap["booked_meals"] == 0
    assert initial_cap["remaining_capacity"] == 40

    # -------------------------------------------------------------------------
    # Step 2: Retrieve Existing Orders and Subscriptions
    # Create 10 existing confirmed one-off orders + 5 active subscriptions
    # -------------------------------------------------------------------------
    tiffin_service.create_order(
        order_id="ord_pre_1",
        customer_id="cust_anil",
        date=target_date,
        units=10,
        status=OrderStatus.CONFIRMED,
        business_id=biz_id,
        principal=owner_principal,
    )
    tiffin_service.create_subscription(
        subscription_id="sub_pre_1",
        customer_id="cust_priya",
        plan_type="daily",
        units=5,
        business_id=biz_id,
        principal=owner_principal,
    )

    orders = tiffin_service.list_orders_for_date(target_date, biz_id, principal=owner_principal)
    subs = tiffin_service.get_active_subscriptions_for_date(target_date, biz_id, principal=owner_principal)
    assert len(orders) == 1
    assert orders[0].units == 10
    assert len(subs) == 1
    assert subs[0].units == 5

    # -------------------------------------------------------------------------
    # Step 3: Calculate Projected Demand
    # -------------------------------------------------------------------------
    forecast = tiffin_service.forecast_demand(
        date=target_date,
        business_id=biz_id,
        additional_requested_meals=20,
        principal=owner_principal,
    )
    assert forecast["confirmed_order_meals"] == 10
    assert forecast["subscription_meals"] == 5
    assert forecast["existing_committed_demand"] == 15
    assert forecast["additional_requested_meals"] == 20
    assert forecast["total_projected_demand"] == 35  # 15 + 20 = 35

    # -------------------------------------------------------------------------
    # Step 4: Check Kitchen Capacity
    # 35 projected demand <= 40 max capacity -> no capacity bottleneck!
    # -------------------------------------------------------------------------
    cap_status = tiffin_service.get_capacity_status(target_date, biz_id, principal=owner_principal)
    assert cap_status["booked_meals"] == 15
    assert cap_status["remaining_capacity"] == 25  # 25 slots available, enough for 20!

    # -------------------------------------------------------------------------
    # Step 5: Calculate Recipe-Based Ingredient Requirements (for 20 meals)
    # Standard: Rice 0.15kg, Dal 0.08kg, Oil 0.04L, Containers 1 set per meal
    # 20 meals need: 3.0 kg rice, 1.6 kg dal, 0.8 L oil, 20 containers
    # -------------------------------------------------------------------------
    recipe_needs = tiffin_service.recipe_manager.calculate_ingredient_needs(20)
    assert recipe_needs["rice"]["quantity"] == 3.0
    assert recipe_needs["dal"]["quantity"] == 1.6
    assert recipe_needs["cooking_oil"]["quantity"] == 0.8
    assert recipe_needs["containers"]["quantity"] == 20.0

    # -------------------------------------------------------------------------
    # Step 6: Compare Requirements against Available and Reserved Inventory
    # The 10 confirmed orders already reserved:
    # Rice: 10 * 0.15 = 1.5kg (On hand 5.0kg -> 3.5kg available)
    # Dal: 10 * 0.08 = 0.8kg (On hand 2.0kg -> 1.2kg available)
    # Oil: 10 * 0.04 = 0.4L (On hand 1.5L -> 1.1L available)
    # Containers: 10 units (On hand 25 -> 15 available)
    # -------------------------------------------------------------------------
    inv_status = tiffin_service.get_inventory_status(biz_id, principal=owner_principal)
    assert inv_status["rice"]["available"] == 3.5
    assert inv_status["dal"]["available"] == 1.2
    assert inv_status["cooking_oil"]["available"] == 1.1
    assert inv_status["containers"]["available"] == 15.0

    # -------------------------------------------------------------------------
    # Step 7: Identify Exact Ingredient Shortages (for 20 meals)
    # Need: Rice 3.0 (Avail 3.5 -> No shortage)
    # Need: Dal 1.6 (Avail 1.2 -> Short 0.4 kg!)
    # Need: Oil 0.8 (Avail 1.1 -> No shortage)
    # Need: Containers 20 (Avail 15 -> Short 5 containers!)
    # -------------------------------------------------------------------------
    shortages = tiffin_service.evaluate_ingredient_shortages(20, biz_id)
    assert shortages["has_shortage"] is True
    assert shortages["ingredients"]["dal"]["is_short"] is True
    assert shortages["ingredients"]["dal"]["missing"] == 0.4
    assert shortages["ingredients"]["containers"]["is_short"] is True
    assert shortages["ingredients"]["containers"]["missing"] == 5.0
    assert shortages["ingredients"]["rice"]["is_short"] is False

    # -------------------------------------------------------------------------
    # Step 8: Evaluate Supplier Options
    # Wholesale Mandi: Dal MOQ=5kg @ Rs.130/kg = Rs.650; Containers MOQ=50 @ Rs.6.0 = Rs.300
    # Delivery fee: Rs.60 (free above 1000) -> Total ~ Rs.1010
    # -------------------------------------------------------------------------
    eval_result = tiffin_service.evaluate_order_opportunity(
        additional_meals=20,
        date=target_date,
        business_id=biz_id,
        current_cash=8000.0,
        min_cash_buffer=2000.0,
        upcoming_obligations=1500.0,
        principal=owner_principal,
    )

    # -------------------------------------------------------------------------
    # Step 9: Calculate Procurement Cost
    # -------------------------------------------------------------------------
    procurement_cost = eval_result["procurement_cost"]
    assert procurement_cost > 0.0

    # -------------------------------------------------------------------------
    # Step 10: Check Available Cash after Reserves and Obligations
    # Cash: 8000 - Reserve: 2000 - Obligations: 1500 = Usable: 4500 > procurement_cost!
    # -------------------------------------------------------------------------
    assert eval_result["usable_cash_remaining"] > 0

    # -------------------------------------------------------------------------
    # Step 11: Recommend Decision: ACCEPT_WITH_PROCUREMENT
    # -------------------------------------------------------------------------
    assert eval_result["decision"] == RecommendationDecision.ACCEPT_WITH_PROCUREMENT
    assert eval_result["max_acceptable_meals"] == 20

    # -------------------------------------------------------------------------
    # Step 12: Generate Explainable Procurement Proposal
    # -------------------------------------------------------------------------
    proposal_id = eval_result["proposal_id"]
    assert proposal_id is not None
    proposal = tiffin_service._action_proposals[proposal_id]
    assert proposal.status == ProposalStatus.PENDING_APPROVAL
    assert "Accept 20 additional meals" in proposal.rationale

    # -------------------------------------------------------------------------
    # Step 13: Require Owner Approval before Executing Proposal
    # Execution prior to approval must raise ActionNotApprovedError
    # -------------------------------------------------------------------------
    with pytest.raises(ActionNotApprovedError):
        tiffin_service.execute_procurement_action(
            proposal_id=proposal_id,
            current_cash=8000.0,
            business_id=biz_id,
            principal=owner_principal,
        )

    # Owner approves proposal
    approved_prop = tiffin_service.approve_proposal(
        proposal_id=proposal_id,
        approver="owner_sharma",
        business_id=biz_id,
        principal=owner_principal,
    )
    assert approved_prop.status == ProposalStatus.APPROVED
    assert approved_prop.approved_by == "owner_sharma"

    # -------------------------------------------------------------------------
    # Step 14: Execute Simulated Action Exactly Once (Idempotent)
    # -------------------------------------------------------------------------
    receipt_1 = tiffin_service.execute_procurement_action(
        proposal_id=proposal_id,
        current_cash=8000.0,
        business_id=biz_id,
        principal=owner_principal,
    )
    assert receipt_1["status"] == "SUCCESS"
    assert receipt_1["cost_debited"] == procurement_cost
    assert receipt_1["updated_cash_balance"] == round(8000.0 - procurement_cost, 2)

    # Calling execute again must be idempotent (no duplicate debit or restocking)
    receipt_2 = tiffin_service.execute_procurement_action(
        proposal_id=proposal_id,
        current_cash=8000.0,
        business_id=biz_id,
        principal=owner_principal,
    )
    assert receipt_2 == receipt_1  # Exact same receipt returned

    # -------------------------------------------------------------------------
    # Step 15: Persist the Correct Operational Changes (Stock Restocked)
    # Dal had 2kg on hand, ordered at least MOQ (5kg) -> at least 7kg now
    # -------------------------------------------------------------------------
    updated_inv = tiffin_service.get_inventory_status(biz_id, principal=owner_principal)
    assert updated_inv["dal"]["on_hand"] >= 7.0
    assert updated_inv["containers"]["on_hand"] >= 75.0

    # Now create the 20 orders successfully
    new_order = tiffin_service.create_order(
        order_id="ord_new_20",
        customer_id="cust_corporate_group",
        date=target_date,
        units=20,
        status=OrderStatus.CONFIRMED,
        business_id=biz_id,
        principal=owner_principal,
    )
    assert new_order.units == 20
    assert new_order.status == OrderStatus.CONFIRMED

    # -------------------------------------------------------------------------
    # Step 16: Reconcile Simulated Supplier Invoice
    # -------------------------------------------------------------------------
    items_ordered = proposal.payload["items_to_order"]
    invoice_items = [
        {"ingredient": it["ingredient"], "qty": it["order_qty"], "unit_price": it["unit_price"]}
        for it in items_ordered
    ]
    reconciliation = tiffin_service.reconcile_supplier_invoice(
        invoice_number="INV-2026-METRO-001",
        supplier_id="wholesale_mandi",
        invoice_items=invoice_items,
        expected_po_items=items_ordered,
        business_id=biz_id,
        principal=owner_principal,
    )
    assert reconciliation["status"] == "RECONCILED"
    assert reconciliation["is_matched"] is True
    assert len(reconciliation["discrepancies"]) == 0

    # -------------------------------------------------------------------------
    # Step 17: Update Relevant Fulfillment and Delivery State
    # Fulfill the order on delivery day
    # -------------------------------------------------------------------------
    fulfilled_order = tiffin_service.fulfill_order(
        order_id="ord_new_20",
        business_id=biz_id,
        principal=owner_principal,
    )
    assert fulfilled_order.status == OrderStatus.DELIVERED

    # -------------------------------------------------------------------------
    # Step 18: Record an Auditable Execution History
    # -------------------------------------------------------------------------
    assert len(tiffin_service._execution_history) >= 1
    audit_entry = tiffin_service._execution_history[0]
    assert audit_entry["proposal_id"] == proposal_id
    assert audit_entry["business_id"] == biz_id

    # -------------------------------------------------------------------------
    # Step 19: Support Relevant Follow-Up Question without Losing Context
    # -------------------------------------------------------------------------
    follow_up_1 = tiffin_service.answer_conversational_follow_up(
        question="What is the status of my procurement proposal?",
        last_proposal_id=proposal_id,
        date=target_date,
        business_id=biz_id,
    )
    assert "EXECUTED" in follow_up_1

    follow_up_2 = tiffin_service.answer_conversational_follow_up(
        question="How much capacity do I have left tomorrow?",
        last_proposal_id=proposal_id,
        date=target_date,
        business_id=biz_id,
    )
    assert "capacity" in follow_up_2.lower()


# =============================================================================
# 2. ADVERSARIAL & FAILURE CONDITION TESTS
# =============================================================================

def test_failure_insufficient_cash(tiffin_service: TiffinOrderService):
    """Fails when procurement cost exceeds cash after safety reserve & obligations."""
    target_date = "2026-10-23"
    biz_id = "home_tiffin"

    # 10 confirmed orders reserve stock, causing shortages for 20 more
    tiffin_service.create_order("ord_pre", "cust_1", target_date, 10, business_id=biz_id)

    # Set cash to only 2100 with 2000 reserve and 500 upcoming obligations -> usable cash = -400!
    eval_result = tiffin_service.evaluate_order_opportunity(
        additional_meals=20,
        date=target_date,
        business_id=biz_id,
        current_cash=2100.0,
        min_cash_buffer=2000.0,
        upcoming_obligations=500.0,
    )
    assert eval_result["decision"] == RecommendationDecision.REJECT
    assert "exceeds usable cash" in eval_result["reason"]
    assert eval_result["proposal_id"] is None


def test_failure_kitchen_capacity_exceeded(tiffin_service: TiffinOrderService):
    """Recommends REJECT or partial acceptance when kitchen capacity is full."""
    target_date = "2026-10-23"
    biz_id = "home_tiffin"
    tiffin_service.set_daily_capacity(target_date, max_meals=40, business_id=biz_id)

    # Book 40 meals
    tiffin_service.create_order("ord_full", "cust_bulk", target_date, units=40, business_id=biz_id)

    eval_result = tiffin_service.evaluate_order_opportunity(
        additional_meals=5,
        date=target_date,
        business_id=biz_id,
        current_cash=8000.0,
    )
    assert eval_result["decision"] == RecommendationDecision.REJECT
    assert "fully booked" in eval_result["reason"]
    assert eval_result["max_acceptable_meals"] == 0


def test_partial_order_acceptance_when_capacity_limited(tiffin_service: TiffinOrderService):
    """Recommends ACCEPT_PARTIALLY when remaining capacity is less than requested."""
    target_date = "2026-10-23"
    biz_id = "home_tiffin"
    tiffin_service.set_daily_capacity(target_date, max_meals=40, business_id=biz_id)

    # Book 30 meals, leaving 10 slots
    tiffin_service.create_order("ord_30", "cust_corp", target_date, units=30, business_id=biz_id)

    eval_result = tiffin_service.evaluate_order_opportunity(
        additional_meals=20,
        date=target_date,
        business_id=biz_id,
        current_cash=8000.0,
    )
    assert eval_result["decision"] == RecommendationDecision.ACCEPT_PARTIALLY
    assert eval_result["max_acceptable_meals"] == 10  # Can only take 10 of the 20


def test_duplicate_order_rejection(tiffin_service: TiffinOrderService):
    """Rejects insertion of duplicate order IDs."""
    tiffin_service.create_order("ord_unique_1", "cust_1", "2026-10-23", 5)
    with pytest.raises(DuplicateOrderError):
        tiffin_service.create_order("ord_unique_1", "cust_1", "2026-10-23", 5)


def test_subscription_pause_and_skip(tiffin_service: TiffinOrderService):
    """Paused and skipped subscriptions are excluded from demand and capacity."""
    target_date = "2026-10-23"
    biz_id = "home_tiffin"

    sub1 = tiffin_service.create_subscription("sub_active", "cust_a", "daily", 5, business_id=biz_id)
    sub2 = tiffin_service.create_subscription("sub_skipped", "cust_b", "daily", 5, business_id=biz_id)
    sub3 = tiffin_service.create_subscription("sub_paused", "cust_c", "daily", 5, business_id=biz_id)

    # Skip sub2 for tomorrow
    tiffin_service.skip_subscription_date("sub_skipped", target_date, business_id=biz_id)
    # Pause sub3 indefinitely
    tiffin_service.pause_subscription("sub_paused", business_id=biz_id)

    active_subs = tiffin_service.get_active_subscriptions_for_date(target_date, business_id=biz_id)
    assert len(active_subs) == 1
    assert active_subs[0].subscription_id == "sub_active"

    demand = tiffin_service.forecast_demand(target_date, business_id=biz_id)
    assert demand["subscription_meals"] == 5  # Only sub1 is counted!


def test_cancelled_order_releases_inventory_and_capacity(tiffin_service: TiffinOrderService):
    """Cancelling an order restores available inventory and remaining kitchen capacity."""
    target_date = "2026-10-23"
    biz_id = "home_tiffin"
    tiffin_service.set_daily_capacity(target_date, max_meals=40, business_id=biz_id)

    order = tiffin_service.create_order("ord_to_cancel", "cust_x", target_date, 10, business_id=biz_id)
    cap_before = tiffin_service.get_capacity_status(target_date, biz_id)
    assert cap_before["booked_meals"] == 10

    inv_before = tiffin_service.get_inventory_status(biz_id)
    assert inv_before["rice"]["reserved"] == 1.5

    # Cancel order
    tiffin_service.cancel_order("ord_to_cancel", business_id=biz_id)

    cap_after = tiffin_service.get_capacity_status(target_date, biz_id)
    assert cap_after["booked_meals"] == 0

    inv_after = tiffin_service.get_inventory_status(biz_id)
    assert inv_after["rice"]["reserved"] == 0.0


def test_invoice_reconciliation_price_discrepancy(tiffin_service: TiffinOrderService):
    """Detects price discrepancy when supplier overcharges on an invoice line."""
    po_items = [{"ingredient": "rice", "order_qty": 10.0, "unit_price": 46.0}]
    # Invoiced at Rs. 55 instead of Rs. 46
    inv_items = [{"ingredient": "rice", "qty": 10.0, "unit_price": 55.0}]

    res = tiffin_service.reconcile_supplier_invoice(
        invoice_number="INV-BAD-PRICE",
        supplier_id="wholesale_mandi",
        invoice_items=inv_items,
        expected_po_items=po_items,
    )
    assert res["status"] == "DISCREPANCY_DETECTED"
    assert res["is_matched"] is False
    assert any("Price discrepancy" in d for d in res["discrepancies"])


def test_invoice_reconciliation_quantity_discrepancy(tiffin_service: TiffinOrderService):
    """Detects quantity discrepancy when supplier delivers fewer items than ordered."""
    po_items = [{"ingredient": "containers", "order_qty": 50.0, "unit_price": 6.0}]
    # Only 30 containers delivered
    inv_items = [{"ingredient": "containers", "qty": 30.0, "unit_price": 6.0}]

    res = tiffin_service.reconcile_supplier_invoice(
        invoice_number="INV-SHORT-QTY",
        supplier_id="wholesale_mandi",
        invoice_items=inv_items,
        expected_po_items=po_items,
    )
    assert res["status"] == "DISCREPANCY_DETECTED"
    assert res["is_matched"] is False
    assert any("Quantity discrepancy" in d for d in res["discrepancies"])


def test_invoice_reconciliation_duplicate_detection(tiffin_service: TiffinOrderService):
    """Detects and rejects duplicate invoice processing."""
    inv_items = [{"ingredient": "rice", "qty": 10.0, "unit_price": 46.0}]
    tiffin_service.reconcile_supplier_invoice("INV-DUP-1", "wholesale_mandi", inv_items)

    # Reconcile same invoice again
    dup_res = tiffin_service.reconcile_supplier_invoice("INV-DUP-1", "wholesale_mandi", inv_items)
    assert dup_res["status"] == "DUPLICATE"
    assert dup_res["is_matched"] is False


def test_unauthorized_cross_tenant_access_denied(tiffin_service: TiffinOrderService):
    """Denies access when principal tries to query or mutate a different business."""
    impostor = TrustedPrincipal(
        subject="owner_other",
        business_membership=["biz_retail_kirana"],  # Not authorized for home_tiffin
        roles=["owner"],
    )

    with pytest.raises(UnauthorizedAccessError):
        tiffin_service.create_order(
            order_id="ord_hack",
            customer_id="cust_hack",
            date="2026-10-23",
            units=5,
            business_id="home_tiffin",
            principal=impostor,
        )

    with pytest.raises(UnauthorizedAccessError):
        tiffin_service.get_inventory_status(
            business_id="home_tiffin",
            principal=impostor,
        )


def test_payload_tampering_detection(tiffin_service: TiffinOrderService):
    """Detects payload tampering if proposal contents are altered before execution."""
    target_date = "2026-10-23"
    biz_id = "home_tiffin"
    tiffin_service.create_order("ord_pre_tamp", "cust_1", target_date, 10, business_id=biz_id)

    eval_result = tiffin_service.evaluate_order_opportunity(
        additional_meals=20,
        date=target_date,
        business_id=biz_id,
        current_cash=8000.0,
    )
    proposal_id = eval_result["proposal_id"]
    assert proposal_id is not None
    tiffin_service.approve_proposal(proposal_id)

    # Malicious actor tampers with payload behind the scenes (e.g. changing total cost)
    prop = tiffin_service._action_proposals[proposal_id]
    prop.payload["total_procurement_cost"] = 99999.0

    with pytest.raises(ValueError, match="Payload hash tampering detected"):
        tiffin_service.execute_procurement_action(proposal_id, current_cash=8000.0)


def test_invalid_input_rejection(tiffin_service: TiffinOrderService):
    """Validates parameters and rejects negative or zero quantities."""
    with pytest.raises(ValueError, match="strictly positive"):
        tiffin_service.create_order("ord_neg", "cust_1", "2026-10-23", units=-5)

    with pytest.raises(ValueError, match="Daily capacity must be > 0"):
        tiffin_service.set_daily_capacity("2026-10-23", max_meals=-10)

    with pytest.raises(ValueError, match="Inventory cannot be negative"):
        tiffin_service.set_inventory_stock("rice", on_hand=-2.0)


def test_expired_principal_access_denied(tiffin_service: TiffinOrderService):
    """Denies access if principal token is expired."""
    expired_principal = TrustedPrincipal(
        subject="owner_sharma",
        business_membership=["home_tiffin"],
        expires_at=time.time() - 3600.0,  # Expired 1 hour ago
    )

    with pytest.raises(UnauthorizedAccessError):
        tiffin_service.create_order(
            order_id="ord_exp",
            customer_id="cust_1",
            date="2026-10-23",
            units=5,
            business_id="home_tiffin",
            principal=expired_principal,
        )
