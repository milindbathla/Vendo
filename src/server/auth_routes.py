"""
OAuth Callback & Connection Management Routes.
==============================================
Standalone FastAPI APIRouter — mount in web_app.py with:

    from src.server.auth_routes import router as auth_router
    app.include_router(auth_router)

Provides:
  GET  /auth/{provider}/login    — returns redirect URL for merchant to start OAuth
  GET  /auth/{provider}/callback — receives code, exchanges for refresh_token, stores encrypted
  GET  /auth/{provider}/status   — checks whether a merchant has connected a provider
  DELETE /auth/{provider}/disconnect — revokes and deletes stored token

Supported providers: zoho_books, google_places (server-key, no OAuth needed), amazon_pay (future)
"""
from __future__ import annotations

import logging
import os
import json
import logging
import os
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.db.token_store import TokenStore
from src.db.connection import DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["OAuth Connections"])

# Shared token store instance (uses DATABASE_PATH or default)
_DB_PATH = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
_token_store = TokenStore(db_path=_DB_PATH)

# In-memory store for OAuth CSRF state tokens with expiration (15 minutes)
_OAUTH_STATES: Dict[str, Dict[str, Any]] = {}
_STATE_TTL_SECONDS = 900


def _create_oauth_state(provider: str, merchant_id: str) -> str:
    """Generates a cryptographically secure, unguessable state token for CSRF protection."""
    state_token = secrets.token_urlsafe(32)
    _OAUTH_STATES[state_token] = {
        "provider": provider,
        "merchant_id": merchant_id,
        "created_at": time.time(),
    }
    return state_token


def _verify_and_consume_oauth_state(state_token: str, provider: str) -> Optional[str]:
    """Verifies that the CSRF state token is valid, unexpired, and single-use."""
    now = time.time()
    # Prune expired states
    expired = [k for k, v in _OAUTH_STATES.items() if now - v.get("created_at", 0) > _STATE_TTL_SECONDS]
    for k in expired:
        _OAUTH_STATES.pop(k, None)

    entry = _OAUTH_STATES.get(state_token)
    if not entry:
        return None
    if entry.get("provider") != provider:
        return None
    if now - entry.get("created_at", 0) > _STATE_TTL_SECONDS:
        _OAUTH_STATES.pop(state_token, None)
        return None
    _OAUTH_STATES.pop(state_token, None)
    return entry.get("merchant_id")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic request/response models
# ─────────────────────────────────────────────────────────────────────────────

class LoginRedirectResponse(BaseModel):
    provider: str
    redirect_url: str
    instructions: str


class ConnectionStatus(BaseModel):
    provider: str
    merchant_id: str
    is_connected: bool
    scopes: Optional[str] = None
    message: str


class DisconnectResponse(BaseModel):
    provider: str
    merchant_id: str
    status: str


# ─────────────────────────────────────────────────────────────────────────────
# Provider configuration helpers
# ─────────────────────────────────────────────────────────────────────────────

def _zoho_login_url(merchant_id: str, state_token: str) -> str:
    """Builds the Zoho OAuth authorisation URL with cryptographic CSRF state token."""
    client_id     = os.environ.get("ZOHO_CLIENT_ID", "YOUR_ZOHO_CLIENT_ID")
    accounts_url  = os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
    redirect_uri  = os.environ.get("ZOHO_REDIRECT_URI", "http://localhost:8000/auth/zoho_books/callback")
    scope         = "ZohoBooks.fullaccess.all"

    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id":     client_id,
        "scope":         scope,
        "redirect_uri":  redirect_uri,
        "access_type":   "offline",
        "state":         state_token,   # Cryptographic CSRF state token
    })
    return f"{accounts_url}/oauth/v2/auth?{params}"


