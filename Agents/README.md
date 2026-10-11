# Alexa Business Autopilot: Specialist Agents

This directory contains the specialist agents that compose **Alexa Business Autopilot**.

## Available Agents

### 1. [Data Analytics Agent (`data_analytics_agent`)](data_analytics_agent/README.md)

The combined **Business Context Agent + Business Analytics Agent** for Indian owner-operated cloud kitchens.

- **Morning briefing & cash position:** Real-time liquidity, buffer headroom, and operational load.
- **Tomorrow's prep alerts:** Shortfall detection, booking load, and delivery slot capacity.
- **Financial performance analytics:** P&L, sales trends, day-of-week profiles, and anomaly detection.
- **Unit economics & breakeven:** Contribution margins, bottom-up COGS, and daily breakeven calculations.
- **Supplier cost trends:** Inflation tracking and per-meal ingredient cost impact.
- **Memory & policy management:** Authorizer-protected business memory with verified record conflict resolution.

See [`data_analytics_agent/README.md`](data_analytics_agent/README.md) for tool contracts, CLI usage, and test benchmarks.

### 2. [Demand & Capacity Agent (`demand_capacity_agent`)](demand_capacity_agent/README.md)

The **Demand Forecasting & Operating Capacity Specialist Agent**.

- **Demand forecasting:** Date-bounded meal forecast units with confidence bounds, method attribution, demand driver context (festivals, weather, holidays), and confirmed/tentative order distinction.
- **Historical pattern analysis:** 2,200+ historical orders categorized by weekday distribution, subscription vs one-off mix, and customer retention metrics.
- **Capacity & delivery status:** Real-time production capacity limits (40 meals/day), cook hours, and per-delivery-slot utilization.
- **Demand simulation:** Read-only feasibility analysis evaluating production capacity, delivery slots, BOM ingredient requirements, and financial headroom.

See [`demand_capacity_agent/README.md`](demand_capacity_agent/README.md) for tool contracts, usage examples, and test suite.

### 3. [Inventory & Procurement Agent (`inventory_procurement_agent`)](inventory_procurement_agent/README.md)

The **Inventory Analysis & Procurement Specialist Agent**.

- **Inventory shortfall analysis:** Recipe BOM stock explosion identifying acute stockouts vs below-reorder thresholds.
- **Restock need assessment:** Urgency categorization (`CRITICAL` vs `HIGH`), needed quantities, and production shift deadlines (cooking start 09:00, packing start 11:00).
- **Procurement options & catalogue:** Supplier pricing, pack size rounding, delivery fees, free-delivery thresholds, cutoffs, and arrival feasibility.
- **Cash-buffer compliant plan optimization:** Selects lowest-cost procurement strategies while strictly enforcing the mandatory Rs 5,000 cash buffer.
- **Two-phase purchase planning & execution:** Creates draft purchase plans with cryptographic approval tokens, and performs atomic, idempotent execution into simulated orders with audit logging.

See [`inventory_procurement_agent/README.md`](inventory_procurement_agent/README.md) for tool contracts, approval flow, and test suite.

### 4. [Document & Reconciliation Agent (`document_reconciliation_agent`)](document_reconciliation_agent/README.md)

The **Document Processing & Transaction Reconciliation Specialist Agent**.

- **Document data extraction:** Extracts structured business information from documents, including supplier details, invoice dates, line items, quantities, amounts, and tax breakdowns where supported by the source.
- **Invoice-to-PO reconciliation:** Intended to compare invoice details against purchase orders and goods-receipt records when the required records and database contracts are available.
- **Transaction discrepancy detection:** Identifies potential amount, quantity, tax, currency, date, supplier-identity, and duplicate-transaction mismatches, with supporting evidence where available.
- **Verification before recording:** Intended to verify transaction data and require the appropriate authorization before recording; unsupported or unverified transactions should be flagged for review rather than treated as approved.
- **Auditability and safeguards:** Designed to avoid duplicate recording, preserve traceability, treat document contents as untrusted input, and avoid claiming verification without supporting evidence.

See [`document_reconciliation_agent/README.md`](document_reconciliation_agent/README.md) for the agent's documented scope, setup instructions, and implementation details.

---

## Standalone Prototype Agents (not yet integrated)

The following two modules are **self-contained prototypes**. They run entirely
on deterministic, in-memory data, are **not wired into the MCP server or the
shared `demo.db`**, and overlap with existing logic in `src/` (`finance_agent`
mirrors `src/engine/finance.py`; `supplier_intelligence` mirrors
`src/services/supplier_simulator.py`). They are documented here for visibility
and are candidates for either consolidation into `src/` or promotion into full
`demo.db`-backed specialist agents.

- **`finance_agent/`** — cash/P&L/affordability/what-if projections (in-memory).
- **`supplier_intelligence/`** — supplier profiling, comparison, and scoring (in-memory).

---

## Agent Responsibilities

Each specialist agent focuses on a distinct business capability. Their integration should respect existing database schemas, tool contracts, authorization requirements, and audit controls. Capabilities that depend on unavailable data or integrations must be reported as unsupported or pending review rather than assumed to have succeeded.
