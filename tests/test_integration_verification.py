"""
Amazon Business Autopilot -- Integration Verification Suite
============================================================
Covers:
  Section 2 -- Adaptive Gemini path (mocked via tool dispatch)
  Section 3 -- Correction auditability / structured history
  Section 5 -- End-to-end acceptance demonstration (OFFLINE MODE, no Gemini key)

All tests use disposable in-memory or temp-file SQLite databases.
No real Gemini API calls are made.  No writes to data/demo.db.
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional

import pytest

from src.agent.onboarding import AdaptiveBusinessOnboarder
from src.agent.orchestrator import AdaptiveBusinessOrchestrator
from src.agent.tools import (
    TOOL_REGISTRY,
    set_active_profile_repo,
    set_active_business_id,
    get_business_overview,
)
from src.db.connection import get_connection, initialize_database
from src.db.profile_repository import AdaptiveProfileRepository
from src.models.adaptive_profile import FactStatus


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_repo():
    """Isolated in-memory adaptive repository per test."""
    conn = get_connection(":memory:")
    initialize_database(conn=conn)
    repo = AdaptiveProfileRepository(":memory:", shared_conn=conn)
    yield repo
    repo.close()


@pytest.fixture(autouse=True)
def reset_global_tools():
    """Reset module-level tool globals after every test."""
    yield
    set_active_profile_repo(None)
    set_active_business_id(None)


def _make_temp_repo():
    """Returns (repo, tmp_path) backed by a disposable temp-file database."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = f.name
    f.close()
    conn = get_connection(tmp_path)
    initialize_database(conn=conn)
    conn.close()
    return AdaptiveProfileRepository(tmp_path), tmp_path


def _onboard(repo: AdaptiveProfileRepository, utterance: str, biz_id: Optional[str] = None):
    """Run one onboarding utterance through the orchestrator."""
    orch = AdaptiveBusinessOrchestrator(repo=repo)
    return orch.handle_user_message(message=utterance, business_id=biz_id)


# ===========================================================================
# Section 2 -- Adaptive Gemini Path (exercised via real tool dispatch)
# ===========================================================================

class TestAdaptiveGeminiPath:
    """
    Verifies the flow: user message -> tool dispatch -> adaptive repo -> result.
    Tools are called directly (as Gemini would call them) against a real
    in-memory repository. No real Gemini LLM calls are made.
    """

    def test_clothing_profile_loaded_via_tool(self, mem_repo):
        """After onboarding a clothing shop, get_business_overview returns its facts."""
        _onboard(
            mem_repo,
            "I own Regal Menswear, a clothing shop selling shirts for Rs 850. "
            "Material cost is Rs 420 per shirt. We can prepare 25 garments daily.",
            biz_id="biz_regal_menswear",
        )
        set_active_profile_repo(mem_repo)
        ov = get_business_overview(business_type="biz_regal_menswear")

        assert ov["status"] == "SUCCESS"
        assert ov["is_adaptive"] is True
        assert ov["business_type"] == "biz_regal_menswear"
        assert ov["selling_price"] == 850.0
        assert ov["unit_cost"] == 420.0
        assert ov["daily_capacity"] == 25.0
        assert ov.get("category") != "home_tiffin"

    def test_second_business_id_cannot_access_first_business_data(self, mem_repo):
        """Querying a different business_id returns NOT_FOUND, not the first business."""
        _onboard(mem_repo, "I own Style Palace, clothing at Rs 900.", biz_id="biz_style_palace")
        set_active_profile_repo(mem_repo)

        result = get_business_overview(business_type="biz_wrong_id_xyz")

        assert result["status"] == "NOT_FOUND"
        assert result.get("selling_price") is None

    def test_unknown_business_id_does_not_silently_return_tiffin(self, mem_repo):
        """An unknown ID must return NOT_FOUND, never the home_tiffin static profile."""
        set_active_profile_repo(mem_repo)
        set_active_business_id(None)

        result = get_business_overview(business_type="biz_absolutely_unknown_999")

        assert result["status"] == "NOT_FOUND"
        assert result.get("business_type") != "home_tiffin"

    def test_home_tiffin_overridden_by_active_business_id(self, mem_repo):
        """
        If Gemini dispatches get_business_overview('home_tiffin') but an active
        business_id is set, the tool uses the adaptive profile, not the tiffin static.
        """
        _onboard(
            mem_repo,
            "I run Quick Stitch Tailor. Charge Rs 300 per garment. Material Rs 120. Capacity 15.",
            biz_id="biz_quick_stitch",
        )
        set_active_profile_repo(mem_repo)
        set_active_business_id("biz_quick_stitch")

        result = get_business_overview(business_type="home_tiffin")

        assert result["status"] == "SUCCESS"
        assert result["business_type"] == "biz_quick_stitch"
        assert result["selling_price"] == 300.0

    def test_offline_fallback_uses_correct_adaptive_profile(self, mem_repo):
        """
        When GEMINI_API_KEY is absent, run_autopilot_agent falls back to the
        offline orchestrator using the correct adaptive profile.
        LABEL: OFFLINE MODE -- no real Gemini LLM call made.
        """
        from src.agent.autopilot_agent import run_autopilot_agent

        _onboard(
            mem_repo,
            "I run Sharma Garage. Bikes serviced at Rs 600. Parts cost Rs 200 per bike. Capacity 10.",
            biz_id="biz_sharma_garage",
        )

        saved_key = os.environ.pop("GEMINI_API_KEY", None)
        try:
            result = run_autopilot_agent(
                user_goal="How is my business doing?",
                business_id="biz_sharma_garage",
                profile_repo=mem_repo,
                allow_offline=True,
            )
        finally:
            if saved_key is not None:
                os.environ["GEMINI_API_KEY"] = saved_key

        assert result.error is None or result.error == ""
        # Rationale must explicitly declare offline mode
        assert "offline" in result.rationale.lower() or "deterministic" in result.rationale.lower()


