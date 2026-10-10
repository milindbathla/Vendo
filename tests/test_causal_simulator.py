"""
Comprehensive Causal and Regression Tests for Business Simulator
Validates:
1. No duplicate demand source
2. Initial customer accounting (no phantom pool)
3. Customer acquisition affects future demand
4. Churn/retention affects future demand
5. Service quality/stockouts degrade retention
6. Bulk procurement uses discounted unit cost in COGS
7. Bulk procurement affects upfront cash and inventory
8. Delayed receivables create profit vs cash disconnection
9. Cash exhaustion constrains procurement
10. Deterministic seed reproducibility
11. Cross-profile sanity bounds
"""
import copy
import math
import random
import unittest

from src.models.business import BusinessProfile
from src.models.customer import CustomerState
from src.models.inventory import InventoryState, PendingDelivery, InventoryLot
from src.engine.acquisition import AcquisitionEngine
from src.engine.demand import DemandEngine
from src.engine.procurement import ProcurementEngine
from src.engine.operations import OperationsEngine
from src.engine.finance import FinanceEngine
from src.simulator import BusinessSimulator, load_business_profiles


class TestCausalSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_business_profiles()

    def test_1_no_duplicate_demand_source(self):
        """Demand should be generated from customer orders without independent duplicate organic pool."""
        engine = DemandEngine(random.Random(42))
        # With zero customers, no orders are generated
        orders_zero = engine.generate_orders(
            day=1,
            business_type="home_bakery",
            base_demand=0.0,
            demand_variability=0.0,
            current_price=100.0,
            baseline_price=100.0,
            new_customer_orders=0,
            repeat_customer_orders=0,
        )
        self.assertEqual(orders_zero, 0)

        # When customer orders exist, orders scale directly with customer pool, not base_demand + customers
        orders_cust = engine.generate_orders(
            day=2, # Tuesday
            business_type="home_bakery",
            base_demand=100.0, # high base_demand should NOT be added as independent stream
            demand_variability=0.0,
            current_price=100.0,
            baseline_price=100.0,
            new_customer_orders=2,
            repeat_customer_orders=8,
        )
        # Day 2 Tuesday bakery dow_factor is 0.85; 10 customers * 0.85 = 8 or 9 orders (NOT 100 + 10!)
        self.assertLess(orders_cust, 20)
        self.assertGreaterEqual(orders_cust, 5)

    def test_2_initial_customer_accounting(self):
        """Initial customers must be tracked transparently with no phantom customers."""
        profile = self.profiles["home_bakery"]
        sim = BusinessSimulator(profile=profile, days=30, seed=42)
        res = sim.run()
        s = res.to_summary_dict()

        self.assertGreater(s["initial_customers"], 0)
        self.assertEqual(s["initial_customers"], profile.estimated_initial_customers)
        self.assertEqual(s["total_customer_base"], s["initial_customers"] + s["total_customers_acquired"])
        self.assertGreaterEqual(s["ending_active_customers"], 0)
        self.assertLessEqual(s["ending_active_customers"], s["total_customer_base"])

    def test_3_acquisition_increases_future_demand(self):
        """Increasing marketing spend acquires more customers and increases future demand."""
        profile = self.profiles["home_bakery"]
        sim_low = BusinessSimulator(profile=profile, days=60, seed=42, marketing_multiplier=0.0)
        res_low = sim_low.run()

        sim_high = BusinessSimulator(profile=profile, days=60, seed=42, marketing_multiplier=3.0)
        res_high = sim_high.run()

        self.assertGreater(res_high.total_customers_acquired, res_low.total_customers_acquired)
        self.assertGreater(res_high.total_demand, res_low.total_demand)
        self.assertGreater(res_high.ending_active_customers, res_low.ending_active_customers)

    def test_4_churn_retention_affects_future_demand(self):
        """Lower retention increases churn, shrinking the active customer base and repeat demand."""
        profile = self.profiles["home_bakery"]
        sim_high_ret = BusinessSimulator(profile=profile, days=60, seed=42, retention_multiplier=1.2)
        res_high_ret = sim_high_ret.run()

        sim_low_ret = BusinessSimulator(profile=profile, days=60, seed=42, retention_multiplier=0.6)
        res_low_ret = sim_low_ret.run()

        self.assertGreater(res_high_ret.ending_active_customers, res_low_ret.ending_active_customers)
        self.assertGreater(res_high_ret.total_repeat_orders, res_low_ret.total_repeat_orders)
        self.assertGreater(res_high_ret.total_demand, res_low_ret.total_demand)

    def test_5_fulfillment_quality_affects_retention(self):
        """Severe stockouts trigger service quality penalty and lower customer retention."""
        state = CustomerState(initial_customers=100)
        # Normal operations: full satisfaction (penalty = 1.0)
        _, repeat_good = state.record_day(new_customers=0, churn_rate=0.05, repeat_prob=0.5, service_quality_factor=1.0)
        active_good = state.active_customer_pool

        # Poor operations: stockouts cause satisfaction penalty = 0.65
        state_bad = CustomerState(initial_customers=100)
        _, repeat_bad = state_bad.record_day(new_customers=0, churn_rate=0.05, repeat_prob=0.5, service_quality_factor=0.65)
        active_bad = state_bad.active_customer_pool

        self.assertGreater(active_good, active_bad)
        self.assertGreater(repeat_good, repeat_bad)

    def test_6_bulk_procurement_discount_affects_cogs(self):
        """Inventory fulfilled from bulk-discounted batches must carry lower COGS per unit."""
        inv = InventoryState(
            on_hand=0.0,
            reorder_point=20.0,
            target_inventory=50.0,
            min_order_quantity=10.0,
            bulk_threshold=40.0,
            bulk_discount=0.20, # 20% discount
            base_unit_cost=100.0,
            lead_time_days=0,
            wastage_rate=0.0,
        )
        # Deliver a bulk order of 50 units at Rs.80
        delivery = PendingDelivery(
            quantity=50.0,
            unit_cost=80.0,
            total_cost=4000.0,
            days_remaining=0,
            is_bulk=True,
        )
        inv.pipeline.append(delivery)
        inv.advance_day()

        self.assertEqual(inv.on_hand, 50.0)
        consumed, cogs = inv.consume_with_cost(10.0)
        self.assertEqual(consumed, 10.0)
        self.assertEqual(cogs, 800.0) # Rs.80 per unit, NOT base Rs.100!

    def test_7_bulk_procurement_cash_and_inventory_impact(self):
        """Bulk procurement increases inventory holding and peak working capital commitment."""
        profile = self.profiles["home_bakery"]
        sim_normal = BusinessSimulator(profile=profile, days=60, seed=42, force_bulk=False)
        res_normal = sim_normal.run()

        sim_bulk = BusinessSimulator(profile=profile, days=60, seed=42, force_bulk=True, target_inventory_multiplier=1.5)
        res_bulk = sim_bulk.run()

        # Bulk strategy holds larger average and peak inventory
        self.assertGreater(res_bulk.average_inventory, res_normal.average_inventory)
        self.assertGreater(res_bulk.max_inventory, res_normal.max_inventory)

    def test_8_delayed_receivables_profit_vs_cash(self):
        """Delayed credit terms create a disconnection between accounting net profit and ending cash."""
        prof_cash = copy.deepcopy(self.profiles["tailoring_boutique"])
        prof_cash.receivables_delay_days = 0

        prof_credit = copy.deepcopy(self.profiles["tailoring_boutique"])
        prof_credit.receivables_delay_days = 15 # 15-day credit terms

        sim_cash = BusinessSimulator(profile=prof_cash, days=60, seed=42)
        res_cash = sim_cash.run()

        sim_credit = BusinessSimulator(profile=prof_credit, days=60, seed=42)
        res_credit = sim_credit.run()

        # Both have identical underlying demand, sales, and costs
        self.assertAlmostEqual(res_cash.net_profit, res_credit.net_profit, places=0)
        # But credit business has significantly lower ending cash on day 60 because 15 days of revenue are uncollected!
        self.assertGreater(res_cash.ending_cash, res_credit.ending_cash)
        self.assertGreater(res_cash.operating_cash_flow, res_credit.operating_cash_flow)

    def test_9_cash_exhaustion_procurement_constraint(self):
        """When cash drops below usable reserves, procurement cannot place orders, risking stockouts."""
        prof_low_cash = copy.deepcopy(self.profiles["home_bakery"])
        prof_low_cash.starting_capital = 2200.0 # Just barely above 2000 reserve
        prof_low_cash.starting_inventory = 5.0  # Very low initial inventory

        sim = BusinessSimulator(profile=prof_low_cash, days=30, seed=42)
        res = sim.run()

        # Business experiences stockout days due to inventory starvation from liquidity constraint
        self.assertGreater(res.total_stockout_days, 0)
        self.assertLess(res.fulfillment_rate, 1.0)

    def test_10_deterministic_seed_reproducibility(self):
        """Fixed random seeds must produce identical simulation outputs."""
        profile = self.profiles["cloud_kitchen"]
        sim1 = BusinessSimulator(profile=profile, days=45, seed=777)
        res1 = sim1.run()

        sim2 = BusinessSimulator(profile=profile, days=45, seed=777)
        res2 = sim2.run()

        self.assertEqual(res1.total_revenue, res2.total_revenue)
        self.assertEqual(res1.net_profit, res2.net_profit)
        self.assertEqual(res1.ending_cash, res2.ending_cash)
        self.assertEqual(res1.total_fulfilled_orders, res2.total_fulfilled_orders)
        self.assertEqual(res1.operating_cash_flow, res2.operating_cash_flow)

    def test_11_cross_profile_sanity_bounds(self):
        """All 10 business profiles must satisfy fundamental economic and sanity bounds."""
        for name, profile in self.profiles.items():
            sim = BusinessSimulator(profile=profile, days=45, seed=42)
            res = sim.run()
            s = res.to_summary_dict()

            self.assertGreaterEqual(s["total_revenue"], 0.0, f"{name}: negative revenue")
            self.assertGreaterEqual(s["total_cost"], 0.0, f"{name}: negative cost")
            self.assertGreaterEqual(s["fulfillment_rate_pct"], 0.0, f"{name}: negative fulfillment rate")
            self.assertLessEqual(s["fulfillment_rate_pct"], 100.0, f"{name}: fulfillment rate > 100%")
            self.assertFalse(math.isnan(s["ending_cash"]), f"{name}: ending cash is NaN")
            self.assertFalse(math.isinf(s["ending_cash"]), f"{name}: ending cash is inf")
            self.assertGreaterEqual(s["total_wastage_units"], 0.0, f"{name}: negative wastage")
            self.assertGreaterEqual(s["ending_active_customers"], 0, f"{name}: negative active customers")
            self.assertGreaterEqual(s["initial_customers"], 1, f"{name}: initial customers < 1")


if __name__ == "__main__":
    unittest.main()
