"""
Email Provider Interfaces and Mock Ingestion Adapter
=====================================================
Provides provider-agnostic abstractions for inbound email providers and an offline
mock adapter for development and testing across diverse MSME categories.
No live external network calls are performed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from src.db.email_repository import EmailRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.integrations.base import IntegrationError, ValidationError
from src.models.email import (
    EmailAddress,
    EmailAttachment,
    InboundEmail,
    IngestionStatus,
)

logger = logging.getLogger(__name__)


class BaseEmailProvider(ABC):
    """Abstract base class for all email provider adapters."""

    @abstractmethod
    def fetch_new_emails(
        self, business_id: str, since: Optional[str] = None
    ) -> List[InboundEmail]:
        """Fetches newly received emails for a given business."""
        pass

    @abstractmethod
    def get_email(self, message_id: str) -> Optional[InboundEmail]:
        """Retrieves a single email by its message ID."""
        pass

    @abstractmethod
    def mark_as_read(self, message_id: str) -> bool:
        """Marks an email as processed/read in the provider."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the provider name identifier."""
        pass


class MockEmailProvider(BaseEmailProvider):
    """
    Offline in-memory mock email provider.
    Allows staging diverse emails across retail, repair, manufacturing, and services.
    """

    def __init__(self) -> None:
        # business_id -> list of staged InboundEmail
        self._mailboxes: Dict[str, List[InboundEmail]] = {}
        self._read_message_ids: set[str] = set()

    def get_provider_name(self) -> str:
        return "mock_email_provider"

    def stage_email(self, email: InboundEmail) -> None:
        """Stages an email in the mock provider mailbox for its target business."""
        if email.business_id not in self._mailboxes:
            self._mailboxes[email.business_id] = []
        self._mailboxes[email.business_id].append(email)
        logger.debug(f"Staged email {email.message_id} for business {email.business_id}")

    def clear_mailbox(self, business_id: Optional[str] = None) -> None:
        """Clears staged emails for a business or all businesses."""
        if business_id:
            self._mailboxes.pop(business_id, None)
        else:
            self._mailboxes.clear()
        self._read_message_ids.clear()

    def fetch_new_emails(
        self, business_id: str, since: Optional[str] = None
    ) -> List[InboundEmail]:
        """Returns unread emails staged for the business."""
        box = self._mailboxes.get(business_id, [])
        unread = [e for e in box if e.message_id not in self._read_message_ids]
        return unread

    def get_email(self, message_id: str) -> Optional[InboundEmail]:
        for box in self._mailboxes.values():
            for e in box:
                if e.message_id == message_id:
                    return e
        return None

    def mark_as_read(self, message_id: str) -> bool:
        self._read_message_ids.add(message_id)
        return True

    def simulate_inbound_message(
        self,
        business_id: str,
        sender_email: str,
        subject: str,
        body_text: str,
        sender_name: str = "",
        to_email: str = "autopilot@business.in",
        attachments: Optional[List[EmailAttachment]] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[List[str]] = None,
        message_id: Optional[str] = None,
        received_at: Optional[str] = None,
    ) -> InboundEmail:
        """
        Creates and stages a simulated incoming business email.
        """
        mid = message_id or f"<msg-{uuid.uuid4().hex[:12]}@mockmail.internal>"
        email = InboundEmail(
            message_id=mid,
            business_id=business_id,
            sender=EmailAddress(email=sender_email, name=sender_name),
            to_recipients=[EmailAddress(email=to_email)],
            subject=subject,
            body_text=body_text,
            attachments=attachments or [],
            in_reply_to=in_reply_to,
            references=references or ([] if not in_reply_to else [in_reply_to]),
            received_at=received_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            is_untrusted=True,
        )
        self.stage_email(email)
        return email

    # Pre-built scenarios for multi-industry MSMEs
    def simulate_retail_supplier_invoice(
        self, business_id: str, supplier_name: str = "Surat Fabrics Wholesale"
    ) -> InboundEmail:
        body = (
            f"Dear Store Manager,\n\n"
            f"Please find attached Invoice #SF-8842 for 150 meters of Cotton Cambric Fabric.\n"
            f"Total payable: INR 18,500 by net 15 days.\n\n"
            f"Regards,\n{supplier_name}"
        )
        att = EmailAttachment(
            filename="Invoice_SF_8842.pdf",
            content_type="application/pdf",
            raw_data=b"%PDF-1.4 Mock invoice binary content",
            extracted_text="Invoice #SF-8842. Amount: INR 18,500. Supplier: Surat Fabrics Wholesale.",
        )
        return self.simulate_inbound_message(
            business_id=business_id,
            sender_email="accounts@suratfabrics.com",
            sender_name=supplier_name,
            subject="Invoice #SF-8842: Cotton Cambric Delivery",
            body_text=body,
            attachments=[att],
        )

    def simulate_garage_parts_quote(
        self, business_id: str, supplier_name: str = "National Auto Spares"
    ) -> InboundEmail:
        body = (
            f"Hi,\n\n"
            f"Here is the quotation for the 4 sets of Ceramic Brake Pads and 2 Oil Filters requested.\n"
            f"Quotation #NAS-3091: Total INR 7,200 including GST.\n"
            f"Can deliver tomorrow morning.\n\n"
            f"Thanks,\n{supplier_name}"
        )
        return self.simulate_inbound_message(
            business_id=business_id,
            sender_email="orders@nationalautospares.in",
            sender_name=supplier_name,
            subject="Quotation #NAS-3091: Brake Pads & Filters",
            body_text=body,
        )

    def simulate_manufacturing_raw_material(
        self, business_id: str, supplier_name: str = "Apex Precision Steel"
    ) -> InboundEmail:
        body = (
            f"Attention Production Lead,\n\n"
            f"PO #AP-552 Dispatch Update: 500kg 304 Stainless Steel Rods dispatched via V-Trans.\n"
            f"Expected arrival: Thursday afternoon.\n\n"
            f"Regards,\n{supplier_name}"
        )
        return self.simulate_inbound_message(
            business_id=business_id,
            sender_email="dispatch@apexsteel.com",
            sender_name=supplier_name,
            subject="Dispatch Notice: PO #AP-552 Stainless Steel",
            body_text=body,
        )


