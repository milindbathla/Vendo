"""
Adaptive Business Autopilot — Multi-Business Orchestration Demo
================================================================
Demonstrates natural-language onboarding, fact extraction, provenance tracking,
fact corrections, prerequisite validation, and decision evaluation across
TWO completely different business verticals without changing code:
1. Kalyan Electronics Repair (Electronics / Repair Services)
2. Apsara Beauty Salon (Beauty / Personal Care Services)

Run with:
    python -m src.adaptive_demo
"""
import json
import os
import sys

from src.db.connection import get_connection, initialize_database
from src.db.profile_repository import AdaptiveProfileRepository
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.decision.approval_service import PurchaseApprovalService
from src.models.adaptive_profile import FactStatus, FactSource

SEP = "=" * 75
THIN = "-" * 75


def run_adaptive_demo():
    print("\n" + SEP)
    print("  AMAZON BUSINESS AUTOPILOT — ADAPTIVE MULTI-BUSINESS ORCHESTRATION")
    print(SEP)

    # Use a clean, isolated in-memory or dedicated demo database to protect demo.db
    demo_db = ":memory:"
    print(f"  [Storage] Using isolated database session: {demo_db}")
    shared_conn = get_connection(":memory:")
    initialize_database(conn=shared_conn)

    repo = AdaptiveProfileRepository(db_path=":memory:", shared_conn=shared_conn)
    approvals = PurchaseApprovalService(db_path=":memory:")
    orchestrator = AdaptiveBusinessOrchestrator(repo=repo, approval_service=approvals)

    # =========================================================================
    # BUSINESS 1: KALYAN ELECTRONICS REPAIR (Services & Hardware Repair)
    # =========================================================================
    print(f"\n{'#' * 75}")
    print("  SCENARIO 1: ONBOARDING BUSINESS #1 — KALYAN ELECTRONICS REPAIR")
    print(f"{'#' * 75}")

    utterance_1 = (
        "I run Kalyan Electronics Repair in Kakadeo. We repair mobile phones and laptops. "
        "Our average repair charge is Rs 450, and spare parts cost around Rs 180 per job. "
        "We can handle up to 15 repair jobs per day. Right now I have Rs 12,000 in cash "
        "and 8 spare screen/battery kits in stock. My shop rent is Rs 300 per day."
    )
    print(f"\n[USER]: \"{utterance_1}\"\n")

    res_1 = orchestrator.handle_user_message(utterance_1, business_id="biz_kalyan_electronics")
    biz_1_id = res_1["business_id"]

    print(f"[AUTOPILOT RESPONSE]:\n  {res_1['reply']}\n")
    print(THIN)
    print(f"  Extracted Category    : {res_1['category']}")
    print(f"  Confirmed Facts Count : {len(res_1['extracted_facts'])}")
    for f in res_1["extracted_facts"]:
        print(f"    • {f['key']:<22}: {f['value']} (status: {f['status']}, source: {f['source']})")
    print(f"  Onboarding Complete?  : {res_1['onboarding_completed']}")
    print(THIN)

    # 1B: Profitability & Unit Economics Query
    print(f"\n[USER]: \"How are my profit margins and break-even volume looking?\"\n")
    res_1_profit = orchestrator.handle_user_message("how is my profit and break-even?", business_id=biz_1_id)
    print(f"[AUTOPILOT RESPONSE]:\n{res_1_profit['reply']}\n")

    # 1C: Fact Correction
    print(THIN)
    print("  USER CORRECTION: Price / cost adjustment")
    print(THIN)
    utterance_corr = "Actually, my spare parts cost is Rs 220, not 180."
    print(f"\n[USER]: \"{utterance_corr}\"\n")
    res_1_corr = orchestrator.handle_user_message(utterance_corr, business_id=biz_1_id)
    print(f"[AUTOPILOT RESPONSE]:\n  {res_1_corr['reply']}\n")

    # Recalculate profit after correction
    res_1_profit_updated = orchestrator.handle_user_message("recalculate profit margin", business_id=biz_1_id)
    print(f"[AUTOPILOT UPDATED PROFIT]:\n{res_1_profit_updated['reply']}\n")

    # 1D: Opportunity Evaluation
    print(THIN)
    print("  OPPORTUNITY EVALUATION: Bulk repair contract")
    print(THIN)
    utterance_opp = "Can I take on 10 more repairs tomorrow?"
    print(f"\n[USER]: \"{utterance_opp}\"\n")
    res_1_opp = orchestrator.handle_user_message(utterance_opp, business_id=biz_1_id)
    print(f"[AUTOPILOT DECISION]:\n{res_1_opp['reply']}\n")

    # Verify Gated Purchase Plan Safety
    if res_1_opp.get("purchase_plan"):
        plan = res_1_opp["purchase_plan"]
        print(f"  [SAFETY GATE] Generated Purchase Plan ID: {plan['plan_id']}")
        print(f"                Status: {plan['status']} (Awaiting Owner Confirmation)")
        print(f"                Total Cost: Rs.{plan['total_cost']:,.2f}")

        # Attempt premature execution (must fail)
        try:
            approvals.execute_plan(plan_id=plan["plan_id"], current_cash=12000.0, safety_reserve=2000.0)
            print("  [ERROR] Plan executed without approval!")
        except Exception as e:
            print(f"  [OK] Premature execution safely blocked: {type(e).__name__}: {e}")

        # Explicit owner approval
        approvals.confirm_plan(plan_id=plan["plan_id"], decision="APPROVE")
        receipt = approvals.execute_plan(plan_id=plan["plan_id"], current_cash=12000.0, safety_reserve=2000.0)
        print(f"  [OK] Executed after explicit approval! Receipt ID: {receipt['order_id']}")

    # =========================================================================
    # BUSINESS 2: APSARA BEAUTY SALON (Personal Care & Services)
    # =========================================================================
    print(f"\n{'#' * 75}")
    print("  SCENARIO 2: ONBOARDING BUSINESS #2 — APSARA BEAUTY SALON")
    print(f"{'#' * 75}")

    utterance_2 = (
        "I own Apsara Beauty Salon in Swaroop Nagar. We offer haircuts, facials and bridal grooming. "
        "Average service ticket is Rs 600, cosmetic consumables cost about Rs 120 per client. "
        "We have 4 chairs and can do at most 24 clients a day."
    )
    print(f"\n[USER]: \"{utterance_2}\"\n")

    res_2 = orchestrator.handle_user_message(utterance_2, business_id="biz_apsara_salon")
    biz_2_id = res_2["business_id"]

    print(f"[AUTOPILOT RESPONSE]:\n  {res_2['reply']}\n")
    print(THIN)
    print(f"  Detected Missing Critical: {res_2['missing_critical_facts']}")
    print(f"  Next Follow-up Question  : {res_2['next_question']}")
    print(THIN)

    # Answering the follow-up question
    utterance_2_followup = "I currently have Rs 25,000 in cash and keep a Rs 5,000 safety buffer. Fixed expenses are Rs 650 per day."
    print(f"\n[USER]: \"{utterance_2_followup}\"\n")
    res_2_followup = orchestrator.handle_user_message(utterance_2_followup, business_id=biz_2_id)
    print(f"[AUTOPILOT RESPONSE]:\n  {res_2_followup['reply']}\n")

    # 2B: Local Competitor Scouting (Tailored to Salons)
    print(THIN)
    print("  EXTERNAL SCOUT: Nearby Beauty Salons in Kanpur via Google Places")
    print(THIN)
    res_2_scout = orchestrator.handle_user_message("show me nearby competitors", business_id=biz_2_id)
    print(f"[AUTOPILOT COMPETITOR SCOUT]:\n{res_2_scout['reply']}\n")

    # 2C: Accounting Integration Overview
    print(THIN)
    print("  EXTERNAL ACCOUNTING: Zoho Books financial status")
    print(THIN)
    res_2_zoho = orchestrator.handle_user_message("check my zoho invoices and bills", business_id=biz_2_id)
    print(f"[AUTOPILOT ACCOUNTING]:\n{res_2_zoho['reply']}\n")

    # =========================================================================
    # MULTI-TENANT ISOLATION & PERSISTENCE VERIFICATION
    # =========================================================================
    print(f"\n{'#' * 75}")
    print("  PERSISTENCE & TENANT ISOLATION AUDIT")
    print(f"{'#' * 75}")

    all_profiles = repo.list_profiles()
    print(f"  Total Registered Businesses: {len(all_profiles)}\n")
    for p in all_profiles:
        print(f"  [{p['business_id']}] {p['display_name']} ({p['category']}) — {p['facts_count']} facts tracked")

    p1 = repo.get_profile(biz_1_id)
    p2 = repo.get_profile(biz_2_id)

    print("\n  [Isolation Check]:")
    print(f"  • Business 1 ({p1.display_name}) selling price : Rs.{p1.get_value('selling_price')}")
    print(f"  • Business 1 corrected parts cost              : Rs.{p1.get_value('unit_material_cost')}")
    print(f"  • Business 2 ({p2.display_name}) selling price : Rs.{p2.get_value('selling_price')}")
    print(f"  • Business 2 consumables cost                  : Rs.{p2.get_value('unit_material_cost')}")

    assert p1.get_value("selling_price") == 450.0
    assert p1.get_value("unit_material_cost") == 220.0
    assert p2.get_value("selling_price") == 600.0
    assert p2.get_value("unit_material_cost") == 120.0
    print("\n  [OK] Both profiles are strictly isolated in storage with independent fact histories!")
    print(SEP + "\n")


if __name__ == "__main__":
    run_adaptive_demo()
