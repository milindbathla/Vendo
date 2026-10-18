"""
Base interfaces, configurations, and exception hierarchy for external integrations.
===================================================================================
Provides provider-agnostic exceptions, credential sanitation, and configuration helpers.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class IntegrationError(Exception):
    """Base exception for all external provider integration errors."""

    def __init__(self, message: str, provider: str, status_code: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        self.sanitized_message = sanitize_credentials(message)
        super().__init__(f"[{self.provider}] {self.sanitized_message}")


class ValidationError(IntegrationError):
    """Raised when request parameters fail client-side validation."""


class AuthenticationError(IntegrationError):
    """Raised on 401 Unauthorized, 403 Forbidden, or invalid/expired credentials."""


class RateLimitError(IntegrationError):
    """Raised when provider rate limits or quotas are exceeded (HTTP 429)."""


class ProviderUnavailableError(IntegrationError):
    """Raised on network timeout, DNS resolution failure, or provider 5xx outages."""


# ---------------------------------------------------------------------------
# Secret & Credential Sanitation
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"(key=)[^&\s'\"]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(Zoho-oauthtoken\s+)[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(client_secret=)[^&\s'\"]+", re.IGNORECASE),
    re.compile(r"(refresh_token=)[^&\s'\"]+", re.IGNORECASE),
    re.compile(r"(access_token=)[^&\s'\"]+", re.IGNORECASE),
    re.compile(r"(X-Goog-Api-Key:\s*)[^\r\n]+", re.IGNORECASE),
]


def sanitize_credentials(text: str) -> str:
    """Strips API keys, bearer tokens, and OAuth secrets from strings."""
    if not text:
        return ""
    sanitized = text
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
    return sanitized


def load_dotenv_safe(env_path: Optional[str] = None) -> None:
    """Safely loads key-value pairs from .env into os.environ if not already present."""
    from pathlib import Path
    path = Path(env_path) if env_path else Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception as e:
        logger.debug("Could not read .env: %s", e)


# Automatically load .env on module import
load_dotenv_safe()


# ---------------------------------------------------------------------------
# Base Configuration
# ---------------------------------------------------------------------------

class IntegrationConfig:
    """Helper to detect mock vs live mode and load sanitized config."""

    @staticmethod
    def is_mock_enabled(explicit_mock: Optional[bool] = None) -> bool:
        """Determines if mock mode is forced via argument or environment."""
        load_dotenv_safe()
        if explicit_mock is not None:
            return explicit_mock
        env_val = os.environ.get("MOCK_INTEGRATIONS", "").strip().lower()
        return env_val in ("1", "true", "yes", "on")

    @staticmethod
    def get_google_maps_api_key() -> Optional[str]:
        """Returns the configured Google Maps API key, if present and not a placeholder."""
        key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
        if not key or "your_" in key.lower() or "placeholder" in key.lower():
            return None
        return key

    @staticmethod
    def get_zoho_config() -> Dict[str, str]:
        """Returns Zoho Books configuration dictionary."""
        return {
            "client_id": os.environ.get("ZOHO_CLIENT_ID", "").strip(),
            "client_secret": os.environ.get("ZOHO_CLIENT_SECRET", "").strip(),
            "refresh_token": os.environ.get("ZOHO_REFRESH_TOKEN", "").strip(),
            "org_id": os.environ.get("ZOHO_ORG_ID", "").strip(),
            "accounts_url": os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in").strip(),
            "api_domain": os.environ.get("ZOHO_API_DOMAIN", "").strip(),
        }

