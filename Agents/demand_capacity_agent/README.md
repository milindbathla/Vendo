# Demand & Capacity Specialist Agent

A standalone, deterministic Python agent for the **Business MCP Server** project operating against the seeded SQLite database for **Maa Ki Rasoi Cloud Kitchen**.

---

## Capabilities & Tools

1. **`forecast_demand(start_date=None, end_date=None, scenario=None)`**
   - Retrieves demand forecasts, confidence intervals, demand driver context (weekday, holidays, festivals, weather), and confirmed order commitments.
   - Dynamically reads planning dates from `meta` (`tomorrow_date: 2026-10-11`).
   - Flags missing dates explicitly as `status="unavailable"` without inventing data.

2. **`analyze_demand_patterns(date=None, start_date=None, end_date=None)`**
   - Analyzes order history across 2,200+ historical records.
   - Evaluates weekday distributions, subscription vs. one-off order mix, and customer retention metrics without claiming causal relationships.

3. **`get_capacity_status(date=None)`**
   - Evaluates daily kitchen production limits (40 meals, 6.0 cook hours) vs committed orders.
   - Analyzes delivery slot capacities and booked units across all delivery windows.
   - Identifies saturated delivery slots and tightest operational constraints.

4. **`simulate_additional_demand(additional_units, date=None, delivery_slot_id=None, slot_allocation_preference=None)`**
   - Read-only feasibility simulation.
   - Translates simulated meals into raw stock requirements via `recipe_bom` and applies the `safety_stock_pct` (10%) policy.
   - Detects binding constraints: kitchen production capacity, delivery slots, or inventory stockouts.

---

## Directory Layout

```
demand_capacity_agent/
├── data/
│   └── demo.db              # Seeded demo database
├── src/
│   └── demand_capacity/
│       ├── __init__.py      # Package exports
│       ├── agent.py         # DemandCapacityAgent implementation
│       ├── config.py        # Database path resolution
│       ├── db.py            # Parameterized SQLite connector
│       ├── engine.py        # Deterministic calculations
│       ├── models.py        # Typed dataclass input/output models
│       └── repository.py    # Parameterized SQL queries
├── tests/
│   └── test_demand_capacity.py # 9 unit & integration tests
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Quickstart & Local Execution

### 1. Run Unit Tests

```bash
python3 -m unittest discover tests -v
```

### 2. Python Usage Example

```python
import sys
sys.path.insert(0, "src")

from demand_capacity import DemandCapacityAgent, resolve_db_path

# Initialize agent
agent = DemandCapacityAgent.from_db_path(resolve_db_path())

# 1. Forecast tomorrow's demand
forecast = agent.forecast_demand()
print(f"Planning Date: {forecast.planning_date}")
print(f"Forecast: {forecast.total_forecast_units} meals | Confirmed: {forecast.total_confirmed_units} meals")

# 2. Check kitchen and delivery slot capacity
capacity = agent.get_capacity_status()
print(f"Production Remaining: {capacity.remaining_production_capacity} meals")
print(f"Delivery Slots Free: {capacity.total_slot_free} units")

# 3. Simulate adding 5 additional meals
sim = agent.simulate_additional_demand(additional_units=5)
print(f"Feasible: {sim.feasible} | Binding Constraint: {sim.binding_constraint}")
```

