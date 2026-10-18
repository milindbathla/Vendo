"""
Tests for the Adaptive Multi-Business Onboarding system.
=========================================================
All tests use isolated :memory: or temp-file SQLite databases.
data/demo.db is NEVER touched.

Run with:
    python -m pytest tests/test_adaptive_onboarding.py -v
"""
import sqlite3
import tempfile
import os
import pytest

from src.db.connection import get_connection, initialize_database
from src.db.profile_repository import AdaptiveProfileRepository
from src.agent.onboarding import AdaptiveBusinessOnboarder, CATEGORY_KEYWORDS
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.decision.approval_service import PurchaseApprovalService
from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactStatus,
    FactSource,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_repo():
    shared_conn = get_connection(":memory:")
    initialize_database(conn=shared_conn)
    repo = AdaptiveProfileRepository(db_path=":memory:", shared_conn=shared_conn)
    yield repo
    repo.close()


@pytest.fixture
def mem_approvals():
    return PurchaseApprovalService(db_path=":memory:")


@pytest.fixture
def orchestrator(mem_repo, mem_approvals):
    return AdaptiveBusinessOrchestrator(repo=mem_repo, approval_service=mem_approvals)


# ---------------------------------------------------------------------------
# 1. Category Detection
# ---------------------------------------------------------------------------


class TestCategoryDetection:
    def _detect(self, text):
        onboarder = AdaptiveBusinessOnboarder()
        return onboarder._detect_category(text.lower())

    def test_detects_home_tiffin(self):
        assert self._detect("I run a tiffin service delivering meal dabba daily") == "home_tiffin"

    def test_detects_electronics_repair(self):
        assert self._detect("We repair mobile phones and laptops") == "electronics_repair"

    def test_detects_salon_service(self):
        assert self._detect("I own a beauty salon offering haircuts and facials") == "salon_service"

    def test_detects_retail_kirana(self):
        assert self._detect("My kirana grocery store sells FMCG provisions") == "retail_kirana"

    def test_detects_tailoring_boutique(self):
        assert self._detect("We do tailoring and stitching at our boutique") == "tailoring_boutique"

    def test_detects_home_bakery(self):
        assert self._detect("I bake cakes and pastries from home") == "home_bakery"

    def test_detects_small_fabrication(self):
        assert self._detect("We do metal welding and fabrication at our workshop") == "small_fabrication"

    def test_returns_none_for_unknown(self):
        assert self._detect("I work in software engineering and data science") is None


# ---------------------------------------------------------------------------
# 2. Onboarding - Tiffin Business
# ---------------------------------------------------------------------------


class TestTiffinOnboarding:
    def test_onboards_tiffin_from_single_utterance(self):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "I run Annapurna Tiffin Service. We deliver home-cooked meal dabba. "
            "Each tiffin sells for Rs 80. Ingredients cost Rs 35 per tiffin. "
            "We can deliver 50 tiffins a day. Right now I have Rs 8,000 cash. "
            "My daily overhead is Rs 400 per day."
        )
        p = onboarder.profile
        assert p.category == "home_tiffin"
        assert p.get_value("selling_price") == 80.0
        assert p.get_value("unit_material_cost") == 35.0
        assert p.get_value("daily_capacity") == 50.0
        assert p.get_value("cash_balance") == 8000.0
        assert p.get_value("daily_fixed_cost") == 400.0

    def test_tiffin_facts_are_confirmed(self):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "I run a tiffin delivery service. Fee is Rs 90. Ingredients cost Rs 40. "
            "We handle up to 30 tiffins per day."
        )
        p = onboarder.profile
        assert p.facts["selling_price"].status == FactStatus.CONFIRMED
        assert p.facts["unit_material_cost"].status == FactStatus.CONFIRMED
        assert p.facts["daily_capacity"].status == FactStatus.CONFIRMED

    def test_tiffin_source_is_user_stated(self):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "We cook and deliver tiffin. Fee is Rs 70. Ingredients cost Rs 30 per meal."
        )
        assert onboarder.profile.facts["selling_price"].source == FactSource.USER_STATED


# ---------------------------------------------------------------------------
# 3. Onboarding - Tailoring / Clothing Store
# ---------------------------------------------------------------------------


