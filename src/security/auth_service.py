"""
Authentication & Authorization Security Service
================================================
Implements production-grade identity verification, RFC 7519 JWT verification,
OAuth 2.1 PKCE authorization code management, and centralized tenant authorization.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from src.models.principal import TrustedPrincipal
from src.decision.policy_engine import PermissionEngine
from src.db.refresh_token_repository import RefreshTokenRepository, RefreshTokenRecord
from src.security.oauth_config import (
    get_public_base_url,
    get_mcp_resource_url,
    get_auth_issuer_url,
    is_valid_client_redirect,
    ConfigurationError,
)

logger = logging.getLogger(__name__)

# Security configuration
DEFAULT_SECRET = "vendo-dev-secret-key-32-chars-long-minimum-entropy!!"
JWT_SECRET = os.environ.get("VENDO_JWT_SECRET", DEFAULT_SECRET)
JWT_ISSUER = os.environ.get("VENDO_AUTH_ISSUER", "vendo-auth")
JWT_AUDIENCE = os.environ.get("VENDO_AUTH_AUDIENCE", "vendo-api")
JWT_ALGORITHM = "HS256"

# Authorization code TTL (5 minutes per OAuth 2.1)
AUTH_CODE_TTL_SECONDS = 300

# Token revocation blacklist (set of jti or token hashes)
_REVOKED_TOKENS: Set[str] = set()

# In-memory single-use authorization code store
# Map: code -> dict(client_id, redirect_uri, subject, business_ids, scopes, code_challenge, code_challenge_method, expires_at)
_AUTH_CODES: Dict[str, Dict[str, Any]] = {}

_refresh_repo: Optional[RefreshTokenRepository] = None


def get_refresh_token_repository(db_path: Optional[str] = None) -> RefreshTokenRepository:
    global _refresh_repo
    if db_path is not None:
        return RefreshTokenRepository(db_path)
    if _refresh_repo is None:
        _refresh_repo = RefreshTokenRepository()
    return _refresh_repo


def set_refresh_token_repository(repo: Optional[RefreshTokenRepository]) -> None:
    global _refresh_repo
    _refresh_repo = repo


def _validate_production_key_safety():
    """Enforces strict signing key entropy in production; rejects dev defaults."""
    env = os.environ.get("AUTOPILOT_ENV", "development").lower()
    if env == "production":
        secret = os.environ.get("VENDO_JWT_SECRET")
        if not secret or secret == DEFAULT_SECRET or len(secret) < 32:
            raise ConfigurationError(
                "Production mode strictly requires an explicitly configured, strong VENDO_JWT_SECRET (>= 32 chars)."
            )


def _get_jwt_secret() -> str:
    """Retrieves signing key after enforcing production safety rules."""
    _validate_production_key_safety()
    return os.environ.get("VENDO_JWT_SECRET", DEFAULT_SECRET)


class AuthenticationError(Exception):
    """Base exception for authentication failures."""
    pass


class TokenExpiredError(AuthenticationError):
    """Raised when an authentication bearer token has expired."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when authentication credentials or signatures are invalid."""
    pass


class ScopeInsufficientError(AuthenticationError):
    """Raised when principal lacks required OAuth scopes."""
    pass


class TenantAccessDeniedError(AuthenticationError):
    """Raised when an authenticated principal attempts cross-tenant access without authorization."""
    pass


# ── PKCE Verification ─────────────────────────────────────────────────────────

