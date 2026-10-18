"""
HTTP Client for Amazon Pay India API.
======================================
Implements RSA-SHA256 signed requests using the Amazon Pay
Signature V2 pattern (Public Key ID + private .pem file).

Falls back gracefully to mock mode when credentials are absent.

Required env vars (when using live mode):
  AMAZON_PAY_PUBLIC_KEY_ID   - e.g. SANDBOX-XXXXX
  AMAZON_PAY_PRIVATE_KEY_PATH - path to the downloaded .pem file
  AMAZON_PAY_MERCHANT_ID      - Seller Central merchant ID
  AMAZON_PAY_SANDBOX          - "true" for sandbox, "false" for production
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from src.integrations.base import (
    AuthenticationError,
    IntegrationError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    sanitize_credentials,
)

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://pay-api.amazon.in/sandbox/v2"
LIVE_BASE_URL    = "https://pay-api.amazon.in/live/v2"


class AmazonPayClient:
    """
    Low-level HTTP client for Amazon Pay India REST API (v2).

    Request signing uses RSA-SHA256 via the cryptography package if
    available.  When the package is absent, the client raises a clear
    ConfigurationError so the caller can fall back to mock mode cleanly.
    """

    def __init__(
        self,
        public_key_id: str,
        private_key_path: str,
        merchant_id: str,
        sandbox: bool = True,
        timeout_seconds: float = 12.0,
        max_retries: int = 2,
    ):
        if not public_key_id:
            raise ValidationError("AMAZON_PAY_PUBLIC_KEY_ID is required", provider="amazon_pay")
        if not private_key_path or not os.path.isfile(private_key_path):
            raise ValidationError(
                f"Amazon Pay private key not found at: {private_key_path}",
                provider="amazon_pay",
            )
        if not merchant_id:
            raise ValidationError("AMAZON_PAY_MERCHANT_ID is required", provider="amazon_pay")

        self.public_key_id = public_key_id
        self.merchant_id = merchant_id
        self.sandbox = sandbox
        self.base_url = SANDBOX_BASE_URL if sandbox else LIVE_BASE_URL
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        # Load private key bytes once
        with open(private_key_path, "rb") as f:
            self._private_key_pem = f.read()

        # Verify cryptography package is available for signing
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            self._rsa_available = True
        except ImportError:
            raise IntegrationError(
                "The 'cryptography' package is required for Amazon Pay request signing. "
                "Install it with: pip install cryptography",
                provider="amazon_pay",
            )

    def _sign_request(self, string_to_sign: str) -> str:
        """Signs the canonical request string with the merchant's RSA private key."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(self._private_key_pem, password=None)
        signature_bytes = private_key.sign(
            string_to_sign.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature_bytes).decode("utf-8")

    def _build_auth_header(self, method: str, url: str, payload: Optional[str] = None) -> str:
        """Constructs the Amazon Pay Signature V2 Authorization header."""
        timestamp = str(int(time.time()))
        hashed_payload = hashlib.sha256((payload or "").encode("utf-8")).hexdigest()

        string_to_sign = "\n".join([
            "AMZN-PAY-RSASSA-PSS-V2",
            timestamp,
            hashed_payload,
        ])

        signature = self._sign_request(string_to_sign)

        return (
            f"AMZN-PAY-RSASSA-PSS-V2 "
            f"PublicKeyId={self.public_key_id}, "
            f"SignedHeaders=content-type;x-amz-pay-date, "
            f"Signature={signature}"
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Executes a signed HTTP request against Amazon Pay API."""
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(payload).encode("utf-8") if payload else None
        body_str = json.dumps(payload) if payload else ""

        auth_header = self._build_auth_header(method, url, body_str)

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "x-amz-pay-sdk-type": "Python",
            "x-amz-pay-sdk-version": "2.6.0",
        }

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    resp_text = resp.read().decode("utf-8")
                    return json.loads(resp_text) if resp_text.strip() else {}
            except urllib.error.HTTPError as exc:
                body_text = sanitize_credentials(exc.read().decode("utf-8", errors="replace"))
                if exc.code == 401:
                    raise AuthenticationError(
                        f"Amazon Pay auth failed: {body_text}", provider="amazon_pay", status_code=401
                    )
                if exc.code == 422:
                    raise ValidationError(
                        f"Amazon Pay validation error: {body_text}", provider="amazon_pay", status_code=422
                    )
                if exc.code == 429:
                    raise RateLimitError(
                        "Amazon Pay rate limit exceeded", provider="amazon_pay", status_code=429
                    )
                if exc.code >= 500:
                    last_error = ProviderUnavailableError(
                        f"Amazon Pay server error {exc.code}", provider="amazon_pay", status_code=exc.code
                    )
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise IntegrationError(
                    f"Amazon Pay HTTP {exc.code}: {body_text}", provider="amazon_pay", status_code=exc.code
                )
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = ProviderUnavailableError(
                    f"Amazon Pay network error: {exc}", provider="amazon_pay"
                )
                time.sleep(min(2 ** attempt, 4))

        raise last_error or ProviderUnavailableError("Amazon Pay request failed", provider="amazon_pay")

    # -------------------------------------------------------------------------
    # Public API methods
    # -------------------------------------------------------------------------

    def get_charge(self, charge_id: str) -> Dict[str, Any]:
        """GET /charges/{chargeId} — retrieves a single payment charge."""
        return self._request("GET", f"/charges/{charge_id}")

    def create_charge(
        self,
        charge_permission_id: str,
        amount: str,
        currency_code: str = "INR",
        merchant_note: str = "",
        can_handle_pending: bool = False,
    ) -> Dict[str, Any]:
        """POST /charges — creates a new payment charge."""
        payload = {
            "chargePermissionId": charge_permission_id,
            "chargeAmount": {"amount": amount, "currencyCode": currency_code},
            "captureNow": True,
            "merchantNote": merchant_note,
            "canHandlePendingAuthorization": can_handle_pending,
        }
        return self._request("POST", "/charges", payload)

    def capture_charge(self, charge_id: str, amount: str, currency_code: str = "INR") -> Dict[str, Any]:
        """POST /charges/{chargeId}/capture — captures a previously authorised charge."""
        payload = {"captureAmount": {"amount": amount, "currencyCode": currency_code}}
        return self._request("POST", f"/charges/{charge_id}/capture", payload)

    def cancel_charge(self, charge_id: str, reason: str = "MERCHANT_CANCELLED") -> Dict[str, Any]:
        """DELETE /charges/{chargeId}/cancel."""
        payload = {"cancellationReason": reason}
        return self._request("DELETE", f"/charges/{charge_id}/cancel", payload)

    def create_refund(
        self,
        charge_id: str,
        refund_amount: str,
        currency_code: str = "INR",
        merchant_note: str = "",
    ) -> Dict[str, Any]:
        """POST /refunds — initiates a refund for a captured charge."""
        payload = {
            "chargeId": charge_id,
            "refundAmount": {"amount": refund_amount, "currencyCode": currency_code},
            "softDescriptor": merchant_note,
        }
        return self._request("POST", "/refunds", payload)

    def get_refund(self, refund_id: str) -> Dict[str, Any]:
        """GET /refunds/{refundId}."""
        return self._request("GET", f"/refunds/{refund_id}")

    def get_charge_permission(self, charge_permission_id: str) -> Dict[str, Any]:
        """GET /chargePermissions/{chargePermissionId}."""
        return self._request("GET", f"/chargePermissions/{charge_permission_id}")
