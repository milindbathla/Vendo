"""Unit tests for the integrated Specialist Agent tools in MCP and runtime architecture."""

import unittest
from Agents.finance_agent import FinanceAgent
from Agents.supplier_intelligence import SupplierIntelligenceAgent


class TestSpecialistAgentTools(unittest.TestCase):
    """Test suite verifying the 4 specialist agent tool functions added to MCP architecture."""

    def setUp(self):
        self.finance_agent = FinanceAgent(business_type="home_tiffin")
        self.supplier_agent = SupplierIntelligenceAgent()

    def test_get_profitability_analysis_tool(self):
        res = self.finance_agent.analyze_profitability()
        self.assertIsInstance(res, dict)
        self.assertEqual(res["business_type"], "home_tiffin")
        self.assertIn("pricing", res)
        self.assertIn("contribution_margin_per_unit_rs", res)
        self.assertIn("break_even_units_per_day", res)
        self.assertIn("insights", res)

    def test_forecast_cash_flow_tool(self):
        res = self.finance_agent.forecast_cash_flow(
            days=7,
            planned_procurement_cost=1000.0,
            planned_procurement_day=2,
        )
        self.assertIsInstance(res, dict)
        self.assertEqual(res["forecast_days"], 7)
        self.assertEqual(len(res["daily_breakdown"]), 7)
        self.assertIn("end_cash_balance_rs", res)

    def test_get_supplier_profile_tool(self):
        res = self.supplier_agent.get_supplier_profile(supplier_id="wholesale_mandi")
        self.assertIsInstance(res, dict)
        self.assertEqual(res["supplier_id"], "wholesale_mandi")
        self.assertEqual(res["name"], "Metro Wholesale Mandi")
        self.assertIn("min_order_value", res)

    def test_get_supplier_profile_unknown(self):
        with self.assertRaises(ValueError):
            self.supplier_agent.get_supplier_profile(supplier_id="invalid_vendor")

    def test_evaluate_supplier_tool(self):
        res = self.supplier_agent.evaluate_supplier(supplier_id="wholesale_mandi")
        self.assertIsInstance(res, dict)
        self.assertEqual(res["supplier_id"], "wholesale_mandi")
        self.assertIn("scores", res)
        self.assertIn("composite", res["scores"])
        self.assertIn("insights", res)


if __name__ == "__main__":
    unittest.main()