# ===========================================================================
# Section 3 -- Correction Auditability
# ===========================================================================

class TestCorrectionAuditability:
    """
    Verifies that:
    - After a correction, get_value() returns the new value, never the old.
    - A structured correction_log list is populated.
    - The log survives a save/reload cycle (persisted via notes column sentinel).
    - The notes field exposed to users is human-readable (no raw JSON sentinel).
    - Multiple corrections accumulate history entries.
    """

    def test_old_value_not_current_after_correction(self, mem_repo):
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_aud1")
        ob.process_utterance("I sell garments at Rs 800.")
        ob.process_utterance("Correction, our price is actually Rs 950.")

        assert ob.profile.get_value("selling_price") == 950.0
        assert ob.profile.get_fact("selling_price").value == 950.0

    def test_correction_log_populated(self, mem_repo):
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_aud2")
        ob.process_utterance("I sell garments at Rs 800.")
        ob.process_utterance("Correction, our price is actually Rs 950.")

        fact = ob.profile.get_fact("selling_price")
        assert len(fact.correction_log) >= 1
        assert fact.correction_log[0]["old_value"] == 800.0
        assert "replaced_at" in fact.correction_log[0]

    def test_correction_log_survives_save_and_reload(self, mem_repo):
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_aud3")
        ob.process_utterance("I sell garments at Rs 800.")
        ob.process_utterance("Correction, our price is actually Rs 950.")

        mem_repo.save_profile(ob.profile)
        reloaded = mem_repo.get_profile("biz_aud3")

        fact = reloaded.get_fact("selling_price")
        assert fact.value == 950.0
        assert len(fact.correction_log) >= 1
        assert fact.correction_log[0]["old_value"] == 800.0

    def test_notes_human_readable_in_to_dict(self, mem_repo):
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_aud4")
        ob.process_utterance("I sell at Rs 800.")
        ob.process_utterance("Correction, price is actually Rs 900.")

        mem_repo.save_profile(ob.profile)
        reloaded = mem_repo.get_profile("biz_aud4")
        d = reloaded.get_fact("selling_price").to_dict()

        # Human-readable notes must not expose the JSON sentinel
        assert "HISTORY" not in d["notes"]
        # Structured log must still be accessible
        assert len(d["correction_log"]) >= 1

    def test_multiple_corrections_accumulate_in_log(self, mem_repo):
        ob = AdaptiveBusinessOnboarder(business_id_hint="biz_aud5")
        ob.process_utterance("We charge Rs 400.")
        ob.process_utterance("Correction, charge is actually Rs 500.")
        ob.process_utterance("Correction, charge is actually Rs 550.")

        fact = ob.profile.get_fact("selling_price")
        assert fact.value == 550.0
        assert len(fact.correction_log) >= 2


# ===========================================================================
# Section 5 -- End-to-end Acceptance Demonstration (OFFLINE MODE)
# ===========================================================================

