"""
Tests: Phase 1 — Inbound Email Ingestion, Deduplication, and Thread Correlation
================================================================================
Verifies:
  - Normalized email models and attachment models
  - Strict untrusted data tagging on external input
  - Exact message_id deduplication
  - Content-hash deterministic deduplication
  - Thread correlation via In-Reply-To, References, and normalized subject
  - Multi-industry mock provider scenarios (retail, garage, manufacturing, services)
  - Full isolation using disposable test databases without touching data/demo.db
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import pytest

from src.db.email_repository import EmailRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.integrations.email_provider import (
    EmailIngestionService,
    MockEmailProvider,
)
from src.models.adaptive_profile import AdaptiveBusinessProfile
from src.models.email import (
    EmailAddress,
    EmailAttachment,
    InboundEmail,
    IngestionStatus,
    normalize_subject,
)


@pytest.fixture
def temp_db_path():
    """Provides a fresh temporary database path for full test isolation."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tf:
        path = tf.name
    yield path
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


@pytest.fixture
def email_repo(temp_db_path):
    """Provides an isolated EmailRepository backed by a temporary SQLite file."""
    return EmailRepository(db_path=temp_db_path)


@pytest.fixture
def mock_provider():
    """Provides a clean MockEmailProvider."""
    return MockEmailProvider()


# ── 1. Model & Untrusted Tagging Tests ────────────────────────────────────────

def test_email_address_parsing_and_normalization():
    addr1 = EmailAddress.from_str("  Ramesh Kumar <RAMESH@SURATFABRICS.COM> ")
    assert addr1.name == "Ramesh Kumar"
    assert addr1.email == "ramesh@suratfabrics.com"
    assert addr1.format() == "Ramesh Kumar <ramesh@suratfabrics.com>"

    addr2 = EmailAddress.from_str("orders@parts.in")
    assert addr2.name == ""
    assert addr2.email == "orders@parts.in"
    assert addr2.format() == "orders@parts.in"


def test_subject_normalization():
    assert normalize_subject("Re: Invoice #102") == "Invoice #102"
    assert normalize_subject("Fwd:  Re:  FW: Quotation NAS-99") == "Quotation NAS-99"
    assert normalize_subject("   [EXT]   Delivery status  ") == "[EXT] Delivery status"
    assert normalize_subject("") == ""


def test_email_attachment_hashing_and_untrusted_flag():
    raw_bytes = b"Sample quotation PDF binary content"
    att = EmailAttachment(
        filename="quote.pdf",
        content_type="application/pdf",
        raw_data=raw_bytes,
    )
    assert att.size_bytes == len(raw_bytes)
    assert len(att.content_hash) == 64  # SHA-256 hex digest
    assert att.is_untrusted is True  # Untrusted external payload guarantee

    att_dict = att.to_dict(include_raw=True)
    assert att_dict["filename"] == "quote.pdf"
    assert att_dict["is_untrusted"] is True
    assert "raw_data_hex" in att_dict


def test_inbound_email_untrusted_guarantee_and_content_hash():
    email = InboundEmail(
        message_id="<msg-001@example.com>",
        business_id="biz_clothing_01",
        sender=EmailAddress(email="supplier@textiles.com", name="Textile Hub"),
        to_recipients=[EmailAddress(email="store@boutique.in")],
        subject="Re: Autumn Collection Samples",
        body_text="Hi, the samples are dispatched today.",
    )
    assert email.is_untrusted is True
    assert email.normalized_subject == "Autumn Collection Samples"
    assert len(email.content_hash) == 64
    assert email.thread_id == "<msg-001@example.com>"


# ── 2. Deduplication Tests ────────────────────────────────────────────────────

def test_exact_message_id_deduplication(email_repo):
    email = InboundEmail(
        message_id="<dup-001@vendor.in>",
        business_id="biz_garage_01",
        sender=EmailAddress(email="spares@nationalauto.in"),
        to_recipients=[EmailAddress(email="service@garage.in")],
        subject="Parts Quotation #991",
        body_text="Brake pads and oil filter availability confirmed.",
    )
    first = email_repo.ingest_email(email)
    assert first.ingestion_status == IngestionStatus.PARSED
    assert email_repo.count_emails("biz_garage_01") == 1

    # Ingesting the identical message_id again
    second = email_repo.ingest_email(email)
    assert second.ingestion_status == IngestionStatus.DUPLICATE
    # Database still has only 1 record
    assert email_repo.count_emails("biz_garage_01") == 1


