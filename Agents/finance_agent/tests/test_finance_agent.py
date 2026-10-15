"""Unit tests for Finance specialist agent."""

import os
import sys
import unittest

# Ensure agent directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Agents.finance_agent import FinanceAgent


class TestFinanceAgent(unittest.TestCase):
    """Test suite verifying financial positioning, cash forecasting, profitability, and affordability."""

    def setUp(self):
        self.agent = FinanceAgent()

    def test_get_financial_position(self):
        pos = self.agent.get_financial_position()
        self.assertIsInstance(pos, dict)
        self.assertIn("business_type", pos)
        self.assertIn("cash_balance_rs", pos)
        self.assertIn("today", pos)
        self.assertIn("cash_runway_days", pos)
        self.assertIn("health_label", pos)
        self.assertGreater(pos["cash_balance_rs"], 0)
        self.assertIn(pos["health_label"], ["healthy", "caution", "critical"])

    def test_forecast_cash_flow_default(self):
        forecast = self.agent.forecast_cash_flow(days=7)
        self.assertIsInstance(forecast, dict)
        self.assertEqual(forecast["forecast_days"], 7)
        self.assertEqual(len(forecast["daily_breakdown"]), 7)
        self.assertIn("starting_cash_rs", forecast)
        self.assertIn("end_cash_balance_rs", forecast)
        self.assertIn("daily_breakdown", forecast)

    def test_forecast_cash_flow_with_procurement(self):
        forecast_proc = self.agent.forecast_cash_flow(
            days=5,
            planned_procurement_cost=5000.0,
            planned_procurement_day=2,
        )
        self.assertEqual(forecast_proc["forecast_days"], 5)
        day2 = next(d for d in forecast_proc["daily_breakdown"] if d["day"] == 2)
        day1 = next(d for d in forecast_proc["daily_breakdown"] if d["day"] == 1)
        self.assertGreater(day2["outflow_rs"], day1["outflow_rs"])

    def test_analyze_profitability(self):
        analysis = self.agent.analyze_profitability()
        self.assertIsInstance(analysis, dict)
        self.assertIn("pricing", analysis)
        self.assertIn("break_even_units_per_day", analysis)
        self.assertIn("profit_at_current_demand_rs", analysis)
        self.assertIn("insights", analysis)
        self.assertIsInstance(analysis["insights"], list)

    def test_analyze_purchase_affordability_affordable(self):
        # Small purchase should be affordable
        res = self.agent.analyze_purchase_affordability(purchase_amount=500.0)
        self.assertIsInstance(res, dict)
        self.assertIn("is_affordable", res)
        self.assertIn("recommendation", res)
        self.assertTrue(res["is_affordable"])
        self.assertIn(res["risk_label"], ["safe", "moderate", "high"])

    def test_analyze_purchase_affordability_unaffordable(self):
        # Extremely large purchase should not be affordable
        res = self.agent.analyze_purchase_affordability(purchase_amount=500000.0)
        self.assertIsInstance(res, dict)
        self.assertFalse(res["is_affordable"])
        self.assertEqual(res["risk_label"], "infeasible")
        self.assertIn("alternatives", res)
        self.assertTrue(len(res["alternatives"]) > 0)

    def test_simulate_financial_impact(self):
        sim = self.agent.simulate_financial_impact(
            scenario_name="Price increase",
            price_change_rs=10.0,
        )
        self.assertIsInstance(sim, dict)
        self.assertIn("scenario_name", sim)
        self.assertIn("baseline", sim)
        self.assertIn("simulated", sim)
        self.assertIn("summary", sim)
        self.assertIn("risk_label", sim)


if __name__ == "__main__":
    unittest.main()
