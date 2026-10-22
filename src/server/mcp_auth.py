"""
MCP Authentication & Context Middleware
=======================================
Enforces RFC 6750 / OAuth 2.1 Bearer Token authentication on remote FastMCP
Streamable HTTP requests. Propagates verified TrustedPrincipal to tools via ContextVar.
"""
from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from typing import Optional

from starlette.responses import Response

from src.models.principal import TrustedPrincipal
from src.security.auth_service import (
    verify_access_token,
    AuthenticationError,
    TokenExpiredError,
    InvalidCredentialsError,
    ScopeInsufficientError,
)

logger = logging.getLogger(__name__)

# Context variable holding the server-verified principal for the active MCP request
_current_mcp_principal: ContextVar[Optional[TrustedPrincipal]] = ContextVar(
    "current_mcp_principal", default=None
)


def get_current_mcp_principal() -> Optional[TrustedPrincipal]:
    """Retrieves the verified TrustedPrincipal for the currently executing tool."""
    return _current_mcp_principal.get()


class MCPAuthenticationMiddleware:
    """
    ASGI middleware intercepting remote MCP HTTP requests to enforce validated
    Bearer token authentication.
    - Rejects missing, invalid, or expired tokens with HTTP 401 Unauthorized.
    - Sets RFC 6750 WWW-Authenticate response header for Alexa+ MCP discovery.
    - Binds verified TrustedPrincipal to request context for downstream tools.
    - Allows non-production development shortcuts only when AUTOPILOT_ENV != 'production'.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8").strip()
        env = os.environ.get("AUTOPILOT_ENV", "development").lower()

        principal: Optional[TrustedPrincipal] = None

        if auth_header:
            if not auth_header.lower().startswith("bearer "):
                response = Response(
                    content=json.dumps({
                        "error": "invalid_request",
                        "error_description": "Authorization header must use Bearer scheme.",
                    }),
                    status_code=401,
                    media_type="application/json",
                    headers={"WWW-Authenticate": 'Bearer error="invalid_request", error_description="Bearer scheme required"'},
                )
                await response(scope, receive, send)
                return

            try:
                principal = verify_access_token(auth_header)
            except TokenExpiredError as e:
                response = Response(
                    content=json.dumps({
                        "error": "invalid_token",
                        "error_description": "Bearer token has expired.",
                    }),
                    status_code=401,
                    media_type="application/json",
                    headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The access token expired"'},
                )
                await response(scope, receive, send)
                return
            except AuthenticationError as e:
                response = Response(
                    content=json.dumps({
                        "error": "invalid_token",
                        "error_description": str(e),
                    }),
                    status_code=401,
                    media_type="application/json",
                    headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{str(e)}"'},
                )
                await response(scope, receive, send)
                return
        else:
            # In development, check mock developer headers if not in production
            actor_header = headers.get(b"x-autopilot-actor-id") or headers.get(b"x-autopilot-owner-id")
            if env != "production" and actor_header:
                actor = actor_header.decode("utf-8").strip()
                principal = TrustedPrincipal(
                    subject=actor,
                    issuer="vendo-dev",
                    audience="vendo-api",
                    is_authenticated=True,
                    business_membership=["*"],
                    roles=["owner"],
                    scopes=["*"],
                    auth_method="dev_mock",
                )
            else:
                # Alexa+ MCP unauthenticated discovery request:
                # Per Amazon Alexa+ MCP Toolkit QuickStart contract:
                # Returns HTTP 401 Unauthorized WITHOUT WWW-Authenticate header.
                # Must not expose tools, tenant data, or session information.
                response = Response(
                    content=json.dumps({
                        "error": "unauthorized",
                        "error_description": "Authentication required. Provide a valid Bearer token.",
                    }),
                    status_code=401,
                    media_type="application/json",
                    # Explicitly omit WWW-Authenticate header per Alexa+ MCP Toolkit requirement
                )
                await response(scope, receive, send)
                return

        token = _current_mcp_principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_mcp_principal.reset(token)
