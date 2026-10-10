"""
Small Business Value-Chain Simulator
====================================
Core simulation orchestrator and CLI entry point.
Models: Acquisition -> Demand -> Orders -> Procurement -> Inventory ->
        Operations -> Fulfillment -> Revenue -> Costs -> Profit -> Cash -> Retention.
"""
import argparse
import json
import os
import random
from typing import Dict, Any, Optional, List

from src.models.business import BusinessProfile
from src.models.customer import CustomerState
from src.models.inventory import InventoryState
from src.models.simulation import DailyMetric, SimulationResult
from src.engine.acquisition import AcquisitionEngine
from src.engine.demand import DemandEngine
from src.engine.procurement import ProcurementEngine
from src.engine.operations import OperationsEngine
from src.engine.finance import FinanceEngine


class BusinessSimulator:
    def __init__(
        self,
        profile: BusinessProfile,
        days: int = 90,
        seed: int = 42,
        marketing_multiplier: float = 1.0,
        price_multiplier: float = 1.0,
        capacity_multiplier: float = 1.0,
        supplier_cost_multiplier: float = 1.0,
        repeat_rate_multiplier: float = 1.0,
        retention_multiplier: float = 1.0,
        force_bulk: Optional[bool] = None,
        target_inventory_multiplier: float = 1.0,
    ):
        self.profile = profile
        self.days = days
        self.seed = seed
        self.rng = random.Random(seed)

        # Modifiers
        self.marketing_multiplier = marketing_multiplier
        self.price_multiplier = price_multiplier
        self.capacity_multiplier = capacity_multiplier
        self.supplier_cost_multiplier = supplier_cost_multiplier
        self.repeat_rate_multiplier = repeat_rate_multiplier
        self.retention_multiplier = retention_multiplier
        self.force_bulk = force_bulk
        self.target_inventory_multiplier = target_inventory_multiplier

    def run(self) -> SimulationResult:
        # 1. Initialize Sub-Engines with Modifiers
        effective_capacity = self.profile.daily_capacity * self.capacity_multiplier
        effective_selling_price = self.profile.selling_price * self.price_multiplier
        effective_supplier_cost = self.profile.supplier_unit_cost * self.supplier_cost_multiplier
        effective_marketing_spend = self.profile.daily_marketing_spend * self.marketing_multiplier
        effective_target_inventory = self.profile.target_inventory * self.target_inventory_multiplier
        effective_reorder_point = self.profile.reorder_point * self.target_inventory_multiplier
        effective_repeat_prob = min(0.95, self.profile.daily_repeat_order_probability * self.repeat_rate_multiplier)

        # Initialize State Models
        initial_cust = self.profile.estimated_initial_customers
        customer_state = CustomerState(
            initial_customers=initial_cust,
        )
        inventory_state = InventoryState(
            on_hand=self.profile.starting_inventory,
            reorder_point=effective_reorder_point,
            target_inventory=effective_target_inventory,
            min_order_quantity=self.profile.min_order_quantity,
            bulk_threshold=self.profile.bulk_order_threshold,
            bulk_discount=self.profile.bulk_discount,
            base_unit_cost=effective_supplier_cost,
            lead_time_days=self.profile.procurement_lead_time_days,
            wastage_rate=self.profile.daily_wastage_rate,
        )

        acquisition_engine = AcquisitionEngine(self.rng)
        demand_engine = DemandEngine(self.rng)
        procurement_engine = ProcurementEngine(force_bulk=self.force_bulk)
        operations_engine = OperationsEngine(daily_capacity=effective_capacity)
        finance_engine = FinanceEngine(
            starting_cash=self.profile.starting_capital,
            daily_fixed_cost=self.profile.daily_fixed_cost,
            platform_commission_rate=self.profile.platform_commission_rate,
            receivables_delay_days=self.profile.receivables_delay_days,
        )

        daily_records: List[DailyMetric] = []
        recent_stockout_penalty = 1.0

        # 2. Main Daily Simulation Loop
        for day in range(1, self.days + 1):
            starting_inv = inventory_state.on_hand

            # A. Inventory Deliveries Arrive
            units_delivered = inventory_state.advance_day()

            # B. Customer Acquisition
            new_customers, eff_cac = acquisition_engine.calculate_new_customers(
                marketing_spend=effective_marketing_spend,
                base_cac=self.profile.acquisition_cost_per_customer,
                conversion_rate=self.profile.customer_conversion_rate,
            )

            # C. Customer Retention and Repeat Dynamics
            # Convert monthly retention rate (30 days) to daily retention rate
            monthly_retention = max(0.01, min(0.99, self.profile.customer_retention_rate * self.retention_multiplier))
            daily_retention_rate = monthly_retention ** (1.0 / 30.0)
            daily_churn_rate = 1.0 - daily_retention_rate

            new_orders, repeat_orders = customer_state.record_day(
                new_customers=new_customers,
                churn_rate=daily_churn_rate,
                repeat_prob=effective_repeat_prob,
                service_quality_factor=recent_stockout_penalty,
            )

            # D. Total Demand & Orders Placed
            total_orders = demand_engine.generate_orders(
                day=day,
                business_type=self.profile.business_type,
                base_demand=self.profile.base_daily_demand,
                demand_variability=self.profile.demand_variability,
                current_price=effective_selling_price,
                baseline_price=self.profile.selling_price,
                new_customer_orders=new_orders,
                repeat_customer_orders=repeat_orders,
            )

            # E. Procurement Evaluation (Triggered by Inventory Position)
            ordered_units, procurement_spend, is_bulk = procurement_engine.evaluate_procurement(
                inventory=inventory_state,
                available_cash=finance_engine.cash_balance,
            )

            # F. Production / Service Operations & Fulfillment
            (
                fulfilled_orders,
                stockout_units,
                capacity_util,
                wastage_units,
                var_opex,
                delivery_cost,
                material_cogs,
            ) = operations_engine.execute_fulfillment(
                orders_demanded=total_orders,
                inventory=inventory_state,
                variable_cost_per_unit=self.profile.variable_cost_per_unit,
                delivery_cost_per_unit=self.profile.delivery_cost_per_unit,
            )

            # Service quality feedback loop: stockouts degrade customer retention
            stockout_occurred = stockout_units > 0
            if stockout_occurred:
                recent_stockout_penalty = max(0.65, recent_stockout_penalty - 0.05)
            else:
                recent_stockout_penalty = min(1.0, recent_stockout_penalty + 0.02)

            # G. Accounting & Cash Flow Settlement
            (
                revenue,
                cogs,
                plat_comm,
                fixed_oh,
                total_cost,
                profit,
                start_cash,
                end_cash,
                cash_in,
                cash_out,
            ) = finance_engine.process_daily_finance(
                fulfilled_orders=fulfilled_orders,
                selling_price=effective_selling_price,
                unit_material_cost=inventory_state.current_unit_cost,
                variable_operating_cost=var_opex,
                delivery_cost=delivery_cost,
                marketing_spend=effective_marketing_spend,
                procurement_cash_outflow=procurement_spend,
                actual_cogs=material_cogs,
            )

            # Record Daily Metric
            metric = DailyMetric(
                day=day,
                gross_demand=float(total_orders),
                orders_placed=total_orders,
                orders_fulfilled=fulfilled_orders,
                orders_stockout=stockout_units,
                production_capacity=effective_capacity,
                capacity_utilization=capacity_util,
                starting_inventory=starting_inv,
                ending_inventory=inventory_state.on_hand,
                procurement_units_ordered=ordered_units,
                procurement_units_delivered=units_delivered,
                procurement_spend=procurement_spend,
                wastage_units=wastage_units,
                revenue=revenue,
                cogs=cogs,
                variable_operating_cost=var_opex,
                delivery_cost=delivery_cost,
                platform_commission=plat_comm,
                marketing_spend=effective_marketing_spend,
                fixed_overhead=fixed_oh,
                total_cost=total_cost,
                daily_profit=profit,
                starting_cash=start_cash,
                ending_cash=end_cash,
                cash_inflow=cash_in,
                cash_outflow=cash_out,
                new_customers_acquired=new_customers,
                active_customers=int(customer_state.active_customer_pool),
                repeat_orders=repeat_orders,
                stockout_occurred=stockout_occurred,
                initial_customers=initial_cust,
            )
            daily_records.append(metric)

        return SimulationResult(
            business_type=self.profile.business_type,
            display_name=self.profile.display_name,
            simulation_days=self.days,
            seed=self.seed,
            daily_records=daily_records,
        )