class TestTailoringOnboarding:
    def test_onboards_tailoring(self):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "I run Shri Tailor Boutique. We do stitching and alterations. "
            "We charge Rs 350 per garment. Fabric costs around Rs 80. "
            "We can stitch up to 12 garments a day."
        )
        p = onboarder.profile
        assert p.category == "tailoring_boutique"
        assert p.get_value("selling_price") == 350.0
        assert p.get_value("unit_material_cost") == 80.0
        assert p.get_value("daily_capacity") == 12.0

    def test_tailoring_does_not_get_tiffin_category(self):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "My shop does stitching and garment alterations. Charge is Rs 300 per piece."
        )
        assert onboarder.profile.category != "home_tiffin"
        # No tiffin-specific facts should be invented
        assert "meal_name" not in onboarder.profile.facts
        assert "recipe_breakdown" not in onboarder.profile.facts


# ---------------------------------------------------------------------------
# 4. Missing Facts and Follow-up Questions
# ---------------------------------------------------------------------------


class TestMissingFactsAndFollowups:
    def test_asks_for_selling_price_when_missing(self):
        onboarder = AdaptiveBusinessOnboarder()
        result = onboarder.process_utterance(
            "I have a small electronics repair shop in town."
        )
        nq = result["next_question"]
        assert nq is not None
        assert "price" in nq.lower() or "fee" in nq.lower() or "charge" in nq.lower()

    def test_asks_for_cash_balance_when_price_and_cost_present(self):
        onboarder = AdaptiveBusinessOnboarder()
        result = onboarder.process_utterance(
            "I run a bakery. Each cake sells for Rs 500. Ingredients cost about Rs 200. "
            "We bake up to 10 cakes a day."
        )
        nq = result["next_question"]
        assert nq is not None
        assert "cash" in nq.lower() or "balance" in nq.lower()

    def test_no_follow_up_when_all_facts_present(self):
        onboarder = AdaptiveBusinessOnboarder()
        result = onboarder.process_utterance(
            "I run Annapurna Tiffin. Fee is Rs 80. Ingredients cost Rs 35. "
            "We do 50 tiffins a day. I have Rs 8,000 cash. Fixed cost is Rs 400 per day."
        )
        assert result["next_question"] is None

    def test_unknown_price_stays_unknown(self):
        """System must not fabricate a price."""
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance("I own a small salon.")
        p = onboarder.profile
        price_fact = p.facts.get("selling_price")
        assert price_fact is None or price_fact.status == FactStatus.UNKNOWN

    def test_unknown_inventory_stays_unknown(self):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "We repair phones. Charge is Rs 450. Parts cost Rs 180."
        )
        inv = onboarder.profile.facts.get("current_inventory")
        assert inv is None or inv.status == FactStatus.UNKNOWN


# ---------------------------------------------------------------------------
# 5. Fact Correction and Provenance
# ---------------------------------------------------------------------------


class TestFactCorrection:
    def _setup(self, cost):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            f"I repair phones. Charge is Rs 450. Parts cost Rs {cost}. "
            "We handle up to 15 repairs a day."
        )
        return onboarder

    def test_correction_updates_value(self):
        onboarder = self._setup(180)
        onboarder.process_utterance("Actually, my spare parts cost is Rs 220, not 180.")
        assert onboarder.profile.get_value("unit_material_cost") == 220.0

    def test_correction_appears_in_corrections_list(self):
        onboarder = self._setup(180)
        result = onboarder.process_utterance("Actually, my spare parts cost is Rs 220, not 180.")
        assert len(result["corrections"]) > 0
        corr = result["corrections"][0]
        assert corr["key"] == "unit_material_cost"
        assert corr["old_value"] == 180.0
        assert corr["new_value"] == 220.0

    def test_price_correction(self):
        onboarder = AdaptiveBusinessOnboarder()
        onboarder.process_utterance(
            "I run a tiffin service. Fee is Rs 80. Ingredients Rs 35. Capacity 40/day."
        )
        onboarder.process_utterance("Actually my ticket price is Rs 90, not 80.")
        assert onboarder.profile.get_value("selling_price") == 90.0

    def test_corrected_fact_stays_confirmed(self):
        onboarder = self._setup(180)
        onboarder.process_utterance("Actually, my spare parts cost is Rs 220, not 180.")
        assert onboarder.profile.facts["unit_material_cost"].status == FactStatus.CONFIRMED

    def test_corrected_fact_source_stays_user_stated(self):
        onboarder = self._setup(180)
        onboarder.process_utterance("Actually, my spare parts cost is Rs 220, not 180.")
        assert onboarder.profile.facts["unit_material_cost"].source == FactSource.USER_STATED


