"""
Regression tests for Adaptive Multi-Business Autopilot & Gemini Integration.
=============================================================================
Covers:
  - Multi-vertical classification: Tiffin, Clothing, Salon, Mechanical Repair,
    Small Fabrication, and Unseen category (Pottery/Ceramics).
  - Capacity vs Inventory distinction.
  - Missing financial facts & safe assumption labeling.
  - Multi-turn onboarding & fact correction history.
  - Cross-business isolation across independent SQLite DB connections.
  - Unknown business IDs reject cleanly without silent fallback to home_tiffin.
  - Offline fallback behavior when GEMINI_API_KEY is missing.
  - Real tool dispatch against adaptive profiles using mocked Gemini client.
  - Purchase approval safeguards for non-food businesses.

All tests are 100% offline, use temporary/disposable SQLite databases,
and NEVER touch data/demo.db.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional
import pytest

from src.db.connection import get_connection, initialize_database
from src.db.profile_repository import AdaptiveProfileRepository
from src.agent.onboarding import AdaptiveBusinessOnboarder
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.agent.autopilot_agent import run_autopilot_agent, AgentResult
from src.agent.tools import (
    set_active_profile_repo,
    set_active_business_id,
    get_business_overview,
    evaluate_order_opportunity,
)
from src.decision.approval_service import PurchaseApprovalService, PlanStatus
from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactStatus,
    FactSource,
)


# ---------------------------------------------------------------------------
# Test Mocks for Gemini Client
# ---------------------------------------------------------------------------
class MockCandidate:
    def __init__(self):
        self.content = None


class MockFunctionCall:
    def __init__(self, name: str, args: Dict[str, Any]):
        self.name = name
        self.args = args


class MockResponse:
    def __init__(self, text: Optional[str] = None, function_calls: Optional[List[MockFunctionCall]] = None):
        self._text = text
        self._function_calls = function_calls
        self.candidates = [MockCandidate()]

    @property
    def text(self) -> Optional[str]:
        return self._text

    @property
    def function_calls(self) -> Optional[List[MockFunctionCall]]:
        return self._function_calls


class MockModels:
    def __init__(self, responses: List[MockResponse]):
        self._responses = list(responses)
        self._calls: List[Dict[str, Any]] = []

    def generate_content(self, **kwargs) -> MockResponse:
        self._calls.append(kwargs)
        if self._responses:
            return self._responses.pop(0)
        return MockResponse(text="recommendation: All operations completed.")


class MockGeminiClient:
    def __init__(self, responses: List[MockResponse]):
        self.models = MockModels(responses)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_repo():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = get_connection(db_path)
    initialize_database(db_path, conn=conn)
    repo = AdaptiveProfileRepository(db_path=db_path, shared_conn=conn)
    set_active_profile_repo(repo)
    yield repo
    repo.close()
    try:
        conn.close()
    except Exception:
        pass
    set_active_profile_repo(None)
    set_active_business_id(None)
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.fixture
def temp_approvals():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    service = PurchaseApprovalService(db_path=db_path)
    yield service
    service.close()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


def build_and_save_profile(
    repo: AdaptiveProfileRepository,
    business_id: str,
    display_name: str,
    category: str,
    facts: Dict[str, Any],
) -> AdaptiveBusinessProfile:
    prof = AdaptiveBusinessProfile(
        business_id=business_id,
        display_name=display_name,
        category=category,
    )
    for k, v in facts.items():
        prof.set_fact(k, v, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
    repo.save_profile(prof)
    return prof


# ---------------------------------------------------------------------------
# 1. Multi-Vertical Classification & Extraction Tests
# ---------------------------------------------------------------------------
class TestMultiVerticalClassification:
    def setup_method(self):
        self.onboarder = AdaptiveBusinessOnboarder()

    def test_clothing_shop_classification_and_extraction(self):
        """Clothing shop selling shirts and jeans -> clothing_retail, NOT kirana."""
        text = (
            "I own Regal Menswear, a clothing shop selling shirts and jeans in Kanpur. "
            "Our average selling price is Rs 850 per garment. Material and wholesale cost is Rs 420 per shirt. "
            "We can alter and prepare 25 garments daily. We currently have 40 garments in stock. "
            "Our liquid cash balance is Rs 35,000 with a safety reserve of Rs 10,000. "
            "Monthly rent and electricity is Rs 12,000."
        )
        res = self.onboarder.process_utterance(text)
        profile = self.onboarder.profile

        assert profile.category == "clothing_retail"
        assert profile.get_value("selling_price") == 850.0
        assert profile.get_value("unit_material_cost") == 420.0
        assert profile.get_value("daily_capacity") == 25.0
        assert profile.get_value("current_inventory") == 40.0
        assert profile.get_value("cash_balance") == 35000.0
        assert profile.get_value("safety_reserve") == 10000.0
        assert profile.get_value("monthly_fixed_cost") == 12000.0

    def test_mechanical_repair_classification_and_extraction(self):
        """Two-wheeler repair and engine tuning -> mechanical_repair, NOT electronics."""
        text = (
            "Welcome to Sharma Auto Garage. We do two-wheeler repair, bike servicing, and engine tuning. "
            "We charge Rs 650 per servicing. Parts and lubricants cost Rs 260 per bike. "
            "We have the capacity to service 12 bikes a day. On hand inventory is 8 spare oil filters. "
            "Cash balance in our current account is Rs 18,000 with a reserve buffer of Rs 4,000."
        )
        res = self.onboarder.process_utterance(text)
        profile = self.onboarder.profile

        assert profile.category == "mechanical_repair"
        assert profile.get_value("selling_price") == 650.0
        assert profile.get_value("unit_material_cost") == 260.0
        assert profile.get_value("daily_capacity") == 12.0
        assert profile.get_value("current_inventory") == 8.0
        assert profile.get_value("cash_balance") == 18000.0
        assert profile.get_value("safety_reserve") == 4000.0

    def test_metal_fabrication_workshop_classification_and_extraction(self):
        """Metal welding and fabrication workshop -> small_fabrication, NOT kirana."""
        text = (
            "We run Vishwakarma Iron Works, a metal welding and fabrication workshop. "
            "We fabricate iron gates, window grills, and steel frames. Average job charge is Rs 3,200. "
            "Raw steel and welding rods cost Rs 1,600 per job. We can complete 4 fabrication jobs per day. "
            "We have Rs 45,000 in cash and fixed shop overhead of Rs 600 per day."
        )
        res = self.onboarder.process_utterance(text)
        profile = self.onboarder.profile

        assert profile.category == "small_fabrication"
        assert profile.get_value("selling_price") == 3200.0
        assert profile.get_value("unit_material_cost") == 1600.0
        assert profile.get_value("daily_capacity") == 4.0
        assert profile.get_value("cash_balance") == 45000.0
        assert profile.get_value("daily_fixed_cost") == 600.0

    def test_beauty_salon_classification_and_extraction(self):
        """Beauty salon -> salon_service."""
        text = (
            "I run Glow Beauty Parlour. We offer facial, hair spa, haircuts, and bridal makeup. "
            "Average customer service bill is Rs 450. Consumables and cosmetics cost Rs 90 per client. "
            "We can handle 20 clients daily. Cash in hand is Rs 12,000."
        )
        res = self.onboarder.process_utterance(text)
        profile = self.onboarder.profile

        assert profile.category == "salon_service"
        assert profile.get_value("selling_price") == 450.0
        assert profile.get_value("unit_material_cost") == 90.0
        assert profile.get_value("daily_capacity") == 20.0
        assert profile.get_value("cash_balance") == 12000.0

    def test_unseen_category_gracefully_handled(self):
        """Unseen category (e.g. handmade pottery workshop) does not hallucinate tiffin."""
        text = "I run a handmade ceramic pottery studio making clay pots and decorative vases."
        res = self.onboarder.process_utterance(text)
        profile = self.onboarder.profile

        # Should not force into home_tiffin
        assert profile.category != "home_tiffin"
        # Should ask follow-up questions
        assert res["next_question"] is not None


# ---------------------------------------------------------------------------
# 2. Capacity vs Inventory Distinctions
# ---------------------------------------------------------------------------
class TestCapacityVsInventoryDistinction:
    def test_capacity_is_not_conflated_with_stock(self):
        """Verify that capacity to stitch 15 shirts does not set inventory to 15."""
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "We run a boutique. We can stitch 15 suits a day, but right now we have 3 finished suits in stock."
        )
        profile = onboarder.profile
        assert profile.get_value("daily_capacity") == 15.0
        assert profile.get_value("current_inventory") == 3.0
        assert profile.get_value("daily_capacity") != profile.get_value("current_inventory")

    def test_inventory_without_capacity_stays_distinct(self):
        """Inventory alone does not populate daily capacity."""
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "We have 50 packets of detergent in stock at our grocery store."
        )
        profile = onboarder.profile
        assert profile.get_value("current_inventory") == 50.0
        assert profile.get_value("daily_capacity") is None


# ---------------------------------------------------------------------------
# 3. Missing Financial Facts & Safe Fallback/Assumption Labeling
# ---------------------------------------------------------------------------
class TestFinancialSafetyAndAssumptions:
    def test_missing_facts_flagged_with_explicit_assumptions(self, temp_repo, temp_approvals):
        """When cash or reserve are unconfirmed, orchestrator labels them in assumptions."""
        orch = AdaptiveBusinessOrchestrator(repo=temp_repo, approval_service=temp_approvals)
        prof = build_and_save_profile(
            temp_repo,
            business_id="biz_clothing_unconfirmed",
            display_name="Kalyan Garments",
            category="clothing_retail",
            facts={
                "daily_capacity": 30.0,
                "unit_material_cost": 200.0,
                "selling_price": 450.0,
            },
        )

        res = orch.evaluate_opportunity(profile=prof, additional_units=5.0)
        assert res["status"] == "SUCCESS"
        # Must explicitly declare assumptions
        assert len(res["assumptions"]) > 0
        assumption_text = " ".join(res["assumptions"])
        assert "assumed" in assumption_text.lower()
        assert "unconfirmed" in assumption_text.lower()

    def test_missing_capacity_blocks_opportunity_evaluation(self, temp_repo, temp_approvals):
        """Evaluation returns PREREQUISITES_MISSING if daily capacity is unknown."""
        orch = AdaptiveBusinessOrchestrator(repo=temp_repo, approval_service=temp_approvals)
        prof = build_and_save_profile(
            temp_repo,
            business_id="biz_no_cap",
            display_name="Test Shop",
            category="clothing_retail",
            facts={"unit_material_cost": 150.0},
        )

        res = orch.evaluate_opportunity(profile=prof, additional_units=5.0)
        assert res["status"] == "PREREQUISITES_MISSING"
        assert res["missing_field"] == "daily_capacity"


# ---------------------------------------------------------------------------
# 4. Multi-Turn Onboarding & Fact Correction Persistence
# ---------------------------------------------------------------------------
class TestMultiTurnOnboardingAndCorrection:
    def test_multi_turn_accumulation_and_history(self, temp_repo):
        """Turn 1 gives basic info, Turn 2 provides missing facts, Turn 3 corrects price."""
        biz_id = "biz_bike_garage"
        prof = AdaptiveBusinessProfile(business_id=biz_id, display_name="Super Bike Care", category="mechanical_repair")
        onboarder = AdaptiveBusinessOnboarder(profile=prof)

        # Turn 1: Name and capacity
        res1 = onboarder.process_utterance(
            "I run Super Bike Care in Lucknow. We can service 10 motorcycles per day."
        )
        assert prof.get_value("daily_capacity") == 10.0
        assert prof.get_value("selling_price") is None
        assert "charge" in res1["next_question"].lower() or "price" in res1["next_question"].lower()

        # Turn 2: Provide price and parts cost
        res2 = onboarder.process_utterance(
            "We charge Rs 500 for a service and spare parts cost Rs 200 per bike."
        )
        assert prof.get_value("selling_price") == 500.0
        assert prof.get_value("unit_material_cost") == 200.0

        # Turn 3: Correction of price
        res3 = onboarder.process_utterance(
            "Correction, our servicing charge is actually Rs 550."
        )
        assert prof.get_value("selling_price") == 550.0

        # Verify persistence and correction history
        temp_repo.save_profile(prof)
        reloaded = temp_repo.get_profile(biz_id)
        assert reloaded.get_value("selling_price") == 550.0
        price_fact = reloaded.facts["selling_price"]
        assert price_fact.status == FactStatus.CONFIRMED
        assert price_fact.source == FactSource.USER_STATED
        # Correction history is recorded in the notes field
        assert "500" in price_fact.notes or "corrected" in price_fact.notes.lower()


# ---------------------------------------------------------------------------
# 5. Cross-Business Isolation & Unknown Business ID Handling
# ---------------------------------------------------------------------------
class TestCrossBusinessIsolation:
    def test_profiles_isolated_in_storage(self, temp_repo):
        """Updating biz_a does not affect biz_b."""
        build_and_save_profile(
            temp_repo, "biz_cloth_1", "Style Fashion", "clothing_retail", {"selling_price": 999.0}
        )
        build_and_save_profile(
            temp_repo, "biz_repair_1", "Quick Fix Garage", "mechanical_repair", {"selling_price": 350.0}
        )

        reloaded_a = temp_repo.get_profile("biz_cloth_1")
        reloaded_b = temp_repo.get_profile("biz_repair_1")

        assert reloaded_a.get_value("selling_price") == 999.0
        assert reloaded_b.get_value("selling_price") == 350.0

        # Update biz_a
        reloaded_a.set_fact("selling_price", 1099.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
        temp_repo.save_profile(reloaded_a)

        assert temp_repo.get_profile("biz_cloth_1").get_value("selling_price") == 1099.0
        assert temp_repo.get_profile("biz_repair_1").get_value("selling_price") == 350.0

    def test_unknown_business_id_never_falls_back_to_tiffin(self, temp_repo):
        """Querying an unknown business returns NOT_FOUND, never home_tiffin."""
        res_overview = get_business_overview("unknown_biz_999")
        assert res_overview["status"] == "NOT_FOUND"
        assert "not found" in res_overview["error"].lower()

        res_opp = evaluate_order_opportunity(additional_orders=5.0, business_type="unknown_biz_999")
        assert res_opp["status"] == "NOT_FOUND"
        assert res_opp["decision"] == "REJECT"


# ---------------------------------------------------------------------------
# 6. Gemini Agent Adaptive Profile Tool Dispatch (Mocked)
# ---------------------------------------------------------------------------
class TestGeminiAgentAdaptiveIntegration:
    def test_agent_reads_adaptive_profile_via_tool_calls(self, temp_repo):
        """Gemini requests get_business_overview and receives adaptive facts for clothing."""
        build_and_save_profile(
            temp_repo,
            "biz_cloth_test",
            "Anand Garments",
            "clothing_retail",
            {
                "selling_price": 750.0,
                "unit_material_cost": 350.0,
                "daily_capacity": 20.0,
                "cash_balance": 20000.0,
                "safety_reserve": 5000.0,
            },
        )

        # Mock sequence: Gemini calls get_business_overview, then returns structured text
        responses = [
            MockResponse(function_calls=[MockFunctionCall("get_business_overview", {"business_type": "biz_cloth_test"})]),
            MockResponse(text="recommendation: Anand Garments has a healthy gross margin of Rs 400 per garment.\n"
                              "rationale: Selling price is Rs 750 and unit cost is Rs 350 from verified facts.\n"
                              "trade_offs: None.\n"
                              "next_steps: Maintain current production.\n"
                              "approvals_required:\n"
                              "assumptions:\n"
                              "unknowns:"),
        ]
        client = MockGeminiClient(responses)

        result = run_autopilot_agent(
            "How profitable is my clothing business?",
            business_id="biz_cloth_test",
            profile_repo=temp_repo,
            _client=client,
        )

        assert isinstance(result, AgentResult)
        assert len(result.tools_invoked) == 1
        assert result.tools_invoked[0]["tool"] == "get_business_overview"
        assert "750" in result.tools_invoked[0]["summary"] or "Anand Garments" in result.tools_invoked[0]["summary"]
        assert "Anand Garments" in result.recommendation or "400" in result.recommendation

    def test_agent_evaluates_opportunity_for_mechanical_repair(self, temp_repo):
        """Gemini calls evaluate_order_opportunity for a mechanical repair shop."""
        build_and_save_profile(
            temp_repo,
            "biz_mechanic_test",
            "City Bike Care",
            "mechanical_repair",
            {
                "selling_price": 500.0,
                "unit_material_cost": 180.0,
                "daily_capacity": 15.0,
                "cash_balance": 12000.0,
                "safety_reserve": 3000.0,
            },
        )

        responses = [
            MockResponse(function_calls=[MockFunctionCall(
                "evaluate_order_opportunity",
                {"additional_orders": 4.0, "business_type": "biz_mechanic_test"}
            )]),
            MockResponse(text="recommendation: Accept 4 more bike servicing jobs tomorrow.\n"
                              "rationale: Capacity allows 15 bikes and procurement of parts is within cash limits.\n"
                              "trade_offs: Mechanics will work near full capacity.\n"
                              "next_steps: Procure 4 service kits today.\n"
                              "approvals_required:\n"
                              "- Sign off on parts purchase plan.\n"
                              "assumptions:\n"
                              "unknowns:"),
        ]
        client = MockGeminiClient(responses)

        result = run_autopilot_agent(
            "Can we service 4 extra bikes tomorrow?",
            business_id="biz_mechanic_test",
            profile_repo=temp_repo,
            _client=client,
        )

        assert isinstance(result, AgentResult)
        assert len(result.tools_invoked) == 1
        assert result.tools_invoked[0]["tool"] == "evaluate_order_opportunity"
        assert "ACCEPT" in result.tools_invoked[0]["summary"]
        assert len(result.approvals_required) >= 1


# ---------------------------------------------------------------------------
# 7. Gemini Offline Fallback Behavior
# ---------------------------------------------------------------------------
class TestGeminiOfflineFallback:
    def test_offline_mode_returns_structured_result_when_key_missing(self, temp_repo, monkeypatch):
        """When allow_offline=True and GEMINI_API_KEY is missing, executes via deterministic orchestrator."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        build_and_save_profile(
            temp_repo,
            "biz_offline_test",
            "Offline Tailors",
            "tailoring_boutique",
            {
                "selling_price": 600.0,
                "unit_material_cost": 250.0,
                "daily_capacity": 10.0,
            },
        )

        result = run_autopilot_agent(
            "Can I take 3 more dresses?",
            business_id="biz_offline_test",
            profile_repo=temp_repo,
            allow_offline=True,
        )

        assert isinstance(result, AgentResult)
        assert result.error is None
        assert "Executed in offline mode without Gemini LLM." in result.assumptions
        assert result.tools_invoked[0]["tool"] == "offline_orchestrator"
        assert "Decision" in result.recommendation or "ACCEPT" in result.recommendation

    def test_offline_mode_false_raises_environment_error(self, monkeypatch):
        """When allow_offline=False (default) and GEMINI_API_KEY is missing, raises EnvironmentError."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
            run_autopilot_agent("Any message", allow_offline=False)


# ---------------------------------------------------------------------------
# 8. Purchase Approval Safeguards for Non-Food Businesses
# ---------------------------------------------------------------------------
class TestNonFoodPurchaseApprovalSafeguards:
    def test_fabric_purchase_plan_gated_by_owner_approval(self, temp_repo, temp_approvals):
        """Procurement for a clothing shop creates a purchase plan that requires approval."""
        orch = AdaptiveBusinessOrchestrator(repo=temp_repo, approval_service=temp_approvals)
        prof = build_and_save_profile(
            temp_repo,
            "biz_boutique_gate",
            "Pooja Boutique",
            "tailoring_boutique",
            {
                "daily_capacity": 20.0,
                "unit_material_cost": 300.0,
                "selling_price": 700.0,
                "cash_balance": 15000.0,
                "safety_reserve": 3000.0,
                "current_inventory": 0.0,
            },
        )

        res = orch.evaluate_opportunity(profile=prof, additional_units=10.0)

        assert res["decision"] == "ACCEPT_WITH_PROCUREMENT"
        assert res["purchase_plan"] is not None
        plan_id = res["purchase_plan"]["plan_id"]

        # Verify plan is PENDING_APPROVAL and cannot be executed without approval
        plan = temp_approvals.get_plan(plan_id)
        assert plan.status == PlanStatus.PENDING_APPROVAL

        with pytest.raises(Exception):
            # Attempt execution without owner sign-off
            temp_approvals.execute_plan(plan_id)

        # After approval, execution succeeds
        temp_approvals.approve_plan(plan_id)
        receipt = temp_approvals.execute_plan(plan_id, current_cash=15000.0, safety_reserve=3000.0)
        assert isinstance(receipt, dict)
        executed_plan = temp_approvals.get_plan(plan_id)
        assert executed_plan.status == PlanStatus.EXECUTED


# ---------------------------------------------------------------------------
# 9. Focused Regression Tests for Integration Verification Bug Fixes
# ---------------------------------------------------------------------------
class TestThreeBugFixesRegression:
    """
    Focused regressions ensuring:
    - Bug 1: Cost phrases do not overwrite selling price; multiple word orders supported.
    - Bug 2: Corrections log old value, replacement value, and timestamp; survive restart; accumulate.
    - Bug 3: Follow-up financial facts are persisted under existing profiles with appropriate keys.
    """

    # --- Bug 1: Price and cost extraction precedence & word order ---

    def test_bug1_regal_menswear_exact_input(self):
        """Input: Regal Menswear clothing shop with price, material cost, and capacity."""
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_regal_reg")
        res = ob.process_utterance(
            "I own Regal Menswear, a clothing shop selling shirts for Rs 850. "
            "Material cost is Rs 420 per shirt. We can prepare 25 garments daily."
        )
        assert ob.profile.get_value("selling_price") == 850.0
        assert ob.profile.get_value("unit_material_cost") == 420.0
        assert ob.profile.get_value("daily_capacity") == 25.0

    def test_bug1_cost_before_selling_price_word_order(self):
        """Cost phrase appears before selling price in utterance."""
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_order1")
        ob.process_utterance(
            "Material cost is Rs 420 per shirt. We sell shirts for Rs 850. We can prepare 25 garments daily."
        )
        assert ob.profile.get_value("selling_price") == 850.0
        assert ob.profile.get_value("unit_material_cost") == 420.0
        assert ob.profile.get_value("daily_capacity") == 25.0

    def test_bug1_parts_cost_and_servicing_charge_word_order(self):
        """Parts cost phrase before servicing charge in garage utterance."""
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_order2")
        ob.process_utterance(
            "Parts and lubricants cost Rs 260 per bike. Average servicing charge is Rs 750. Capacity 15 bikes daily."
        )
        assert ob.profile.get_value("selling_price") == 750.0
        assert ob.profile.get_value("unit_material_cost") == 260.0
        assert ob.profile.get_value("daily_capacity") == 15.0

    def test_bug1_wholesale_price_phrase_treated_as_cost_not_selling_price(self):
        """Wholesale price phrase must resolve to unit_material_cost, not selling_price."""
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_order3")
        ob.process_utterance("Wholesale cost is Rs 350 per unit. We sell at Rs 650.")
        assert ob.profile.get_value("selling_price") == 650.0
        assert ob.profile.get_value("unit_material_cost") == 350.0

    # --- Bug 2: Correction logging, persistence, and accumulation ---

    def test_bug2_correction_records_old_and_replacement_value(self):
        """Correction sequence records old value and replacement value with timestamp."""
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_corr_flow")
        ob.process_utterance("I sell garments at Rs 800.")
        assert ob.profile.get_value("selling_price") == 800.0

        ob.process_utterance("Correction, our price is actually Rs 950.")
        fact = ob.profile.get_fact("selling_price")

        assert fact.value == 950.0
        assert len(fact.correction_log) == 1
        entry = fact.correction_log[0]
        assert entry["old_value"] == 800.0
        assert entry.get("replacement_value") == 950.0 or entry.get("new_value") == 950.0
        assert "replaced_at" in entry

    def test_bug2_correction_survives_save_and_reload(self, temp_repo):
        """Correction history is preserved across database save and reload cycles."""
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_corr_reload")
        ob.process_utterance("I sell garments at Rs 800.")
        ob.process_utterance("Correction, our price is actually Rs 950.")

        temp_repo.save_profile(ob.profile)
        reloaded = temp_repo.get_profile("biz_corr_reload")

        assert reloaded is not None
        assert reloaded.get_value("selling_price") == 950.0
        fact = reloaded.get_fact("selling_price")
        assert len(fact.correction_log) == 1
        assert fact.correction_log[0]["old_value"] == 800.0
        assert fact.correction_log[0].get("replacement_value") == 950.0 or fact.correction_log[0].get("new_value") == 950.0

    def test_bug2_multiple_corrections_accumulate_history(self, temp_repo):
        """Multiple corrections accumulate sequentially and survive repository save/reload."""
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_corr_multi")
        ob.process_utterance("I sell garments at Rs 800.")
        ob.process_utterance("Correction, our price is actually Rs 900.")
        ob.process_utterance("Correction, our price is actually Rs 950.")

        temp_repo.save_profile(ob.profile)
        reloaded = temp_repo.get_profile("biz_corr_multi")

        fact = reloaded.get_fact("selling_price")
        assert fact.value == 950.0
        assert len(fact.correction_log) == 2
        assert fact.correction_log[0]["old_value"] == 800.0
        assert fact.correction_log[0].get("replacement_value") == 900.0 or fact.correction_log[0].get("new_value") == 900.0
        assert fact.correction_log[1]["old_value"] == 900.0
        assert fact.correction_log[1].get("replacement_value") == 950.0 or fact.correction_log[1].get("new_value") == 950.0

    # --- Bug 3: Follow-up financial fact persistence ---

    def test_bug3_follow_up_financial_fact_saved_without_repeating_onboarding(self, temp_repo):
        """Follow-up containing rent and electricity is saved under existing business profile."""
        orch = AdaptiveBusinessOrchestrator(repo=temp_repo)
        orch.handle_user_message(
            "I own Regal Menswear, a clothing shop selling shirts for Rs 850. "
            "Material cost is Rs 420 per shirt. We can prepare 25 garments daily.",
            business_id="biz_regal_fu",
        )

        # Follow-up containing only financial facts
        res = orch.handle_user_message(
            "Monthly rent and electricity is Rs 12,000.",
            business_id="biz_regal_fu",
        )
        assert res["intent"] == "onboarding"

        reloaded = temp_repo.get_profile("biz_regal_fu")
        assert reloaded is not None
        assert reloaded.get_value("monthly_fixed_cost") == 12000.0
        # Explicitly documented daily equivalent conversion (12000 / 30 = 400.0)
        assert reloaded.get_value("daily_fixed_cost") == 400.0
        # Original facts remain preserved
        assert reloaded.get_value("selling_price") == 850.0
        assert reloaded.get_value("unit_material_cost") == 420.0
        assert reloaded.get_value("daily_capacity") == 25.0

    def test_bug3_follow_up_with_per_month_phrasing(self, temp_repo):
        """Follow-up with 'Rs 15,000 per month' phrasing persists monthly and daily overhead."""
        orch = AdaptiveBusinessOrchestrator(repo=temp_repo)
        orch.handle_user_message(
            "I run Sharma Auto Garage. We service bikes at Rs 600. "
            "Parts cost Rs 220 per bike. Capacity 10 bikes per day.",
            business_id="biz_sharma_fu",
        )

        orch.handle_user_message(
            "Rent and electricity is Rs 15,000 per month.",
            business_id="biz_sharma_fu",
        )

        reloaded = temp_repo.get_profile("biz_sharma_fu")
        assert reloaded is not None
        assert reloaded.get_value("monthly_fixed_cost") == 15000.0
        assert reloaded.get_value("daily_fixed_cost") == 500.0
        assert reloaded.get_value("selling_price") == 600.0
