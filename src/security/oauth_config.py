"""
Centralized OAuth 2.1 & Deployment URL Configuration
=====================================================
Validates canonical deployment endpoints, prevents open-redirect vulnerabilities,
enforces HTTPS in production, and manages registered OAuth client credentials.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ConfigurationError(Exception):
    """Raised when security or deployment URL configuration is invalid."""
    pass


def _normalize_url(url: str) -> str:
    """Normalizes URL by stripping trailing slashes and whitespace."""
    if not url:
        return ""
    return url.strip().rstrip("/")


def validate_deployment_url(url: str, var_name: str, allow_loopback: bool = True) -> str:
    """
    Validates a canonical deployment URL:
    - Enforces HTTPS for non-local production deployments
    - Validates valid hostname structure
    - Forbids embedded credentials (user:pass@host)
    - Forbids placeholder .example.com in production
    - Forbids localhost/loopback in production unless allow_loopback is explicitly allowed for local testing
    """
    if not url:
        raise ConfigurationError(f"{var_name} must not be empty.")

    clean_url = _normalize_url(url)
    parsed = urlparse(clean_url)

    if parsed.scheme not in ("http", "https"):
        raise ConfigurationError(f"{var_name} must have 'http' or 'https' scheme (got: {parsed.scheme!r}).")

    if parsed.username or parsed.password:
        raise ConfigurationError(f"{var_name} must not embed credentials.")

    if not parsed.hostname:
        raise ConfigurationError(f"{var_name} has invalid or missing hostname.")

    env = os.environ.get("AUTOPILOT_ENV", "development").lower()

    if env == "production":
        # Production strict validation
        if parsed.scheme != "https":
            raise ConfigurationError(f"{var_name} must use HTTPS in production (got: {clean_url}).")

        if ".example.com" in parsed.hostname.lower() or parsed.hostname.lower().endswith("example.com"):
            raise ConfigurationError(
                f"{var_name} cannot use placeholder '.example.com' domain in production (got: {clean_url})."
            )

        if not allow_loopback and parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise ConfigurationError(
                f"{var_name} cannot use loopback address '{parsed.hostname}' in production."
            )

    return clean_url


def get_public_base_url() -> str:
    """
    Retrieves the canonical public base URL for Vendo.
    Env var: VENDO_PUBLIC_BASE_URL (defaults to http://localhost:8000 in dev).
    """
    env = os.environ.get("AUTOPILOT_ENV", "development").lower()
    raw = os.environ.get("VENDO_PUBLIC_BASE_URL")
    if not raw:
        if env == "production":
            raise ConfigurationError("VENDO_PUBLIC_BASE_URL must be configured in production.")
        return "http://localhost:8000"
    return validate_deployment_url(raw, "VENDO_PUBLIC_BASE_URL", allow_loopback=(env != "production"))


def get_mcp_resource_url() -> str:
    """
    Retrieves the canonical Protected Resource identifier for the MCP endpoint (RFC 9728).
    Env var: VENDO_MCP_RESOURCE_URL (defaults to {VENDO_PUBLIC_BASE_URL}/mcp).
    """
    env = os.environ.get("AUTOPILOT_ENV", "development").lower()
    raw = os.environ.get("VENDO_MCP_RESOURCE_URL")
    if raw:
        return validate_deployment_url(raw, "VENDO_MCP_RESOURCE_URL", allow_loopback=(env != "production"))
    base = get_public_base_url()
    return f"{base}/mcp"


def get_auth_issuer_url() -> str:
    """
    Retrieves the canonical Authorization Server Issuer identifier (RFC 8414).
    Env var: VENDO_AUTH_ISSUER_URL (defaults to VENDO_PUBLIC_BASE_URL).
    """
    env = os.environ.get("AUTOPILOT_ENV", "development").lower()
    raw = os.environ.get("VENDO_AUTH_ISSUER_URL") or os.environ.get("VENDO_AUTH_ISSUER")
    if raw:
        if raw.startswith("http://") or raw.startswith("https://"):
            return validate_deployment_url(raw, "VENDO_AUTH_ISSUER_URL", allow_loopback=(env != "production"))
        # In test/dev it might be an identifier string like 'vendo-auth'
        if env == "production":
            raise ConfigurationError("VENDO_AUTH_ISSUER_URL must be a valid canonical HTTPS URL in production.")
        return raw
    return get_public_base_url()


# ── Registered OAuth Clients and Redirect URI Allowlist ────────────────────────

# Standard Amazon Alexa+ account-linking exchange endpoints
ALEXA_ACCOUNT_LINKING_REDIRECTS = {
    "https://pitangui.amazon.com/api/flutter/accountlinking/v1/auth/exchange",
    "https://layla.amazon.com/api/flutter/accountlinking/v1/auth/exchange",
    "https://alexa.amazon.co.jp/api/flutter/accountlinking/v1/auth/exchange",
    "https://alexa.amazon.com/api/skills/redirect",
    "https://pitangui.amazon.com/api/skills/redirect",
    "https://layla.amazon.com/api/skills/redirect",
}

# Registered clients configuration: client_id -> dict(client_secret, allowed_redirect_uris, allowed_grant_types)
DEFAULT_REGISTERED_CLIENTS: Dict[str, Dict[str, Any]] = {
    "alexa-mcp-client": {
        "client_secret": None,  # Public client using PKCE S256
        "token_endpoint_auth_method": "none",
        "redirect_uris": list(ALEXA_ACCOUNT_LINKING_REDIRECTS),
        "allowed_grant_types": ["authorization_code", "refresh_token"],
        "client_name": "Amazon Alexa+ MCP Toolkit",
    },
    "alexa_mcp_client": {
        "client_secret": None,
        "token_endpoint_auth_method": "none",
        "redirect_uris": list(ALEXA_ACCOUNT_LINKING_REDIRECTS),
        "allowed_grant_types": ["authorization_code", "refresh_token"],
        "client_name": "Amazon Alexa+ MCP Toolkit (Legacy ID)",
    },
    "alexa_skill_vendo_01": {
        "client_secret": None,
        "token_endpoint_auth_method": "none",
        "redirect_uris": list(ALEXA_ACCOUNT_LINKING_REDIRECTS),
        "allowed_grant_types": ["authorization_code", "refresh_token"],
        "client_name": "Amazon Alexa Skill Test Client",
    },
    "valid_client": {
        "client_secret": None,
        "token_endpoint_auth_method": "none",
        "redirect_uris": [
            "https://valid.redirect/callback",
            "https://alexa.amazon.com/api/skills/redirect",
            "http://localhost:8000/oauth/callback",
        ],
        "allowed_grant_types": ["authorization_code", "refresh_token"],
        "client_name": "Valid Test Client",
    },
    "test-client-id": {
        "client_secret": None,
        "token_endpoint_auth_method": "none",
        "redirect_uris": [
            "http://localhost:8000/oauth/callback",
            "http://127.0.0.1:8000/oauth/callback",
            "https://oauth.pstmn.io/v1/callback",
            "https://test.vendo.local/callback",
        ],
        "allowed_grant_types": ["authorization_code", "refresh_token"],
        "client_name": "Vendo Test Fixture Client",
    },
}


def get_registered_client(client_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves client registration by client_id."""
    # Check dynamic env if present
    custom_alexa_id = os.environ.get("ALEXA_MCP_CLIENT_ID")
    if custom_alexa_id and client_id == custom_alexa_id:
        return DEFAULT_REGISTERED_CLIENTS["alexa-mcp-client"]
    return DEFAULT_REGISTERED_CLIENTS.get(client_id)


def is_valid_client_redirect(client_id: str, redirect_uri: str) -> bool:
    """
    Strictly verifies that redirect_uri is an exact registered redirect URI for client_id.
    Prevents open redirect vulnerabilities.
    """
    if not client_id or not redirect_uri:
        return False

    client = get_registered_client(client_id)
    if not client:
        # In non-production testing, allow loopback callbacks for ad-hoc tests if not registered
        env = os.environ.get("AUTOPILOT_ENV", "development").lower()
        if env != "production" and (redirect_uri.startswith("http://localhost") or redirect_uri.startswith("http://127.0.0.1")):
            return True
        return False

    allowed_uris = client.get("redirect_uris", [])
    clean_target = _normalize_url(redirect_uri)
    for uri in allowed_uris:
        if _normalize_url(uri) == clean_target:
            return True

    # In non-production testing, allow loopback callbacks
    env = os.environ.get("AUTOPILOT_ENV", "development").lower()
    if env != "production" and (clean_target.startswith("http://localhost") or clean_target.startswith("http://127.0.0.1")):
        return True

    return False
