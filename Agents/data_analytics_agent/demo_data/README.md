# Alexa Business Autopilot: Demo Database

Deterministic, self-verifying synthetic test database for **Alexa Business Autopilot**, a voice-first business operating agent for Indian owner-operated small enterprises.

---

## 1. Context & Business Archetype

- **Business Name**: Maa Ki Rasoi Cloud Kitchen
- **Location**: Kakadeo, Kanpur, Uttar Pradesh (Pin: 208025)
- **Archetype**: Cloud Kitchen / Daily Tiffin Delivery Service
- **Menu Configuration**: Single hero menu item — **Standard Veg Tiffin**
  - **One-off price**: ₹90 / meal
  - **Subscriber price**: ₹85 / meal
- **Frozen Clock**: `as_of = '2026-10-10T19:10:00+05:30'` (Saturday evening).
  - "Tomorrow" = `2026-10-11` (Sunday).
  - The frozen clock is stored in `meta(key, value)` and used by all views and tools. The system clock is never accessed.
- **Currency & Taxation**: All amounts in INR (₹). Catalogue and item prices are GST-inclusive.
- **Data Integrity**: All person names, phone numbers (`+91 XXXXXX4821`), and GSTINs (`09ZZZZZ9999Z1Z5`) are synthetic.

---

## 2. Directory Structure

```text
demo_data/
  ├── schema.sql              # Relational schema (DDL), PK/FK/CHECK constraints, performance indexes
  ├── seed_anchor.sql         # Ground-truth exact anchor rows for headline demo scenario
  ├── generate_bulk.py        # Seeded generator (seed=42) producing 90 days of operational volume
  ├── seed_bulk.sql           # Generated bulk dataset (committed)
  ├── views.sql               # Core decision views (shortfall, cash headroom, plan costs)
  ├── tool_queries.sql        # Parameterized tool queries for the Business MCP server
  ├── verify_demo.sql         # Invariant assertions A1..A16 returning (id, expected, actual, status)
  ├── build_db.py             # Master build & verification script (exits non-zero on any failure)
  ├── data_dictionary.md      # Mapping of handwritten notes to schema + table specifications
  ├── README.md               # Architecture documentation, run instructions, and backend guide
  └── fixtures/
      ├── invoice_clean.json     # Extracted JSON for Gupta Oil Agency (zero discrepancies)
      ├── invoice_mismatch.json  # Extracted JSON for Packaging Mart (+20 pcs, 28% vs 18% GST)
      ├── make_invoices.py       # Standalone PDF generator (pure Python + reportlab fallback)
      ├── INV-GUPTA-0912.pdf     # Rendered PDF fixture for clean invoice
      └── INV-PKG-0245.pdf       # Rendered PDF fixture for discrepant invoice
```

---

## 3. Key Invariants & Decision Loop Results

Building the database verifies the headline decision loop across all 16 invariants:

