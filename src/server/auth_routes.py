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
import urllib.parse
import urllib.request
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.db.token_store import TokenStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["OAuth Connections"])

# Shared token store instance (uses DATABASE_PATH or default)
_DB_PATH = os.environ.get("DATABASE_PATH", "data/demo.db")
_token_store = TokenStore(db_path=_DB_PATH)


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

def _zoho_login_url(merchant_id: str) -> str:
    """Builds the Zoho OAuth authorisation URL for a merchant."""
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
        "state":         merchant_id,   # round-tripped to identify the merchant on callback
    })
    return f"{accounts_url}/oauth/v2/auth?{params}"


def _zoho_exchange_code(code: str) -> Dict[str, Any]:
    """Exchanges a Zoho authorisation code for a refresh token (server-side)."""
    client_id     = os.environ.get("ZOHO_CLIENT_ID", "")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
    redirect_uri  = os.environ.get("ZOHO_REDIRECT_URI", "http://localhost:8000/auth/zoho_books/callback")
    accounts_url  = os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")

    if not (client_id and client_secret):
        raise HTTPException(status_code=500, detail="Zoho OAuth credentials not configured on server.")

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
        redirect_url = _zoho_login_url(merchant_id)
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
    state: str = Query(default="default", description="Merchant ID round-tripped from login"),
    error: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """
    OAuth callback endpoint — provider redirects here after merchant approval.
    Exchanges the authorization code for a refresh_token and stores it encrypted.

    The 'state' parameter carries the merchant_id set during /login.
    """
    merchant_id = state or "default"

    if error:
        logger.warning("OAuth callback error for provider=%s merchant=%s: %s", provider, merchant_id, error)
        raise HTTPException(status_code=400, detail=f"OAuth error from provider: {error}")

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
