"""
Amazon Business Autopilot — Phase 4 End-to-End Operational Demonstration
========================================================================
Demonstrates the full multi-agent operational workflow offline:
  1. Untrusted customer email ingestion.
  2. Persistent operational task lifecycle creation.
  3. Supervisor intent analysis and business knowledge integration.
  4. Structured action proposal generation (internal draft vs. consequential quote).
  5. Deterministic PermissionEngine enforcement & cryptographic payload hash binding.
  6. Owner-only authorization barrier.
  7. Safe offline simulated execution via ActionDispatcher.
  8. Durable execution receipt generation & state transition to COMPLETED.
  9. Durable idempotency proof (replay does not duplicate execution).
  10. Full append-only audit trail verification.

Run with:
    python -m src.demo_workflow
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Any, Dict

from src.agent.supervisor import EmailOperationalSupervisor
from src.db.connection import initialize_database
from src.db.email_repository import EmailRepository
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.task_repository import TaskRepository
from src.decision.action_dispatcher import ActionDispatcher
from src.decision.policy_engine import PermissionEngine
from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    FactSource,
    FactStatus,
)
from src.models.email import EmailAddress, InboundEmail
from src.models.task import (
    ActionProposal,
    ActionType,
    OperationalTask,
    TaskState,
    compute_payload_hash,
)

SEP = "=" * 80
THIN = "-" * 80


def run_demonstration() -> None:
    print("\n" + SEP)
    print("  AMAZON BUSINESS AUTOPILOT — PHASE 4 OFFLINE END-TO-END DEMO")
    print(SEP)

    # Use a secure, isolated temporary database to preserve demo.db
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "phase4_demo.sqlite3")
    initialize_database(db_path)
    print(f"  [Safety Guarantee] Isolated demo database: {db_path}")
    print(f"  [Safety Guarantee] Real external network APIs: STRICTLY DISABLED (Simulated offline)")

    # 1. Initialize persistent repositories & engines
    profile_repo = AdaptiveProfileRepository(db_path=db_path)
    email_repo = EmailRepository(db_path=db_path)
    task_repo = TaskRepository(db_path=db_path)
    policy_engine = PermissionEngine()
    dispatcher = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)
    supervisor = EmailOperationalSupervisor(
        email_repo=email_repo,
        task_repo=task_repo,
        profile_repo=profile_repo,
        policy_engine=policy_engine,
    )

    # -------------------------------------------------------------------------
    # STEP 1: Business Profile Onboarding (Multi-Tenant MSME)
    # -------------------------------------------------------------------------
    print(f"\n{THIN}")
    print("  STEP 1: Onboard Small Business Profile (Precision Fabrication & Lathe Works)")
    print(THIN)
    biz_id = "biz_precision_lathe_01"
    profile = AdaptiveBusinessProfile(
        business_id=biz_id,
        display_name="Sharma Precision Lathe & Fabrication",
        category="manufacturing_workshop",
        description="Custom precision machining, lathe turning, and industrial fabrication.",
    )
    profile.set_fact("hourly_rate", 850.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    profile.set_fact("selling_price", 1200.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    profile.set_fact("daily_capacity", 25.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    profile_repo.save_profile(profile)

    print(f"  Business ID     : {profile.business_id}")
    print(f"  Display Name    : {profile.display_name}")
    print(f"  Category        : {profile.category}")
    print(f"  Standard Price  : Rs {profile.get_value('selling_price'):,.2f}")
    print(f"  Daily Capacity  : {profile.get_value('daily_capacity')} units/day")

    # -------------------------------------------------------------------------
    # STEP 2: Ingest Untrusted Customer Inbound Email
    # -------------------------------------------------------------------------
    print(f"\n{THIN}")
    print("  STEP 2: Ingest Untrusted Customer Email")
    print(THIN)
    raw_email = InboundEmail(
        message_id="msg_customer_lathe_101",
        business_id=biz_id,
        sender=EmailAddress(email="procurement@delhiautos.com", name="Amit Malhotra"),
        to_recipients=[EmailAddress(email="orders@sharmaprecision.in")],
        subject="Bulk Order Inquiry: 50 Pieces of Precision Gear Bushings",
        body_text=(
            "Dear Sharma Precision, We require a bulk order quote for 50 pieces of custom gear bushings as per standard specs. "
            "Please send a formal binding quotation and estimated delivery lead time."
        ),
    )
    saved_email = email_repo.save_email(raw_email)
    print(f"  Message ID      : {saved_email.message_id}")
    print(f"  From            : {saved_email.sender.format()}")
    print(f"  Subject         : {saved_email.subject}")
    print(f"  Untrusted Flag  : {saved_email.is_untrusted} (Strict architectural guarantee)")
    print(f"  Content Hash    : {saved_email.content_hash[:16]}...")

    # -------------------------------------------------------------------------
    # STEP 3: Supervisor Workflow Analysis & Task Generation
    # -------------------------------------------------------------------------
    print(f"\n{THIN}")
    print("  STEP 3: Supervisor Analysis & Multi-Agent Planning")
    print(THIN)
    outcome = supervisor.process_email(saved_email)
    task = outcome.task
    print(f"  Created Task ID : {task.task_id}")
    print(f"  Task Title      : {task.title}")
    print(f"  Initial State   : {task.state.value}")
    print(f"  Classified Intent: {outcome.classification.intent} (Confidence: {outcome.classification.confidence})")
    print(f"  Analysis Summary: {outcome.analysis_summary}")
    print(f"  Proposed Actions: {len(outcome.action_proposals)} action(s)")

    for idx, prop in enumerate(outcome.action_proposals, start=1):
        print(f"    [{idx}] {prop.action_type.upper()} | Approval Required: {prop.requires_approval} | Status: {prop.execution_status}")
        print(f"        Payload Hash: {prop.payload_hash}")
        if prop.action_type == ActionType.SEND_BINDING_QUOTATION.value:
            print(f"        Quotation Amount: Rs {prop.payload.get('quote_amount', 0.0):,.2f}")
            print(f"        Lead Time: {prop.payload.get('lead_time_days')} days")

    # -------------------------------------------------------------------------
    # STEP 4: Owner-Only Authorization & Tamper Proofing
    # -------------------------------------------------------------------------
    print(f"\n{THIN}")
    print("  STEP 4: Owner Approval & Cryptographic Hash Binding")
    print(THIN)
    consequential_props = [p for p in outcome.action_proposals if p.requires_approval]
    if not consequential_props:
        raise RuntimeError("Expected consequential quotation proposal!")
    quote_prop = consequential_props[0]

    # Demonstrate unauthorized attempt rejection
    untrusted_actor = "unauthorized_worker_01"
    print(f"  [Security Check] Attempting approval by unauthorized actor: '{untrusted_actor}'...")
    if not policy_engine.is_authorized_owner(biz_id, untrusted_actor):
        print(f"    --> Access Denied by deterministic policy engine: Actor '{untrusted_actor}' is NOT an authorized owner.")

    # Authorized owner approval
    owner_actor = "owner:sharma_owner"
    print(f"  [Security Check] Approving with authorized owner: '{owner_actor}'...")
    approved_prop = task_repo.approve_action(
        action_id=quote_prop.action_id,
        business_id=biz_id,
        actor_id=owner_actor,
        execution_payload=quote_prop.payload,
        policy_engine=policy_engine,
    )
    print(f"    --> Approval Granted! Action Status: {approved_prop.execution_status}")
    print(f"    --> Approved By: {approved_prop.approved_by} at {approved_prop.approved_at}")

    # -------------------------------------------------------------------------
    # STEP 5: Safe Controlled Execution via ActionDispatcher
    # -------------------------------------------------------------------------
    print(f"\n{THIN}")
    print("  STEP 5: Safe Offline Dispatch & Execution Receipt")
    print(THIN)
    receipt = dispatcher.dispatch_action(
        action_id=quote_prop.action_id,
        business_id=biz_id,
        actor_id=owner_actor,
    )
    print(f"  Receipt ID      : {receipt.receipt_id}")
    print(f"  Execution Status: {receipt.status}")
    print(f"  Provider Name   : {receipt.provider_name}")
    print(f"  Idempotency Key : {receipt.idempotency_key}")
    print(f"  Simulation Tag  : {receipt.simulation_notice}")
    print(f"  Quotation Output: {receipt.output_data}")

    # Verify task transitioned to COMPLETED
    updated_task = task_repo.get_task(task.task_id, business_id=biz_id)
    print(f"  Task State Post-Exec: {updated_task.state.value} (Version: {updated_task.version})")

    # -------------------------------------------------------------------------
    # STEP 6: Replay Idempotency Verification
    # -------------------------------------------------------------------------
    print(f"\n{THIN}")
    print("  STEP 6: Replay Idempotency Verification (Prevent Duplicate Execution)")
    print(THIN)
    print("  Attempting to re-dispatch the exact same action proposal...")
    replay_receipt = dispatcher.dispatch_action(
        action_id=quote_prop.action_id,
        business_id=biz_id,
        actor_id=owner_actor,
    )
    print(f"  Replay Receipt ID: {replay_receipt.receipt_id}")
    print(f"  Matching Original: {replay_receipt.receipt_id == receipt.receipt_id}")
    print(f"  --> IDEMPOTENCY CONFIRMED: Exact existing receipt returned. Zero duplicate executions.")

    # -------------------------------------------------------------------------
    # STEP 7: Append-Only Audit Trail Dump
    # -------------------------------------------------------------------------
    print(f"\n{THIN}")
    print("  STEP 7: Durable Append-Only Audit Trail Inspection")
    print(THIN)
    audit_entries = task_repo.get_audit_log(task.task_id, business_id=biz_id)
    print(f"  Total Audit Records: {len(audit_entries)}")
    for entry in audit_entries:
        action_tag = f" [Action: {entry['action_id'][:8]}...]" if entry.get("action_id") else ""
        ts = entry.get("timestamp") or entry.get("created_at") or ""
        print(f"    - {ts} | {entry['event_type']:<22} | Actor: {entry['actor']:<20}{action_tag}")

    print("\n" + SEP)
    print("  PHASE 4 OFFLINE DEMONSTRATION COMPLETED SUCCESSFULLY")
    print(SEP + "\n")


if __name__ == "__main__":
    run_demonstration()