| Assertion | Invariant Description | Expected / Actual Result | Status |
|---|---|---|---|
| **A1** | Tomorrow confirmed units & slot split | 20 confirmed units (split 6/8/4/2 across 4 slots); exactly 2 afternoon slots with free capacity (6 & 8) | **PASS** |
| **A2** | Effective meal forecast for tomorrow | 23 units forecast × 1.10 safety factor = **25.3 units** | **PASS** |
| **A3** | Ingredient/packaging shortfall tomorrow | EXACTLY **OIL-SUN-1L: 0.718 L** and **CONT-750: 14.0 pcs**; all other items have stock >= requirement | **PASS** |
| **A4** | Catalogue items below reorder point | EXACTLY **{ATTA-10, CONT-750, DAL-MOONG, OIL-SUN-1L}** | **PASS** |
| **A5** | Supplier delivery feasibility for oil | Regular suppliers cannot deliver before 09:00 cooking start; **only QuickKart Now (SUP-04) feasible** | **PASS** |
| **A6** | Packaging supplier delivery feasibility | Packaging Mart (SUP-02) cutoff 20:00, order placed at 19:10 arrives by 07:00 (before 11:00 packing) | **PASS** |
| **A7** | Recomputed reference plan costs | `REF-RECOMMENDED` = **₹1,675**, `REF-ALL-FAST` = **₹2,217**, `REF-OIL-CONT-FAST` = **₹2,077** | **PASS** |
| **A8** | Cash headroom over mandatory buffer | Min projected cash ₹6,900 − buffer ₹5,000 = **₹1,900 headroom** | **PASS** |
| **A9** | Minimum cash balance after procurement | `RECOMMENDED` = **₹5,225** (>= buffer); `ALL-FAST` = **₹4,683** (< buffer); `OIL-CONT-FAST` = **₹4,823** (< buffer) | **PASS** |
| **A10** | Supplier accounts payable reconciliation | `upcoming_payments` Sharma dues (₹4,200) equals open balance in `supplier_business_records` | **PASS** |
| **A11** | Customer metrics rollup consistency | Metrics match live active customers: **96 active**, **62 recurring**, **64.6% recurring ratio** | **PASS** |
| **A12** | Multimodal document reconciliation | Clean invoice has 0 discrepancies; mismatch invoice has exactly 2 (+20 pcs, 28% GST, excess ₹113.92) | **PASS** |
| **A13** | Business memory conflict handling | Deliberate conflict detected: verified invoice ₹146 vs owner verbal statement ₹135 for Gupta oil | **PASS** |
| **A14** | Database constraints & slot integrity | Zero foreign key errors, zero negative stock, no overbooked delivery slots | **PASS** |
| **A15** | Financial ledger & MTD consistency | Daily order sums match daily revenue within 1%; October MTD rolls up directly from daily metrics | **PASS** |
| **A16** | Deterministic byte reproducibility | Rebuilding from clean checkout produces identical SHA256 SQL dump hash | **PASS** |

---

## 4. Engineering Assumptions

1. **Kitchen Deadlines**:
   - Cooking starts daily at **09:00**. All cooking ingredients (Oil, Atta, Dal, Rice, Spices) must be on-site by 09:00.
   - Packing starts daily at **11:00**. Packaging materials (Containers, Bags) must be on-site by 11:00.
2. **Supplier Cutoffs & Schedules**:
   - **SUP-01 (Sharma General Traders)**: Wholesale grocery. Order cutoff 20:00, arrives next day at 10:00 (too late for 09:00 cooking). Free delivery above ₹500, else ₹40.
   - **SUP-02 (Kanpur Packaging Mart)**: Packaging specialist. Order cutoff 20:00, arrives next day at 07:00 (in time for 11:00 packing). Delivery fee ₹30.
   - **SUP-03 (Gupta Oil Agency)**: Wholesale oil distributor. Fixed alternate-day route; next delivery is Monday 2026-10-12 at 15:00 (too late for Sunday production).
   - **SUP-04 (QuickKart Now)**: Simulated instant dark-store actuator. ETA 25–45 minutes, flat delivery fee ₹49 (free above ₹2,500).
3. **Discrete vs. Continuous Unit Handling**:
   - Discrete items (`pcs`, such as containers and carry bags) use ceiling arithmetic `CEIL(units × BOM)` to avoid fractional packaging.
   - Continuous items (`L`, `kg`) preserve fractional precision to 3 decimal places.
4. **Liquidity Buffer Rule**:
   - Operating policy dictates that projected bank cash must never drop below **₹5,000**.
   - Procurement plans are evaluated assuming payment at time of order (2026-10-10 evening), reducing projected balances across the planning horizon.
5. **Document Verification vs. Extraction**:
   - In accordance with hackathon guidelines, document parsing captures OCR extraction confidence (e.g. 0.93 or 0.96). No table asserts that an unverified document is authentic or legally genuine without authoritative source confirmation.
6. **PostgreSQL Portability**:
   - Data types are restricted to standard `INTEGER`, `REAL`, and `TEXT`.
   - SQLite-specific functions are avoided in favor of standard SQL (`CASE WHEN`, `ROUND`, `GROUP_CONCAT` / `STRING_AGG`, window functions).
   - Differences when porting to PostgreSQL: replace `PRAGMA foreign_keys = ON;` with native constraints, use `NUMERIC` for exact currency, and use `STRING_AGG(..., ', ')` in place of `GROUP_CONCAT`.

