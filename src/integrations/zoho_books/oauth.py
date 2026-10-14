"""
Zoho Books OAuth 2.0 Token Manager.
===================================
Manages token refreshing via refresh_token, token expiration caching,
multi-datacenter accounts URL, and concurrency race-condition prevention.
Never logs or leaks client secrets or tokens.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from src.integrations.base import (
    AuthenticationError,
    IntegrationError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    sanitize_credentials,
)

logger = logging.getLogger(__name__)

DEFAULT_ZOHO_ACCOUNTS_URL = "https://accounts.zoho.in"
DEFAULT_ZOHO_API_DOMAIN = "https://www.zohoapis.in"
SAFETY_MARGIN_SECONDS = 300  # Refresh 5 minutes before actual expiration


class ZohoOAuthManager:
    """Thread-safe OAuth manager for refreshing and caching Zoho Books access tokens."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        accounts_url: str = DEFAULT_ZOHO_ACCOUNTS_URL,
        api_domain: Optional[str] = None,
        force_mock: bool = False,
    ):
        self.client_id = client_id.strip() if client_id else ""
        self.client_secret = client_secret.strip() if client_secret else ""
        self.refresh_token = refresh_token.strip() if refresh_token else ""
        self.accounts_url = accounts_url.strip().rstrip("/") if accounts_url else DEFAULT_ZOHO_ACCOUNTS_URL
        self._custom_api_domain = api_domain.strip().rstrip("/") if api_domain else None
        self.force_mock = force_mock

        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._discovered_api_domain: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        """True if sufficient credentials exist to attempt live OAuth token exchange."""
        return bool(self.client_id and self.client_secret and self.refresh_token and not self.force_mock)

    @property
    def api_domain(self) -> str:
        """Resolved base API domain for Books API calls."""
        if self._custom_api_domain:
            return self._custom_api_domain
        if self._discovered_api_domain:
            return self._discovered_api_domain
        # Derive from accounts URL domain if possible (.in vs .com)
        if ".zoho.in" in self.accounts_url:
            return "https://www.zohoapis.in"
        elif ".zoho.eu" in self.accounts_url:
            return "https://www.zohoapis.eu"
        elif ".zoho.com.au" in self.accounts_url:
            return "https://www.zohoapis.com.au"
        return "https://www.zohoapis.com"

    def get_access_token(self) -> str:
        """Retrieves a valid cached access token or performs a thread-safe refresh."""
        if not self.is_configured:
            # If not configured or mock mode, return a dummy mock token
            return "MOCK_ZOHO_ACCESS_TOKEN_FOR_LOCAL_DEV"

        now = time.time()
        # Fast read path if token is valid
        if self._access_token and (now + SAFETY_MARGIN_SECONDS < self._expires_at):
            return self._access_token

        # Acquire lock to refresh token safely without concurrent races
        with self._lock:
            # Double-check inside lock
            if self._access_token and (time.time() + SAFETY_MARGIN_SECONDS < self._expires_at):
                return self._access_token

            token, expires_in, api_domain = self._refresh_access_token()
            self._access_token = token
            self._expires_at = time.time() + expires_in
            if api_domain:
                self._discovered_api_domain = api_domain.rstrip("/")
            logger.info("Successfully refreshed Zoho Books OAuth token (valid for %d s)", expires_in)
            return self._access_token

    def _refresh_access_token(self) -> Tuple[str, int, Optional[str]]:
        """Makes an authorized POST request to Zoho Accounts OAuth token endpoint."""
        token_url = f"{self.accounts_url}/oauth/v2/token"
        params = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                resp_text = resp.read().decode("utf-8")
                payload = json.loads(resp_text)

        except urllib.error.HTTPError as e:
            status = e.code
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            sanitized = sanitize_credentials(f"HTTP {status} {e.reason}: {body}")
            if status in (400, 401, 403):
                raise AuthenticationError(
                    f"Zoho OAuth token refresh failed ({status}): {sanitized}",
                    provider="zoho_books",
                    status_code=status,
                )
            elif status == 429:
                raise RateLimitError(
                    f"Zoho Accounts rate limit exceeded: {sanitized}",
                    provider="zoho_books",
                    status_code=429,
                )
            raise ProviderUnavailableError(
                f"Zoho Accounts unavailable ({status}): {sanitized}",
                provider="zoho_books",
                status_code=status,
            )

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            sanitized = sanitize_credentials(str(e))
            raise ProviderUnavailableError(
                f"Connection to Zoho Accounts failed: {sanitized}",
                provider="zoho_books",
            )

        if "error" in payload:
            err_code = payload.get("error")
            sanitized = sanitize_credentials(json.dumps(payload))
            if err_code in ("invalid_client", "invalid_code", "invalid_grant", "access_denied"):
                raise AuthenticationError(
                    f"Zoho OAuth error ({err_code}): {sanitized}",
                    provider="zoho_books",
                )
            raise IntegrationError(f"Zoho OAuth token error: {sanitized}", provider="zoho_books")

        access_token = payload.get("access_token")
        if not access_token:
            raise AuthenticationError("Zoho OAuth response missing access_token", provider="zoho_books")

        expires_in = int(payload.get("expires_in", 3600))
        api_domain = payload.get("api_domain")

        return access_token, expires_in, api_domain