def _zoho_exchange_code(code: str) -> Dict[str, Any]:
    """Exchanges a Zoho authorisation code for a refresh token (server-side)."""
    client_id     = os.environ.get("ZOHO_CLIENT_ID", "")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
    redirect_uri  = os.environ.get("ZOHO_REDIRECT_URI", "http://localhost:8000/auth/zoho_books/callback")
    accounts_url  = os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")

    if not (client_id and client_secret) or client_id == "YOUR_ZOHO_CLIENT_ID":
        raise HTTPException(
            status_code=503,
            detail="Zoho OAuth credentials not configured on server. Live OAuth token exchange is disabled.",
        )

    token_url = f"{accounts_url}/oauth/v2/token"
    payload = urllib.parse.urlencode({
        "grant_type":    "authorization_code",
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  redirect_uri,
        "code":          code,
    }).encode("utf-8")

    req = urllib.request.Request(
        token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Zoho token exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Zoho token exchange failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{provider}/login", response_model=LoginRedirectResponse)
def get_login_url(
    provider: str,
    merchant_id: str = Query(default="default", description="Unique merchant identifier"),
) -> LoginRedirectResponse:
    """
    Returns the OAuth redirect URL the merchant should be sent to.
    The front-end / Alexa companion app opens this URL in a browser.
    """
    if provider == "zoho_books":
        state_token = _create_oauth_state(provider, merchant_id)
        redirect_url = _zoho_login_url(merchant_id, state_token)
        return LoginRedirectResponse(
            provider=provider,
            redirect_url=redirect_url,
            instructions=(
                "Open this URL in a browser. The merchant logs in to Zoho, "
                "approves access, and is redirected back to /auth/zoho_books/callback."
            ),
        )

    if provider == "google_places":
        return LoginRedirectResponse(
            provider=provider,
            redirect_url="N/A — Google Places uses a server-side API key, not per-merchant OAuth.",
            instructions="Set GOOGLE_MAPS_API_KEY in your .env file. No merchant OAuth required.",
        )

    if provider == "amazon_pay":
        return LoginRedirectResponse(
            provider=provider,
            redirect_url="N/A — Amazon Pay uses Public Key ID + private .pem for signing.",
            instructions=(
                "Set AMAZON_PAY_PUBLIC_KEY_ID, AMAZON_PAY_PRIVATE_KEY_PATH, and "
                "AMAZON_PAY_MERCHANT_ID in your .env file."
            ),
        )

    raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="Cryptographic CSRF state token"),
    error: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """
    OAuth callback endpoint — provider redirects here after merchant approval.
    Exchanges the authorization code for a refresh_token and stores it encrypted.
    Validates cryptographic single-use CSRF state parameter.
    """
    if error:
        logger.warning("OAuth callback error for provider=%s: %s", provider, error)
        raise HTTPException(status_code=400, detail=f"OAuth error from provider: {error}")

    merchant_id = _verify_and_consume_oauth_state(state, provider)
    if not merchant_id:
        env = os.environ.get("AUTOPILOT_ENV", "development").lower()
        if env == "production":
            raise HTTPException(
                status_code=403,
                detail="Invalid, expired, or replayed OAuth CSRF state parameter. Authorization aborted.",
            )
        # Development fallback (warn and allow if state is non-empty)
        if state and state != "default":
            merchant_id = state
            logger.warning("OAuth callback: Accepting unverified state '%s' in development mode only.", state)
        else:
            merchant_id = "default"

    if provider == "zoho_books":
        token_data = _zoho_exchange_code(code)

        if "error" in token_data:
            raise HTTPException(
                status_code=400,
                detail=f"Zoho token exchange error: {token_data.get('error')}",
            )

        refresh_token = token_data.get("refresh_token", "")
        scopes        = token_data.get("scope", "")

        if not refresh_token:
            raise HTTPException(
                status_code=400,
                detail="Zoho did not return a refresh_token. Ensure access_type=offline in the login URL.",
            )

        _token_store.save_token(
            provider=provider,
            merchant_id=merchant_id,
            refresh_token=refresh_token,
            scopes=scopes,
        )
        logger.info("OAuth callback: stored Zoho refresh_token for merchant=%s", merchant_id)

        return {
            "status": "connected",
            "provider": provider,
            "merchant_id": merchant_id,
            "scopes": scopes,
            "message": (
                "Zoho Books connected successfully. "
                "Refresh token stored encrypted. "
                "You can now close this window."
            ),
        }

    raise HTTPException(
        status_code=404,
        detail=f"OAuth callback not implemented for provider: {provider}",
    )


@router.get("/{provider}/status", response_model=ConnectionStatus)
def connection_status(
    provider: str,
    merchant_id: str = Query(default="default"),
) -> ConnectionStatus:
    """Checks whether a merchant has a connected (token stored) provider."""
    is_connected = _token_store.token_exists(provider, merchant_id)
    connections  = _token_store.list_connections(merchant_id)
    scopes = next(
        (c.get("scopes") for c in connections if c["provider"] == provider),
        None,
    )
    return ConnectionStatus(
        provider=provider,
        merchant_id=merchant_id,
        is_connected=is_connected,
        scopes=scopes,
        message="Connected" if is_connected else "Not connected — call /auth/{provider}/login first.",
    )


@router.delete("/{provider}/disconnect", response_model=DisconnectResponse)
def disconnect(
    provider: str,
    merchant_id: str = Query(default="default"),
) -> DisconnectResponse:
    """Revokes and deletes the stored token for a merchant+provider pair."""
    if not _token_store.token_exists(provider, merchant_id):
        raise HTTPException(
            status_code=404,
            detail=f"No token found for provider={provider} merchant={merchant_id}",
        )
    _token_store.delete_token(provider, merchant_id)
    logger.info("Disconnected provider=%s for merchant=%s", provider, merchant_id)
    return DisconnectResponse(
        provider=provider,
        merchant_id=merchant_id,
        status="disconnected",
    )


@router.get("/connections")
def list_all_connections(
    merchant_id: str = Query(default="default"),
) -> Dict[str, Any]:
    """Lists all provider connections for a merchant (token values never returned)."""
    connections = _token_store.list_connections(merchant_id)
    return {
        "merchant_id": merchant_id,
        "connections": connections,
        "total": len(connections),
    }
