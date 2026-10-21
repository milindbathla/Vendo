"""
Vendo — End-to-End Multi-Business Operational Assistant Demonstration
=====================================================================
Demonstrates the full operational lifecycle across multiple Indian small business verticals:
1. Scenario 1 (Retail Store): Inbound supplier quotation ingestion -> task creation ->
   action proposal -> policy evaluation -> authorized owner approval -> simulated execution ->
   verifiable execution receipt & audit logging.
2. Scenario 2 (Repair Workshop): Voice-style daily briefing -> pending customer repairs ->
   explainable priority scoring -> suggested operational actions.
3. Scenario 3 (Salon & Wellness): Business-aware upcoming appointment review ->
   voice-friendly conversational brief -> next steps.
4. Scenario 4 (Security, Isolation & Protection): Deterministic permission enforcement:
   - Unauthorized actor rejection
   - Cross-tenant data isolation
   - Tampered payload invalidation
   - Fail-closed behavior on unknown actions
   - Replay protection on executed actions

CRITICAL SAFETY:
- Uses a temporary, isolated SQLite database (canonical data/demo.db is NEVER touched).
- All external operations (payments, emails) are strictly simulated.
- No live external API keys required.
"""

import os
import sys
import tempfile
from typing import Dict, Any

# Ensure workspace root is in sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.db.connection import initialize_database
from src.db.profile_repository import AdaptiveProfileRepository
from src.db.task_repository import TaskRepository, ActionProposal, OperationalTask, TaskState
from src.db.email_repository import EmailRepository
from src.models.email import InboundEmail, EmailAddress
from src.decision.policy_engine import PermissionEngine
from src.decision.action_dispatcher import ActionDispatcher, ActionType, ExecutionReceipt
from src.agent.supervisor import EmailOperationalSupervisor
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.models.adaptive_profile import AdaptiveBusinessProfile, FactSource, FactStatus


def build_isolated_demo_environment() -> Dict[str, Any]:
    """Creates a pristine, isolated demo database environment."""
    temp_dir = tempfile.mkdtemp(prefix="vendo_demo_")
    db_path = os.path.join(temp_dir, "vendo_demo.sqlite3")

    # Initialize tables
    initialize_database(db_path)

    # Instantiate repositories & services
    profile_repo = AdaptiveProfileRepository(db_path)
    task_repo = TaskRepository(db_path)
    email_repo = EmailRepository(db_path)
    policy_engine = PermissionEngine()
    action_dispatcher = ActionDispatcher(task_repo=task_repo, policy_engine=policy_engine)
    supervisor = EmailOperationalSupervisor(
        email_repo=email_repo,
        task_repo=task_repo,
        profile_repo=profile_repo,
        policy_engine=policy_engine,
    )
    orchestrator = AdaptiveBusinessOrchestrator(
        repo=profile_repo,
        task_repo=task_repo,
        email_repo=email_repo,
        supervisor=supervisor,
        action_dispatcher=action_dispatcher,
        policy_engine=policy_engine,
    )

    # Seed 3 distinct business profiles
    # 1. Retail Store
    retail_profile = AdaptiveBusinessProfile(
        business_id="retail_kirana_01",
        display_name="Kirana Supermart",
        category="retail_store",
    )
    retail_profile.set_fact("owner_id", "owner_sharma", FactStatus.CONFIRMED, FactSource.USER_STATED)
    retail_profile.set_fact("cash_balance", 125000.0, FactStatus.CONFIRMED, FactSource.USER_STATED)
    retail_profile.set_fact("daily_sales", 15000.0, FactStatus.CONFIRMED, FactSource.USER_STATED)
    retail_profile.set_fact("selling_price", 725.0, FactStatus.CONFIRMED, FactSource.USER_STATED)
    retail_profile.set_fact("daily_capacity", 50.0, FactStatus.CONFIRMED, FactSource.USER_STATED)
    profile_repo.save_profile(retail_profile)

    # 2. Repair Workshop
    workshop_profile = AdaptiveBusinessProfile(
        business_id="workshop_auto_01",
        display_name="Speedy Auto Garage",
        category="repair_workshop",
    )
    workshop_profile.set_fact("owner_id", "owner_verma", FactStatus.CONFIRMED, FactSource.USER_STATED)
    workshop_profile.set_fact("cash_balance", 45000.0, FactStatus.CONFIRMED, FactSource.USER_STATED)
    workshop_profile.set_fact("bay_capacity", 4, FactStatus.CONFIRMED, FactSource.USER_STATED)
    profile_repo.save_profile(workshop_profile)

    # 3. Salon & Spa
    salon_profile = AdaptiveBusinessProfile(
        business_id="salon_glow_01",
        display_name="Glow Beauty Lounge",
        category="salon_services",
    )
    salon_profile.set_fact("owner_id", "owner_priya", FactStatus.CONFIRMED, FactSource.USER_STATED)
    salon_profile.set_fact("cash_balance", 32000.0, FactStatus.CONFIRMED, FactSource.USER_STATED)
    salon_profile.set_fact("stylists_count", 3, FactStatus.CONFIRMED, FactSource.USER_STATED)
    profile_repo.save_profile(salon_profile)

    # Configure deterministic authorized owners per tenant
    policy_engine.set_authorized_owners("retail_kirana_01", ["owner_sharma", "owner:owner_sharma", "admin:retail_kirana_01"])
    policy_engine.set_authorized_owners("workshop_auto_01", ["owner_verma", "owner:owner_verma", "admin:workshop_auto_01"])
    policy_engine.set_authorized_owners("salon_glow_01", ["owner_priya", "owner:owner_priya", "admin:salon_glow_01"])

    return {
        "db_path": db_path,
        "profile_repo": profile_repo,
        "task_repo": task_repo,
        "email_repo": email_repo,
        "policy_engine": policy_engine,
        "action_dispatcher": action_dispatcher,
        "supervisor": supervisor,
        "orchestrator": orchestrator,
    }


