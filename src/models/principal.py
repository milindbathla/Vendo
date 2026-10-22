"""
Trusted Principal Model
=======================
Defines the server-verified security principal for authenticated callers across
FastAPI REST routes and remote FastMCP tool executions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional


@dataclass
class TrustedPrincipal:
    """
    Represents an authenticated, server-verified identity.
    Constructed strictly from validated bearer credentials or server-side authorization records,
    never from untrusted request body parameters or client-supplied actor strings.
    """
    subject: str                                  # User / owner identifier (e.g. "owner_sharma", "usr_942")
    issuer: str = "vendo-auth"                    # Token issuer authority
    audience: str = "vendo-api"                   # Intended audience / resource
    issued_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 3600.0)
    is_authenticated: bool = True
    business_membership: List[str] = field(default_factory=list)  # Authorized business_ids
    roles: List[str] = field(default_factory=lambda: ["owner"])   # Roles: "owner", "admin", "service"
    scopes: List[str] = field(default_factory=lambda: [
        "business:read",
        "business:write",
        "approvals:read",
        "approvals:execute",
        "tasks:read",
        "tasks:write",
    ])
    session_id: Optional[str] = None              # Bound conversation session ID if present
    auth_method: str = "bearer_jwt"               # "bearer_jwt", "dev_mock", "service_token"
    extra_claims: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Verifies if the principal is authenticated and within its validity window."""
        now = time.time()
        return self.is_authenticated and (self.expires_at > now)

    def has_business_access(self, business_id: str) -> bool:
        """
        Determines if this principal is authorized for the given tenant/business.
        Admins or wildcard memberships have access; otherwise exact business_id match.
        """
        if not self.is_valid():
            return False
        if "admin" in self.roles:
            return True
        if "*" in self.business_membership:
            return True
        return business_id in self.business_membership

    def has_scope(self, required_scope: str) -> bool:
        """Validates that the principal possesses the requested permission scope."""
        if not self.is_valid():
            return False
        if "*" in self.scopes or "admin" in self.scopes:
            return True
        return required_scope in self.scopes

    def has_scopes(self, required_scopes: List[str]) -> bool:
        """Validates that all requested scopes are granted."""
        return all(self.has_scope(s) for s in required_scopes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "issuer": self.issuer,
            "audience": self.audience,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "is_authenticated": self.is_authenticated,
            "business_membership": list(self.business_membership),
            "roles": list(self.roles),
            "scopes": list(self.scopes),
            "session_id": self.session_id,
            "auth_method": self.auth_method,
        }
