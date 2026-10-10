"""
Unit tests for Finance and Cash Flow Engine
"""
import unittest
from src.engine.finance import FinanceEngine

class TestFinanceEngine(unittest.TestCase):
    def test_immediate_cash_inflow(self):
        engine = FinanceEngine(
            starting_cash=10000.0,
            daily_fixed_cost=500.0,
            platform_commission_rate=0.0,
            receivables_delay_days=0,
        )
        (
            rev, cogs, comm, fixed, total_cost,
            profit, start_c, end_c, cash_in, cash_out
        ) = engine.process_daily_finance(
            fulfilled_orders=10,
            selling_price=200.0,
            unit_material_cost=80.0,
            variable_operating_cost=200.0,
            delivery_cost=100.0,
            marketing_spend=150.0,
            procurement_cash_outflow=1000.0,
        )
        # Revenue = 10 * 200 = 2000
        # Total cost = (10*80) + 200 + 100 + 0 + 150 + 500 = 800 + 950 = 1750
        # Profit = 2000 - 1750 = 250
        self.assertEqual(rev, 2000.0)
        self.assertEqual(total_cost, 1750.0)
        self.assertEqual(profit, 250.0)

        # Cash flow:
        # Inflow = 2000
        # Outflow = procurement(1000) + var(200) + del(100) + mkt(150) + fixed(500) = 1950
        # Ending cash = 10000 + 2000 - 1950 = 10050
        self.assertEqual(cash_in, 2000.0)
        self.assertEqual(cash_out, 1950.0)
        self.assertEqual(end_c, 10050.0)

    def test_delayed_receivables_cash_disconnect(self):
        # Business is profitable but cash drops because revenue is trapped in credit receivables!
        engine = FinanceEngine(
            starting_cash=5000.0,
            daily_fixed_cost=200.0,
            platform_commission_rate=0.0,
            receivables_delay_days=7, # 7 days payment delay
        )
        (
            rev, cogs, comm, fixed, total_cost,
            profit, start_c, end_c, cash_in, cash_out
        ) = engine.process_daily_finance(
            fulfilled_orders=10,
            selling_price=100.0,
            unit_material_cost=40.0,
            variable_operating_cost=50.0,
            delivery_cost=50.0,
            marketing_spend=50.0,
            procurement_cash_outflow=500.0,
        )
        # Profit = 1000 - (400 + 50 + 50 + 50 + 200) = 1000 - 750 = +250 (Profitable!)
        self.assertEqual(profit, 250.0)
        # But day 1 cash inflow is 0 due to 7-day delay!
        self.assertEqual(cash_in, 0.0)
        # Cash outflow = 500 + 50 + 50 + 50 + 200 = 850
        self.assertEqual(cash_out, 850.0)
        # Ending cash = 5000 - 850 = 4150 (Cash drops despite profit!)
        self.assertEqual(end_c, 4150.0)

if __name__ == "__main__":
    unittest.main()