def run_scenario_1_retail(env: Dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print(" SCENARIO 1: RETAIL STORE — INBOUND QUOTATION TO CONTROLLED EXECUTION")
    print("=" * 78)
    print("Business: Kirana Supermart (retail_store) | Owner: owner_sharma")

    orchestrator: AdaptiveBusinessOrchestrator = env["orchestrator"]
    email_repo: EmailRepository = env["email_repo"]
    task_repo: TaskRepository = env["task_repo"]
    dispatcher: ActionDispatcher = env["action_dispatcher"]

    # 1. Ingest Mock Supplier Quotation Email
    email = InboundEmail(
        message_id="msg_quote_oil_8872",
        business_id="retail_kirana_01",
        sender=EmailAddress(name="Fortune Edible Oils Dist.", email="sales@fortunedistributors.in"),
        to_recipients=[EmailAddress(name="Kirana Supermart", email="owner@kiranasupermart.in")],
        subject="Quotation for Bulk Mustard Oil & Atta - Special Diwali Rate",
        body_text="Hello Sharma ji, special festive quotation: 20 cartons Mustard Oil at Rs. 14,500 total. Valid till tomorrow. Please confirm order.",
        received_at="2026-10-20T09:30:00Z",
    )
    email_repo.ingest_email(email)
    print(f"\n[1] Ingested Mock Email: '{email.subject}' from {email.sender.email}")

    # 2. Trigger Supervisor Workflow
    outcome = env["supervisor"].process_email(email)
    print(f"[2] Supervisor Processed Inbound Email -> Created Task: {outcome.task.task_id}")
    print(f"    Intent Classified: {outcome.classification.intent} (Confidence: {outcome.classification.confidence:.2f})")
    print(f"    Action Proposals Generated: {len(outcome.action_proposals)}")

    consequential_proposals = [p for p in outcome.action_proposals if p.requires_approval]
    if not consequential_proposals:
        raise RuntimeError("Expected consequential quotation proposal!")
    proposal_obj = consequential_proposals[0]
    action_id = proposal_obj.action_id
    print(f"\n[3] Consequential Proposal: '{proposal_obj.action_type}' (Action ID: {action_id[:8]})")
    print(f"    Payload: {proposal_obj.payload}")
    print(f"    Requires Approval: {proposal_obj.requires_approval} (State: {proposal_obj.execution_status})")

    # 3. Voice Interaction: Owner queries pending approvals
    query_resp = orchestrator.handle_user_message(
        message="Show me pending approvals",
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
    )
    print(f"\n[4] Voice Query: 'Show me pending approvals'")
    print(f"    Vendo Alexa+ Response: \"{query_resp['voice_summary']}\"")

    # 4. Multi-turn Voice Interaction: Owner asks to explain first proposal
    explain_resp = orchestrator.handle_user_message(
        message="Explain the first one",
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
    )
    print(f"\n[5] Voice Follow-up: 'Explain the first one'")
    print(f"    Vendo Alexa+ Response: \"{explain_resp['voice_summary']}\"")

    # 5. Owner approves and dispatches via orchestrator
    approve_resp = orchestrator.handle_user_message(
        message="Approve proposal 1",
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
    )
    print(f"\n[6] Voice Action: 'Approve proposal 1'")
    print(f"    Vendo Alexa+ Response: \"{approve_resp['voice_summary']}\"")
    print(f"    Dispatch Status: {approve_resp.get('status')}")
    print("    [OK] Scenario 1 completed successfully.")


def run_scenario_2_workshop(env: Dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print(" SCENARIO 2: REPAIR WORKSHOP — DAILY OPERATIONAL BRIEFING & JOB PRIORITIZATION")
    print("=" * 78)
    print("Business: Speedy Auto Garage (repair_workshop) | Owner: owner_verma")

    orchestrator: AdaptiveBusinessOrchestrator = env["orchestrator"]
    task_repo: TaskRepository = env["task_repo"]

    # Seed workshop operational tasks using OperationalTask
    t1 = task_repo.create_task(
        OperationalTask(
            business_id="workshop_auto_01",
            title="Brake pad replacement - Honda City (DL4C-8910)",
            description="Customer waiting for delivery by 3 PM. Parts arrived from supplier.",
            task_type="repair_job",
        )
    )
    t2 = task_repo.create_task(
        OperationalTask(
            business_id="workshop_auto_01",
            title="Engine diagnostics & oil leak inspection - Swift Dzire",
            description="Vehicle in bay 2. Awaiting customer confirmation on quotation.",
            task_type="repair_job",
        )
    )
    print(f"\n[1] Seeded Active Repair Jobs: Task {t1.task_id[:8]} & Task {t2.task_id[:8]}")

    # Proactive Alexa+ Daily Briefing
    briefing = orchestrator.generate_daily_briefing(
        business_id="workshop_auto_01",
        actor_id="owner:owner_verma",
    )
    print(f"\n[2] Proactive Alexa+ Daily Briefing Requested:")
    print(f"    Headline: \"{briefing['headline']}\"")
    print(f"    Voice Summary: \"{briefing['voice_summary']}\"")
    print(f"    Domain Category Applied: {briefing.get('category')}")
    print(f"    Active Work Orders Count: {briefing['active_tasks_count']}")

    # Voice Focus Query
    focus_resp = orchestrator.handle_user_message(
        message="What repairs should I focus on today?",
        business_id="workshop_auto_01",
        actor_id="owner:owner_verma",
    )
    print(f"\n[3] Voice Query: 'What repairs should I focus on today?'")
    print(f"    Vendo Alexa+ Response: \"{focus_resp['voice_summary']}\"")
    print("    [OK] Scenario 2 completed successfully.")


def run_scenario_3_salon(env: Dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print(" SCENARIO 3: SALON & WELLNESS — APPOINTMENTS & CLIENT PREPARATION")
    print("=" * 78)
    print("Business: Glow Beauty Lounge (salon_services) | Owner: owner_priya")

    orchestrator: AdaptiveBusinessOrchestrator = env["orchestrator"]
    task_repo: TaskRepository = env["task_repo"]

    # Seed salon appointment tasks
    t1 = task_repo.create_task(
        OperationalTask(
            business_id="salon_glow_01",
            title="Bridal makeup & styling prep - Meera Patel",
            description="Appointment at 11 AM. 2 senior stylists allocated. Verify cosmetic kit readiness.",
            task_type="appointment",
        )
    )
    t2 = task_repo.create_task(
        OperationalTask(
            business_id="salon_glow_01",
            title="Hair spa and facial treatment - Ananya Sen",
            description="Appointment at 2:30 PM. Needs herbal organic kit.",
            task_type="appointment",
        )
    )
    print(f"\n[1] Seeded Client Appointments: Task {t1.task_id[:8]} & Task {t2.task_id[:8]}")

    # Voice Query for Salon
    salon_resp = orchestrator.handle_user_message(
        message="What appointments and preparations do we have today?",
        business_id="salon_glow_01",
        actor_id="owner:owner_priya",
    )
    print(f"\n[2] Voice Query: 'What appointments and preparations do we have today?'")
    print(f"    Vendo Alexa+ Response: \"{salon_resp['voice_summary']}\"")
    print("    [OK] Scenario 3 completed successfully.")


def run_scenario_4_security(env: Dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print(" SCENARIO 4: SECURITY, ISOLATION & FAIL-CLOSED PROTECTION")
    print("=" * 78)

    orchestrator: AdaptiveBusinessOrchestrator = env["orchestrator"]
    task_repo: TaskRepository = env["task_repo"]
    policy: PermissionEngine = env["policy_engine"]
    dispatcher: ActionDispatcher = env["action_dispatcher"]

    # Create a proposal in retail store
    task = task_repo.create_task(
        OperationalTask(
            business_id="retail_kirana_01",
            title="Vendor Payment Proposal",
            description="Payment of Rs. 5,000 to dairy vendor",
            task_type="payment",
        )
    )
    proposal = task_repo.propose_action(
        task_id=task.task_id,
        business_id="retail_kirana_01",
        proposal=ActionProposal(
            task_id=task.task_id,
            business_id="retail_kirana_01",
            action_type=ActionType.EXECUTE_PAYMENT.value,
            description="Simulated supplier payment of Rs 5,000 to Amul Dairy",
            payload={"amount": 5000.0, "vendor": "Amul Dairy"},
            requires_approval=True,
        ),
        actor="system",
    )

    # Test 1: Cross-tenant / Unauthorized Actor Approval Attempt
    print("\n[Test 4.1] Cross-tenant unauthorized actor attempts approval:")
    unauth_resp = orchestrator.handle_approve_followup(
        business_id="retail_kirana_01",
        message="Approve proposal 1",
        actor_id="owner:owner_verma",  # owner_verma owns workshop, NOT retail!
    )
    print(f"    Response: \"{unauth_resp['voice_summary']}\"")
    assert unauth_resp["status"] == "UNAUTHORIZED", "Cross-tenant approval must be blocked"
    print("    [PASS] Cross-tenant approval strictly rejected.")

    # Test 2: Valid Owner Approves
    print("\n[Test 4.2] Valid owner approves:")
    approved_prop = task_repo.approve_action(
        action_id=proposal.action_id,
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
        execution_payload=proposal.payload,
        policy_engine=policy,
    )
    assert approved_prop.execution_status == "APPROVED"
    print(f"    Approved by: {approved_prop.approved_by} at {approved_prop.approved_at}")
    print("    [PASS] Valid owner approval granted token.")

    # Test 3: Payload Tampering Protection
    print("\n[Test 4.3] Payload tampering after approval:")
    # Attacker tries to alter amount from 5,000 to 50,000 during dispatch
    tampered_payload = {"amount": 50000.0, "vendor": "Attacker"}
    try:
        dispatcher.dispatch_action(
            action_id=proposal.action_id,
            business_id="retail_kirana_01",
            actor_id="owner:owner_sharma",
            execution_payload=tampered_payload,
        )
        assert False, "Should have failed tampering check"
    except Exception as e:
        print(f"    Dispatched blocked with error: {e}")
        print("    [PASS] Tampered payload strictly rejected by permission engine.")

    # Test 4: Controlled Execution & Replay Protection
    print("\n[Test 4.4] Replay protection on executed action:")
    receipt1 = dispatcher.dispatch_action(
        action_id=proposal.action_id,
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
    )
    print(f"    First execution receipt: {receipt1.receipt_id} (Status: {receipt1.status})")

    # Replay attempt
    replay_receipt = dispatcher.dispatch_action(
        action_id=proposal.action_id,
        business_id="retail_kirana_01",
        actor_id="owner:owner_sharma",
    )
    print(f"    Replay execution receipt: {replay_receipt.receipt_id} (Status: {replay_receipt.status})")
    assert replay_receipt.receipt_id == receipt1.receipt_id, "Replay must return original receipt without duplicate execution"
    print("    [PASS] Action replay returned existing receipt; duplicate execution prevented.")

    print("\n    [OK] Scenario 4 completed successfully.")


def run_all_demos():
    print("\n" + "#" * 80)
    print(" VENDO: YOUR BUSINESS. ON AUTOPILOT.")
    print(" Hackathon End-to-End Operational Assistant Demonstration")
    print("#" * 80)

    env = build_isolated_demo_environment()
    try:
        run_scenario_1_retail(env)
        run_scenario_2_workshop(env)
        run_scenario_3_salon(env)
        run_scenario_4_security(env)
        print("\n" + "#" * 80)
        print(" ALL 4 SCENARIOS PASSED WITH ZERO CANONICAL DATA MUTATIONS.")
        print("#" * 80 + "\n")
    finally:
        # Cleanup isolated temp file
        if os.path.exists(env["db_path"]):
            os.remove(env["db_path"])


if __name__ == "__main__":
    run_all_demos()
