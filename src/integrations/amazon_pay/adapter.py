"""
Amazon Pay India Adapter: High-level orchestration and mock fallback.
======================================================================
Wraps AmazonPayClient with auto-mock mode when credentials are absent,
consistent error handling, and normalized response objects.

Set in .env:
  AMAZON_PAY_PUBLIC_KEY_ID    = SANDBOX-XXXXXXXXXXXXXXXXXX
  AMAZON_PAY_PRIVATE_KEY_PATH = /path/to/private.pem
  AMAZON_PAY_MERCHANT_ID      = XXXXXXXXXXXXXX
  AMAZON_PAY_SANDBOX          = true        # flip to false for production
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from src.integrations.base import IntegrationConfig, IntegrationError, ValidationError
from src.integrations.amazon_pay.client import AmazonPayClient
from src.integrations.amazon_pay.mock_data import (
    MOCK_CHARGE_PERMISSION,
    MOCK_PAYMENT_SUMMARY,
    get_mock_charge,
    get_mock_charges_list,
    get_mock_refunds_list,
)
from src.integrations.amazon_pay.models import (
    AmazonPayCharge,
    AmazonPayChargePermission,
    AmazonPayPaymentSummary,
    AmazonPayRefund,
    AmazonPayWebhookEvent,
)

logger = logging.getLogger(__name__)


def _get_amazon_pay_config() -> Dict[str, str]:
    """Loads Amazon Pay credentials from environment variables."""
    return {
        "public_key_id":    os.environ.get("AMAZON_PAY_PUBLIC_KEY_ID", "").strip(),
        "private_key_path": os.environ.get("AMAZON_PAY_PRIVATE_KEY_PATH", "").strip(),
        "merchant_id":      os.environ.get("AMAZON_PAY_MERCHANT_ID", "").strip(),
        "sandbox":          os.environ.get("AMAZON_PAY_SANDBOX", "true").strip().lower(),
    }


class AmazonPayAdapter:
    """
    High-level adapter for Amazon Pay India payment operations.

    Auto-detects live vs mock mode from environment variables:
    - Live mode: AMAZON_PAY_PUBLIC_KEY_ID, AMAZON_PAY_PRIVATE_KEY_PATH,
                 AMAZON_PAY_MERCHANT_ID all set
    - Mock mode: any credential missing, or MOCK_INTEGRATIONS=true
    """

    def __init__(
        self,
        public_key_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        merchant_id: Optional[str] = None,
        sandbox: Optional[bool] = None,
        force_mock: Optional[bool] = None,
        timeout_seconds: float = 12.0,
    ):
        cfg = _get_amazon_pay_config()

        self.public_key_id   = public_key_id   or cfg["public_key_id"]
        self.private_key_path = private_key_path or cfg["private_key_path"]
        self.merchant_id     = merchant_id     or cfg["merchant_id"]
        self.sandbox         = sandbox if sandbox is not None else (cfg["sandbox"] != "false")

        self.force_mock = IntegrationConfig.is_mock_enabled(force_mock)

        self._client: Optional[AmazonPayClient] = None

        if not self.force_mock and self.public_key_id and self.private_key_path and self.merchant_id:
            try:
                self._client = AmazonPayClient(
                    public_key_id=self.public_key_id,
                    private_key_path=self.private_key_path,
                    merchant_id=self.merchant_id,
                    sandbox=self.sandbox,
                    timeout_seconds=timeout_seconds,
                )
                logger.info(
                    "AmazonPayAdapter: live mode (sandbox=%s, merchant=%s)",
                    self.sandbox,
                    self.merchant_id,
                )
            except Exception as exc:
                logger.warning(
                    "AmazonPayAdapter: failed to init live client (%s). Falling back to mock.", exc
                )
                self.force_mock = True
        else:
            self.force_mock = True
            logger.info("AmazonPayAdapter: mock mode (credentials absent or MOCK_INTEGRATIONS=true)")

    @property
    def is_mock(self) -> bool:
        return self.force_mock or self._client is None

    # -------------------------------------------------------------------------
    # Charge operations
    # -------------------------------------------------------------------------

    def get_charge(self, charge_id: str) -> Dict[str, Any]:
        """Retrieves a payment charge by ID."""
        if self.is_mock:
            return get_mock_charge(charge_id)
        raw = self._client.get_charge(charge_id)
        return {**raw, "is_mock": False}

    def create_charge(
        self,
        charge_permission_id: str,
        amount: str,
        currency_code: str = "INR",
        merchant_note: str = "",
    ) -> Dict[str, Any]:
        """
        Creates and immediately captures a payment charge.
        In sandbox mode this creates a SANDBOX test payment.
        """
        if self.is_mock:
            mock_charge = AmazonPayCharge(
                charge_id=f"MOCK-CHG-{abs(hash(charge_permission_id + amount)) % 999999:06d}",
                charge_permission_id=charge_permission_id,
                merchant_id=self.merchant_id or "MOCK_MERCHANT",
                amount=amount,
                currency_code=currency_code,
                charge_state="Captured",
                payment_method="Amazon Pay Balance (Mock)",
                is_mock=True,
            )
            return mock_charge.to_dict()
        raw = self._client.create_charge(
            charge_permission_id=charge_permission_id,
            amount=amount,
            currency_code=currency_code,
            merchant_note=merchant_note,
        )
        return {**raw, "is_mock": False}

    def create_refund(
        self,
        charge_id: str,
        refund_amount: str,
        currency_code: str = "INR",
        merchant_note: str = "",
    ) -> Dict[str, Any]:
        """Initiates a refund against a previously captured charge."""
        if self.is_mock:
            mock_refund = AmazonPayRefund(
                refund_id=f"MOCK-REF-{abs(hash(charge_id + refund_amount)) % 999999:06d}",
                charge_id=charge_id,
                refund_amount=refund_amount,
                currency_code=currency_code,
                refund_state="Refunded",
                is_mock=True,
            )
            return mock_refund.to_dict()
        raw = self._client.create_refund(
            charge_id=charge_id,
            refund_amount=refund_amount,
            currency_code=currency_code,
            merchant_note=merchant_note,
        )
        return {**raw, "is_mock": False}

    # -------------------------------------------------------------------------
    # Payment history & summary
    # -------------------------------------------------------------------------

    def list_recent_charges(self) -> List[Dict[str, Any]]:
        """
        Returns recent charges for the configured merchant.
        NOTE: Amazon Pay v2 does not expose a bulk list endpoint — in live
        mode this returns charges tracked internally.  Mock returns sample data.
        """
        if self.is_mock:
            return get_mock_charges_list()
        # Live mode: Amazon Pay does not have a list-all charges endpoint.
        # Callers should track charge IDs and look them up individually.
        logger.info(
            "AmazonPayAdapter.list_recent_charges: Amazon Pay v2 has no bulk list endpoint. "
            "Store and query charge IDs individually."
        )
        return []

    def list_recent_refunds(self) -> List[Dict[str, Any]]:
        """Returns recent refunds (mock only — see note above)."""
        if self.is_mock:
            return get_mock_refunds_list()
        return []

    def get_payment_summary(self) -> Dict[str, Any]:
        """Returns aggregated payment summary for the merchant."""
        if self.is_mock:
            return MOCK_PAYMENT_SUMMARY.to_dict()
        charges = self.list_recent_charges()
        captured = sum(
            float(c.get("chargeAmount", {}).get("amount", 0))
            for c in charges
            if c.get("chargeState", {}).get("state") == "Captured"
        )
        return AmazonPayPaymentSummary(
            merchant_id=self.merchant_id or "",
            total_charges=len(charges),
            total_amount_captured=captured,
            total_refunded=0.0,
            pending_charges=sum(1 for c in charges if c.get("chargeState", {}).get("state") == "Chargeable"),
            declined_charges=sum(1 for c in charges if c.get("chargeState", {}).get("state") == "Declined"),
            is_mock=False,
        ).to_dict()

    def get_charge_permission(self, charge_permission_id: str) -> Dict[str, Any]:
        """Retrieves a long-lived charge permission."""
        if self.is_mock:
            perm = MOCK_CHARGE_PERMISSION
            return perm.to_dict()
        raw = self._client.get_charge_permission(charge_permission_id)
        return {**raw, "is_mock": False}

    # -------------------------------------------------------------------------
    # Webhook parsing
    # -------------------------------------------------------------------------

    def parse_webhook_event(self, raw_payload: Dict[str, Any]) -> AmazonPayWebhookEvent:
        """
        Parses an Amazon Pay IPN (webhook) payload into a structured event.
        The caller is responsible for IPN signature verification before parsing.
        """
        notif = raw_payload.get("NotificationType", "UNKNOWN")
        obj_type = raw_payload.get("ObjectType", "UNKNOWN")
        obj_id = (
            raw_payload.get("ChargeId")
            or raw_payload.get("RefundId")
            or raw_payload.get("ChargePermissionId")
            or "UNKNOWN"
        )
        return AmazonPayWebhookEvent(
            notification_type=notif,
            object_type=obj_type,
            object_id=obj_id,
            merchant_id=raw_payload.get("MerchantId", self.merchant_id or ""),
            timestamp=raw_payload.get("EventTime", ""),
            raw_payload=raw_payload,
        )

    def get_status(self) -> Dict[str, Any]:
        """Returns adapter connectivity and mode status."""
        return {
            "provider": "amazon_pay",
            "mode": "mock" if self.is_mock else ("sandbox" if self.sandbox else "live"),
            "merchant_id": self.merchant_id or "NOT_CONFIGURED",
            "is_configured": bool(self.public_key_id and self.private_key_path and self.merchant_id),
            "api_base_url": (
                "NOT_CONFIGURED" if self.is_mock
                else ("https://pay-api.amazon.in/sandbox/v2" if self.sandbox else "https://pay-api.amazon.in/live/v2")
            ),
        }