def load_business_profiles(path: str = "data/business_profiles.json") -> Dict[str, BusinessProfile]:
    if not os.path.exists(path):
        # Fallback to absolute or relative directory
        alt_path = os.path.join(os.path.dirname(__file__), "..", "data", "business_profiles.json")
        if os.path.exists(alt_path):
            path = alt_path
        else:
            raise FileNotFoundError(f"Could not locate business profiles at {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profiles = {}
    for key, val in data["profiles"].items():
        profiles[key] = BusinessProfile.from_dict(val)
    return profiles


def print_simulation_report(res: SimulationResult):
    s = res.to_summary_dict()
    print("\n" + "=" * 65)
    print(f" SIMULATION RESULTS: {s['display_name'].upper()}")
    print("=" * 65)
    print(f" Simulation Horizon : {s['simulation_days']} Days (Random Seed: {s['seed']})")
    print("-" * 65)
    print(f" Total Revenue      : Rs.{s['total_revenue']:,.2f}")
    print(f" Total Costs        : Rs.{s['total_cost']:,.2f}")
    print(f" Net Profit         : Rs.{s['net_profit']:,.2f}  {'[PROFITABLE]' if s['net_profit'] >= 0 else '[LOSS]'}")
    print(f" Operating Cash Flow: Rs.{s['operating_cash_flow']:,.2f}")
    print(f" Starting Cash      : Rs.{s['starting_cash']:,.2f}")
    print(f" Ending Cash        : Rs.{s['ending_cash']:,.2f}")
    print(f" Minimum Cash Point : Rs.{s['min_cash_balance']:,.2f}  {'[LIQUIDITY CRUNCH!]' if s['min_cash_balance'] < 2000 else '[HEALTHY]'}")
    print("-" * 65)
    print(f" Total Customer Orders   : {s['total_demand_orders']:,}")
    print(f" Fulfilled Orders        : {s['total_fulfilled_orders']:,} ({s['fulfillment_rate_pct']}%)")
    print(f" Stockout Days           : {s['total_stockout_days']} / {s['simulation_days']} Days")
    print(f" Total Inventory Wastage : {s['total_wastage_units']:,.1f} units")
    print(f" Average Daily Inventory : {s['average_inventory']:,.1f} units (Peak: {s['max_inventory']:,.1f})")
    print("-" * 65)
    print(f" Initial Customers       : {s['initial_customers']}")
    print(f" Customers Acquired      : {s['total_customers_acquired']} (CAC: Rs.{s['customer_acquisition_cost']:,.2f})")
    print(f" Total Customer Base     : {s['total_customer_base']} customers")
    print(f" Active Customer Base    : {s['ending_active_customers']} customers")
    print(f" Repeat Orders Generated : {s['total_repeat_orders']:,}")
    print(f" Avg Capacity Utilization: {s['average_capacity_utilization_pct']}%")
    print(f" Marketing ROI (Profit/M): {s['marketing_roi']}x")
    print("=" * 65 + "\n")


def run_cli():
    profiles = load_business_profiles()
    keys = list(profiles.keys())

    print("\n" + "=" * 60)
    print(" INDIAN SMALL BUSINESS VALUE-CHAIN SIMULATOR (CLI)")
    print("=" * 60)
    print("Select a Business Category to Simulate:\n")
    for idx, k in enumerate(keys, 1):
        print(f"  [{idx:2d}] {profiles[k].display_name}")

    try:
        choice = input("\nEnter choice (1-10) [Default: 2 (Home Bakery)]: ").strip()
        selected_idx = int(choice) - 1 if choice else 1
        if selected_idx < 0 or selected_idx >= len(keys):
            selected_idx = 1
    except ValueError:
        selected_idx = 1

    profile_key = keys[selected_idx]
    profile = profiles[profile_key]
    print(f"\nSelected: {profile.display_name}")
    print(f"Description: {profile.description}")

    # Prompt days & seed
    days_input = input("Enter simulation horizon in days [Default: 90]: ").strip()
    days = int(days_input) if days_input.isdigit() else 90

    seed_input = input("Enter random seed for reproducibility [Default: 42]: ").strip()
    seed = int(seed_input) if seed_input.isdigit() else 42

    print(f"\nRunning {days}-day simulation with seed {seed}...")
    sim = BusinessSimulator(profile=profile, days=days, seed=seed)
    result = sim.run()
    print_simulation_report(result)


if __name__ == "__main__":
    run_cli()
