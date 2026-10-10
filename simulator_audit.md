# Small Business Simulator: Mathematical & Causal Audit Report

## 1. Executive Summary

This document records the audit findings, mathematical corrections, and causal validation for the **Small Business Value-Chain Simulator** tailored for Indian micro and small enterprises.

The goal of this audit and refactor was to ensure that the simulator is **mathematically sound, causally coherent, and deterministic**. All artificial double-counting, phantom pools, ungrounded demand streams, and inventory costing disconnects have been eliminated.

---

## 2. Core Value Chain Architecture

The simulator models the following end-to-end value chain:

```
Customer Acquisition (Marketing Spend, CAC, Conversion)
        ↓
Customers (Initial Base + Acquired - Churned)
        ↓
Demand / Orders (Active Base × Repeat Propensity × Seasonality × Elasticity + New Orders)
        ↓
Procurement (Inventory Position vs Reorder Point, MOQ, Bulk Discounts, Usable Cash Reserve)
        ↓
Inventory (Pipeline Lead Times, FIFO Lots, Perishable Wastage)
        ↓
Production / Operations (Throughput Ceiling, Resource Bottlenecks)
        ↓
Fulfillment (Min[Demand, Inventory, Daily Capacity])
        ↓
Revenue / Receivables (Credit Terms Delay Pipeline)
        ↓
Costs (Actual FIFO Material COGS + Fixed Overheads + Variable OPEX + Logistics + Commissions)
        ↓
Profit (Accounting Net Profit)
        ↓
Cash (Operating Cash Flow = Cash Collections - Cash Outflows)
        ↓
Retention & Future Demand (Stockout Penalty Loop -> Service Quality -> Retention Degradation)
```

---

## 3. Audit Findings & Implemented Fixes (P1–P6)

### P1: Demand Double-Counting Elimination
- **Issue:** Previously, `DemandEngine.generate_orders()` calculated an `organic_orders` stream based on `base_daily_demand` and added it to `new_customer_orders + repeat_customer_orders`. This created two parallel, disconnected sources of demand.
- **Fix:** Customer demand is now **solely driven by actual customers**:
  $$\text{Customer Orders} = \text{New Orders} + \text{Repeat Orders}$$
  $$\text{Total Daily Orders} = \text{Round}\left(\text{Customer Orders} \times \text{DOW Factor} \times \text{Price Elasticity Factor} \times (1 + \text{Noise})\right)$$
  `base_daily_demand` is now coherently used to parameterize the market baseline and seed the initial customer base ($C_0 = \frac{\text{Base Daily Demand}}{\text{Repeat Probability}}$), ensuring Day 1 demand naturally matches baseline expectations without duplicate addition.

### P2: Phantom Customer Pool Removal
- **Issue:** `CustomerState` was seeded with an unrecorded `active_customer_pool = base_daily_demand * 1.5`, while customer acquisition metrics tracked 0 initial customers.
- **Fix:** Initial customers are explicitly represented in `BusinessProfile.estimated_initial_customers`, tracked in `CustomerState.initial_customers`, and exposed in `SimulationResult.initial_customers` and `total_customer_base = initial_customers + acquired_customers`.

### P3: Bulk Procurement & Actual Inventory Lot Costing (FIFO)
- **Issue:** `FinanceEngine` previously calculated COGS as $\text{Fulfilled Orders} \times \text{base\_unit\_cost}$, ignoring bulk procurement lot discounts.
- **Fix:** Implemented `InventoryLot(quantity, unit_cost)` queue with strict FIFO consumption in `InventoryState.consume_with_cost()`.
  - When a bulk purchase arrives, units enter inventory with their discounted acquisition unit cost.
  - When units are fulfilled or wasted, they are consumed from the oldest lots first.
  - Actual FIFO lot cost is passed directly into `FinanceEngine.process_daily_finance(actual_cogs=material_cogs)`. Bulk purchasing now directly flows through to gross margin and COGS.

### P4: Cash Flow vs Accounting Profit Disconnect
- **Issue:** Profit was conflated with cash generation, and a 1-day credit delay bug caused immediate same-day collection.
- **Fix:**
  - Added explicit cash flow metrics: `operating_cash_flow = total_cash_inflow - total_cash_outflow` and `net_cash_flow = ending_cash - starting_cash`.
  - Fixed receivables pipeline sequence: matured receivables from prior days are collected before enqueuing current day's new credit receivables.
  - Credit sales correctly recognize revenue and profit today while postponing cash inflow until maturation.

### P5: Procurement Cash & Operational Timing
- **Issue:** Procurement timing and liquidity constraint checking needed verification.
- **Resolution:** Validated daily chronological ordering:
  1. Inventory deliveries arrive & advance FIFO lots
  2. Customer acquisition executes
  3. Retention & churn update customer pool
  4. Demand generation calculates total orders
  5. Procurement evaluates inventory position against available liquid cash (protecting ₹2,000 safety reserve)
  6. Operations fulfills demand up to capacity and inventory limits, computing FIFO COGS
  7. Service quality penalty updates based on stockout occurrence
  8. Finance processes collections of matured receivables, enqueues new receivables, pays OPEX and procurement, and updates liquid cash balance.

