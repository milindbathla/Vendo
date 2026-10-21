# Alexa Business Autopilot: Business MCP Server

An autonomous operating and decision layer for Indian micro, small, and medium businesses (MSMEs). The system combines an official Model Context Protocol (MCP) server, FastAPI backend, causal value-chain simulation engine, and external market and accounting integrations.

> **Scope Notice**: Amazon Pay is explicitly **out of scope** for this phase.

---

## 1. Project Overview & Architecture

Alexa Business Autopilot assists business owners across 10 diverse Indian business profiles (cloud kitchens, kiranas, salons, tailoring boutiques, bakeries, etc.). The anchor test profile is **Maa Ki Rasoi Cloud Kitchen** located in Kakadeo, Kanpur, Uttar Pradesh.

The system is strictly backend-first and connects to voice/chat clients (Alexa, WhatsApp, MCP clients) via:
1. **Model Context Protocol (MCP)**: Streamable HTTP and Server-Sent Events (SSE) tools.
2. **FastAPI Web Application**: REST endpoints for health, state, evaluations, and external integrations.
3. **Causal Business Engine & Simulators**: 90-day value chain modeling customer acquisition, demand elasticity, FIFO inventory lot costing, and liquidity buffers.
4. **Approval Service**: Two-phase cryptographic approval state machine gating purchase execution.

### Architectural Flow

```text
       Existing MCP Server (FastMCP) / FastAPI HTTP Endpoints
                                 |
                                 v
                      Existing Business Engine
                                 |
        +------------------------+------------------------+
        |                                                 |
        v                                                 v
  Google Places Adapter                           Zoho Books Adapter
  (Places API New)                                (OAuth 2.0 & Books v3)
        |                                                 |
        v                                                 v
  Google Places API / Mock                        Zoho Books API / Mock
        |                                                 |
        +------------------------+------------------------+
                                 |
                                 v
                     Normalization Layer
                     (BusinessDataNormalizer)
                                 |
                                 v
             Existing Business Data & Safety Checks
             (demo.db & autopilot_provider_connections)
                                 |
                                 v
                    MCP Tools & Gemini Agent
```

---

## 2. External Integrations Overview

### A. Google Maps Platform: Places API (New)
* **Purpose**: Discovers nearby commercial businesses and competitor density around the business coordinates without presenting map listings as proof of customer demand.
* **API Standard**: Uses the current **Google Places API (New)** endpoint: `POST https://places.googleapis.com/v1/places:searchNearby` with field masks (`places.id`, `places.displayName`, `places.formattedAddress`, `places.location`, `places.types`, `places.rating`, `places.userRatingCount`, `places.businessStatus`, `places.priceLevel`).
* **Capabilities**:
  * Coordinate and radius validation (latitude: -90° to 90°, longitude: -180° to 180°, radius: 1m to 50,000m).
  * Haversine distance calculation and proximity sorting.
  * Competitor density analysis (rating averages, direct food/service competitor counting).
  * HTTP timeout handling and bounded exponential-backoff retries on rate limits (429/503).
  * Built-in offline mock mode reproducing realistic commercial establishments in Kakadeo, Kanpur.

### B. Zoho Books API & OAuth 2.0
* **Purpose**: Connects read-only financial accounting records (organizations, customer invoices, vendor bills, operating expenses) into the Autopilot's liquidity and decision flow.
* **API Standard**: Zoho Books REST API v3 with OAuth 2.0 token refresh (`POST {accounts_url}/oauth/v2/token`).
* **Capabilities**:
  * Thread-safe `ZohoOAuthManager` with concurrent race-condition prevention (`threading.Lock`).
  * In-memory access token caching with proactive expiration buffer (5 minutes).
  * Multi-datacenter support (`.in`, `.com`, `.eu`, `.com.au`) with automatic API domain derivation.
  * Pagination support for invoices, bills, and expenses (`page`, `per_page`, `has_more_page`).
  * **Strict Financial Separation**: Distinguishes **billed revenue**, **cash collected**, **outstanding receivables**, and **vendor payables**.
  * Offline mock mode matching anchor suppliers in `data/demo.db` (Gupta Oil Agency, Packaging Mart).

---

## 3. Files Created and Modified

