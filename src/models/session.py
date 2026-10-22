"""
Persistent Conversation Session Models
=======================================
Represents stateful, multi-turn conversation sessions bound to authenticated
identities and tenant boundaries for Vendo and Alexa+ interactions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class ConversationTurn:
    """A single dialogue turn within a session."""
    turn_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConversationTurn:
        return cls(
            turn_id=data.get("turn_id", str(uuid.uuid4())),
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=float(data.get("timestamp", time.time())),
            metadata=data.get("metadata") or {},
        )


@dataclass
class ConversationSession:
    """
    Durable conversation session bound to a tenant, owner identity,
    and verified principal subject.
    """
    session_id: str
    business_id: str
    owner_id: str
    subject: str
    status: str = "ACTIVE"  # "ACTIVE" | "EXPIRED" | "REVOKED"
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 86400.0)
    referenced_action_ids: List[str] = field(default_factory=list)
    relevant_task_ids: List[str] = field(default_factory=list)
    context_version: int = 1
    turns: List[ConversationTurn] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE" and not self.is_expired

    def add_turn(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> ConversationTurn:
        """Appends a turn to the session and updates activity timestamp."""
        turn = ConversationTurn(
            turn_id=f"turn_{uuid.uuid4().hex[:12]}",
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self.turns.append(turn)
        self.last_activity_at = time.time()
        self.context_version += 1
        return turn

    def set_referenced_actions(self, action_ids: List[str]) -> None:
        """Stores the exact proposal IDs presented to the user in ordered sequence."""
        self.referenced_action_ids = [aid.strip() for aid in action_ids if aid and aid.strip()]
        self.last_activity_at = time.time()
        self.context_version += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "business_id": self.business_id,
            "owner_id": self.owner_id,
            "subject": self.subject,
            "status": self.status,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "referenced_action_ids": self.referenced_action_ids,
            "relevant_task_ids": self.relevant_task_ids,
            "context_version": self.context_version,
            "turns": [t.to_dict() for t in self.turns],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConversationSession:
        raw_turns = data.get("turns") or []
        turns = [
            t if isinstance(t, ConversationTurn) else ConversationTurn.from_dict(t)
            for t in raw_turns
        ]
        return cls(
            session_id=data["session_id"],
            business_id=data["business_id"],
            owner_id=data["owner_id"],
            subject=data.get("subject", data["owner_id"]),
            status=data.get("status", "ACTIVE"),
            created_at=float(data.get("created_at", time.time())),
            last_activity_at=float(data.get("last_activity_at", time.time())),
            expires_at=float(data.get("expires_at", time.time() + 86400.0)),
            referenced_action_ids=list(data.get("referenced_action_ids") or []),
            relevant_task_ids=list(data.get("relevant_task_ids") or []),
            context_version=int(data.get("context_version", 1)),
            turns=turns,
            metadata=data.get("metadata") or {},
        )
