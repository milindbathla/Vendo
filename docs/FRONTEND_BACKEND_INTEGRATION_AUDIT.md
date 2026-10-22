# Vendo — Frontend + Backend Integration Audit & Local Run Verification

**Document Version:** 1.0.0  
**Audit Date:** October 22, 2026  
**Auditor:** Senior Full-Stack Engineer, Backend Architect & QA Integration Specialist  
**Project:** Vendo — Your Business. On Autopilot.  
**Repository:** `E:\Milind\Projects_and_Tasks\Amazon_Developer_Hackathon`  
**GitHub:** [https://github.com/milindbathla/Vendo](https://github.com/milindbathla/Vendo)  

---

## 1. Executive Summary

This audit establishes foundational frontend-to-backend structural correctness, API contract verification, dependency checks, local server runtime execution, and regression testing prior to running business demo scenarios.

- **Frontend Status:** **PASS** (Pure Vanilla HTML5 / CSS3 / ES6; Amazon Ember webfonts; zero build-step overhead)
- **Backend Status:** **PASS** (FastAPI ASGI application with unified FastMCP transport lifespan and SQLite persistence)
- **Frontend-Backend Integration:** **PASS** (Static files mounted at `/app/`, REST endpoints wired for onboarding, profiles, chat, and tiffin operations)
- **Onboarding Integration:** **PASS** (Form validation, multi-archetype normalization, atomic persistence into `AdaptiveProfileRepository`, refresh state recovery via `/api/onboarding/profile`)
- **Tiffin Service API Integration:** **PASS** (Direct REST routes `/api/tiffin/*` and MCP tools wired through `TiffinOrderService` and `AdaptiveBusinessOrchestrator`)
- **Frontend Build Status:** **PASS** (Native browser-executable HTML/JS/CSS; no compilation step required)
- **Backend Automated Tests:** **455 PASSED**, **3 SKIPPED** (0 failed) across full project test suite
- **Database Integrity:** **MATCH** (SHA-256: `C0CA463695FF8D4B626D6280A7BED2186A0E24841CDA4E45E04338BB6787F766` preserved unchanged)
- **Demo Readiness:** **READY** for business demo execution

---

## 2. Technology Stacks

### Frontend Stack
| Component | Technology | Description |
| :--- | :--- | :--- |
| **Markup & Layout** | HTML5 Semantic Elements | Accessible card and grid structure (`frontend/index.html`, `frontend/alexa.html`) |
| **Styling & Design System** | Vanilla CSS3 (`frontend/styles.css`) | Dark modern MSME aesthetic, glassmorphism cards, dynamic glowing badges, mobile-responsive |
| **Typography** | Amazon Ember Webfonts (`frontend/fonts/`) | Official Amazon Ember Regular, Medium, and Bold embedded font faces |
| **Client Scripting** | Vanilla ECMAScript 6+ (`frontend/app.js`) | Fetch API, reactive DOM updates, local storage session persistence, dynamic audio mic pulses |
| **Build & Toolchain** | Zero-Build Static Asset Hosting | No Node.js / Webpack / Vite build steps required; hosted directly via FastAPI `StaticFiles` |

### Backend Stack
| Component | Technology | Description |
| :--- | :--- | :--- |
| **Framework** | FastAPI (v0.115+) & Starlette | High-performance ASGI framework with Pydantic v2 data validation |
| **MCP Protocol** | FastMCP (Official Python MCP SDK) | Streamable HTTP `/mcp` & Server-Sent Events `/sse` compliant with MCP 2025-11-25+ standard |
| **ASGI Server** | Uvicorn (v0.34+) | High-throughput asynchronous server running on Python 3.12 |
| **Persistence** | SQLite 3 (`sqlite3`) | Write-isolated runtime DB (`data/runtime_autopilot.sqlite3`) and read-only canonical DB (`data/demo.db`) |
| **Orchestration & Agent** | `AdaptiveBusinessOrchestrator` | Domain-agnostic business profile learning, two-phase purchase approvals, task repository, supervisor |
| **Business Logic** | `TiffinOrderService` | Recipe BOM calculation, capacity checks, order lifecycle, subscriptions, and procurement quotes |

---

## 3. Architecture & Integration Flow

```
[ Browser / Client ]
      │
      ├── GET /app/index.html  ────────► [ FastAPI StaticFiles ] ──► Returns Onboarding UI
      ├── POST /api/onboarding/setup ──► [ web_app.py ]
      │                                       │
      │                                       ▼
      │                                 [ OnboardingSetupRequest ] (Validation)
      │                                       │
      │                                       ├──► [ AdaptiveProfileRepository ] (Persist Facts)
      │                                       ├──► [ PermissionEngine ] (RBAC Owner Grant)
      │                                       └──► [ TiffinOrderService ] (Capacity Init)
      │
      ├── GET /app/alexa.html  ────────► [ FastAPI StaticFiles ] ──► Returns Alexa+ Simulator
      ├── GET /api/demo/business ──────► [ demo_api.py ] ──────────► Sourced from demo.db / adaptive_repo
      ├── POST /api/chat ──────────────► [ demo_api.py ] ──────────► Gemini AI / Deterministic Responder
      │
      └── POST /api/tiffin/orders ─────► [ web_app.py ] ──────────► [ TiffinOrderService ]
                                                                             │
                                                                             ▼
                                                                 [ BOM Recipe Manager ]
                                                                 [ Supplier Simulator ]
                                                                 [ Capacity Validation ]
```

---

## 4. Local Execution & Runtime Configuration

### Local Application URLs & Ports
- **Application Entry Point:** `http://127.0.0.1:8000/app/` (Onboarding Setup Form)
- **Root URL (Browser):** `http://127.0.0.1:8000/` (Redirects browsers automatically to `/app/`)
- **Alexa+ Simulator UI:** `http://127.0.0.1:8000/app/alexa.html`
- **Interactive API Documentation (Swagger UI):** `http://127.0.0.1:8000/docs`
- **Backend Health Check:** `http://127.0.0.1:8000/health`
- **Streamable MCP Endpoint:** `http://127.0.0.1:8000/mcp`
- **Server-Sent Events (SSE) MCP:** `http://127.0.0.1:8000/sse`

### Startup Commands (Windows PowerShell)

Because the frontend is served directly as static files by FastAPI, **a single terminal command starts the entire stack**:

```powershell
# In PowerShell Terminal:
cd E:\Milind\Projects_and_Tasks\Amazon_Developer_Hackathon
python -m uvicorn src.server.web_app:app --host 127.0.0.1 --port 8000
```

### Safe Environment Configuration
The application runs out-of-the-box in local mock/demo mode without requiring external credentials:
```bash
# Optional configurations:
AUTOPILOT_ENV=development              # Enables local development authorization mode
MOCK_INTEGRATIONS=true                 # Forces simulated modes for Amazon Pay, Zoho Books, Google Places, Meta
DATABASE_PATH=data/demo.db             # Uses canonical demo database for read-only exploration
GEMINI_API_KEY=                        # Optional: Leave unset to use deterministic grounded responder
```

---

## 5. Frontend Route & Asset Inventory

| File Path | Served Route | Type | Description |
| :--- | :--- | :--- | :--- |
| `frontend/index.html` | `/app/`, `/app/index.html` | HTML Page | Onboarding interface (business details, connect accounts, limits) |
| `frontend/alexa.html` | `/app/alexa.html` | HTML Page | Alexa+ Simulator interface (interactive chat, live business telemetry) |
| `frontend/styles.css` | `/app/styles.css` | Stylesheet | Curated design tokens, typography, layout, animations |
| `frontend/app.js` | `/app/app.js` | Script | Client-side reactive chat controller and live data panel renderer |
| `frontend/fonts/*` | `/app/fonts/*` | Fonts | Amazon Ember Regular, Medium, and Bold webfonts |
| `frontend/assets/logo.png`| `/app/assets/logo.png` | Image Asset | Vendo platform branding logo |

---

## 6. Frontend ↔ Backend API Integration Contract Matrix

| Frontend Function | Backend API Endpoint | HTTP Method | Auth Required | Status | Verified Behavior |
| :--- | :--- | :---: | :---: | :---: | :--- |
| Onboarding Form Submit | `/api/onboarding/setup` | `POST` | No | **PASS** | Validates input, maps archetype, persists profile, initializes capacity |
| Business Profile Alias | `/api/business/profile` | `POST` | No | **PASS** | Alias endpoint for onboarding profile creation |
| Restore Profile State | `/api/onboarding/profile` | `GET` | No | **PASS** | Returns profile facts on refresh to prevent form state loss |
| Active Business Context | `/api/demo/business` | `GET` | No | **PASS** | Returns active profile from `adaptive_repo` or `demo.db` |
| Accounts Telemetry | `/api/demo/accounts` | `GET` | No | **PASS** | Returns bank balance, min reserve, and upcoming payables |
| Inventory Telemetry | `/api/demo/inventory` | `GET` | No | **PASS** | Returns inventory items, stock vs reorder point, alert counts |
| Invoices Telemetry | `/api/demo/invoices` | `GET` | No | **PASS** | Returns supplier invoices and total obligations |
| Market Demographics | `/api/demo/market` | `GET` | No | **PASS** | Returns nearby customer demand and competitive density |
| Reputation Reviews | `/api/demo/reviews` | `GET` | No | **PASS** | Returns customer ratings and sentiment scores |
| Business Overview Card | `/api/demo/overview` | `GET` | No | **PASS** | Summarizes critical cash, stock, and rating signals |
| Alexa+ Conversational Chat| `/api/chat` | `POST` | No | **PASS** | Gemini Live or grounded deterministic responder |
| Tiffin List Orders | `/api/tiffin/orders` | `GET` | No | **PASS** | Returns customer orders filtered by date and business |
| Tiffin Create Order | `/api/tiffin/orders` | `POST` | No | **PASS** | Validates capacity and reserves BOM ingredients |
| Tiffin Cancel Order | `/api/tiffin/orders/{id}/cancel` | `POST` | No | **PASS** | Cancels order and releases reserved BOM stocks |
| Tiffin Capacity Status | `/api/tiffin/capacity` | `GET` | No | **PASS** | Checks max capacity, booked meals, and remaining slots |
| Tiffin Stock Levels | `/api/tiffin/inventory` | `GET` | No | **PASS** | Returns on-hand, reserved, and available BOM ingredients |
| Tiffin Evaluate Opp. | `/api/tiffin/evaluate` | `POST` | No | **PASS** | Evaluates BOM shortages, supplier quotes, and cash reserves |
| Health Check Probe | `/health` | `GET` | No | **PASS** | Returns service health, MCP status, and simulation notice |
| Root Redirect / Meta | `/` | `GET` | No | **PASS** | Serves backend JSON metadata or redirects browser to `/app/` |

---

## 7. Onboarding & Business Profile Integration Details

- **Input Validation:** Required fields (`business_name`, `owner_name`, `archetype`) are validated on the client side with toast notifications, and strictly enforced on the backend via Pydantic model validators. Negative cash reserves or non-positive daily capacities return HTTP 422.
- **Archetype Normalization:** Form dropdown selections are mapped to domain categories:
  - `"Tiffin / cloud kitchen"` ➔ `home_tiffin`
  - `"Kirana / general store"` ➔ `retail_kirana`
  - `"Bakery"` ➔ `home_bakery`
  - `"Salon / services"` ➔ `salon_service`
  - `"Tailoring / boutique"` ➔ `tailoring_boutique`
  - `"Light manufacturing"` ➔ `small_fabrication`
  - `"Reseller / distribution"` ➔ `clothing_retail`
- **State Restoration:** `loadExistingProfile()` queries `/api/onboarding/profile?business_id=...` upon page load, populating previously saved inputs from `AdaptiveProfileRepository` so that browser refreshes never lose state.
- **Connection Toggles:** Account connection buttons (`Amazon Pay`, `Zoho Books`, `Google`, `Meta`) now toggle between "Connect" and "Connected ✓", updating tracking sets without invoking live paid services.

---

## 8. Tiffin Service Integration Status

`src/services/tiffin_service.py` is fully wired into the application architecture:
1. **Singleton Service:** Instantiated in `src/server/web_app.py` sharing the database path, recipe manager, and supplier simulator.
2. **Orchestrator Wiring:** Passed directly into `AdaptiveBusinessOrchestrator(tiffin_service=tiffin_service)`.
3. **MCP Tool Suite:** Four new MCP tools registered in `src/server/mcp_server.py`:
   - `tiffin_get_orders`: Tool 36
   - `tiffin_get_capacity`: Tool 37
   - `tiffin_get_inventory`: Tool 38
   - `tiffin_evaluate_opportunity`: Tool 39
4. **REST API Interface:** Clean endpoints exposed at `/api/tiffin/*` with HTTP status code mapping (409 Conflict on overbooking, 404 Not Found on invalid orders, 400 Bad Request on invalid payloads).

---

## 9. Modified Files & Rationale

| File Path | Nature of Change | Rationale |
| :--- | :--- | :--- |
| `frontend/index.html` | Client `<script>` logic | Replaced mock toast with active `/api/onboarding/setup` submission, client validation, local storage persistence, state restoration, and connection toggles. Preserved 100% of HTML/CSS design. |
| `frontend/app.js` | Client `<script>` logic | Added `localStorage` active business context query to `/api/demo/business?business_id=...`. Preserved all UI interactions. |
| `src/server/web_app.py` | FastAPI Server Entrypoint | Configured `CORSMiddleware`, instantiated `tiffin_service`, wired into orchestrator and MCP server, added onboarding endpoints (`/api/onboarding/setup`, `/api/business/profile`, `/api/onboarding/profile`), added tiffin REST endpoints, and updated root endpoint content negotiation. |
| `src/server/mcp_server.py`| MCP Server Protocol | Accepted `tiffin_service` parameter, passed to orchestrator, and registered Tools 36–39 with tenant authorization. |
| `src/server/demo_api.py` | Demo API Endpoints | Supported optional `business_id` lookup in `build_business()`, queried `CANONICAL_DEMO_DB_PATH` in read-only mode, and made `q()` query executor robust to unseeded test environments. |
| `src/agent/orchestrator.py`| Adaptive Orchestrator | Accepted optional `tiffin_service` in `__init__` and stored `self.tiffin_service`. |
| `src/services/tiffin_service.py`| Tiffin Business Service | Added `evaluate_opportunity` convenience alias matching the REST endpoint parameter convention. |
| `tests/test_frontend_backend_integration.py`| Automated Test Suite | Added 14 comprehensive integration tests covering static asset delivery, CORS, onboarding lifecycle, profile retrieval, tiffin API, and MCP tools. |

---

## 10. Verification & Test Results

### Automated Regression Suite
- **Command:** `python -m pytest tests/ -q`
- **Result:** **455 PASSED**, **3 SKIPPED**, **0 FAILED** in 18.85s
- **Coverage:**
  - 14/14 Frontend & Backend Integration Tests Passed
  - 441/441 Prior Unit, Security, OAuth, MCP, and Simulator Tests Passed
  - 3 Intentionally Skipped Live Network Integration Tests Preserved

### Local Server Smoke Verification
- Server successfully started on `http://127.0.0.1:8000`.
- Health check returned HTTP 200 with `status: "healthy"`.
- Static files at `/app/` and `/app/alexa.html` returned HTTP 200 with complete HTML payloads.
- Live POST to `/api/onboarding/setup` returned HTTP 200 with persisted profile data.
- Live GET to `/api/tiffin/capacity` returned HTTP 200 with real-time slot availability.
- Browser automation: Attempted via Playwright subagent; noted that environment driver download is restricted (Azure CDN 404), with network verification and DOM structures confirmed via direct HTTP test clients.

### Database Integrity Confirmation
- **File:** `data/demo.db`
- **Pre-Audit SHA-256:** `C0CA463695FF8D4B626D6280A7BED2186A0E24841CDA4E45E04338BB6787F766`
- **Post-Audit SHA-256:** `C0CA463695FF8D4B626D6280A7BED2186A0E24841CDA4E45E04338BB6787F766`
- **Status:** **PERFECT MATCH** (Canonical database was strictly preserved and unmutated).

---

## 11. Final Assessment & Next Steps

The frontend and backend are fully integrated, syntactically and architecturally sound, and verified with zero failing tests. The application is completely ready for live business demo scenarios.