### Created Files
* **`src/integrations/__init__.py`**: Top-level package exports.
* **`src/integrations/base.py`**: Common exceptions (`ValidationError`, `AuthenticationError`, `RateLimitError`, `ProviderUnavailableError`), regex credential sanitizer, and config helpers.
* **`src/integrations/normalization.py`**: Domain mapping logic (`BusinessDataNormalizer`) and Decimal currency precision.
* **`src/integrations/google_places/__init__.py`**: Module exports.
* **`src/integrations/google_places/models.py`**: Dataclasses (`PlaceLocation`, `PlaceResult`, `NearbySearchResponse`, `CompetitorAnalysisSummary`).
* **`src/integrations/google_places/mock_data.py`**: Synthetic Kanpur places database, Haversine formula, and data limitation disclaimer.
* **`src/integrations/google_places/client.py`**: HTTP client for `places:searchNearby` with field masking, timeouts, and retries.
* **`src/integrations/google_places/adapter.py`**: High-level adapter for validation, mock/live dispatch, and competitor summaries.
* **`src/integrations/zoho_books/__init__.py`**: Module exports.
* **`src/integrations/zoho_books/models.py`**: Dataclasses (`ZohoOrganization`, `ZohoInvoice`, `ZohoBill`, `ZohoExpense`, `ZohoAccountingSummary`, `ZohoPaginatedResponse`).
* **`src/integrations/zoho_books/oauth.py`**: Thread-safe OAuth 2.0 token manager with expiry caching and race prevention.
* **`src/integrations/zoho_books/mock_data.py`**: Synthetic accounting records matching `data/demo.db` anchor suppliers.
* **`src/integrations/zoho_books/client.py`**: HTTP client for Zoho Books API v3 with pagination and token injection.
* **`src/integrations/zoho_books/adapter.py`**: High-level adapter for read-only accounting operations and financial metric aggregation.
* **`tests/test_google_places.py`**: Unit tests and mocked integration tests for Google Places.
* **`tests/test_zoho_books.py`**: Unit tests and mocked integration tests for Zoho Books.
* **`tests/test_integrations_normalization.py`**: Normalization and database mapping tests.
* **`tests/test_integrations_live_smoke.py`**: Optional live smoke test suite for live API credentials.

### Modified Files
* **`src/db/connection.py`**:
  * Bumped schema version to `2`.
  * Added additive DDL `autopilot_provider_connections` table (preserving existing domain tables).
  * Added `upsert_provider_connection` and `get_provider_connection` CRUD helpers.
* **`src/server/mcp_server.py`**:
  * Added MCP Tool 11: `search_nearby_competitors`.
  * Added MCP Tool 12: `get_zoho_organization`.
  * Added MCP Tool 13: `get_zoho_invoices`.
  * Added MCP Tool 14: `get_zoho_expenses_and_bills`.
  * Added MCP Tool 15: `get_external_integrations_status`.
* **`src/server/web_app.py`**:
  * Initialized singleton integration adapters.
  * Added REST endpoints: `GET /api/integrations/status`, `POST /api/integrations/places/nearby`, `GET /api/integrations/zoho/organization`, `GET /api/integrations/zoho/invoices`, `GET /api/integrations/zoho/expenses`.
* **`src/agent/tools.py`**:
  * Registered `search_nearby_competitors` (Tool 6) and `get_zoho_accounting_summary` (Tool 7) in `TOOL_REGISTRY` for Gemini function calling.
* **`.env.example`**:
  * Added configuration placeholders for `GOOGLE_MAPS_API_KEY`, `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`, `ZOHO_ORG_ID`, `ZOHO_ACCOUNTS_URL`, `ZOHO_API_DOMAIN`, `MOCK_INTEGRATIONS`.

---

## 4. Dependencies

No new third-party packages were added. The integration layer is built entirely using Python's standard library:
* `urllib.request`, `urllib.error`, `urllib.parse`: Clean, lightweight HTTP client without third-party transport bloat.
* `json`, `dataclasses`, `typing`: Type-safe schemas and serializations.
* `threading`: Concurrency locking for OAuth token refresh.
* `decimal`: Precision monetary arithmetic.
* `sqlite3`: Native relational persistence.
* `unittest`: Comprehensive offline test execution.

---

## 5. Environment & Credentials Configuration

Copy `.env.example` to `.env` and fill in credentials as needed:

```bash
cp .env.example .env
```

| Variable | Description | Default / Example |
|---|---|---|
| `MOCK_INTEGRATIONS` | Force offline mock mode for all external APIs | `false` (auto-detected if keys missing) |
| `GOOGLE_MAPS_API_KEY` | API Key with access to Places API (New) | `AIzaSy...` |
| `ZOHO_CLIENT_ID` | Zoho OAuth 2.0 Client ID | `1000.XXXX...` |
| `ZOHO_CLIENT_SECRET` | Zoho OAuth 2.0 Client Secret | `secret...` |
| `ZOHO_REFRESH_TOKEN` | Long-lived Zoho OAuth Refresh Token | `1000.YYYY...` |
| `ZOHO_ORG_ID` | Zoho Books Organization ID | `892341...` |
| `ZOHO_ACCOUNTS_URL` | Accounts domain for datacenter | `https://accounts.zoho.in` |
| `ZOHO_API_DOMAIN` | Optional Books API domain override | `https://www.zohoapis.in` |

---

## 6. Provider Setup & Permissions

### Google Cloud Setup (Places API New)
1. In Google Cloud Console, create or select a project.
2. Enable **Places API (New)** under APIs & Services.
3. Create an API Key in Credentials.
4. (Recommended) Restrict key usage to "Places API (New)" and set HTTP/IP restrictions for production.

