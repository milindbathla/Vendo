"""
Full Demo Script: Runs Baseline, What-If Scenarios, and generates dashboard plots.
"""
from src.simulator import BusinessSimulator, load_business_profiles, print_simulation_report
from src.scenarios.scenario_engine import ScenarioEngine
from src.visualizer import plot_simulation_dashboard, plot_scenario_comparison

def run_full_demo():
    print("\n" + "=" * 70)
    print(" EXECUTING VALUE-CHAIN SIMULATOR & SCENARIO ENGINE DEMO")
    print("=" * 70)

    # 1. Load Profile
    profiles = load_business_profiles()
    profile = profiles["home_bakery"]
    print(f"Target Business: {profile.display_name}")

    # 2. Run Baseline 90-Day Simulation
    sim = BusinessSimulator(profile=profile, days=90, seed=42)
    baseline_result = sim.run()
    print_simulation_report(baseline_result)

    # 3. Generate Visual Dashboard Plot
    plot_path = plot_simulation_dashboard(baseline_result, "results/simulation_dashboard.png")
    print(f"[OK] Generated Simulation Dashboard Plot: {plot_path}")

    # 4. Run Multi-Scenario What-If Analysis
    engine = ScenarioEngine(profile=profile)
    scenarios = engine.get_default_scenarios()
    scenario_results = engine.run_all(scenarios=scenarios, days=90, seed=42)

    print("\n" + "=" * 70)
    print(" SCENARIO WHAT-IF COMPARISON RESULTS (90 DAYS, SEED 42)")
    print("=" * 70)
    print(engine.format_comparison_table(scenarios, scenario_results))

    # 5. Generate Scenario Comparison Plot
    comp_path = plot_scenario_comparison(scenarios, scenario_results, "results/scenario_comparison.png")
    print(f"[OK] Generated Scenario Comparison Bar Chart: {comp_path}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    run_full_demo()
