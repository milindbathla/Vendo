# Vendo — Your Shop. On Autopilot.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%20FastMCP-orange.svg)](https://modelcontextprotocol.io/)
[![Amazon Alexa+](https://img.shields.io/badge/Integration-Amazon%20Alexa%2B-232F3E.svg)](https://developer.amazon.com/alexa)
[![Tests Passing](https://img.shields.io/badge/Tests-455%20Passed%2C%203%20Skipped-success.svg)](#testing-and-verification)

> **Autonomous Operating & Decision Layer for Indian Micro & Small Enterprises (MSMEs)**
> Built for the **Amazon Alexa+ Developer Hackathon**.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Problem: Why Indian MSMEs Need an Autopilot](#2-the-problem-why-indian-msmes-need-an-autopilot)
3. [The Solution: How Vendo Works](#3-the-solution-how-vendo-works)
4. [System Architecture](#4-system-architecture)
5. [Alexa+ & Model Context Protocol (MCP) Integration](#5-alexa--model-context-protocol-mcp-integration)
6. [Complete MCP Tools Catalog (45 Tools)](#6-complete-mcp-tools-catalog-45-tools)
7. [AI Agent & Orchestration Engine](#7-ai-agent--orchestration-engine)
8. [Multi-Business Profile Architecture](#8-multi-business-profile-architecture)
9. [External APIs & Integration Adapters](#9-external-apis--integration-adapters)
10. [Technology Stack](#10-technology-stack)
11. [Installation & Setup](#11-installation--setup)
12. [Running the Application](#12-running-the-application)
13. [Judge's Interactive Testing Guide](#13-judges-interactive-testing-guide)
14. [Testing & Verification](#14-testing--verification)
15. [Security, Governance & Safety Rails](#15-security-governance--safety-rails)
16. [Current Limitations & Honest Disclosures](#16-current-limitations--honest-disclosures)
17. [Roadmap & Future Enhancements](#17-roadmap--future-enhancements)
18. [Authors & Project Context](#18-authors--project-context)

---

## 1. Executive Summary

**Vendo** is an autonomous operating and decision-making system designed for Indian micro, small, and medium businesses (cloud kitchens, kiranas, retail boutiques, repair services, bakeries, and catering businesses).

Small business owners in India face severe cognitive overload: juggling supplier credit cycles, ingredient inventory spoilage, unpredictable working capital, customer delivery capacity, and fragmented invoices.

Vendo bridges the physical and financial realities of the business with conversational voice intelligence:
- **Speaks the Merchant's Language:** Understands natural business queries in English, Hindi, and Hinglish via **Amazon Alexa+** and **Model Context Protocol (MCP)**.
- **Understands the Numbers:** Genuinely executes 45 registered MCP tools against live financial and operational data (cash balance, liquidity buffer, inventory stock, invoices, local demand).
- **Protects the Business:** Features a deterministic two-phase cryptographic owner approval gate. Consequential actions (supplier purchase orders, bank payments, external customer emails) are **never** executed autonomously without explicit owner confirmation.
- **Runs Everywhere:** Fully operational offline with deterministic fallback heuristics over SQLite databases, and elevates to live generative intelligence when **Google Gemini** or **Anthropic Claude** API keys are present.

---

## 2. The Problem: Why Indian MSMEs Need an Autopilot

Across India's 63+ million micro and small enterprises:
1. **Working Capital Shocks:** Over 68% of small cloud kitchens and kiranas operate without a dedicated accountant. Cash reserves are frequently depleted by sudden vendor bills or supplier payments due the same week.
2. **Invisible Stockouts & Spoilage:** Inventory is tracked on paper or memory. Kitchens run out of critical packaging or cooking oil mid-shift, while perishable materials spoil in stock.
3. **Capacity Miscalculation:** Accepting large bulk orders without cross-checking daily burner capacity or raw ingredient recipes leads to delayed deliveries and damaged customer reputation.
4. **Tool Fragmentation:** Accounting is in Zoho or Tally, payments are in Amazon Pay or UPI apps, local footfall is on Google Maps, and orders come via phone or WhatsApp. Nothing talks to each other.

---

## 3. The Solution: How Vendo Works

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MERCHANT TOUCHPOINTS                            │
│  • Voice: Amazon Alexa+ Smart Speakers & Echo Displays                 │
│  • Web Portal: Onboarding (http://127.0.0.1:8000/app/)                 │
│  • Web Assistant: Live Visual Simulator (http://127.0.0.1:8000/app/    │
│    alexa.html)                                                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Natural Voice / Text Queries
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   ALEXA+ & MCP PROTOCOL GATEWAY                        │
│  • Official Streamable FastMCP Protocol (/mcp, /sse)                   │
│  • RFC 8414 OAuth Authorization Server Metadata                        │
│  • RFC 9728 Protected Resource Metadata (Canonical /mcp)               │
│  • RFC 9207 PKCE Account Linking with Token Family Replay Protection  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Authenticated Tool Call
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             AUTOPILOT ORCHESTRATION & DECISION ENGINE                  │
│  • Intent Routing: Multi-lingual (English, Hindi, Hinglish)            │
│  • LLM Brain: Google Gemini 2.5 Flash / Claude 3.5 Sonnet              │
│  • Deterministic Safety Rails: Causal working-capital checks           │
│  • Two-Phase Owner Approval Gate: Cryptographic plan verification      │
└───────────────────┬───────────────────────────────┬────────────────────┘
                    │                               │
                    ▼                               ▼
┌──────────────────────────────────┐ ┌───────────────────────────────────┐
│     EXTERNAL ADAPTER LAYER       │ │     ENTERPRISE DATA ENGINE        │
│  • Google Places: Market density │ │  • demo.db: Canonical MSME ledger │
│  • Zoho Books: Invoices & bills  │ │  • FIFO Inventory Lot Costing     │
│  • Amazon Pay: Payments & refund │ │  • Recipe & Shortage Calculator   │
│  • Meta: Social status adapter   │ │  • AdaptiveProfileRepository      │
└──────────────────────────────────┘ └───────────────────────────────────┘
```

---

## 4. System Architecture

Vendo is engineered with a strict **separation of concerns**:
- **`frontend/`**: Zero-build pure HTML5, vanilla CSS3, and ES6 client. Renders official **Amazon Ember** typography (`AmazonEmber_W_Bd`, `AmazonEmber_W_Rg`), dark-mode MSME aesthetics, live audio visualizer pulses, and responsive layouts for desktop, tablet, and mobile.
- **`src/server/`**: FastAPI ASGI web application. Mounts the streamable HTTP/SSE FastMCP protocol server, RFC-compliant OAuth 2.1 metadata endpoints, and merchant REST APIs.
- **`src/decision/`**: Pure business decision logic. Calculates cash buffers, liquidity safety thresholds, and enforces the two-phase approval state machine.
- **`src/integrations/`**: Normalization adapters for external service providers (Google Places, Zoho Books, Amazon Pay, Meta).
- **`src/agent/`**: Adaptive multi-business orchestrator, document fact extractor, and conversational onboarding supervisor.
- **`src/services/`**: High-level domain services including `TiffinOrderService` and `SupplierCatalogueSimulator`.
- **`data/`**: Canonical relational database (`demo.db`), SQLite schema definitions, bulk seeds, and reference test queries.

---

## 5. Alexa+ & Model Context Protocol (MCP) Integration

Vendo treats the **Model Context Protocol (MCP)** as a first-class citizen, fully compliant with Amazon Alexa+ Add-on Toolkit guidelines:

### 5.1 Protocol Compliance
- **Mounted FastMCP Lifespan:** The MCP server is mounted directly into the FastAPI ASGI lifecycle at `/mcp` (Streamable HTTP) and `/sse` (Server-Sent Events).
- **RFC 8414 Authorization Server Metadata:** Advertised at `/.well-known/oauth-authorization-server` with `code` response type, `S256` PKCE challenge method, and token endpoint URLs.
- **RFC 9728 Protected Resource Metadata:** Advertised at `/.well-known/oauth-protected-resource` binding the canonical `/mcp` resource URL.
- **RFC 9207 Issuer Identification:** Injects `iss` parameters into authorization redirects to defeat OAuth mix-up attacks.
- **Alexa+ Discovery Security Contract:** Returns HTTP 401 **without** `WWW-Authenticate` response headers on unauthenticated discovery requests, satisfying Alexa+ Add-on discovery requirements.
- **Token Family Replay Attack Defense:** Refresh tokens are cryptographically random strings (`ref_...`) stored via SHA-256 hashes. Reusing an already-consumed refresh token immediately invalidates the entire token family.

---

## 6. Complete MCP Tools Catalog (45 Tools)

The Vendo MCP server programmatically registers **45 tools** across 6 functional domains:

| # | Tool Name | Scope & Purpose |
|---|---|---|
| **Core Autopilot & Operations** | | |
| 1 | `get_business_state` | Retrieves real-time cash, orders, inventory, and active merchant status. |
| 2 | `get_upcoming_orders` | Lists scheduled customer delivery orders for upcoming shifts. |
| 3 | `get_financial_position` | Returns cash in bank, minimum buffer reserve, and pending payables. |
| 4 | `get_tiffin_recipe_breakdown` | Calculates ingredient bill-of-materials for tiffin orders. |
| 5 | `get_supplier_quotes` | Fetches live supplier price quotes and delivery lead times. |
| 6 | `compare_procurement_channels`| Compares bulk wholesale vs local spot procurement options. |
| 7 | `evaluate_order_opportunity` | Multi-variable check: capacity, inventory shortage, liquidity safety. |
| 8 | `create_purchase_plan` | Prepares a proposed purchase order requiring owner sign-off. |
| 9 | `confirm_purchase_plan` | Transitions proposed plan to confirmed status via owner action. |
| 10 | `execute_purchase_plan` | Dispatches confirmed purchase order to simulated supplier. |
| **Specialist & Value Chain Tools** | | |
| 11 | `get_profitability_analysis` | Unit economics, gross margins, and contribution margins per order. |
| 12 | `forecast_cash_flow` | 7-day to 30-day causal liquidity and working capital projections. |
| 13 | `get_supplier_profile` | Supplier reliability rating, credit terms (net-7/net-15), and lead times. |
| 14 | `evaluate_supplier` | Historical reliability and fulfillment score calculation. |
| 15 | `search_nearby_competitors` | Google Places API search for competitor density and commercial radius. |
| 16 | `get_zoho_organization` | Merchant accounting organization details and base currency. |
| 17 | `get_zoho_invoices` | Read-only ledger of customer invoices and outstanding receivables. |
| 18 | `get_zoho_expenses_and_bills`| Vendor bills, operating expenses, and payment due dates. |
| 19 | `get_external_integrations_status` | Status of Google Places, Zoho Books, and Amazon Pay connections. |
| **Adaptive Onboarding & Context** | | |
| 20 | `onboard_or_chat_business` | Interactive business profile builder from conversational facts. |
| 21 | `get_adaptive_business_profile`| Fetches persisted adaptive business profile and verified facts. |
| 22 | `list_adaptive_business_profiles`| Lists all registered business entities in the merchant database. |
| 23 | `evaluate_adaptive_opportunity`| Generalized opportunity evaluator across any business archetype. |
| **Autonomous Governance & Task Engine** | | |
| 24 | `list_operational_tasks` | Operational queue of system tasks, classifications, and status. |
| 25 | `get_operational_task` | Detailed task view with audit trail and execution metadata. |
| 26 | `list_pending_approvals` | Action proposals waiting for merchant authorization. |
| 27 | `get_action_proposal` | Cryptographic proposal payload, reason, and financial impact. |
| 28 | `approve_action_proposal` | Authenticated approval signing with owner verification. |
| 29 | `reject_action_proposal` | Rejection of proposed action with optional feedback reason. |
| 30 | `dispatch_action` | Execution dispatcher verifying SHA-256 payload integrity. |
| 31 | `list_execution_history` | Historical audit log of all executed and simulated actions. |
| 32 | `reconcile_uncertain_execution`| Idempotency reconciler for recovering ambiguous network outcomes. |
| 33 | `process_incoming_email` | Autonomous parser for vendor emails, invoices, and purchase requests. |
| **Briefing & Orchestration** | | |
| 34 | `get_daily_operational_briefing`| Morning audio summary: cash in hand, bills due, low stock, orders. |
| 35 | `query_business_orchestrator`| Master orchestrator query endpoint for multi-agent reasoning. |
| **Tiffin Service Domain Workflows** | | |
| 36 | `tiffin_get_orders` | Orders management endpoint for meals and tiffins. |
| 37 | `tiffin_get_capacity` | Production throughput check against physical kitchen stove capacity. |
| 38 | `tiffin_get_inventory` | Ingredient inventory balance (rice, dal, oil, packaging boxes). |
| 39 | `tiffin_evaluate_opportunity` | End-to-end evaluation for large corporate lunch/dinner orders. |
| **Alexa+ Live Assistant Data Panels** | | |
| 40 | `get_cash_position` | Cash balance, safe-to-spend buffer, and upcoming vendor payees. |
| 41 | `get_inventory_status` | Kitchen stock levels with critical/reorder status tags. |
| 42 | `get_supplier_invoices` | Supplier bills with line items, tax breakdowns, and confidence. |
| 43 | `get_market_demand` | Neighbourhood customer demand segments within delivery radius. |
| 44 | `get_customer_reviews` | Google / online reviews with sentiment analysis and star ratings. |
| 45 | `get_business_overview` | At-a-glance KPI summary across cash, stock, and reputation. |

---

## 7. AI Agent & Orchestration Engine

### 7.1 True Dynamic Tool Calling
Vendo uses the **Google Gemini SDK** (`google-genai`) and **Anthropic SDK** (`anthropic`) to dynamically bind MCP tool declarations into the LLM context. The model reasons over tool results in a multi-turn loop.

### 7.2 Intent Routing & Hinglish Support
Small merchants in India frequently speak in mixed Hindi-English (Hinglish):
- *"Kitna cash bacha hai buffer ke baad?"* -> Routed to `accounts` (`get_cash_position`)
- *"Kitchen mein kya saaman khatam hone wala hai?"* -> Routed to `inventory` (`get_inventory_status`)
- *"Gupta ji ka bill kitna baaki hai?"* -> Routed to `invoices` (`get_supplier_invoices`)

An LLM intent classifier (`_classify_intent`) handles dialect nuances, backed by a deterministic keyword classifier when running offline.

### 7.3 Two-Phase Cryptographic Owner Approval Gate
LLMs cannot be trusted to independently execute external financial transactions. Vendo enforces a strict **Plan -> Propose -> Approve -> Execute** state machine:
1. **Plan:** The system calculates raw material shortages and proposes a purchase order.
2. **Propose:** The plan is hashed (SHA-256) and locked in `PendingApproval` state.
3. **Approve:** The merchant hears the proposal via Alexa+ (*"Gupta Oil Agency charges ₹2,850 for 30L sunflower oil. Approve payment?"*) and explicitly confirms.
4. **Execute:** The execution dispatcher validates the cryptographic payload hash against the approved record before firing the external adapter.

---

## 8. Multi-Business Profile Architecture

While tests feature **Maa Ki Rasoi Cloud Kitchen** (`home_tiffin`) as an anchor, Vendo is architected to be completely **domain-agnostic**:

| Profile Key | Business Archetype | Real-World Operational Model |
|---|---|---|
| `home_tiffin` | Cloud Kitchen / Tiffin | Kitchen burner capacity, perishable ingredients, daily cutoff hours |
| `kirana_store` | Kirana / Grocery | High SKU counts, fast-moving items, distributor credit cycles |
| `retail_boutique` | Apparel & Retail | Seasonal inventory lots, supplier lead times, consignment margins |
| `mobile_repair` | Electronics Repair | Service labor hours, component stock (screens, batteries), turnaround |
| `catering_events` | Catering & Banquets | High-variance bulk orders, temporary labor costs, large advance deposits |

The onboarding portal at `/app/` dynamically adapts to whichever archetype the owner selects, storing facts with evidence provenance in `AdaptiveProfileRepository`.

---

## 9. External APIs & Integration Adapters

Vendo provides complete normalization adapters with transparent mock and live modes:

| Provider | Purpose | Implementation Class | Live / Mock Mechanism |
|---|---|---|---|
| **Google Places (New)** | Nearby competitor density & commercial radius | `GooglePlacesAdapter` | Uses `places:searchNearby` with field masks. Defaults to offline Kanpur commercial dataset if no key is set. |
| **Zoho Books v3** | Ledger, vendor bills, and customer invoices | `ZohoBooksAdapter` | REST v3 with thread-safe OAuth 2.0 token caching. Defaults to simulated bills matching `demo.db` anchor suppliers. |
| **Amazon Pay India** | Merchant payouts, collections, and refunds | `AmazonPayAdapter` | Supports charge and refund lifecycles. Defaults to sandbox mock mode (`MOCK_INTEGRATIONS=true`). |
| **Meta Graph API** | Social presence & campaign status | `MetaAdapter` | Scaffolds Facebook Graph API connection for merchant marketing. |

*Honest Disclosure:* All integrations fail-safe to high-fidelity local mock data matching the `data/demo.db` database schema, ensuring complete testing without requiring live credentials.

---

## 10. Technology Stack

- **Backend:** Python 3.10+, FastAPI (ASGI), Uvicorn, Pydantic v2.
- **Protocol:** FastMCP (Streamable HTTP & SSE transport), OAuth 2.1 RFC-compliant metadata endpoints.
- **AI & LLM:** Google Gemini (`gemini-2.5-flash`), Anthropic Claude (`claude-3-5-sonnet-20241022`).
- **Database:** SQLite3 (`data/demo.db` canonical ledger, `data/runtime_autopilot.sqlite3` operational cache).
- **Frontend:** Pure HTML5, Vanilla CSS3, Modern ES6 (Zero build step, zero Node.js overhead).
- **Typography:** Official Amazon Ember embedded webfonts (`AmazonEmberDisplay`, `AmazonEmberDuospace`, `AmazonEmber`).
- **Testing:** Pytest, AnyIO, Starlette TestClient, Playwright (Headless Chromium).

---

## 11. Installation & Setup

### Prerequisites
- Python 3.10, 3.11, or 3.12 installed on your machine.
- Git.

### 1. Clone the Repository
```bash
git clone https://github.com/milindbathla/Vendo.git
cd Vendo
```

### 2. Create and Activate a Virtual Environment
```bash
# On Linux / macOS
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (Optional)
Vendo runs out-of-the-box with deterministic responders and mock adapters. To activate live LLM intelligence:
```bash
# Set Gemini API Key (Recommended)
export GEMINI_API_KEY="your-gemini-api-key"
# Windows PowerShell:
# $env:GEMINI_API_KEY="your-gemini-api-key"

# Or set Anthropic API Key
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

---

## 12. Running the Application

Start the unified FastAPI and FastMCP server on port 8000:
```bash
python -m uvicorn src.server.web_app:app --host 127.0.0.1 --port 8000
```

When the server starts, you will see confirmation logs:
```
INFO: Database schema initialised at data/runtime_autopilot.sqlite3 (version 5)
INFO: Registered business data tools on the mounted MCP server.
INFO: Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

## 13. Judge's Interactive Testing Guide

Open your browser to test the full merchant journey:

### Step 1: Merchant Onboarding Portal
**URL:** [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/)

1. Fill out the business details (e.g. *Shree Ganesh Cloud Kitchen*, Owner: *Pooja Varma*, City: *Bengaluru*).
2. Click **Connect** on Amazon Pay and Zoho Books (observing simulated token grants).
3. Set Cash Buffer (`₹6,000`) and Daily Order Capacity (`50`).
4. Click **Activate Alexa+**. The profile will be atomically saved to `AdaptiveProfileRepository` and redirect you to the assistant.
5. *State Persistence Test:* Reloading the onboarding page at any time restores all saved merchant fields from the database.

---

### Step 2: Alexa+ Assistant Simulator
**URL:** [http://127.0.0.1:8000/app/alexa.html](http://127.0.0.1:8000/app/alexa.html)

The Alexa+ interface features an interactive voice/text console on the left, and a **Live Visual Data Panel** on the right displaying the underlying MCP data behind every answer.

Try these five evaluation queries:

#### Query 1: Cash Position & Liquidity
- **Click or Type:** `"How's my cash looking today?"`
- **Alexa+ Speaks:** *"You have ₹12,000 in hand. After keeping your ₹5,000 buffer, ₹7,000 is free — but ₹20,850 is due this week, starting with Kitchen Staff (Ramesh & Geeta)."*
- **Visual Panel Shows:** Live *"Accounts · Amazon Pay + Zoho"* card with Bank balance, Due this week, and upcoming payment schedule.
- **MCP Proof:** The top badge flashes `MCP ▸ get_cash_position()`.

#### Query 2: Kitchen Stock & Spoilage Prevention
- **Click or Type:** `"What's running low in the kitchen?"`
- **Alexa+ Speaks:** *"3 items are below their reorder point — Tiffin container 750ml, Refined sunflower oil, Moong dal. 6 more are getting low, worth topping up on your next order."*
- **Visual Panel Shows:** Live *"Inventory · from your DB"* card listing item stock quantities, reorder points, and color-coded status badges (`CRITICAL`, `LOW`, `OK`).
- **MCP Proof:** The badge flashes `MCP ▸ get_inventory_status()`.

#### Query 3: Supplier Invoices & Accounts Payable
- **Click or Type:** `"Show me supplier invoices"`
- **Alexa+ Speaks:** *"You have 2 invoices on file, ₹15,500 in all. The latest is Gupta Oil Agency for ₹12,500."*
- **Visual Panel Shows:** Live *"Invoices · Zoho Books"* card with invoice line items, tax rate, and extraction confidence percentage.
- **MCP Proof:** The badge flashes `MCP ▸ get_supplier_invoices()`.

#### Query 4: Local Demand & Market Intelligence
- **Click or Type:** `"Who's ordering near me?"`
- **Alexa+ Speaks:** *"Around Kakadeo, your strongest demand is student budget tiffin, about 4,200 households, 82% interest, 1.2 km away."*
- **Visual Panel Shows:** Live *"Market · Google Places"* breakdown of customer demand segments and nearby density.
- **MCP Proof:** The badge flashes `MCP ▸ get_market_demand()`.

#### Query 5: Reputation & Customer Feedback
- **Click or Type:** `"Any new reviews?"`
- **Alexa+ Speaks:** *"You are at 4.2 stars across 18 reviews, 83% of them positive."*
- **Visual Panel Shows:** Live *"Reviews · Google Business"* sentiment summary and recent customer comments.
- **MCP Proof:** The badge flashes `MCP ▸ get_customer_reviews()`.

---

## 14. Testing & Verification

Vendo includes a comprehensive automated test suite verifying business logic, causal simulation, security boundaries, and API contracts.

### 14.1 Running the Full Regression Suite
```bash
pytest tests/ -v
```

**Results:**
```
============================== test session starts ==============================
rootdir: E:\Milind\Projects_and_Tasks\Amazon_Developer_Hackathon
collected 458 items

tests/test_acquisition.py .........................                      [ 5%]
tests/test_adaptive_onboarding.py .................                      [ 9%]
tests/test_alexa_addon.py ......                                         [10%]
tests/test_alexa_security_fixes.py .............                         [13%]
tests/test_amazon_pay.py ..............                                  [16%]
tests/test_approval_service.py ...................                       [20%]
tests/test_auth_and_security.py .................                        [24%]
tests/test_autopilot.py .................                                [28%]
tests/test_conversation_sessions.py ............                         [30%]
tests/test_frontend_backend_integration.py ..............                [33%]
tests/test_google_places.py .....................                        [38%]
tests/test_mcp_server.py .................                               [42%]
tests/test_remote_mcp.py .......................                         [47%]
tests/test_tiffin_service_e2e.py ....................                    [51%]
tests/test_vendo_e2e_scenarios.py ...................                    [55%]
... [additional domain suites] ...
======================= 455 passed, 3 skipped in 12.47s =======================
```
*Note:* 3 skipped tests are live-credential smoke tests that execute only when external API keys are explicitly injected.

### 14.2 Browser QA & Responsive Testing
The frontend was tested via automated browser automation with Playwright Chromium across Desktop (1280x800), Tablet (768x1024), and Mobile (375x667):
- **0** console errors or JavaScript exceptions.
- **0** failed network requests (HTTP 4xx/5xx).
- **0** horizontal overflow elements across all screen widths.
- Verified typography matching official **Amazon Ember**.

---

## 15. Security, Governance & Safety Rails

1. **Deterministic Business Gating:** No AI agent can trigger bank payouts, vendor orders, or customer communications without an authenticated owner signature.
2. **Cryptographic Action Signing:** Proposals contain a SHA-256 hash of `(business_id, action_type, payload)`. If the underlying inventory price or quantity changes before approval, the hash invalidates automatically.
3. **Tenant Context Isolation:** Identity is derived exclusively from the verified token principal via Python `contextvars`. A malicious caller cannot spoof an `actor_id` or cross-access another merchant's ledger.
4. **Fail-Closed Production Safety:** When `AUTOPILOT_ENV=production`, the server strictly rejects default secret keys and unencrypted credentials on boot.

---

## 16. Current Limitations & Honest Disclosures

To ensure full transparency during hackathon evaluation:
- **Physical Hardware:** The Alexa+ integration has been verified via the streamable HTTP/SSE FastMCP protocol, RFC-compliant OAuth endpoints, and the Alexa Add-on Simulator. It has **not** been tested on an unreleased physical Amazon device.
- **Simulated Payment Settlement:** Amazon Pay integration models the complete charge, refund, and webhook verification lifecycle in compliant sandbox mode. No real money is transferred.
- **Local Testing Database:** The canonical database `data/demo.db` is opened in read-only mode (`?mode=ro`) to prevent benchmark corruption during test runs. All runtime modifications write to `data/runtime_autopilot.sqlite3`.

---

## 17. Roadmap & Future Enhancements

- [ ] **WhatsApp Business API Integration:** Push approval cards to merchants via WhatsApp interactive buttons.
- [ ] **Direct GST Portal Ingestion:** Auto-extract GSTR-1 and GSTR-3B filings to verify input tax credit (ITC) on supplier bills.
- [ ] **Voice Biometric Authentication:** Alexa voice-print recognition for authenticating large purchase approvals over ₹10,000.
- [ ] **Vernacular Speech Synthesis:** Multi-lingual voice generation in Tamil, Telugu, Marathi, and Bengali.

---

## 18. Authors & Project Context

- **Developer:** Milind Bathla
- **Project Name:** Vendo — Your Shop. On Autopilot.
- **Hackathon:** Amazon Alexa+ Developer Hackathon
- **Submission Repository:** [https://github.com/milindbathla/Vendo](https://github.com/milindbathla/Vendo)
- **License:** MIT License (or hackathon submission terms).
