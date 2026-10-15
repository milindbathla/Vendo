"""
HTTP Client for Zoho Books REST API.
====================================
Executes authorized requests against Zoho Books API endpoints with
pagination, timeouts, bounded retries, and sanitized error mapping.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional

from src.integrations.base import (
    AuthenticationError,
    IntegrationError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    sanitize_credentials,
)

logger = logging.getLogger(__name__)


class ZohoBooksClient:
    """Low-level HTTP client executing authorized requests against Zoho Books API."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        api_domain: str = "https://www.zohoapis.in",
        timeout_seconds: float = 12.0,
        max_retries: int = 2,
    ):
        self._token_provider = token_provider
        self.api_domain = api_domain.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        data: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Executes an authorized HTTP request with token injection and retries."""
        url = f"{self.api_domain}{endpoint}"
        if params:
            query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query_str:
                url = f"{url}?{query_str}"

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            access_token = self._token_provider()
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(url, data=data, headers=headers, method=method)

            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    resp_text = resp.read().decode("utf-8")
                    if not resp_text.strip():
                        return {"code": 0, "message": "success"}
                    payload = json.loads(resp_text)
                    if payload.get("code") != 0 and "code" in payload:
                        err_code = payload.get("code")
                        err_msg = sanitize_credentials(payload.get("message", "Zoho Books API error"))
                        if err_code in (14, 57):  # Invalid / expired token
                            raise AuthenticationError(
                                f"Zoho Books authentication failed ({err_code}): {err_msg}",
                                provider="zoho_books",
                                status_code=401,
                            )
                        raise IntegrationError(f"Zoho Books error ({err_code}): {err_msg}", provider="zoho_books")
                    return payload

            except urllib.error.HTTPError as e:
                status = e.code
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8")
                except Exception:
                    pass
                sanitized_msg = sanitize_credentials(f"HTTP {status} {e.reason}: {err_body}")

                if status in (401, 403):
                    raise AuthenticationError(
                        f"Zoho Books authentication/permission error ({status}): {sanitized_msg}",
                        provider="zoho_books",
                        status_code=status,
                    )
                elif status == 429:
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (2 ** attempt))
                        continue
                    raise RateLimitError(
                        f"Zoho Books rate limit exceeded: {sanitized_msg}",
                        provider="zoho_books",
                        status_code=429,
                    )
                elif 400 <= status < 500:
                    raise ValidationError(
                        f"Invalid Zoho Books request ({status}): {sanitized_msg}",
                        provider="zoho_books",
                        status_code=status,
                    )
                elif status >= 500:
                    last_error = ProviderUnavailableError(
                        f"Zoho Books server error ({status}): {sanitized_msg}",
                        provider="zoho_books",
                        status_code=status,
                    )
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (2 ** attempt))
                        continue
                    raise last_error
                else:
                    raise IntegrationError(sanitized_msg, provider="zoho_books", status_code=status)

            except (urllib.error.URLError, TimeoutError, OSError) as e:
                sanitized_msg = sanitize_credentials(str(e))
                last_error = ProviderUnavailableError(
                    f"Zoho Books connection failed: {sanitized_msg}",
                    provider="zoho_books",
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise last_error

        if last_error:
            raise last_error
        return {}

    def get_organizations(self) -> Dict[str, Any]:
        """GET /books/v3/organizations."""
        return self._make_request("/books/v3/organizations")

    def get_organization_details(self, organization_id: str) -> Dict[str, Any]:
        """GET /books/v3/organizations/{organization_id}."""
        return self._make_request(f"/books/v3/organizations/{organization_id}")

    def get_invoices(
        self,
        organization_id: str,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """GET /books/v3/invoices."""
        params = {
            "organization_id": organization_id,
            "page": page,
            "per_page": per_page,
        }
        if status:
            params["status"] = status
        return self._make_request("/books/v3/invoices", params=params)

    def get_bills(
        self,
        organization_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """GET /books/v3/bills."""
        params = {
            "organization_id": organization_id,
            "page": page,
            "per_page": per_page,
        }
        return self._make_request("/books/v3/bills", params=params)

    def get_expenses(
        self,
        organization_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """GET /books/v3/expenses."""
        params = {
            "organization_id": organization_id,
            "page": page,
            "per_page": per_page,
        }
        return self._make_request("/books/v3/expenses", params=params)

