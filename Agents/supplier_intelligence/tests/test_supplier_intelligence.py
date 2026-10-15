"""Unit tests for Supplier Intelligence specialist agent."""

import os
import sys
import unittest

# Ensure agent directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.supplier_intelligence import SupplierIntelligenceAgent


class TestSupplierIntelligenceAgent(unittest.TestCase):
    """Test suite verifying supplier profiles, multi-supplier comparisons, order history tracking, and scoring."""

    def setUp(self):
        self.agent = SupplierIntelligenceAgent()

    def test_get_supplier_profile_known(self):
        prof = self.agent.get_supplier_profile("wholesale_mandi")
        self.assertIsInstance(prof, dict)
        self.assertEqual(prof["supplier_id"], "wholesale_mandi")
        self.assertEqual(prof["name"], "Metro Wholesale Mandi")
        self.assertIn("categories", prof)
        self.assertIn("min_order_value", prof)
        self.assertIn("simulation_notice", prof)

    def test_get_supplier_profile_unknown_raises(self):
        with self.assertRaises(ValueError):
            self.agent.get_supplier_profile("nonexistent_supplier")

    def test_compare_suppliers(self):
        comp = self.agent.compare_suppliers("wholesale_mandi", "kirana_express")
        self.assertIsInstance(comp, dict)
        self.assertIn("supplier_a", comp)
        self.assertIn("supplier_b", comp)
        self.assertIn("winner_supplier_id", comp)
        self.assertIn("winner_reason", comp)
        self.assertIn(comp["winner_supplier_id"], ["wholesale_mandi", "kirana_express"])

    def test_get_supplier_history(self):
        hist = self.agent.get_supplier_history("wholesale_mandi", last_n=5)
        self.assertIsInstance(hist, dict)
        self.assertEqual(hist["supplier_id"], "wholesale_mandi")
        self.assertIn("transactions", hist)
        self.assertIn("summary", hist)
        self.assertTrue(len(hist["transactions"]) > 0)
        self.assertIn("avg_quality_rating", hist["summary"])

    def test_evaluate_supplier(self):
        evaluation = self.agent.evaluate_supplier("wholesale_mandi")
        self.assertIsInstance(evaluation, dict)
        self.assertEqual(evaluation["supplier_id"], "wholesale_mandi")
        self.assertIn("scores", evaluation)
        self.assertIn("composite", evaluation["scores"])
        self.assertIn("recommendation", evaluation)
        self.assertIn("insights", evaluation)
        self.assertGreaterEqual(evaluation["scores"]["composite"], 0.0)
        self.assertLessEqual(evaluation["scores"]["composite"], 10.0)

    def test_update_supplier_record(self):
        update_res = self.agent.update_supplier_record(
            supplier_id="wholesale_mandi",
            new_notes="Updated vendor notes after review.",
            new_rating=4.8,
        )
        self.assertIsInstance(update_res, dict)
        self.assertIn("updated_profile", update_res)
        self.assertIn("changelog", update_res)
        self.assertEqual(update_res["updated_profile"]["rating"], 4.8)

        # Verify change persisted in agent session
        prof = self.agent.get_supplier_profile("wholesale_mandi")
        self.assertEqual(prof["rating"], 4.8)


if __name__ == "__main__":
    unittest.main()