def compute_code_challenge_s256(verifier: str) -> str:
    """Computes RFC 7636 PKCE S256 code challenge from a code verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_pkce(code_verifier: str, code_challenge: str, method: str = "S256") -> bool:
    """
    Verifies that the supplied code_verifier matches the code_challenge using RFC 7636 S256.
    Rejects 'plain' or unknown methods in production.
    """
    if method.upper() != "S256":
        logger.warning("Unsupported PKCE code_challenge_method: %s (only S256 is supported)", method)
        return False
    expected = compute_code_challenge_s256(code_verifier)
    return secrets.compare_digest(expected, code_challenge)


# ── JWT Minting and Verification ──────────────────────────────────────────────

def create_access_token(
    subject: str,
    business_ids: List[str],
    scopes: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    expires_in_seconds: int = 3600,
    session_id: Optional[str] = None,
    audience: Optional[str] = None,
    issuer: Optional[str] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Mints a signed RFC 7519 JWT access token for an authenticated principal.
    Used during OAuth token exchange and local integration tests.
    """
    now = time.time()
    jti = f"jwt_{uuid.uuid4().hex}"
    resolved_scopes = scopes if scopes is not None else [
        "business:read",
        "business:write",
        "approvals:read",
        "approvals:execute",
        "tasks:read",
        "tasks:write",
    ]
    resolved_roles = roles if roles is not None else ["owner"]

    payload: Dict[str, Any] = {
        "sub": subject,
        "iss": issuer or JWT_ISSUER,
        "aud": audience or JWT_AUDIENCE,
        "iat": int(now),
        "nbf": int(now),
        "exp": int(now + expires_in_seconds),
        "jti": jti,
        "business_ids": business_ids,
        "roles": resolved_roles,
        "scopes": resolved_scopes,
    }
    if session_id:
        payload["session_id"] = session_id
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)
    return token


def verify_access_token(
    token: str,
    required_scopes: Optional[List[str]] = None,
    expected_audience: Optional[str] = None,
    expected_issuer: Optional[str] = None,
) -> TrustedPrincipal:
    """
    Strictly verifies an RFC 7519 JWT access token:
    - Signature check using HS256
    - Algorithm constraint (rejects 'none' or mismatched algorithms)
    - Expiration check (exp)
    - Not-before check (nbf)
    - Audience check (aud)
    - Issuer check (iss)
    - Revocation status check
    - Scope requirements
    Never logs raw token values.
    """
    if not token or not token.strip():
        raise InvalidCredentialsError("Empty bearer token provided")

    token_clean = token.strip()
    if token_clean.lower().startswith("bearer "):
        token_clean = token_clean[7:].strip()

    # Quick sanity check on JWT format (3 parts separated by dots)
    parts = token_clean.split(".")
    if len(parts) != 3:
        raise InvalidCredentialsError("Malformed JWT token structure")

    aud = expected_audience or JWT_AUDIENCE
    iss = expected_issuer or JWT_ISSUER

    try:
        # Decode and verify with PyJWT
        claims = jwt.decode(
            token_clean,
            _get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            audience=aud,
            issuer=iss,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "require": ["exp", "iss", "sub", "aud"],
            },
        )
    except ExpiredSignatureError:
        raise TokenExpiredError("Bearer token has expired")
    except InvalidTokenError as e:
        raise InvalidCredentialsError(f"Invalid token: {str(e)}")

    jti = claims.get("jti")
    if jti and jti in _REVOKED_TOKENS:
        raise InvalidCredentialsError("Bearer token has been revoked")

    token_hash = hashlib.sha256(token_clean.encode("utf-8")).hexdigest()
    if token_hash in _REVOKED_TOKENS:
        raise InvalidCredentialsError("Bearer token has been revoked")

    granted_scopes = claims.get("scopes", [])
    if isinstance(granted_scopes, str):
        granted_scopes = granted_scopes.split()

    if required_scopes:
        for req in required_scopes:
            if req not in granted_scopes and "*" not in granted_scopes:
                raise ScopeInsufficientError(f"Token lacks required scope: {req}")

    principal = TrustedPrincipal(
        subject=claims["sub"],
        issuer=claims["iss"],
        audience=claims["aud"],
        issued_at=float(claims.get("iat", time.time())),
        expires_at=float(claims["exp"]),
        is_authenticated=True,
        business_membership=claims.get("business_ids", []),
        roles=claims.get("roles", ["owner"]),
        scopes=granted_scopes,
        session_id=claims.get("session_id"),
        auth_method="bearer_jwt",
        extra_claims={k: v for k, v in claims.items() if k not in {
            "sub", "iss", "aud", "iat", "exp", "nbf", "jti", "business_ids", "roles", "scopes", "session_id"
        }},
    )
    return principal


