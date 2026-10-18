"""
Mock data for Amazon Pay India sandbox testing.
================================================
Provides realistic INR payment data for demo and CI runs
when live Amazon Pay credentials are absent.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List

from src.integrations.amazon_pay.models import (
    AmazonPayCharge,
    AmazonPayChargePermission,
    AmazonPayPaymentSummary,
    AmazonPayRefund,
)

_NOW = "2026-10-10T19:10:00Z"

# ---------------------------------------------------------------------------
# Mock charge permission (long-lived merchant authorisation)
# ---------------------------------------------------------------------------
MOCK_CHARGE_PERMISSION = AmazonPayChargePermission(
    charge_permission_id="S02-1234567-1234567",
    merchant_id="MOCK_MERCHANT_KANPUR",
    state="Chargeable",
    limits={"amount": "50000.00", "currencyCode": "INR"},
    buyer={"name": "Demo Buyer", "email": "demo@example.in", "buyerId": "buyerMOCK001"},
    created_timestamp=_NOW,
    is_mock=True,
)

# ---------------------------------------------------------------------------
# Mock charges (individual payment captures)
# ---------------------------------------------------------------------------
MOCK_CHARGES: List[AmazonPayCharge] = [
    AmazonPayCharge(
        charge_id="S02-1234567-1234567-C001",
        charge_permission_id="S02-1234567-1234567",
        merchant_id="MOCK_MERCHANT_KANPUR",
        amount="3600.00",
        currency_code="INR",
        charge_state="Captured",
        payment_method="Amazon Pay Balance",
        created_timestamp="2026-10-08T10:00:00Z",
        status_details={"state": "Captured", "reasonCode": None},
        is_mock=True,
    ),
    AmazonPayCharge(
        charge_id="S02-1234567-1234567-C002",
        charge_permission_id="S02-1234567-1234567",
        merchant_id="MOCK_MERCHANT_KANPUR",
        amount="2400.00",
        currency_code="INR",
        charge_state="Captured",
        payment_method="UPI",
        created_timestamp="2026-10-09T11:30:00Z",
        status_details={"state": "Captured", "reasonCode": None},
        is_mock=True,
    ),
    AmazonPayCharge(
        charge_id="S02-1234567-1234567-C003",
        charge_permission_id="S02-1234567-1234567",
        merchant_id="MOCK_MERCHANT_KANPUR",
        amount="1800.00",
        currency_code="INR",
        charge_state="Declined",
        payment_method="Credit Card",
        created_timestamp="2026-10-10T09:00:00Z",
        status_details={"state": "Declined", "reasonCode": "TRANSACTION_TIMEOUT"},
        is_mock=True,
    ),
    AmazonPayCharge(
        charge_id="S02-1234567-1234567-C004",
        charge_permission_id="S02-1234567-1234567",
        merchant_id="MOCK_MERCHANT_KANPUR",
        amount="4200.00",
        currency_code="INR",
        charge_state="Chargeable",
        payment_method="Amazon Pay Balance",
        created_timestamp="2026-10-10T18:00:00Z",
        status_details={"state": "Chargeable", "reasonCode": None},
        is_mock=True,
    ),
]

# ---------------------------------------------------------------------------
# Mock refunds
# ---------------------------------------------------------------------------
MOCK_REFUNDS: List[AmazonPayRefund] = [
    AmazonPayRefund(
        refund_id="S02-1234567-1234567-R001",
        charge_id="S02-1234567-1234567-C001",
        refund_amount="600.00",
        currency_code="INR",
        refund_state="Refunded",
        created_timestamp="2026-10-09T08:00:00Z",
        is_mock=True,
    ),
]

# ---------------------------------------------------------------------------
# Pre-built summary
# ---------------------------------------------------------------------------
MOCK_PAYMENT_SUMMARY = AmazonPayPaymentSummary(
    merchant_id="MOCK_MERCHANT_KANPUR",
    total_charges=4,
    total_amount_captured=6000.00,   # C001 + C002 captured
    total_refunded=600.00,
    pending_charges=1,               # C004 Chargeable
    declined_charges=1,              # C003 Declined
    currency="INR",
    is_mock=True,
)


def get_mock_charge(charge_id: str) -> Dict[str, Any]:
    """Returns mock charge by ID, or first charge if not found."""
    for c in MOCK_CHARGES:
        if c.charge_id == charge_id:
            return c.to_dict()
    return MOCK_CHARGES[0].to_dict()


def get_mock_charges_list() -> List[Dict[str, Any]]:
    return [c.to_dict() for c in MOCK_CHARGES]


def get_mock_refunds_list() -> List[Dict[str, Any]]:
    return [r.to_dict() for r in MOCK_REFUNDS]