def test_content_hash_deduplication_different_message_ids(email_repo):
    """Detects duplicate emails re-sent under a different message_id."""
    email1 = InboundEmail(
        message_id="<msg-orig-100@vendor.in>",
        business_id="biz_retail_01",
        sender=EmailAddress(email="vendor@wholesale.in"),
        to_recipients=[EmailAddress(email="buyer@store.in")],
        subject="Re: Delivery Schedule Update",
        body_text="Stock delivery arriving Friday 2 PM.",
    )
    email2 = InboundEmail(
        message_id="<msg-resend-200@vendor.in>",  # Different provider ID
        business_id="biz_retail_01",
        sender=EmailAddress(email="vendor@wholesale.in"),
        to_recipients=[EmailAddress(email="buyer@store.in")],
        subject="Delivery Schedule Update",  # Matches normalized subject
        body_text="Stock delivery arriving Friday 2 PM.",
    )
    assert email1.content_hash == email2.content_hash

    r1 = email_repo.ingest_email(email1)
    assert r1.ingestion_status == IngestionStatus.PARSED

    r2 = email_repo.ingest_email(email2)
    assert r2.ingestion_status == IngestionStatus.DUPLICATE
    assert email_repo.count_emails("biz_retail_01") == 1


def test_cross_business_isolation_for_duplicates(email_repo):
    """Same email content sent to two different businesses is preserved for each."""
    e1 = InboundEmail(
        message_id="<broadcast-01@supplier.com>",
        business_id="biz_store_A",
        sender=EmailAddress(email="distributor@pharma.com"),
        to_recipients=[EmailAddress(email="pharmaA@store.in")],
        subject="Price List Revision",
        body_text="Please find the revised wholesale prices effective tomorrow.",
    )
    e2 = InboundEmail(
        message_id="<broadcast-01@supplier.com>",
        business_id="biz_store_B",
        sender=EmailAddress(email="distributor@pharma.com"),
        to_recipients=[EmailAddress(email="pharmaB@store.in")],
        subject="Price List Revision",
        body_text="Please find the revised wholesale prices effective tomorrow.",
    )
    email_repo.ingest_email(e1)
    email_repo.ingest_email(e2)

    assert email_repo.count_emails("biz_store_A") == 1
    assert email_repo.count_emails("biz_store_B") == 1


# ── 3. Thread Correlation Tests ───────────────────────────────────────────────

def test_thread_correlation_via_in_reply_to(email_repo):
    parent = InboundEmail(
        message_id="<order-root@customer.com>",
        business_id="biz_mfg_01",
        sender=EmailAddress(email="buyer@industry.com"),
        to_recipients=[EmailAddress(email="sales@mfg.in")],
        subject="RFQ: Custom Aluminium Brackets 500 pcs",
        body_text="Can you provide lead time and cost for 500 pcs?",
    )
    email_repo.ingest_email(parent)

    child = InboundEmail(
        message_id="<order-reply-1@customer.com>",
        business_id="biz_mfg_01",
        sender=EmailAddress(email="buyer@industry.com"),
        to_recipients=[EmailAddress(email="sales@mfg.in")],
        subject="Re: RFQ: Custom Aluminium Brackets 500 pcs",
        body_text="We have revised the drawing tolerances, please review.",
        in_reply_to="<order-root@customer.com>",
    )
    email_repo.ingest_email(child)

    thread_msgs = email_repo.get_thread_messages("<order-root@customer.com>")
    assert len(thread_msgs) == 2
    assert thread_msgs[0].message_id == "<order-root@customer.com>"
    assert thread_msgs[1].message_id == "<order-reply-1@customer.com>"
    assert thread_msgs[1].thread_id == "<order-root@customer.com>"


def test_thread_correlation_via_references_list(email_repo):
    root = InboundEmail(
        message_id="<ticket-001@client.org>",
        business_id="biz_consulting_01",
        sender=EmailAddress(email="client@client.org"),
        to_recipients=[EmailAddress(email="help@consulting.in")],
        subject="Project Milestone Inquiry",
        body_text="When will phase 1 deliverables be available?",
    )
    email_repo.ingest_email(root)

    followup = InboundEmail(
        message_id="<ticket-003@client.org>",
        business_id="biz_consulting_01",
        sender=EmailAddress(email="client@client.org"),
        to_recipients=[EmailAddress(email="help@consulting.in")],
        subject="Follow-up on Milestone",
        body_text="Attaching additional scope details.",
        references=["<non-existent@client.org>", "<ticket-001@client.org>"],
    )
    email_repo.ingest_email(followup)

    thread_msgs = email_repo.get_thread_messages("<ticket-001@client.org>")
    assert len(thread_msgs) == 2
    assert thread_msgs[1].message_id == "<ticket-003@client.org>"
    assert thread_msgs[1].thread_id == "<ticket-001@client.org>"