---

## 5. How to Run & Verify

### 5.1 Build the Database (Zero to Verified)
From the project root:
```bash
python3 demo_data/build_db.py
```
This executes the build sequence:
`schema.sql` → `seed_anchor.sql` → `seed_bulk.sql` → `views.sql` → `verify_demo.sql`

Output summary:
```text
=================================================================
KEY DECISION NUMBERS & HEADLINE INVARIANTS
=================================================================
 Tomorrow's Shortfall Items:      CONT-750: 14.0 pcs, OIL-SUN-1L: 0.718 L
 Cash Headroom (6900 - 5000):     ₹1,900.00
 Minimum Cash Buffer Required:    ₹5,000.00
 Lowest Projected Cash (10-12):   ₹6,900.00
-----------------------------------------------------------------
PLAN ID              | TOTAL COST | MIN BAL AFTER |  BUFFER OK
-----------------------------------------------------------------
REF-ALL-FAST         | ₹  2217.00 | ₹     4683.00 |  NO (FAIL)
REF-OIL-CONT-FAST    | ₹  2077.00 | ₹     4823.00 |  NO (FAIL)
REF-RECOMMENDED      | ₹  1675.00 | ₹     5225.00 | YES (PASS)
=================================================================
ALL 16 ASSERTIONS PASS
Determinism Verified: SHA256 = da1c614becdc27d2b8b23c3059e58f21799af3669a2511e13764e6bbfc46fc8b
Final Database Size: 1.00 MB (Limit: < 5.0 MB)
```

### 5.2 Regenerate Bulk Data
To recreate `demo_data/seed_bulk.sql` deterministically from scratch:
```bash
python3 demo_data/generate_bulk.py
```

### 5.3 Render Document Fixtures (PDF)
To regenerate the invoice PDF files in `demo_data/fixtures/`:
```bash
python3 demo_data/fixtures/make_invoices.py
```
*(Uses pure Python standard library; ReportLab optional).*

### 5.4 Reset the Database
To reset the database cleanly:
```bash
rm -f demo_data/demo.db demo.db
python3 demo_data/build_db.py
```

---

## 6. How the Mock Backend & MCP Server Connect

The orchestrator and the Business MCP server connect directly to `demo_data/demo.db` using standard SQLite connection drivers.

### 6.1 Connection Pattern (Python / FastAPI / MCP Server)
```python
import sqlite3

DATABASE_PATH = "demo_data/demo.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Dict-like access
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
```

### 6.2 Standard Tool Result Envelope
All queries in `demo_data/tool_queries.sql` project standardized response envelope attributes:
```json
{
  "ok": 1,
  "data": [...],
  "confidence": 0.95,
  "source": "db",      // "db" | "estimate" | "simulated"
  "warnings": "..."
}
```
Rows originating from **QuickKart Now (SUP-04)** are explicitly tagged with `"source": "simulated"`.

### 6.3 Tool Query Mapping
| Tool Function | Query in `tool_queries.sql` | Key Parameters |
|---|---|---|
| `get_inventory()` | `-- :name get_inventory` | None |
| `get_cash_position()` | `-- :name get_cash_position` | None |
| `get_upcoming_payments()` | `-- :name get_upcoming_payments` | None |
| `forecast_demand(date)` | `-- :name forecast_demand` | `:date` (ISO date text) |
| `assess_restock_need()` | `-- :name assess_restock_need` | None |
| `find_procurement_options(items)` | `-- :name find_procurement_options` | `:item_id` (or NULL) |
| `analyze_purchase_affordability(plan_id, amount)` | `-- :name analyze_purchase_affordability` | `:plan_id` or `:amount` |
| `get_capacity_status(date)` | `-- :name get_capacity_status` | `:date` (ISO date text) |
| `identify_growth_opportunities(free_slots)` | `-- :name identify_growth_opportunities` | `:date` |
| `reconcile_document(doc_id)` | `-- :name reconcile_document` | `:doc_id` (`INV-PKG-0245`) |
| `get_business_memory(key)` | `-- :name get_business_memory` | `:key` |
| `analyze_business_performance(period)` | `-- :name analyze_business_performance` | `:period` |