class TestEndToEndAcceptance:
    """
    Six-step acceptance walkthrough using a temp-file SQLite database.
    Restart is simulated by creating a second repository from the same file.

    LABEL: OFFLINE MODE -- uses AdaptiveBusinessOrchestrator directly.
    No real Gemini LLM call. No writes to data/demo.db.
    """

    def test_full_e2e_clothing_shop_and_mechanical_isolation(self):
        repo, tmp_path = _make_temp_repo()
        orch = AdaptiveBusinessOrchestrator(repo=repo)

        # Step 1: Initial onboarding from natural language
        r1 = orch.handle_user_message(
            "I own Regal Menswear in Lucknow, a clothing shop selling shirts. "
            "Average selling price is Rs 850 per garment. Material and wholesale cost is "
            "Rs 420 per shirt. We can alter and prepare 25 garments daily. "
            "Liquid cash balance is Rs 35,000. Safety reserve Rs 10,000.",
            business_id="biz_regal_e2e",
        )
        assert r1["intent"] == "onboarding"
        assert r1["business_id"] == "biz_regal_e2e"

        prof = repo.get_profile("biz_regal_e2e")
        assert prof.get_value("selling_price") == 850.0
        assert prof.get_value("unit_material_cost") == 420.0
        assert prof.get_value("daily_capacity") == 25.0

        # Step 2: Follow-up answer saved
        orch.handle_user_message(
            "Monthly rent and electricity is Rs 12,000.",
            business_id="biz_regal_e2e",
        )
        prof2 = repo.get_profile("biz_regal_e2e")
        has_overhead = (prof2.get_value("monthly_fixed_cost") is not None or
                        prof2.get_value("daily_fixed_cost") is not None)
        assert has_overhead, "Fixed overhead not saved from follow-up answer"

        # Step 3: Correct the selling price
        orch.handle_user_message(
            "Correction, our selling price is actually Rs 900 per garment.",
            business_id="biz_regal_e2e",
        )
        prof3 = repo.get_profile("biz_regal_e2e")
        assert prof3.get_value("selling_price") == 900.0
        cl = prof3.get_fact("selling_price").correction_log
        assert len(cl) >= 1 and cl[0]["old_value"] == 850.0

        # Step 4: Restart -- new repo from same DB file
        repo.close()
        repo2 = AdaptiveProfileRepository(tmp_path)
        reloaded = repo2.get_profile("biz_regal_e2e")
        assert reloaded is not None
        assert reloaded.get_value("selling_price") == 900.0
        assert len(reloaded.get_fact("selling_price").correction_log) >= 1

        # Step 5: Analysis using reloaded profile (offline orchestrator)
        # LABEL: OFFLINE MODE -- no Gemini LLM
        orch2 = AdaptiveBusinessOrchestrator(repo=repo2)
        analysis = orch2.analyze_profitability(reloaded)
        assert analysis.get("intent") in ("profitability", "profitability_analysis", "analysis")
        has_revenue = any("revenue" in k for k in analysis)
        assert has_revenue, f"No revenue key in analysis: {list(analysis.keys())}"

        # Step 6: Mechanical repair -- isolation proof
        orch2.handle_user_message(
            "I run Sharma Auto Garage. We service bikes at Rs 600. "
            "Parts cost Rs 220 per bike. Capacity 10 bikes per day.",
            business_id="biz_sharma_e2e",
        )
        mech = repo2.get_profile("biz_sharma_e2e")
        cloth = repo2.get_profile("biz_regal_e2e")

        assert mech is not None and cloth is not None
        assert mech.get_value("selling_price") == 600.0
        assert cloth.get_value("selling_price") == 900.0
        assert mech.category == "mechanical_repair"
        assert "cloth" in cloth.category or cloth.category in ("clothing_retail", "clothing_shop")

        repo2.close()


class TestAdaptiveToolsInRegistry:
    """Verify all 3 adaptive tools are reachable and functional via TOOL_REGISTRY."""

    def test_onboard_via_registry(self, mem_repo):
        set_active_profile_repo(mem_repo)
        result = TOOL_REGISTRY["onboard_or_update_business"](
            message="I run Lotus Salon. We charge Rs 450 per client. Capacity 18 clients daily.",
            business_id="biz_lotus_reg",
        )
        assert result["intent"] == "onboarding"
        assert result["business_id"] == "biz_lotus_reg"

    def test_get_adaptive_profile_via_registry(self, mem_repo):
        set_active_profile_repo(mem_repo)
        TOOL_REGISTRY["onboard_or_update_business"](
            message="I run Lotus Salon. Rs 450 per client.",
            business_id="biz_lotus_fetch",
        )
        result = TOOL_REGISTRY["get_adaptive_profile"](business_id="biz_lotus_fetch")
        assert result["status"] == "SUCCESS"
        assert "profile" in result

    def test_get_adaptive_profile_not_found(self, mem_repo):
        set_active_profile_repo(mem_repo)
        result = TOOL_REGISTRY["get_adaptive_profile"](business_id="biz_does_not_exist_xyz")
        assert result["status"] == "NOT_FOUND"

    def test_list_registered_businesses(self, mem_repo):
        set_active_profile_repo(mem_repo)
        TOOL_REGISTRY["onboard_or_update_business"](
            message="Shop A, clothing.", business_id="biz_la",
        )
        TOOL_REGISTRY["onboard_or_update_business"](
            message="Garage B, bike repair.", business_id="biz_lb",
        )
        result = TOOL_REGISTRY["list_registered_businesses"]()
        ids = [p["business_id"] for p in result["profiles"]]
        assert "biz_la" in ids and "biz_lb" in ids
        assert result["count"] >= 2