class EmailIngestionService:
    """
    Coordinates email ingestion from provider adapters into persistent EmailRepository.
    Enforces business context validation, duplicate detection, and untrusted tagging.
    """

    def __init__(
        self,
        email_repo: EmailRepository,
        provider: Optional[BaseEmailProvider] = None,
        profile_repo: Optional[AdaptiveProfileRepository] = None,
    ) -> None:
        self.email_repo = email_repo
        self.provider = provider or MockEmailProvider()
        self.profile_repo = profile_repo

    def ingest_single_email(self, email: InboundEmail) -> InboundEmail:
        """
        Ingests and persists a single inbound email safely.
        Validates business profile if profile_repo is available.
        """
        # Ensure email is strictly untrusted
        email.is_untrusted = True
        for att in email.attachments:
            att.is_untrusted = True

        # Check business profile existence if repository is present
        if self.profile_repo and email.business_id:
            profile = self.profile_repo.get_profile(email.business_id)
            if not profile:
                logger.warning(
                    f"Inbound email for unregistered business_id: {email.business_id}"
                )

        # Ingest into durable repository (handles message_id & content_hash deduplication)
        ingested = self.email_repo.ingest_email(email)
        return ingested

    def poll_and_ingest(self, business_id: str) -> Dict[str, Any]:
        """
        Polls new emails from the provider for the business and ingests them.
        Returns a summary report of new, duplicate, and failed messages.
        """
        if not business_id:
            raise ValidationError("business_id is required to poll emails", provider="email_ingestion")

        new_emails = self.provider.fetch_new_emails(business_id)
        results = {
            "business_id": business_id,
            "total_fetched": len(new_emails),
            "ingested_count": 0,
            "duplicate_count": 0,
            "failed_count": 0,
            "emails": [],
        }

        for email in new_emails:
            try:
                ingested = self.ingest_single_email(email)
                if ingested.ingestion_status == IngestionStatus.DUPLICATE:
                    results["duplicate_count"] += 1
                else:
                    results["ingested_count"] += 1
                    self.provider.mark_as_read(email.message_id)
                results["emails"].append(ingested.to_dict())
            except Exception as e:
                logger.error(f"Failed to ingest email {email.message_id}: {e}", exc_info=True)
                results["failed_count"] += 1

        return results
