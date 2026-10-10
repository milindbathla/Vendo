"""
Scenario and What-If Engine
===========================
Executes multi-scenario simulations, computes comparative KPIs, and traces
causal decision propagation through the small-business value chain.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from src.models.business import BusinessProfile
from src.models.simulation import SimulationResult
from src.simulator import BusinessSimulator


@dataclass
class ScenarioConfig:
    scenario_id: str
    name: str
    description: str
    causal_chain: str
    marketing_multiplier: float = 1.0
    price_multiplier: float = 1.0
    capacity_multiplier: float = 1.0
    supplier_cost_multiplier: float = 1.0
    repeat_rate_multiplier: float = 1.0
    retention_multiplier: float = 1.0
    force_bulk: Optional[bool] = None
    target_inventory_multiplier: float = 1.0


class ScenarioEngine:
    def __init__(self, profile: BusinessProfile):
        self.profile = profile

    @staticmethod
    def get_default_scenarios() -> List[ScenarioConfig]:
        return [
            ScenarioConfig(
                scenario_id="scenario_a_baseline",
                name="A: Baseline Strategy",
                description="Status quo business operations with standard parameters.",
                causal_chain="Baseline operations -> Normal demand -> Standard inventory turnover -> Baseline profit.",
            ),
            ScenarioConfig(
                scenario_id="scenario_b_marketing_boost",
                name="B: +30% Marketing Spend",
                description="Aggressively expand customer acquisition spend by 30%.",
                marketing_multiplier=1.30,
                causal_chain=(
                    "Marketing +30% -> More reach -> More new customers -> Higher demand -> "
                    "Inventory pressure -> Earlier procurement -> Potential capacity bottleneck -> "
                    "Higher revenue if capacity holds, or stockouts if inventory lags."
                ),
            ),
            ScenarioConfig(
                scenario_id="scenario_c_bulk_procurement",
                name="C: Forced Bulk Procurement",
                description="Order in larger batches to unlock wholesale supplier discounts.",
                force_bulk=True,
                target_inventory_multiplier=1.5,
                causal_chain=(
                    "Bulk procurement -> High immediate cash outflow -> Lower unit material cost -> "
                    "Higher inventory on hand -> Lower short-term cash liquidity -> "
                    "Improved gross margins over time if working capital sustains."
                ),
            ),
            ScenarioConfig(
                scenario_id="scenario_d_supplier_shock",
                name="D: Supplier Price Shock (+15%)",
                description="Raw materials inflation: supplier unit costs rise by 15%.",
                supplier_cost_multiplier=1.15,
                causal_chain=(
                    "Supplier cost +15% -> Higher procurement outflow per batch -> "
                    "Compressed gross margin -> Decreased net profit -> Faster cash depletion."
                ),
            ),
            ScenarioConfig(
                scenario_id="scenario_e_price_reduction",
                name="E: Price Cut (-10%)",
                description="Discount selling price by 10% to stimulate price-elastic demand.",
                price_multiplier=0.90,
                causal_chain=(
                    "Price -10% -> Elastic demand lift -> More orders demanded -> "
                    "Higher capacity utilization -> Lower revenue per unit -> "
                    "Profit increases only if volume surge outweighs margin compression."
                ),
            ),
            ScenarioConfig(
                scenario_id="scenario_f_retention_focus",
                name="F: Customer Retention Focus (+20%)",
                description="Improve service quality, loyalty perks, and follow-ups to raise repeat orders.",
                repeat_rate_multiplier=1.20,
                causal_chain=(
                    "Higher retention -> More organic repeat orders -> Lower reliance on marketing CAC -> "
                    "Compounding customer base -> Stable demand -> Higher cumulative profit."
                ),
            ),
            ScenarioConfig(
                scenario_id="scenario_g_capacity_expansion",
                name="G: Capacity Expansion (+30%)",
                description="Add cooking burners / work tables / staff to raise daily throughput ceiling by 30%.",
                capacity_multiplier=1.30,
                causal_chain=(
                    "Capacity +30% -> Eliminates fulfillment bottlenecks during peak demand -> "
                    "Fulfills spikes without stockout -> Higher revenue capture during peak days."
                ),
            ),
            ScenarioConfig(
                scenario_id="scenario_h_lean_cash_preservation",
                name="H: Lean Inventory (Preserve Cash)",
                description="Reduce inventory reorder targets by 30% to conserve liquid working capital.",
                target_inventory_multiplier=0.70,
                causal_chain=(
                    "Lower inventory targets -> Smaller procurement checks -> Conserves cash buffer -> "
                    "Higher vulnerability to stockouts during demand spikes -> Lower wastage."
                ),
            ),
        ]

    def run_scenario(
        self,
        scenario: ScenarioConfig,
        days: int = 90,
        seed: int = 42,
    ) -> SimulationResult:
        sim = BusinessSimulator(
            profile=self.profile,
            days=days,
            seed=seed,
            marketing_multiplier=scenario.marketing_multiplier,
            price_multiplier=scenario.price_multiplier,
            capacity_multiplier=scenario.capacity_multiplier,
            supplier_cost_multiplier=scenario.supplier_cost_multiplier,
            repeat_rate_multiplier=scenario.repeat_rate_multiplier,
            retention_multiplier=scenario.retention_multiplier,
            force_bulk=scenario.force_bulk,
            target_inventory_multiplier=scenario.target_inventory_multiplier,
        )
        return sim.run()

    def run_all(
        self,
        scenarios: Optional[List[ScenarioConfig]] = None,
        days: int = 90,
        seed: int = 42,
    ) -> Dict[str, SimulationResult]:
        if scenarios is None:
            scenarios = self.get_default_scenarios()

        results = {}
        for sc in scenarios:
            results[sc.scenario_id] = self.run_scenario(sc, days=days, seed=seed)
        return results

    @staticmethod
    def format_comparison_table(
        scenarios: List[ScenarioConfig],
        results: Dict[str, SimulationResult],
    ) -> str:
        """
        Formats a clean, aligned terminal comparison table of key KPIs.
        """
        header = (
            f"{'Scenario Name':<28} | {'Revenue (Rs)':<13} | {'Profit (Rs)':<13} | "
            f"{'End Cash (Rs)':<13} | {'Fulfill %':<10} | {'Stockouts':<10} | {'CAC (Rs)':<8}"
        )
        sep = "-" * len(header)
        lines = [sep, header, sep]

        baseline_res = results.get(scenarios[0].scenario_id) if scenarios else None
        base_profit = baseline_res.net_profit if baseline_res else 1.0

        for sc in scenarios:
            res = results.get(sc.scenario_id)
            if not res:
                continue
            s = res.to_summary_dict()
            diff_profit = s["net_profit"] - base_profit
            sign = "+" if diff_profit >= 0 else ""
            line = (
                f"{sc.name:<28} | "
                f"Rs.{s['total_revenue']:>8,.0f} | "
                f"Rs.{s['net_profit']:>8,.0f} | "
                f"Rs.{s['ending_cash']:>8,.0f} | "
                f"{s['fulfillment_rate_pct']:>8.1f}% | "
                f"{s['total_stockout_days']:>7d}d | "
                f"Rs.{s['customer_acquisition_cost']:>5.1f}"
            )
            lines.append(line)
        lines.append(sep)
        return "\n".join(lines)


if __name__ == "__main__":
    from src.simulator import load_business_profiles
    profiles = load_business_profiles()
    engine = ScenarioEngine(profiles["home_bakery"])
    scenarios = engine.get_default_scenarios()
    results = engine.run_all(scenarios=scenarios, days=90, seed=42)
    print("\nSCENARIO ENGINE DEMONSTRATION — HOME BAKERY (90 Days, Seed 42):\n")
    print(engine.format_comparison_table(scenarios, results))
