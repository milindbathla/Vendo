"""
Normalized Inbound Email and Attachment Models
===============================================
Represents incoming email communications, attachments, headers, and thread metadata.
Enforces untrusted data tagging and deterministic content hashing for deduplication.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional
import uuid


class IngestionStatus(str, Enum):
    RECEIVED = "received"
    DUPLICATE = "duplicate"
    PARSED = "parsed"
    FAILED = "failed"


@dataclass
class EmailAddress:
    """Normalized email address representation."""
    email: str
    name: str = ""

    def __post_init__(self) -> None:
        self.email = self.email.strip().lower()
        self.name = self.name.strip()

    def format(self) -> str:
        if self.name:
            return f"{self.name} <{self.email}>"
        return self.email

    @classmethod
    def from_str(cls, raw: str) -> "EmailAddress":
        """Parses RFC-like 'Name <email@domain>' or simple 'email@domain'."""
        if not raw:
            return cls(email="")
        raw = raw.strip()
        match = re.match(r"^(.*?)\s*<([^>]+)>$", raw)
        if match:
            return cls(name=match.group(1).strip("\"' "), email=match.group(2).strip())
        return cls(email=raw)

    def to_dict(self) -> Dict[str, str]:
        return {"email": self.email, "name": self.name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailAddress":
        return cls(email=data.get("email", ""), name=data.get("name", ""))


@dataclass
class EmailAttachment:
    """Attachment metadata and payload."""
    attachment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = "attachment"
    content_type: str = "application/octet-stream"
    size_bytes: int = 0
    content_hash: str = ""
    raw_data: Optional[bytes] = None
    extracted_text: Optional[str] = None
    is_untrusted: bool = True  # Untrusted external payload guarantee

    def __post_init__(self) -> None:
        if not self.content_hash and self.raw_data:
            self.content_hash = hashlib.sha256(self.raw_data).hexdigest()
            self.size_bytes = len(self.raw_data)

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        d = {
            "attachment_id": self.attachment_id,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
            "extracted_text": self.extracted_text,
            "is_untrusted": self.is_untrusted,
        }
        if include_raw and self.raw_data:
            d["raw_data_hex"] = self.raw_data.hex()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailAttachment":
        raw = None
        if "raw_data_hex" in data:
            try:
                raw = bytes.fromhex(data["raw_data_hex"])
            except ValueError:
                pass
        return cls(
            attachment_id=data.get("attachment_id", str(uuid.uuid4())),
            filename=data.get("filename", "attachment"),
            content_type=data.get("content_type", "application/octet-stream"),
            size_bytes=int(data.get("size_bytes", 0)),
            content_hash=data.get("content_hash", ""),
            raw_data=raw,
            extracted_text=data.get("extracted_text"),
            is_untrusted=bool(data.get("is_untrusted", True)),
        )


def normalize_subject(subject: str) -> str:
    """Strips reply and forward prefixes, brackets, and extra whitespace."""
    if not subject:
        return ""
    cleaned = subject.strip()
    prefix_pattern = re.compile(r"^(\s*(re|fwd|fw|aw|antw|wg)\s*:\s*)+", re.IGNORECASE)
    while prefix_pattern.match(cleaned):
        cleaned = prefix_pattern.sub("", cleaned).strip()
    # Normalize internal spaces
    return re.sub(r"\s+", " ", cleaned)


@dataclass
class InboundEmail:
    """
    Normalized inbound email model.
    Guarantees that all external email data is marked as untrusted and deduplicable.
    """
    message_id: str
    business_id: str
    sender: EmailAddress
    to_recipients: List[EmailAddress]
    subject: str = ""
    body_text: str = ""
    cc_recipients: List[EmailAddress] = field(default_factory=list)
    body_html: Optional[str] = None
    received_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    thread_id: str = ""
    in_reply_to: Optional[str] = None
    references: List[str] = field(default_factory=list)
    attachments: List[EmailAttachment] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    content_hash: str = ""
    normalized_subject: str = ""
    is_untrusted: bool = True  # Strict architectural guarantee: all external input is untrusted
    ingestion_status: IngestionStatus = IngestionStatus.RECEIVED
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.normalized_subject:
            self.normalized_subject = normalize_subject(self.subject)
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()
        if not self.thread_id:
            # Default thread_id if not correlated yet
            self.thread_id = self.message_id

    def compute_content_hash(self) -> str:
        """
        Computes deterministic SHA-256 hash of sender, normalized subject, body text,
        and attachment hashes to detect exact content duplicates.
        """
        hasher = hashlib.sha256()
        hasher.update(self.sender.email.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(self.normalized_subject.strip().lower().encode("utf-8"))
        hasher.update(b"|")
        # Normalize whitespace in body for resilient content hashing
        norm_body = re.sub(r"\s+", " ", self.body_text or "").strip()
        hasher.update(norm_body.encode("utf-8"))
        for att in sorted(self.attachments, key=lambda a: a.filename):
            hasher.update(b"|")
            hasher.update(att.filename.encode("utf-8"))
            hasher.update(b":")
            hasher.update(att.content_hash.encode("utf-8"))
        return hasher.hexdigest()

    @property
    def email_id(self) -> str:
        """Alias for message_id for consistent identifier naming across systems."""
        return self.message_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "business_id": self.business_id,
            "sender": self.sender.to_dict(),
            "to_recipients": [r.to_dict() for r in self.to_recipients],
            "cc_recipients": [r.to_dict() for r in self.cc_recipients],
            "subject": self.subject,
            "normalized_subject": self.normalized_subject,
            "body_text": self.body_text,
            "body_html": self.body_html,
            "received_at": self.received_at,
            "thread_id": self.thread_id,
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "attachments": [a.to_dict() for a in self.attachments],
            "headers": self.headers,
            "content_hash": self.content_hash,
            "is_untrusted": self.is_untrusted,
            "ingestion_status": self.ingestion_status.value,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InboundEmail":
        sender_data = data.get("sender") or {}
        if isinstance(sender_data, str):
            sender = EmailAddress.from_str(sender_data)
        else:
            sender = EmailAddress.from_dict(sender_data)

        to_recipients = []
        for r in data.get("to_recipients", []):
            if isinstance(r, str):
                to_recipients.append(EmailAddress.from_str(r))
            else:
                to_recipients.append(EmailAddress.from_dict(r))

        cc_recipients = []
        for r in data.get("cc_recipients", []):
            if isinstance(r, str):
                cc_recipients.append(EmailAddress.from_str(r))
            else:
                cc_recipients.append(EmailAddress.from_dict(r))

        attachments = [
            EmailAttachment.from_dict(a) for a in data.get("attachments", [])
        ]

        status = IngestionStatus(data.get("ingestion_status", IngestionStatus.RECEIVED.value))

        return cls(
            message_id=data["message_id"],
            business_id=data.get("business_id", ""),
            sender=sender,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
            subject=data.get("subject", ""),
            normalized_subject=data.get("normalized_subject", ""),
            body_text=data.get("body_text", ""),
            body_html=data.get("body_html"),
            received_at=data.get("received_at", ""),
            thread_id=data.get("thread_id", ""),
            in_reply_to=data.get("in_reply_to"),
            references=data.get("references", []),
            attachments=attachments,
            headers=data.get("headers", {}),
            content_hash=data.get("content_hash", ""),
            is_untrusted=bool(data.get("is_untrusted", True)),
            ingestion_status=status,
            error_message=data.get("error_message"),
        )