### P6: Regression & Causal Property Testing
- Added comprehensive test suite `tests/test_causal_simulator.py` covering all 11 causal properties. All 30 unit and regression tests pass.

---

## 4. Controlled Experiments Summary

| Experiment | Tested Variable | Baseline | Variant | Observed Result | Causal Validation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A: Acquisition** | Marketing Spend | $1.0\times$ Spend | $2.5\times$ Spend | Acquired: 16 $\rightarrow$ 39<br>Demand: 1,095 $\rightarrow$ 1,194<br>Revenue: +₹27,840 | **Confirmed**: Higher spend grows customer base and expands future demand. |
| **B: Retention** | Retention Multiplier | $1.0\times$ (Normal) | $0.6\times$ (Low) | Active Cust: 36 $\rightarrow$ 12<br>Repeat Orders: 1,053 $\rightarrow$ 653<br>Revenue: -₹129,600 | **Confirmed**: Churn erodes active pool, severely shrinking repeat demand. |
| **C: Bulk Procurement** | Reorder Strategy | Normal | Forced Bulk ($1.8\times$) | Avg Inv: 25.1 $\rightarrow$ 51.6<br>Wastage: 144.2 $\rightarrow$ 296.4 units | **Confirmed**: Bulk unlocks discount but increases inventory holding and spoilage risk. |
| **D: Delayed Receivables** | Credit Terms Delay | 0 Days (Cash) | 20 Days Credit | Profit: Identical (₹146,700)<br>End Cash: ₹207,727 $\rightarrow$ ₹138,977 | **Confirmed**: Credit disconnects profit from cash; cash is trapped in uncollected AR. |
| **E: Capacity Choke** | Throughput Limit | $1.0\times$ (30/day) | $0.4\times$ (12/day) | Stockout Days: 2 $\rightarrow$ 4<br>Active Cust: 36 $\rightarrow$ 20 | **Confirmed**: Capacity bottlenecks cause stockouts, degrading customer satisfaction and retention. |

---

## 5. Cross-Profile Sanity Benchmarks (90-Day Simulation, Seed 42)

| Business Profile | Revenue | Total Cost | Net Profit | Oper. Cash Flow | Ending Cash | Fulfill Rate | Stockouts | Wastage | Initial Cust | Acquired Cust | Total Cust Base |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Home Tiffin** | ₹134,900 | ₹131,940 | ₹2,960 | -₹13,983 | ₹21,017 | 92.09% | 12d | 144.2 u | 43 | 17 | 60 |
| **Home Bakery** | ₹345,920 | ₹250,566 | ₹95,354 | ₹79,165 | ₹134,165 | 98.72% | 2d | 128.2 u | 72 | 16 | 88 |
| **Cloud Kitchen** | ₹539,030 | ₹518,602 | ₹20,428 | -₹32,543 | ₹87,457 | 97.83% | 4d | 404.7 u | 200 | 51 | 251 |
| **Tailoring Boutique** | ₹326,700 | ₹180,000 | ₹146,700 | ₹137,278 | ₹197,278 | 95.19% | 5d | 21.8 u | 53 | 13 | 66 |
| **Salon Service** | ₹249,600 | ₹145,820 | ₹103,780 | ₹102,500 | ₹177,500 | 95.94% | 4d | 73.8 u | 75 | 18 | 93 |
| **Handicrafts** | ₹116,960 | ₹114,417 | ₹2,543 | -₹18,243 | ₹61,757 | 89.58% | 4d | 138.3 u | 67 | 11 | 78 |
| **Packaged Food** | ₹196,175 | ₹189,366 | ₹6,810 | -₹19,172 | ₹70,828 | 93.73% | 4d | 113.4 u | 100 | 18 | 118 |
| **Electronics Repair** | ₹389,300 | ₹240,480 | ₹148,820 | ₹137,582 | ₹232,582 | 95.82% | 4d | 22.6 u | 120 | 16 | 136 |
| **Reseller Kirana** | ₹415,288 | ₹445,720 | -₹30,432 | -₹104,850 | ₹45,150 | 95.17% | 4d | 218.0 u | 100 | 18 | 118 |
| **Small Fabrication** | ₹313,250 | ₹279,900 | ₹33,350 | -₹14,092 | ₹125,908 | 94.71% | 3d | 47.7 u | 40 | 7 | 47 |

---

## 6. Readiness for Next Architectural Stage

The deterministic core simulator is now:
1. **Mathematically & causally verified** across all components.
2. **Deterministic & reproducible** with any integer seed.
3. **Equipped with robust regression tests** covering all causal mechanics.

**Status:** The simulator is complete and ready for the subsequent architectural stage (Scenario Optimization & Engine expansion).