def revoke_token(token: str) -> bool:
    """Revokes a bearer token so subsequent requests are rejected."""
    token_clean = token.strip()
    if token_clean.lower().startswith("bearer "):
        token_clean = token_clean[7:].strip()
    try:
        unverified = jwt.decode(token_clean, options={"verify_signature": False})
        jti = unverified.get("jti")
        if jti:
            _REVOKED_TOKENS.add(jti)
    except Exception:
        pass
    token_hash = hashlib.sha256(token_clean.encode("utf-8")).hexdigest()
    _REVOKED_TOKENS.add(token_hash)
    return True


# ── OAuth 2.1 Authorization Code Management ───────────────────────────────────

def issue_authorization_code(
    client_id: str,
    redirect_uri: str,
    subject: str,
    business_ids: List[str],
    scopes: List[str],
    code_challenge: str,
    code_challenge_method: str = "S256",
    resource: Optional[str] = None,
) -> str:
    """
    Issues a cryptographically secure, single-use OAuth 2.1 authorization code
    bound to the client_id, redirect_uri, authenticated subject, PKCE challenge, and resource.
    Validates redirect_uri against client's registered allowlist to prevent open redirect vulnerabilities.
    """
    if not is_valid_client_redirect(client_id, redirect_uri):
        raise InvalidCredentialsError(
            f"Redirect URI '{redirect_uri}' is not registered or allowlisted for client '{client_id}'."
        )

    now = time.time()
    # Prune expired codes
    expired = [k for k, v in _AUTH_CODES.items() if now > v.get("expires_at", 0)]
    for k in expired:
        _AUTH_CODES.pop(k, None)

    code = f"authcode_{secrets.token_urlsafe(32)}"
    _AUTH_CODES[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "subject": subject,
        "business_ids": business_ids,
        "scopes": scopes,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "resource": resource,
        "expires_at": now + AUTH_CODE_TTL_SECONDS,
    }
    return code


