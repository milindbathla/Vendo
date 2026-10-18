"""
Data models for Amazon Pay India API integration.
==================================================
Covers payment charges, charge permissions, refunds,
and webhook notification payloads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AmazonPayCharge:
    """Represents a single Amazon Pay charge (payment)."""
    charge_id: str
    charge_permission_id: str
    merchant_id: str
    amount: str                          # string per Amazon Pay spec e.g. "150.00"
    currency_code: str = "INR"
    charge_state: str = "Chargeable"    # Chargeable, Captured, Declined, Canceled
    payment_method: Optional[str] = None
    created_timestamp: Optional[str] = None
    status_details: Optional[Dict[str, Any]] = None
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chargeId": self.charge_id,
            "chargePermissionId": self.charge_permission_id,
            "merchantId": self.merchant_id,
            "chargeAmount": {"amount": self.amount, "currencyCode": self.currency_code},
            "chargeState": {"state": self.charge_state},
            "paymentPreferences": [{"paymentDescriptor": self.payment_method}] if self.payment_method else [],
            "creationTimestamp": self.created_timestamp,
            "statusDetails": self.status_details,
            "is_mock": self.is_mock,
        }


@dataclass
class AmazonPayRefund:
    """Represents an Amazon Pay refund."""
    refund_id: str
    charge_id: str
    refund_amount: str
    currency_code: str = "INR"
    refund_state: str = "Refunded"       # Pending, Refunded, Declined
    created_timestamp: Optional[str] = None
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "refundId": self.refund_id,
            "chargeId": self.charge_id,
            "refundAmount": {"amount": self.refund_amount, "currencyCode": self.currency_code},
            "refundState": {"state": self.refund_state},
            "creationTimestamp": self.created_timestamp,
            "is_mock": self.is_mock,
        }


@dataclass
class AmazonPayChargePermission:
    """Long-lived charge permission (recurring billing authorisation)."""
    charge_permission_id: str
    merchant_id: str
    state: str = "Chargeable"            # Chargeable, NonChargeable, Closed
    limits: Optional[Dict[str, Any]] = None
    buyer: Optional[Dict[str, str]] = None
    created_timestamp: Optional[str] = None
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chargePermissionId": self.charge_permission_id,
            "merchantId": self.merchant_id,
            "chargePermissionState": {"state": self.state},
            "limits": self.limits,
            "buyer": self.buyer,
            "creationTimestamp": self.created_timestamp,
            "is_mock": self.is_mock,
        }


@dataclass
class AmazonPayWebhookEvent:
    """Parsed Amazon Pay IPN webhook event."""
    notification_type: str               # CHARGE_DECLINED, CHARGE_CAPTURED, REFUND_COMPLETED
    object_type: str                     # CHARGE, REFUND, CHARGE_PERMISSION
    object_id: str
    merchant_id: str
    timestamp: str
    raw_payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notificationType": self.notification_type,
            "objectType": self.object_type,
            "objectId": self.object_id,
            "merchantId": self.merchant_id,
            "timestamp": self.timestamp,
        }


@dataclass
class AmazonPayPaymentSummary:
    """Aggregated payment history summary for a merchant."""
    merchant_id: str
    total_charges: int
    total_amount_captured: float
    total_refunded: float
    pending_charges: int
    declined_charges: int
    currency: str = "INR"
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