### Zoho Books Setup (OAuth 2.0)
1. Go to [Zoho Developer Console](https://api-console.zoho.com).
2. Create a **Self Client** (for single-merchant/internal prototype) or **Server-based Application**.
3. Generate a refresh token using the following read-only scopes:
   * `ZohoBooks.organizations.READ`
   * `ZohoBooks.invoices.READ`
   * `ZohoBooks.bills.READ`
   * `ZohoBooks.expenses.READ`
4. Set redirect URI and copy `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, and the generated refresh token into `.env`.

---

## 7. Database Changes & Migrations

The database migration is **additive and safe**:
* Canonical database: `data/demo.db`.
* Schema migration version bumped from `1` to `2` in `src/db/connection.py`.
* Table created:
  ```sql
  CREATE TABLE IF NOT EXISTS autopilot_provider_connections (
      provider        TEXT    NOT NULL,
      business_type   TEXT    NOT NULL DEFAULT 'home_tiffin',
      org_id          TEXT,
      api_domain      TEXT,
      scopes          TEXT,
      status          TEXT    NOT NULL DEFAULT 'disconnected',
      last_synced_at  TEXT,
      metadata        TEXT,
      created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
      updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
      PRIMARY KEY (provider, business_type)
  );
  ```
* Teammate-owned domain tables (`orders`, `items`, `suppliers`, `recipe_bom`, etc.) are completely unmodified.

---

## 8. Verification & Test Execution

### A. Running in Mock Mode
If API credentials are not set in `.env`, the server automatically runs in mock mode with zero external network calls:
```bash
python3 -c "from src.integrations.google_places import GooglePlacesAdapter; print(GooglePlacesAdapter().is_mock)"
# Output: True
```

### B. Unit & Mocked Integration Tests
Run all integration unit and mocked tests:
```bash
python3 -m unittest tests/test_google_places.py -v
python3 -m unittest tests/test_zoho_books.py -v
python3 -m unittest tests/test_integrations_normalization.py -v
```

### C. Optional Live Smoke Tests
To run live tests when credentials are configured:
```bash
python3 -m unittest tests/test_integrations_live_smoke.py -v
```
*(If credentials are absent, the smoke tests will automatically skip without failing).*

### D. Vendo Multi-Business Operational Assistant & Alexa+ Readiness
Run the end-to-end multi-business operational demonstration across retail, workshop, and salon verticals:
```bash
python src/demo_runner.py
```

### E. Regression Verification
Verify existing invariants, simulations, and agents:
```bash
# Run complete test suite (372 passed, 3 skipped)
python -m pytest tests/ -q

# Verify 16 core business invariant assertions (A1..A16)
python3 data/build_db.py

# Run 90-day simulation across all 10 business profiles
python3 check_all_profiles.py

# Verify Demand & Capacity specialist agent
python3 -m unittest discover Agents/demand_capacity_agent/tests -v

# Verify Inventory & Procurement specialist agent
python3 -m unittest discover Agents/inventory_procurement_agent/tests -v
```

---

## 9. Actual Test Results

```text
================================================================================
Test Suite                                         | Results
================================================================================
python -m pytest tests/ -q                         | 372 PASS, 3 SKIPPED, 0 FAIL (13.15s)
tests/test_vendo_e2e_scenarios.py                  | 5 PASS, 0 FAIL (100%)
tests/test_google_places.py                        | 11 PASS, 0 FAIL (100%)
tests/test_zoho_books.py                           | 10 PASS, 0 FAIL (100%)
tests/test_integrations_normalization.py           |  6 PASS, 0 FAIL (100%)
tests/test_integrations_live_smoke.py              |  2 SKIPPED (No live keys)
data/build_db.py (Invariants A1..A16)              | 16 PASS, 0 FAIL (100%)
check_all_profiles.py (10 Business Profiles)       | 10 PASS, 0 FAIL (100%)
Agents/demand_capacity_agent/tests                 |  9 PASS, 0 FAIL (100%)
Agents/inventory_procurement_agent/tests           |  7 PASS, 0 FAIL (100%)
================================================================================
TOTAL PYTEST SUITE                                 | 372 PASS, 3 SKIPPED, 0 FAIL
================================================================================
```

---

## 10. Status Summary & Remaining Work

* **Core Operational Assistant (Vendo)**:
  * **Unified Orchestrator**: `AdaptiveBusinessOrchestrator` integrates task management, email supervisor, policy engine, and action dispatcher.
  * **Deterministic Prioritization**: Real-time scoring (0–100) based on urgency, consequential proposal presence, financial scale, and lifecycle state.
  * **Voice Briefings**: Proactive, voice-friendly summaries for Alexa+ tailored to retail, repair workshops, salons, and food businesses.
  * **Controlled Execution**: Cryptographic SHA-256 payload binding, owner authorization enforcement, and idempotent execution receipts with simulated payment and refund support.
  * **Protocols**: 37 FastAPI REST endpoints + 35 FastMCP tools.
* **Teammate Integrations & Out of Scope**:
  * Live external API activation (Amazon Pay, Gemini, Google Places, Meta, Zoho, Gmail) is owned by teammates and remains simulated offline.
  * Canonical database `data/demo.db` is strictly protected with `PermissionError` barriers and zero mutations.
