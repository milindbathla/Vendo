"""Unit and integration tests for Inventory & Procurement specialist agent."""

import os
import shutil
import sys
import tempfile
import unittest

# Ensure src is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from inventory_procurement.agent import InventoryProcurementAgent
from inventory_procurement.config import resolve_db_path
from inventory_procurement.models import (
    ConstraintViolationError,
    ResourceNotFoundError,
    ValidationError,
)


class TestInventoryProcurementAgent(unittest.TestCase):
    """Test suite verifying inventory analysis, procurement options, planning, and execution."""

    def setUp(self):
        self.source_db = resolve_db_path()
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_demo.db")
        shutil.copy2(self.source_db, self.test_db)
        self.agent = InventoryProcurementAgent.from_db_path(self.test_db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_analyze_inventory_identifies_shortfalls(self):
        """Verify inventory analysis identifies sunflower oil and container shortfalls."""
        res = self.agent.analyze_inventory()
        self.assertEqual(res.planning_date, "2026-10-11")
        self.assertEqual(res.forecast_units, 23.0)
        self.assertEqual(res.safety_stock_pct, 10.0)
        self.assertEqual(res.effective_units, 25.3)

        items_by_id = {i.item_id: i for i in res.items}

        # Sunflower oil shortfall check
        oil = items_by_id["OIL-SUN-1L"]
        self.assertTrue(oil.is_shortfall)
        self.assertEqual(oil.current_stock, 0.8)
        self.assertAlmostEqual(oil.effective_requirement, 1.518, places=3)
        self.assertAlmostEqual(oil.shortfall_qty, 0.718, places=3)

        # Container shortfall check
        cont = items_by_id["CONT-750"]
        self.assertTrue(cont.is_shortfall)
        self.assertEqual(cont.current_stock, 12.0)
        self.assertEqual(cont.effective_requirement, 26.0)
        self.assertEqual(cont.shortfall_qty, 14.0)

        # Wheat flour below reorder point check
        atta = items_by_id["ATTA-10"]
        self.assertFalse(atta.is_shortfall)
        self.assertTrue(atta.below_reorder_point)
        self.assertEqual(atta.current_stock, 14.0)
        self.assertAlmostEqual(atta.effective_requirement, 5.06, places=2)
        self.assertAlmostEqual(atta.projected_stock, 8.94, places=2)
        self.assertEqual(atta.reorder_point, 10.0)

    def test_assess_restock_need(self):
        """Verify restock need assessment classifies urgency and deadlines."""
        res = self.agent.assess_restock_need()
        self.assertEqual(len(res.critical_shortfalls), 2)

        shortfall_ids = {i.item_id for i in res.critical_shortfalls}
        self.assertEqual(shortfall_ids, {"OIL-SUN-1L", "CONT-750"})

        rop_ids = {i.item_id for i in res.reorder_point_triggers}
        self.assertIn("ATTA-10", rop_ids)
        self.assertIn("DAL-MOONG", rop_ids)

        for need in res.critical_shortfalls:
            self.assertEqual(need.urgency, "CRITICAL")
        for need in res.reorder_point_triggers:
            self.assertEqual(need.urgency, "HIGH")

        self.assertGreater(len(res.recommended_actions), 0)

    def test_find_procurement_options_filters_feasibility(self):
        """Verify procurement options calculate pack quantities and filter out late/stockout options."""
        res = self.agent.find_procurement_options(
            target_items=[{"item_id": "OIL-SUN-1L", "needed_qty": 1.0}]
        )
        self.assertGreater(len(res.options), 0)

        qk_opt = next((o for o in res.options if o.supplier_id == "SUP-04"), None)
        self.assertIsNotNone(qk_opt)
        self.assertTrue(qk_opt.is_feasible)
        self.assertEqual(qk_opt.packs_needed, 1)
        self.assertEqual(qk_opt.total_cost, 207.0)
        self.assertTrue(qk_opt.is_simulated)

        sharma_rejected = next(
            (o for o in res.filtered_out_options if o["supplier_id"] == "SUP-01" and o["item_id"] == "OIL-SUN-1L"),
            None,
        )
        self.assertIsNotNone(sharma_rejected)
        self.assertIn("Out of stock", sharma_rejected["feasibility_reason"])

        gupta_rejected = next(
            (o for o in res.filtered_out_options if o["supplier_id"] == "SUP-03" and o["item_id"] == "OIL-SUN-1L"),
            None,
        )
        self.assertIsNotNone(gupta_rejected)
        self.assertIn("after required deadline", gupta_rejected["feasibility_reason"])

    def test_optimize_procurement_plan_selects_buffer_compliant_plan(self):
        """Verify optimal procurement plan selection rejects plans breaching minimum cash buffer."""
        res = self.agent.optimize_procurement_plan()
        self.assertTrue(res.is_fully_feasible)
        self.assertIsNotNone(res.recommended_plan)

        rec = res.recommended_plan
        self.assertEqual(rec.strategy, "mixed_optimal")
        self.assertEqual(rec.total_cost, 1675.0)
        self.assertTrue(rec.buffer_compliant)
        self.assertEqual(rec.post_plan_min_balance, 5225.0)
        self.assertGreaterEqual(rec.post_plan_min_balance, rec.min_cash_buffer)

        all_fast = next(
            (p for p in res.candidate_alternatives if p["strategy"] == "all_fast"),
            None,
        )
        self.assertIsNotNone(all_fast)
        self.assertFalse(all_fast["buffer_compliant"])
        self.assertEqual(all_fast["post_plan_min_balance"], 4683.0)
        self.assertLess(all_fast["post_plan_min_balance"], rec.min_cash_buffer)

    def test_create_purchase_plan_and_approval_flow(self):
        """Verify draft plan creation, token generation, and execution idempotency."""
        plan_lines = [
            {"supplier_id": "SUP-04", "item_id": "OIL-SUN-1L", "pack_qty": 2},
            {"supplier_id": "SUP-02", "item_id": "CONT-750", "pack_qty": 2},
        ]

        draft_res = self.agent.create_purchase_plan(plan_lines=plan_lines)
        self.assertEqual(draft_res.status, "draft")
        self.assertTrue(draft_res.plan_id.startswith("PLAN-"))
        self.assertTrue(draft_res.approval_token.startswith("APPR-"))
        self.assertEqual(draft_res.lines_count, 2)

        plan_row = self.agent.repo.get_purchase_plan(draft_res.plan_id)
        self.assertIsNotNone(plan_row)
        self.assertEqual(plan_row["status"], "draft")

        stock_before = self.agent.repo.get_inventory_stock()

        exec_res = self.agent.execute_purchase(
            plan_id=draft_res.plan_id,
            approval_token=draft_res.approval_token,
        )
        self.assertTrue(exec_res.success)
        self.assertEqual(exec_res.status, "executed")
        self.assertGreater(len(exec_res.simulated_orders), 0)

        plan_after = self.agent.repo.get_purchase_plan(draft_res.plan_id)
        self.assertEqual(plan_after["status"], "executed")

        approval_after = self.agent.repo.get_approval_by_token(draft_res.approval_token)
        self.assertEqual(approval_after["used"], 1)

        stock_after = self.agent.repo.get_inventory_stock()
        self.assertEqual(stock_before, stock_after)

        repeat_res = self.agent.execute_purchase(
            plan_id=draft_res.plan_id,
            approval_token=draft_res.approval_token,
        )
        self.assertTrue(repeat_res.success)
        self.assertEqual(repeat_res.status, "executed")
        self.assertIn("already executed", repeat_res.message)

    def test_execute_purchase_rejects_invalid_or_used_token(self):
        """Verify execution rejection with invalid, mismatched, or already used approval token."""
        plan_lines = [{"supplier_id": "SUP-04", "item_id": "OIL-SUN-1L", "pack_qty": 1}]
        draft = self.agent.create_purchase_plan(plan_lines=plan_lines)

        with self.assertRaises(ValidationError):
            self.agent.execute_purchase(plan_id=draft.plan_id, approval_token="APPR-FAKE-TOKEN")

        self.agent.execute_purchase(plan_id=draft.plan_id, approval_token=draft.approval_token)

        draft2 = self.agent.create_purchase_plan(plan_lines=plan_lines)
        with self.assertRaises(ValidationError):
            self.agent.execute_purchase(plan_id=draft2.plan_id, approval_token=draft.approval_token)

    def test_create_purchase_plan_validation_errors(self):
        """Verify validation errors for empty lines, non-existent items, and invalid quantities."""
        with self.assertRaises(ValidationError):
            self.agent.create_purchase_plan(plan_lines=[])

        with self.assertRaises(ValidationError):
            self.agent.create_purchase_plan(
                plan_lines=[{"supplier_id": "SUP-04", "item_id": "NON-EXISTENT", "pack_qty": 1}]
            )

        with self.assertRaises(ValidationError):
            self.agent.create_purchase_plan(
                plan_lines=[{"supplier_id": "SUP-04", "item_id": "OIL-SUN-1L", "pack_qty": -1}]
            )


if __name__ == "__main__":
    unittest.main()

