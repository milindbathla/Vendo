"""
Security and Identity Module
============================
"""
from src.models.principal import TrustedPrincipal
from src.security.auth_service import (
    create_access_token,
    verify_access_token,
    revoke_token,
    verify_pkce,
    compute_code_challenge_s256,
    issue_authorization_code,
    exchange_authorization_code,
    check_business_authorization,
    AuthenticationError,
    TokenExpiredError,
    InvalidCredentialsError,
    ScopeInsufficientError,
    TenantAccessDeniedError,
)

__all__ = [
    "TrustedPrincipal",
    "create_access_token",
    "verify_access_token",
    "revoke_token",
    "verify_pkce",
    "compute_code_challenge_s256",
    "issue_authorization_code",
    "exchange_authorization_code",
    "check_business_authorization",
    "AuthenticationError",
    "TokenExpiredError",
    "InvalidCredentialsError",
    "ScopeInsufficientError",
    "TenantAccessDeniedError",
]