# ---------------------------------------------------------------------------
# 6. Profile Persistence and Retrieval
# ---------------------------------------------------------------------------


class TestProfilePersistence:
    def test_save_and_reload(self, mem_repo):
        p = AdaptiveBusinessProfile(
            business_id="biz_persist", display_name="Persist Shop", category="electronics_repair"
        )
        p.set_fact("selling_price", 400.0)
        p.set_fact("unit_material_cost", 150.0)
        mem_repo.save_profile(p)

        loaded = mem_repo.get_profile("biz_persist")
        assert loaded is not None
        assert loaded.display_name == "Persist Shop"
        assert loaded.get_value("selling_price") == 400.0
        assert loaded.get_value("unit_material_cost") == 150.0

    def test_update_fact_persists(self, mem_repo):
        p = AdaptiveBusinessProfile(
            business_id="biz_update", display_name="Update Shop", category="salon_service"
        )
        p.set_fact("selling_price", 300.0)
        mem_repo.save_profile(p)
        p.set_fact("selling_price", 350.0)
        mem_repo.save_profile(p)

        loaded = mem_repo.get_profile("biz_update")
        assert loaded.get_value("selling_price") == 350.0

    def test_missing_profile_returns_none(self, mem_repo):
        assert mem_repo.get_profile("biz_does_not_exist") is None

    def test_list_profiles(self, mem_repo):
        for i in range(3):
            p = AdaptiveBusinessProfile(
                business_id=f"biz_list_{i}", display_name=f"Shop {i}", category="retail_kirana"
            )
            mem_repo.save_profile(p)
        ids = [x["business_id"] for x in mem_repo.list_profiles()]
        assert "biz_list_0" in ids
        assert "biz_list_1" in ids
        assert "biz_list_2" in ids

    def test_fact_status_preserved(self, mem_repo):
        p = AdaptiveBusinessProfile(
            business_id="biz_status", display_name="Status Shop", category="home_tiffin"
        )
        p.set_fact("selling_price", 90.0, status=FactStatus.CONFIRMED, source=FactSource.USER_STATED)
        mem_repo.save_profile(p)

        loaded = mem_repo.get_profile("biz_status")
        assert loaded.facts["selling_price"].status == FactStatus.CONFIRMED
        assert loaded.facts["selling_price"].source == FactSource.USER_STATED

    def test_delete_profile(self, mem_repo):
        p = AdaptiveBusinessProfile(
            business_id="biz_delete", display_name="Delete Me", category="home_bakery"
        )
        mem_repo.save_profile(p)
        assert mem_repo.delete_profile("biz_delete") is True
        assert mem_repo.get_profile("biz_delete") is None

    def test_cross_session_persistence_with_tempfile(self):
        """Simulate profile surviving across sessions via a temp SQLite file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn_a = get_connection(db_path)
            initialize_database(conn=conn_a)
            repo_a = AdaptiveProfileRepository(db_path=db_path, shared_conn=conn_a)
            p = AdaptiveBusinessProfile(
                business_id="biz_xsession", display_name="Cross Session Shop", category="salon_service"
            )
            p.set_fact("selling_price", 500.0)
            repo_a.save_profile(p)
            repo_a.close()

            conn_b = get_connection(db_path)
            repo_b = AdaptiveProfileRepository(db_path=db_path, shared_conn=conn_b)
            loaded = repo_b.get_profile("biz_xsession")
            assert loaded is not None
            assert loaded.get_value("selling_price") == 500.0
            repo_b.close()
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# 7. Tenant Isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_two_businesses_are_isolated(self, mem_repo):
        p1 = AdaptiveBusinessProfile(
            business_id="biz_t1", display_name="Electronics", category="electronics_repair"
        )
        p1.set_fact("selling_price", 450.0)
        p1.set_fact("unit_material_cost", 200.0)
        mem_repo.save_profile(p1)

        p2 = AdaptiveBusinessProfile(
            business_id="biz_t2", display_name="Salon", category="salon_service"
        )
        p2.set_fact("selling_price", 600.0)
        p2.set_fact("unit_material_cost", 120.0)
        mem_repo.save_profile(p2)

        l1 = mem_repo.get_profile("biz_t1")
        l2 = mem_repo.get_profile("biz_t2")
        assert l1.get_value("selling_price") == 450.0
        assert l1.get_value("unit_material_cost") == 200.0
        assert l2.get_value("selling_price") == 600.0
        assert l2.get_value("unit_material_cost") == 120.0

    def test_correction_for_biz1_does_not_affect_biz2(self, orchestrator, mem_repo):
        orchestrator.handle_user_message(
            "I run Kalyan Electronics. We repair phones. Charge is Rs 450. Parts cost Rs 180. "
            "We handle 15 repairs a day. I have Rs 12,000 cash. Rent is Rs 300 per day.",
            business_id="biz_iso_elec",
        )
        orchestrator.handle_user_message(
            "I own Apsara Salon. We do haircuts. Ticket is Rs 600. Consumables cost Rs 120. "
            "We do 24 clients a day. I have Rs 25,000 cash. Fixed expenses Rs 650 per day.",
            business_id="biz_iso_salon",
        )
        orchestrator.handle_user_message(
            "Actually my spare parts cost is Rs 220, not 180.",
            business_id="biz_iso_elec",
        )
        salon = mem_repo.get_profile("biz_iso_salon")
        assert salon.get_value("unit_material_cost") == 120.0

    def test_business_id_hint_respected(self, orchestrator, mem_repo):
        orchestrator.handle_user_message(
            "I run a tiffin service. Each tiffin sells for Rs 80. "
            "Ingredients cost Rs 35. We do 50 tiffins per day.",
            business_id="biz_exact_hint",
        )
        loaded = mem_repo.get_profile("biz_exact_hint")
        assert loaded is not None
        assert loaded.get_value("selling_price") == 80.0


# ---------------------------------------------------------------------------
# 8. Prerequisite Gating (no fabrication of unknown facts)
# ---------------------------------------------------------------------------


class TestPrerequisiteGating:
    def test_profitability_blocked_without_selling_price(self, orchestrator):
        p = AdaptiveBusinessProfile(
            business_id="biz_np", display_name="No Price", category="salon_service"
        )
        p.set_fact("unit_material_cost", 150.0)
        result = orchestrator.analyze_profitability(p)
        assert result["status"] == "PREREQUISITES_MISSING"
        assert result["missing_field"] == "selling_price"

    def test_profitability_blocked_without_unit_cost(self, orchestrator):
        p = AdaptiveBusinessProfile(
            business_id="biz_nc", display_name="No Cost", category="electronics_repair"
        )
        p.set_fact("selling_price", 400.0)
        result = orchestrator.analyze_profitability(p)
        assert result["status"] == "PREREQUISITES_MISSING"
        assert result["missing_field"] == "unit_material_cost"

    def test_opportunity_blocked_without_capacity(self, orchestrator):
        p = AdaptiveBusinessProfile(
            business_id="biz_nocap", display_name="No Cap", category="home_tiffin"
        )
        p.set_fact("selling_price", 80.0)
        p.set_fact("unit_material_cost", 35.0)
        result = orchestrator.evaluate_opportunity(p, 20.0)
        assert result["status"] == "PREREQUISITES_MISSING"
        assert result["missing_field"] == "daily_capacity"

    def test_profitability_succeeds_with_required_facts(self, orchestrator):
        p = AdaptiveBusinessProfile(
            business_id="biz_full", display_name="Full Facts", category="electronics_repair"
        )
        p.set_fact("selling_price", 450.0)
        p.set_fact("unit_material_cost", 200.0)
        p.set_fact("daily_capacity", 15.0)
        p.set_fact("daily_fixed_cost", 300.0)
        result = orchestrator.analyze_profitability(p)
        assert result["status"] == "SUCCESS"
        assert result["contribution_margin"] == 250.0
        assert result["margin_pct"] > 0


# ---------------------------------------------------------------------------
# 9. Purchase Approval Safeguards
# ---------------------------------------------------------------------------


class TestPurchaseApprovalSafeguards:
    def _create_ready_profile(self, business_id):
        p = AdaptiveBusinessProfile(
            business_id=business_id, display_name="Approval Shop", category="electronics_repair"
        )
        p.set_fact("selling_price", 450.0)
        p.set_fact("unit_material_cost", 200.0)
        p.set_fact("daily_capacity", 15.0)
        p.set_fact("cash_balance", 15000.0)
        p.set_fact("safety_reserve", 2000.0)
        p.set_fact("current_inventory", 0.0)
        p.set_fact("daily_fixed_cost", 300.0)
        return p

    def test_plan_blocked_before_approval(self, orchestrator, mem_repo, mem_approvals):
        p = self._create_ready_profile("biz_blocked")
        mem_repo.save_profile(p)

        result = orchestrator.evaluate_opportunity(p, 10.0)
        assert result["decision"] == "ACCEPT_WITH_PROCUREMENT"
        plan_id = result["purchase_plan"]["plan_id"]

        from src.decision.approval_service import InvalidPlanStateError
        with pytest.raises(InvalidPlanStateError):
            mem_approvals.execute_plan(plan_id=plan_id, current_cash=15000.0, safety_reserve=2000.0)

    def test_plan_executes_after_approval(self, orchestrator, mem_repo, mem_approvals):
        p = self._create_ready_profile("biz_approved2")
        mem_repo.save_profile(p)

        result = orchestrator.evaluate_opportunity(p, 10.0)
        plan_id = result["purchase_plan"]["plan_id"]

        mem_approvals.confirm_plan(plan_id=plan_id, decision="APPROVE")
        receipt = mem_approvals.execute_plan(plan_id=plan_id, current_cash=15000.0, safety_reserve=2000.0)
        assert receipt is not None
        assert "order_id" in receipt

    def test_reject_at_capacity(self, orchestrator, mem_repo):
        p = AdaptiveBusinessProfile(
            business_id="biz_at_cap", display_name="At Cap", category="home_tiffin"
        )
        p.set_fact("selling_price", 80.0)
        p.set_fact("unit_material_cost", 35.0)
        p.set_fact("daily_capacity", 10.0)
        p.set_fact("base_daily_demand", 10.0)
        p.set_fact("cash_balance", 10000.0)
        p.set_fact("safety_reserve", 1000.0)
        p.set_fact("current_inventory", 0.0)
        mem_repo.save_profile(p)

        result = orchestrator.evaluate_opportunity(p, 5.0)
        assert result["decision"] == "REJECT"


# ---------------------------------------------------------------------------
# 10. End-to-end orchestrator routing
# ---------------------------------------------------------------------------


class TestOrchestratorRouting:
    def test_onboarding_returns_correct_keys(self, orchestrator):
        result = orchestrator.handle_user_message(
            "I run a kirana store selling groceries. Each sale averages Rs 200. "
            "Wholesale cost is around Rs 150. We serve 100 customers a day.",
            business_id="biz_kirana",
        )
        assert result["intent"] == "onboarding"
        assert result["business_id"] == "biz_kirana"
        assert result["category"] == "retail_kirana"

    def test_profit_query_after_onboarding(self, orchestrator):
        orchestrator.handle_user_message(
            "I repair electronics. Charge is Rs 400. Parts cost Rs 150. "
            "Capacity 10/day. Cash Rs 5000. Fixed Rs 200 per day.",
            business_id="biz_prof",
        )
        result = orchestrator.handle_user_message("How is my profit margin?", business_id="biz_prof")
        assert result["status"] == "SUCCESS"
        assert result["contribution_margin"] == 250.0

    def test_correction_updates_downstream_calculation(self, orchestrator):
        orchestrator.handle_user_message(
            "I repair electronics. Charge is Rs 400. Parts cost Rs 150. Capacity 10/day. Fixed Rs 200/day.",
            business_id="biz_recalc2",
        )
        orchestrator.handle_user_message(
            "Actually, parts cost Rs 200, not 150.",
            business_id="biz_recalc2",
        )
        result = orchestrator.handle_user_message("Recalculate my profit margin.", business_id="biz_recalc2")
        assert result["status"] == "SUCCESS"
        assert result["unit_cost"] == 200.0
        assert result["contribution_margin"] == 200.0


# ---------------------------------------------------------------------------
# 11. Sentinel: data/demo.db must not be touched
# ---------------------------------------------------------------------------


def test_demo_db_not_empty():
    """Sentinel: data/demo.db must not have been emptied or deleted by these tests."""
    db_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "demo.db")
    )
    if os.path.exists(db_path):
        assert os.path.getsize(db_path) > 0


# ---------------------------------------------------------------------------
# 12. Regression: existing model exports
# ---------------------------------------------------------------------------


def test_models_exports_intact():
    from src.models import (  # noqa: F401
        BusinessProfile,
        CustomerState,
        InventoryState,
        DailyMetric,
        SimulationResult,
        FactStatus,
        FactSource,
        BusinessFact,
        AdaptiveBusinessProfile,
    )
    from src.decision.business_autopilot import OpportunityDecision  # noqa: F401
    from src.decision.approval_service import PurchasePlan  # noqa: F401


def test_mcp_server_importable():
    from src.server.mcp_server import server  # noqa: F401
    assert server is not None
