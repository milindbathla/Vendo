# Inventory & Procurement Specialist Agent

A standalone, deterministic Python agent for the **Business MCP Server** project operating against the seeded SQLite database for **Maa Ki Rasoi Cloud Kitchen**.

---

## Capabilities & Tools

1. **`analyze_inventory(planning_date=None, demand_scenario=None)`**
   - Translates forecasted tiffin demand into stock requirements via `recipe_bom` with policy safety stock buffer (10%).
   - Identifies acute stockouts (`OIL-SUN-1L` shortfall: 0.718L, `CONT-750` shortfall: 14 pcs) vs items that are merely below reorder point (`ATTA-10`, `DAL-MOONG`).

2. **`assess_restock_need(planning_date=None, demand_scenario=None)`**
   - Classifies restock urgency into `CRITICAL` (immediate stockout by tomorrow's shift) vs `HIGH` (projected below safety threshold).
   - Assigns operational deadlines (cooking ingredients by 09:00, packaging by 11:00).

3. **`find_procurement_options(target_items=None, required_by_date=None, urgency=None, budget=None)`**
   - Queries `catalogue`, `suppliers`, and `supplier_inventory_info`.
   - Computes integer pack requirements, delivery fees, and free-delivery thresholds (e.g. Sharma General Traders free delivery for subtotal ≥ Rs 500).
   - Filters out late arrivals (Gupta Oil arrives 2026-10-12) and stockouts (Sharma is out of stock for oil).

4. **`optimize_procurement_plan(target_items=None, planning_date=None, strategy_preference=None)`**
   - Evaluates procurement options against the minimum cash buffer (Rs 5,000) using `v_cash_headroom` and `v_plan_cost`.
   - Selects `Recommended Optimal Plan` (Cost: Rs 1,675, leaves Rs 5,225 cash balance, buffer compliant).
   - Rejects `All Fast Emergency Plan` because its Rs 2,217 cost leaves Rs 4,683 (< Rs 5,000 buffer).

5. **`create_purchase_plan(plan_lines, plan_name=None, strategy=None)`**
   - Validates catalogue lines and drafts a plan in `purchase_plans` (`status='draft'`).
   - Generates an approval token in `approvals` with a 2-hour expiration window.
   - Records an entry in `audit_log` without altering inventory or cash balances.

6. **`execute_purchase(plan_id, approval_token)`**
   - Validates approval token validity, token reuse, expiration, and cash buffer sufficiency.
   - Executes atomically in a single database transaction: marks plan `executed`, marks token `used=1`, creates `simulated_orders` record, and writes `audit_log`.
   - **Idempotent**: Calling a second time succeeds with an idempotent confirmation without duplicating simulated orders.
   - **Invariants preserved**: `inventory_stock` and `purchase_history` remain unchanged until actual physical receipt and payment.

---

## Directory Layout

```
inventory_procurement_agent/
├── data/
│   └── demo.db                    # Seeded demo database
├── src/
│   └── inventory_procurement/
│       ├── __init__.py            # Package exports
│       ├── agent.py               # InventoryProcurementAgent implementation
│       ├── config.py              # Database path resolution
│       ├── db.py                  # Parameterized SQLite connector & transactions
│       ├── engine.py              # Deterministic calculations
│       ├── models.py              # Typed dataclass input/output models
│       └── repository.py          # Parameterized SQL queries & writes
├── tests/
│   └── test_inventory_procurement.py # 7 unit & integration tests
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

from inventory_procurement import InventoryProcurementAgent, resolve_db_path

# Initialize agent
agent = InventoryProcurementAgent.from_db_path(resolve_db_path())

# 1. Analyze inventory shortfalls
inv = agent.analyze_inventory()
print(f"Shortfalls: {inv.shortfall_items_count} | Below Reorder: {inv.below_reorder_items_count}")

# 2. Assess restock needs
restock = agent.assess_restock_need()
for need in restock.critical_shortfalls:
    print(f"CRITICAL: {need.item_name} (Need: {need.needed_qty} {need.unit} by {need.needed_by})")

# 3. Optimize procurement plan
opt = agent.optimize_procurement_plan()
rec = opt.recommended_plan
print(f"Plan: {rec.plan_name} (Cost: Rs {rec.total_cost}, Buffer Compliant: {rec.buffer_compliant})")

# 4. Draft purchase plan & get approval token
draft = agent.create_purchase_plan(
    plan_lines=[
        {"supplier_id": "SUP-04", "item_id": "OIL-SUN-1L", "pack_qty": 2},
        {"supplier_id": "SUP-02", "item_id": "CONT-750", "pack_qty": 2},
    ]
)
print(f"Drafted Plan ID: {draft.plan_id} | Token: {draft.approval_token}")

# 5. Atomically execute purchase
exec_res = agent.execute_purchase(plan_id=draft.plan_id, approval_token=draft.approval_token)
print(f"Success: {exec_res.success} | Status: {exec_res.status} | Audit ID: {exec_res.audit_log_id}")
```