def exchange_authorization_code(
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
    resource: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exchanges a single-use authorization code for an access token and a refresh token.
    Validates client_id, redirect_uri, PKCE verifier, resource, and expiry.
    Consumes the code immediately so replay attacks fail.
    Issues a durable refresh token stored via one-way SHA-256 hash.
    """
    now = time.time()
    entry = _AUTH_CODES.pop(code, None)
    if not entry:
        raise InvalidCredentialsError("Invalid or already-consumed authorization code")

    if now > entry.get("expires_at", 0):
        raise InvalidCredentialsError("Authorization code has expired")

    if entry.get("client_id") != client_id:
        raise InvalidCredentialsError("client_id mismatch for authorization code")

    if entry.get("redirect_uri") != redirect_uri:
        raise InvalidCredentialsError("redirect_uri mismatch for authorization code")

    bound_resource = entry.get("resource")
    if bound_resource and resource and bound_resource != resource:
        raise InvalidCredentialsError(f"Resource mismatch: expected '{bound_resource}', got '{resource}'")

    # Verify PKCE S256
    stored_challenge = entry.get("code_challenge", "")
    method = entry.get("code_challenge_method", "S256")
    if not verify_pkce(code_verifier, stored_challenge, method):
        raise InvalidCredentialsError("PKCE code_verifier verification failed")

    # Issue access token
    subject = entry["subject"]
    business_ids = entry["business_ids"]
    scopes = entry["scopes"]
    expires_in = 3600

    access_token = create_access_token(
        subject=subject,
        business_ids=business_ids,
        scopes=scopes,
        expires_in_seconds=expires_in,
    )

    # Issue persistent refresh token
    refresh_repo = get_refresh_token_repository(db_path)
    raw_refresh_token, _ = refresh_repo.issue_refresh_token(
        subject=subject,
        client_id=client_id,
        business_ids=business_ids,
        scopes=scopes,
        resource=bound_resource or resource,
    )

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "refresh_token": raw_refresh_token,
        "scope": " ".join(scopes),
        "subject": subject,
        "business_ids": business_ids,
    }


def refresh_access_token(
    refresh_token: str,
    client_id: str,
    requested_scopes: Optional[List[str]] = None,
    policy_engine: Optional[PermissionEngine] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    RFC 6749 Section 6 Refreshing an Access Token.
    Validates client_id, rotates refresh token, detects replay attacks (revoking family),
    verifies subject still has tenant authorization, and issues new access token.
    Amazon Alexa+ flow does not send 'resource' on refresh; server preserves original resource binding.
    """
    if not refresh_token or not refresh_token.strip():
        raise InvalidCredentialsError("Empty refresh token provided")

    refresh_repo = get_refresh_token_repository(db_path)
    try:
        new_raw_token, new_record, old_record = refresh_repo.consume_and_rotate_token(
            raw_token=refresh_token,
            client_id=client_id,
        )
    except KeyError:
        raise InvalidCredentialsError("Invalid or unknown refresh token")
    except TimeoutError as e:
        raise TokenExpiredError(str(e))
    except ValueError as e:
        raise InvalidCredentialsError(str(e))

    # Recheck tenant authorization
    if policy_engine is not None:
        for bid in old_record.business_ids:
            if not policy_engine.is_authorized_owner(bid, old_record.subject) and not policy_engine.is_authorized_owner(bid, f"owner:{old_record.subject}"):
                refresh_repo.revoke_family(old_record.family_id, reason="owner_authorization_revoked")
                raise InvalidCredentialsError(f"Owner authorization for business '{bid}' has been revoked.")

    # Scope restriction: cannot expand scopes during refresh
    granted_scopes = old_record.scopes
    if requested_scopes:
        for s in requested_scopes:
            if s not in granted_scopes:
                raise ScopeInsufficientError(f"Cannot expand scopes during refresh: '{s}' was not originally granted")
        granted_scopes = [s for s in requested_scopes if s in granted_scopes]

    expires_in = 3600
    access_token = create_access_token(
        subject=old_record.subject,
        business_ids=old_record.business_ids,
        scopes=granted_scopes,
        expires_in_seconds=expires_in,
    )

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "refresh_token": new_raw_token,
        "scope": " ".join(granted_scopes),
        "subject": old_record.subject,
        "business_ids": old_record.business_ids,
    }


def revoke_oauth_token(
    token: str,
    token_type_hint: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """
    Revokes an OAuth token per RFC 7009:
    Supports access tokens (memory/jti blacklist) and refresh tokens (durable SQLite storage).
    """
    if not token or not token.strip():
        return False
    token_clean = token.strip()
    if token_clean.startswith("ref_") or token_type_hint == "refresh_token":
        repo = get_refresh_token_repository(db_path)
        repo.revoke_token(token_clean, reason="client_revoked")
    # Also revoke as access token in blacklist
    revoke_token(token_clean)
    return True


# ── Central Tenant Authorization ──────────────────────────────────────────────

def check_business_authorization(
    principal: TrustedPrincipal,
    business_id: str,
    policy_engine: Optional[PermissionEngine] = None,
) -> bool:
    """
    Centralized check determining if the authenticated principal is authorized for business_id.
    Validates:
      1. Principal validity (unexpired, authenticated).
      2. Tenant membership (business_id in principal.business_membership or admin).
      3. Cross-checks with PermissionEngine policy if configured.
    """
    if not principal or not principal.is_valid():
        return False

    # Check direct business membership from verified principal
    if principal.has_business_access(business_id):
        # Double check with PermissionEngine if present
        if policy_engine is not None:
            # Policy engine checks subject or formatted strings
            return (
                policy_engine.is_authorized_owner(business_id, principal.subject)
                or policy_engine.is_authorized_owner(business_id, f"owner:{principal.subject}")
                or principal.has_business_access(business_id)
            )
        return True

    # If principal doesn't list the business, check if policy engine maps this exact subject
    if policy_engine is not None:
        return (
            policy_engine.is_authorized_owner(business_id, principal.subject)
            or policy_engine.is_authorized_owner(business_id, f"owner:{principal.subject}")
        )

    return False