def test_thread_correlation_via_normalized_subject(email_repo):
    first = InboundEmail(
        message_id="<inq-10@buyer.com>",
        business_id="biz_tailor_01",
        sender=EmailAddress(email="customer@gmail.com"),
        to_recipients=[EmailAddress(email="custom@tailor.in")],
        subject="Wedding Suit Measurement Appointment",
        body_text="Do you have slots open this Saturday?",
    )
    email_repo.ingest_email(first)

    # Subsequent email without in_reply_to header but matching normalized subject
    second = InboundEmail(
        message_id="<inq-11@buyer.com>",
        business_id="biz_tailor_01",
        sender=EmailAddress(email="customer@gmail.com"),
        to_recipients=[EmailAddress(email="custom@tailor.in")],
        subject="Re: Wedding Suit Measurement Appointment",
        body_text="Can we make it 4 PM instead?",
    )
    email_repo.ingest_email(second)

    thread_msgs = email_repo.get_thread_messages("<inq-10@buyer.com>")
    assert len(thread_msgs) == 2
    assert thread_msgs[1].thread_id == "<inq-10@buyer.com>"


# ── 4. Mock Provider & Ingestion Service Scenarios ────────────────────────────

def test_mock_provider_lifecycle_and_mark_as_read(mock_provider):
    email = mock_provider.simulate_inbound_message(
        business_id="biz_retail_01",
        sender_email="accounts@vendor.com",
        subject="Monthly Statement",
        body_text="Attached statement for September.",
    )
    unread = mock_provider.fetch_new_emails("biz_retail_01")
    assert len(unread) == 1
    assert unread[0].message_id == email.message_id

    # Mark as read
    mock_provider.mark_as_read(email.message_id)
    unread_after = mock_provider.fetch_new_emails("biz_retail_01")
    assert len(unread_after) == 0


def test_multi_industry_mock_scenarios(mock_provider, email_repo):
    service = EmailIngestionService(email_repo=email_repo, provider=mock_provider)

    # 1. Retail clothing store invoice with PDF attachment
    mock_provider.simulate_retail_supplier_invoice("biz_apparel_01")
    res_retail = service.poll_and_ingest("biz_apparel_01")
    assert res_retail["ingested_count"] == 1
    assert res_retail["duplicate_count"] == 0

    ingested_retail = email_repo.list_emails("biz_apparel_01")
    assert len(ingested_retail) == 1
    assert len(ingested_retail[0].attachments) == 1
    assert ingested_retail[0].attachments[0].filename == "Invoice_SF_8842.pdf"
    assert ingested_retail[0].attachments[0].is_untrusted is True

    # 2. Auto garage parts quotation
    mock_provider.simulate_garage_parts_quote("biz_garage_01")
    res_garage = service.poll_and_ingest("biz_garage_01")
    assert res_garage["ingested_count"] == 1

    # 3. Manufacturing steel dispatch update
    mock_provider.simulate_manufacturing_raw_material("biz_mfg_01")
    res_mfg = service.poll_and_ingest("biz_mfg_01")
    assert res_mfg["ingested_count"] == 1

    # Verify counts per business
    assert email_repo.count_emails("biz_apparel_01") == 1
    assert email_repo.count_emails("biz_garage_01") == 1
    assert email_repo.count_emails("biz_mfg_01") == 1


def test_ingestion_service_with_adaptive_profile_context(temp_db_path):
    """Verifies that EmailIngestionService integrates with AdaptiveProfileRepository."""
    from src.db.connection import initialize_database
    initialize_database(temp_db_path)
    profile_repo = AdaptiveProfileRepository(temp_db_path)
    profile = AdaptiveBusinessProfile(
        business_id="biz_salon_luxury_01",
        display_name="Elite Hair & Spa",
        category="beauty_salon",
        description="Premium unisex hair and beauty salon in Indiranagar, Bengaluru.",
        city="Bengaluru",
        state="Karnataka",
    )
    profile_repo.save_profile(profile)

    email_repo = EmailRepository(temp_db_path)
    provider = MockEmailProvider()
    service = EmailIngestionService(
        email_repo=email_repo, provider=provider, profile_repo=profile_repo
    )

    provider.simulate_inbound_message(
        business_id="biz_salon_luxury_01",
        sender_email="distributor@loreal.in",
        subject="Keratin Treatment Stock Delivery",
        body_text="Your shipment of 24 kits has been dispatched.",
    )

    res = service.poll_and_ingest("biz_salon_luxury_01")
    assert res["ingested_count"] == 1
    assert res["duplicate_count"] == 0

    # Polling again immediately should see 0 new emails (since provider marked them read)
    res_repeat = service.poll_and_ingest("biz_salon_luxury_01")
    assert res_repeat["ingested_count"] == 0
    assert res_repeat["total_fetched"] == 0
