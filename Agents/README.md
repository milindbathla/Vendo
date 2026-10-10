# Alexa Business Autopilot: Specialist Agents

This directory contains the specialist agents that compose **Alexa Business Autopilot**.

## Available Agents

### 1. [Data Analytics Agent (`data_analytics_agent`)](./data_analytics_agent/README.md)
The combined **Business Context Agent + Business Analytics Agent** for Indian owner-operated cloud kitchens.
- **Morning briefing & cash position:** Real-time liquidity, buffer headroom, and operational load.
- **Tomorrow's prep alerts:** Shortfall detection, booking load, and delivery slot capacity.
- **Financial performance analytics:** P&L, sales trends, day-of-week profiles, and anomaly detection.
- **Unit economics & breakeven:** Contribution margins, bottom-up COGS, and daily breakeven calculations.
- **Supplier cost trends:** Inflation tracking and per-meal ingredient cost impact.
- **Memory & policy management:** Authorizer-protected business memory with verified record conflict resolution.

See [`data_analytics_agent/README.md`](./data_analytics_agent/README.md) for tool contracts, CLI usage, and test benchmarks.

### 2. [Demand & Capacity Agent (`demand_capacity_agent`)](./demand_capacity_agent/README.md)
The **Demand Forecasting & Operating Capacity Specialist Agent**.
- **Demand forecasting:** Date-bounded meal forecast units with confidence bounds, method attribution, demand driver context (festivals, weather, holidays), and confirmed/tentative order distinction.
- **Historical pattern analysis:** 2,200+ historical orders categorized by weekday distribution, subscription vs one-off mix, and customer retention metrics.
- **Capacity & delivery status:** Real-time production capacity limits (40 meals/day), cook hours, and per-delivery-slot utilization.
- **Demand simulation:** Read-only feasibility analysis evaluating production capacity, delivery slots, BOM ingredient requirements, and financial headroom.

See [`demand_capacity_agent/README.md`](./demand_capacity_agent/README.md) for tool contracts, usage examples, and test suite.

### 3. [Inventory & Procurement Agent (`inventory_procurement_agent`)](./inventory_procurement_agent/README.md)
The **Inventory Analysis & Procurement Specialist Agent**.
- **Inventory shortfall analysis:** Recipe BOM stock explosion identifying acute stockouts vs below-reorder thresholds.
- **Restock need assessment:** Urgency categorization (`CRITICAL` vs `HIGH`), needed quantities, and production shift deadlines (cooking start 09:00, packing start 11:00).
- **Procurement options & catalogue:** Supplier pricing, pack size rounding, delivery fees, free-delivery thresholds, cutoffs, and arrival feasibility.
- **Cash-buffer compliant plan optimization:** Selects lowest-cost procurement strategies while strictly enforcing the mandatory Rs 5,000 cash buffer.
- **Two-phase purchase planning & execution:** Creates draft purchase plans with cryptographic approval tokens, and performs atomic, idempotent execution into simulated orders with audit logging.

See [`inventory_procurement_agent/README.md`](./inventory_procurement_agent/README.md) for tool contracts, approval flow, and test suite.
