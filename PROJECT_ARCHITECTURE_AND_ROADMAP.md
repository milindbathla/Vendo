# Amazon Business Autopilot — Architecture, Working Explanation & Roadmap

> **Audience:** The developer who built this project and now wants a complete mental model of its architecture, execution flow, codebase layout, and remaining work.
>
> **Scope:** Documentation only. No source code is modified by this document.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [End-to-End Execution Walkthrough](#3-end-to-end-execution-walkthrough)
4. [AI vs. Deterministic Layer Analysis](#4-ai-vs-deterministic-layer-analysis)
5. [Codebase Module Guide](#5-codebase-module-guide)
6. [Database and Persistence Architecture](#6-database-and-persistence-architecture)
7. [Security and Authorization Model](#7-security-and-authorization-model)
8. [REST API Reference](#8-rest-api-reference)
9. [MCP Server and Tools Reference](#9-mcp-server-and-tools-reference)
10. [Document Onboarding Workflow](#10-document-onboarding-workflow)
11. [Phase 0–4 Completion Summary](#11-phase-04-completion-summary)
12. [Remaining Roadmap Gaps](#12-remaining-roadmap-gaps)
13. [Recommended Next Development Phase](#13-recommended-next-development-phase)
14. [Running the Project Locally](#14-running-the-project-locally)
15. [Technical Glossary](#15-technical-glossary)
16. [Latest Repository Updates — Commit c3277da](#16-latest-repository-updates--commit-c3277da)

---

## 1. Project Overview

**Amazon Business Autopilot** is an autonomous operating layer for Indian micro and small businesses (MSMEs) spanning any vertical — retail, kirana, services, food/catering, repair, light manufacturing, and distribution.

It is **not** a tiffin-only application. The `home_tiffin` profile appears in tests and demo data as one illustrative example.

### What the system does

| Capability | Description |
|---|---|
| **Business Profile Onboarding** | Conversational or document-based extraction of business facts (prices, costs, capacity, cash) with evidence provenance tracking |
| **Email-Triggered Operations** | Ingests incoming emails, creates operational tasks, classifies intent, and proposes authorized actions |
| **Deterministic Permission Gating** | All consequential actions (external emails, payments, POs) are blocked until an authenticated business owner explicitly approves them |
| **Controlled Action Execution** | Simulated handlers execute approved actions with SHA-256 payload integrity checks, idempotency, and failure recovery |
| **Multi-Protocol Interface** | Exposed via both a FastAPI HTTP REST API (35 endpoints) and an official MCP server (33 tools) for Alexa/voice integration |
| **Payment Integration** | Amazon Pay India adapter (mock mode; live sandbox mode with credentials) for charge, refund, and webhook operations |
| **Social Integration** | Meta (Facebook Graph API) adapter scaffolded for status and future campaign/engagement metrics |
| **Provider OAuth Flows** | OAuth callback routes and encrypted token store for connecting external provider accounts per merchant |

### Architectural Constraints

- **Backend-only**: No HTML/CSS/JS frontend. The user-facing interface is voice/chat through MCP or HTTP API.
- **Business-agnostic**: All logic operates on abstract `AdaptiveBusinessProfile` facts — not hardcoded schemas.
- **Offline-safe**: All simulated handlers run without calling live external APIs.
- **Database co-ownership**: `data/demo.db` has 45+ domain tables owned by teammates. The autopilot adds its own `autopilot_*` tables additively and never touches domain tables.

---

## 2. High-Level Architecture

### System Layers

```mermaid
graph TB
    subgraph "External Input"
        EMAIL["Inbound Email (Mock or future Gmail/Outlook)"]
        DOC["Documents (PDF, CSV, XLSX, TXT)"]
        OWNER["Business Owner (HTTP or voice/MCP)"]
    end

    subgraph "Interface Layer - src/server/"
        WEB["FastAPI Web App\nweb_app.py - 35 REST endpoints"]
        MCP["MCP Server\nmcp_server.py - 33 MCP tools"]
        AUTH["Auth Router\nauth_routes.py - OAuth callbacks\n⚠ Defined but NOT mounted"]
    end

    subgraph "Agent Layer - src/agent/"
        SUP["EmailOperationalSupervisor\nsupervisor.py"]
        ORCH["AdaptiveBusinessOrchestrator\norchestrator.py"]
        DOC_SVC["DocumentOnboardingService\ndocument_onboarding.py"]
        AUTO["AutopilotAgent (Gemini LLM)\nautopilot_agent.py"]
    end

    subgraph "Decision Layer - src/decision/"
        POLICY["PermissionEngine\npolicy_engine.py - Deterministic, no LLM"]
        DISPATCHER["ActionDispatcher\naction_dispatcher.py - Simulated Handlers"]
        APPROVAL["PurchaseApprovalService\napproval_service.py"]
        BIZ_AUTO["BusinessAutopilotV2\nbusiness_autopilot.py"]
    end

    subgraph "Integration Layer - src/integrations/"
        PAY_ADAPTER["AmazonPayAdapter\namazon_pay/adapter.py\nMock mode (no live credentials)"]
        PAY_CLIENT["AmazonPayClient\namazon_pay/client.py\nRSA-SHA256 signed HTTP"]
        PLACES_ADAPTER["GooglePlacesAdapter\ngoogle_places/adapter.py"]
        PLACES_DETAIL["PlaceDetailsClient\ngoogle_places/place_details.py"]
        ZOHO["ZohoBooksAdapter\nzoho_books/adapter.py"]
        META["MetaAdapter\nmeta/adapter.py\nScaffolded only"]
        BASE["IntegrationBase\nbase.py - exceptions, sanitize, dotenv"]
    end

    subgraph "Persistence Layer - src/db/"
        EMAIL_REPO["EmailRepository"]
        TASK_REPO["TaskRepository"]
        PROFILE_REPO["AdaptiveProfileRepository"]
        TOKEN_STORE["TokenStore\ntoken_store.py\nFernet-encrypted OAuth tokens"]
        CONN["Connection + Schema - connection.py"]
    end

    subgraph "Data Store"
        SQLITE[("SQLite data/demo.db\nautopilot_* tables + 45 domain tables\nautopilot_oauth_tokens (new)")]
    end

    subgraph "External APIs (Live - requires credentials)"
        AMZN_API["Amazon Pay India API\npay-api.amazon.in/sandbox/v2"]
        GPLACES_API["Google Places API (New)\nplaces.googleapis.com"]
        ZOHO_API["Zoho Books API\nwww.zohoapis.in"]
        META_API["Meta Graph API\ngraph.facebook.com\n(not yet called)"]
    end

    EMAIL --> WEB
    DOC --> WEB
    OWNER --> WEB
    OWNER --> MCP

    WEB --> SUP
    WEB --> ORCH
    WEB --> DOC_SVC
    WEB --> PAY_ADAPTER
    WEB --> META
    MCP --> SUP
    MCP --> ORCH

    SUP --> POLICY
    SUP --> TASK_REPO
    SUP --> EMAIL_REPO
    SUP --> PROFILE_REPO

    ORCH --> PROFILE_REPO
    ORCH --> BIZ_AUTO

    POLICY --> DISPATCHER
    DISPATCHER --> TASK_REPO

    PAY_ADAPTER --> PAY_CLIENT
    PAY_CLIENT -.->|live sandbox only| AMZN_API
    PLACES_ADAPTER -.->|live only| GPLACES_API
    PLACES_DETAIL -.->|live only| GPLACES_API
    ZOHO -.->|live only| ZOHO_API
    META -.->|not yet called| META_API

    AUTH -->|would save to| TOKEN_STORE
    TOKEN_STORE --> SQLITE

    TASK_REPO --> CONN
    EMAIL_REPO --> CONN
    PROFILE_REPO --> CONN
    CONN --> SQLITE
```

> **Note on the Auth Router:** `src/server/auth_routes.py` defines an `APIRouter` and is imported in `web_app.py`, but `app.include_router(auth_router)` is **never called**. The `/auth/*` endpoints are therefore **not reachable** at runtime in the current codebase.

### Multi-Tenant Design

Each business has a `business_id` that is set at **ingestion time** from the server's trusted context — never from untrusted email or document contents. All repository queries enforce `business_id` as a mandatory filter so no business can access another's data.

---

## 3. End-to-End Execution Walkthrough

The following describes one complete cycle: **incoming email → task creation → analysis → owner approval → execution → audit history**.

### Step 1 — Ingest Email

```
POST /api/emails/ingest
{
  "message_id": "msg-001",
  "business_id": "kiranamart_001",   <-- SET BY SERVER (trusted context)
  "sender": {"email": "supplier@example.com"},
  "subject": "Wholesale Rice Quote",
  "body_text": "We can offer 500kg at Rs 40/kg ..."
}
```

The `EmailRepository` persists the email with:
- `is_untrusted = True` (architectural guarantee on all external data)
- `content_hash` = SHA-256(sender + normalized_subject + body) for exact-duplicate detection
- `normalized_subject` stripped of Re:/Fwd: prefixes for thread correlation

### Step 2 — Trigger Supervisor Analysis

```
POST /api/emails/msg-001/process
```

`EmailOperationalSupervisor.process_email(email)` executes:

1. Loads the `AdaptiveBusinessProfile` for `kiranamart_001` from `AdaptiveProfileRepository`
2. Creates an `OperationalTask` (`state=RECEIVED`) linked to the email
3. Classifies intent via deterministic keyword/pattern matching → `state=CLASSIFIED`
4. Retrieves relevant confirmed business facts from the profile
5. Builds `ActionProposal` objects for each proposed action
6. Each proposal evaluated by `PermissionEngine.evaluate_action()`:
   - `classify_task` → **ALLOW** (low-risk internal, autonomous)
   - `send_external_email` → **REQUIRE_APPROVAL** (consequential)
   - Unknown action type → **DENY** (fail-closed)
7. Task transitions to `AWAITING_APPROVAL` or `WORKING` depending on proposals

### Step 3 — Owner Reviews and Approves

```
POST /api/actions/{action_id}/approve
{
  "actor_id": "owner:rajesh",
  "execution_payload": { ... exact payload ... }
}
```

`PermissionEngine.verify_approval()` runs three independent checks:

1. **Tenant isolation**: `proposal.business_id == request.business_id`
2. **Actor authorization**: `actor_id` in `authorized_owners[business_id]`
3. **Payload hash match**: `SHA-256(execution_payload) == proposal.payload_hash`

All three must pass. Failure in any one check rejects the execution.

### Step 4 — Execute Action

```
POST /api/actions/{action_id}/dispatch
{
  "actor_id": "owner:rajesh",
  "execution_payload": { ... }
}
```

`ActionDispatcher.dispatch_action()`:
1. Re-evaluates policy (not cached)
2. Verifies approval and hash
3. Checks idempotency key (prevents double-execution)
4. Calls `SimulatedHandler` (no live external APIs)
5. Records `ExecutionReceipt` to `autopilot_action_executions`
6. Appends immutable audit log entry
7. Transitions task to `COMPLETED` or `EXECUTION_UNCERTAIN`

### Step 5 — Audit History

```
GET /api/tasks/{task_id}
```

Returns the full task with state transition history from `autopilot_task_audit_log` (append-only, never updated or deleted).

> **Integration Note:** The Amazon Pay and Meta adapters instantiated in `web_app.py` are **not connected** to the `EmailOperationalSupervisor`, `PermissionEngine`, or `ActionDispatcher`. Payment operations do not flow through the approval pipeline. This is an explicit gap documented in Section 12.

---

## 4. AI vs. Deterministic Layer Analysis

### Component Classification

| Component | File | Type | Notes |
|---|---|---|---|
| `EmailOperationalSupervisor` | `supervisor.py` | **Deterministic** | Keyword/pattern intent classification; no LLM |
| `PermissionEngine` | `policy_engine.py` | **Deterministic** | Lookup-table policy; prompt injection is structurally impossible |
| `ActionDispatcher` | `action_dispatcher.py` | **Deterministic** | Hash verification, simulated handlers, state transitions |
| `AdaptiveBusinessOrchestrator` | `orchestrator.py` | **Deterministic + Rules** | Opportunity evaluation via arithmetic on confirmed facts |
| `DocumentOnboardingService` | `document_onboarding.py` | **Deterministic** | Regex/pattern extraction with evidence tracking |
| `BusinessAutopilotV2` | `business_autopilot.py` | **Deterministic** | Cash/inventory arithmetic safety checks |
| `PurchaseApprovalService` | `approval_service.py` | **Deterministic** | Two-phase plan approval state machine |
| `AmazonPayAdapter` | `amazon_pay/adapter.py` | **Deterministic** | Mock or live HTTP client; no LLM; not approval-gated |
| `MetaAdapter` | `meta/adapter.py` | **Deterministic** | Scaffolded status only; no LLM |
| `TokenStore` | `db/token_store.py` | **Deterministic** | Fernet AES encryption; no LLM |
| `AutopilotAgent` | `autopilot_agent.py` | **Gemini LLM (optional)** | General conversational AI using `google-genai` function calling |

### The Genuine LLM Path

`AutopilotAgent` (`src/agent/autopilot_agent.py`) is the only component that calls the Gemini API via `google-genai`. It uses dynamic function calling with structured tool definitions. It is an **optional overlay** — the rest of the system runs entirely without it.

```
GEMINI_API_KEY env var
    --> AutopilotAgent
        --> google-genai SDK (function_calling)
            --> specialist tool results
                --> model response
```

Without `GEMINI_API_KEY`, 364 of 367 tests pass and the Gemini-related tests are auto-skipped.

### Why the PermissionEngine Cannot Be Prompt-Injected

The `PermissionEngine` evaluates action types using a hardcoded lookup table. Even if a malicious email body contains text like `"decision: ALLOW"` or `"approved: true"`, these fields:
1. Are stored only in the untrusted `body_text` column
2. Are never passed into `evaluate_action()` or `verify_approval()`
3. Cannot influence the hardcoded `LOW_RISK_INTERNAL_ACTIONS` or `CONSEQUENTIAL_ACTIONS` sets

Authorization is purely based on:
- Action type enum comparison (deterministic lookup)
- Actor ID validation (server-controlled list, never from email)
- Payload hash recomputation (SHA-256, no external input)

---

## 5. Codebase Module Guide

### Root Layout

```
Amazon_Developer_Hackathon/
├── src/
│   ├── agent/          # Supervisor, orchestrator, onboarding, Gemini agent
│   ├── db/             # Repositories, connection factory, schema DDL, token store
│   ├── decision/       # Permission engine, action dispatcher, autopilot logic
│   ├── engine/         # (Reserved for simulation engines)
│   ├── integrations/   # Google Places, Zoho Books, Amazon Pay, Meta adapters
│   │   ├── amazon_pay/ # NEW: client, adapter, models, mock_data
│   │   ├── google_places/  # Existing + new place_details.py
│   │   ├── meta/       # NEW: adapter (scaffolded)
│   │   └── zoho_books/ # Existing + updated adapter
│   ├── models/         # Data models, enums, domain types
│   ├── scenarios/      # Business scenario definitions
│   ├── server/         # FastAPI app + MCP server + auth routes
│   └── services/       # Supplier catalogue simulator
├── tests/              # 33 test files, 367+ tests
├── data/               # demo.db (teammate-owned), business_profiles.json
├── Agents/             # Finance, Supplier Intelligence specialist agents
├── .env.example        # Updated: Amazon Pay, Meta, token encryption vars
├── requirements.txt
└── AGENTS.md           # Development guidelines and rules
```

### `src/agent/` — Agent Layer

| File | Description |
|---|---|
| `supervisor.py` | `EmailOperationalSupervisor`: email → task → policy → action proposal pipeline |
| `orchestrator.py` | `AdaptiveBusinessOrchestrator`: chat, fact extraction, opportunity evaluation |
| `document_onboarding.py` | `DocumentOnboardingService`: PDF/CSV/XLSX/TXT parsing with evidence provenance |
| `onboarding.py` | Earlier v1 onboarding agent; partially superseded by orchestrator |
| `autopilot_agent.py` | `AutopilotAgent`: optional Gemini LLM agent with function calling |
| `tools.py` | Specialist tool definitions for the Gemini agent |

### `src/db/` — Persistence Layer

| File | Description |
|---|---|
| `connection.py` | `get_connection()`, `initialize_database()`, `seed_business_state()`, DDL V1–V3 |
| `task_repository.py` | Full task/action/audit/execution CRUD, state transition enforcement, approval verification |
| `email_repository.py` | Email persistence, SHA-256 duplicate detection, thread correlation, business-scoped queries |
| `profile_repository.py` | Adaptive profile and business fact CRUD with full provenance |
| `plan_repository.py` | Purchase plan persistence (legacy two-phase approval system) |
| `state_repository.py` | Live cash/inventory state for legacy static business profiles |
| `token_store.py` | **NEW** `TokenStore`: Fernet-encrypted OAuth refresh token persistence per merchant+provider |

### `src/decision/` — Decision and Safety Layer

| File | Description |
|---|---|
| `policy_engine.py` | `PermissionEngine`: ALLOW/REQUIRE_APPROVAL/DENY with three-check verification |
| `action_dispatcher.py` | `ActionDispatcher`: controlled execution, simulated handlers, hash binding, idempotency |
| `approval_service.py` | `PurchaseApprovalService`: legacy two-phase approval for purchase plans |
| `business_autopilot.py` | `BusinessAutopilotV2`: cash/inventory/capacity safety arithmetic |
| `autopilot.py` | Earlier v1 autopilot logic |

### `src/models/` — Data Models

| File | Key Types |
|---|---|
| `task.py` | `TaskState` (12 states), `VALID_TRANSITIONS`, `ActionType`, `PolicyDecision`, `OperationalTask`, `ActionProposal`, `compute_payload_hash()` |
| `email.py` | `InboundEmail`, `EmailAddress`, `EmailAttachment`, `normalize_subject()`, SHA-256 content hash |
| `adaptive_profile.py` | `AdaptiveBusinessProfile`, `BusinessFact`, `FactStatus`, `FactSource`, `to_standard_business_profile()` |
| `business.py` | `BusinessProfile` (legacy static schema for simulator compatibility) |
| `recipe.py` | `TiffinRecipeManager`, `STANDARD_TIFFIN_RECIPE` (food-specific, used only for tiffin profile) |
| `simulation.py` | Causal simulation result models |
| `customer.py` | Customer acquisition/retention models |
| `inventory.py` | Inventory management models |

### `src/integrations/` — External Integration Layer

#### Base (`src/integrations/base.py`) — Updated

| Symbol | Description |
|---|---|
| `IntegrationError` | Base exception; auto-sanitizes credentials from error messages |
| `ValidationError`, `AuthenticationError`, `RateLimitError`, `ProviderUnavailableError` | Provider-specific exception subclasses |
| `sanitize_credentials()` | Strips API keys, Bearer tokens, OAuth secrets from any string before logging |
| `load_dotenv_safe()` | **NEW** Reads `.env` file at project root into `os.environ` on module import (keys already set are preserved) |
| `IntegrationConfig` | Helper: `is_mock_enabled()`, `get_google_maps_api_key()`, `get_zoho_config()` |

#### Amazon Pay (`src/integrations/amazon_pay/`) — New Package

| File | Class/Symbol | Description |
|---|---|---|
| `models.py` | `AmazonPayCharge` | Charge dataclass: amount, currency, state (Chargeable/Captured/Declined/Canceled) |
| `models.py` | `AmazonPayRefund` | Refund dataclass: refund amount, state (Pending/Refunded/Declined) |
| `models.py` | `AmazonPayChargePermission` | Long-lived charge authorization, merchant limits, buyer identity |
| `models.py` | `AmazonPayWebhookEvent` | Parsed IPN webhook notification (CHARGE_CAPTURED, REFUND_COMPLETED, etc.) |
| `models.py` | `AmazonPayPaymentSummary` | Aggregated payment metrics for a merchant |
| `mock_data.py` | `MOCK_CHARGES`, `MOCK_REFUNDS`, `MOCK_CHARGE_PERMISSION`, `MOCK_PAYMENT_SUMMARY` | Realistic INR sample data (Kanpur merchant) |
| `client.py` | `AmazonPayClient` | Low-level HTTP client: RSA-SHA256 `AMZN-PAY-RSASSA-PSS-V2` signed requests, retry logic, per-status-code error mapping |
| `adapter.py` | `AmazonPayAdapter` | High-level orchestration: auto-detects live vs mock from env vars; exposes `get_charge()`, `create_charge()`, `create_refund()`, `list_recent_charges()`, `get_payment_summary()`, `parse_webhook_event()`, `get_status()` |
| `__init__.py` | Package exports | Re-exports `AmazonPayAdapter` and all models |

#### Google Places (`src/integrations/google_places/`) — Extended

| File | Class/Symbol | Description |
|---|---|---|
| `adapter.py` | `GooglePlacesAdapter` | Existing nearby-search adapter (unchanged) |
| `place_details.py` | `PlaceDetailsClient` | **NEW** Rich single-place lookup: opening hours, phone, website, editorial summary, rating, price level |
| `place_details.py` | `PlaceDetails` | Dataclass for normalized place detail response |
| `place_details.py` | `OpeningHoursPeriod` | Day/time open-close period within `PlaceDetails` |
| `place_details.py` | `get_place_details_mock()` | Mock fallback returning a realistic Kanpur tiffin competitor |

#### Meta (`src/integrations/meta/`) — New Package (Scaffolded)

| File | Class/Symbol | Description |
|---|---|---|
| `adapter.py` | `MetaAdapter` | Auto-detects live vs mock from `META_ACCESS_TOKEN`, `META_APP_ID`, `META_APP_SECRET`; currently only implements `get_status()` — no Graph API calls are made |
| `__init__.py` | Package exports | Re-exports `MetaAdapter` |

#### Zoho Books (`src/integrations/zoho_books/`) — Updated

| Change | Description |
|---|---|
| Month name parsing fix | `adapter.py` now parses string month names (e.g. `"October"`) in addition to integer months; prevents `ValueError` on real Zoho invoice date fields |
| Scope handling | Handles cases where `scope` field is absent or None in token response without crashing |
| Auto `.env` loading | Via `base.py` `load_dotenv_safe()` called on import; credentials load automatically without manual `python-dotenv` dependency |

### `src/server/` — Interface Layer

| File | Description |
|---|---|
| `web_app.py` | FastAPI application: 35 REST endpoints, `AmazonPayAdapter` and `MetaAdapter` instantiated as singletons; auth router imported but **not mounted** |
| `mcp_server.py` | FastMCP server: 33 MCP tools, `create_mcp_server()` factory for dependency injection |
| `auth_routes.py` | **NEW** `APIRouter` at `/auth` prefix with OAuth login/callback/status/disconnect routes; instantiates its own `TokenStore`; **not yet registered with the FastAPI app** |

---

## 6. Database and Persistence Architecture

### Overview

Single SQLite file (`data/demo.db`) with WAL journal mode. Autopilot-owned tables are prefixed `autopilot_*` and created additively via `CREATE TABLE IF NOT EXISTS`. Teammate-owned domain tables (45+) are never touched.

### Schema Version History

| Version | Tables Added | Purpose |
|---|---|---|
| V1 | `autopilot_schema_migrations`, `autopilot_business_state`, `autopilot_purchase_plans`, `autopilot_plan_items`, `autopilot_audit_events`, `autopilot_execution_receipts` | Legacy purchase plan lifecycle |
| V2 | `autopilot_provider_connections` | External provider connection tracking (Places, Zoho) |
| V3 | `autopilot_business_profiles`, `autopilot_business_facts` | Adaptive multi-business profiles and provenance facts |
| V4 (new) | `autopilot_oauth_tokens` | Encrypted per-merchant OAuth refresh token storage |

### Phase 4 Tables (created by `TaskRepository.initialize_schema()`)

| Table | Purpose |
|---|---|
| `autopilot_inbound_emails` | Normalized email storage with SHA-256 content hash for deduplication |
| `autopilot_email_attachments` | Attachment metadata linked to inbound emails |
| `autopilot_tasks` | Operational tasks with 12-state lifecycle and `version` column for optimistic concurrency |
| `autopilot_action_proposals` | Action proposals with SHA-256 `payload_hash`, approval status, idempotency key |
| `autopilot_task_audit_log` | Append-only audit trail for task state transitions |
| `autopilot_action_executions` | Execution receipts for dispatched actions |

### New: `autopilot_oauth_tokens` Table

Created on `TokenStore.__init__()`, independently of the main connection factory DDL.

| Column | Type | Notes |
|---|---|---|
| `provider` | TEXT | Provider name (e.g. `zoho_books`) — part of composite primary key |
| `merchant_id` | TEXT | Merchant identifier — part of composite primary key; defaults to `"default"` |
| `token_blob` | TEXT | Fernet-encrypted (or `b64:`-prefixed) refresh token — never stored in plaintext |
| `scopes` | TEXT | OAuth scope string granted at authorization time |
| `created_at` | TEXT | ISO-8601 UTC timestamp of initial storage |
| `updated_at` | TEXT | ISO-8601 UTC timestamp of last update |

### Connection Configuration

```python
conn = sqlite3.connect(db_path, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")   # concurrent readers during writes
conn.execute("PRAGMA foreign_keys=ON")    # cascade deletes enforced
conn.execute("PRAGMA busy_timeout=5000")  # 5s retry before SQLITE_BUSY
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| No ORM | Zero extra dependencies; raw `sqlite3` for full control |
| WAL mode | Safe for FastAPI thread pool; concurrent reads during writes |
| INSERT OR IGNORE seeding | `seed_business_state()` never overwrites live operator cash/inventory |
| Optimistic concurrency | `version` column on tasks detects concurrent updates |
| Append-only audit | `autopilot_task_audit_log` entries are never updated or deleted |
| Schema versioning | `autopilot_schema_migrations` tracks applied DDL versions; `initialize_database()` is idempotent |
| Fernet token encryption | Optional AES-128-CBC + HMAC-SHA256 at rest for OAuth tokens; base64 fallback for dev |

---

## 7. Security and Authorization Model

### Trust Boundary

```
UNTRUSTED (never used for auth/identity)     TRUSTED (server-controlled)
--------------------------------------------  ------------------------------
Email From: header                            business_id at ingestion
Email body / subject text                     actor_id from HTTP auth header
Attachment content                            PermissionEngine lookup tables
Document text                                 Authorized owner registry
Any LLM-generated text                        SHA-256 hash recomputed server-side
OAuth state parameter (merchant hint only)    TOKEN_ENCRYPTION_KEY (server env)
```

### Three-Check Approval Verification

`PermissionEngine.verify_approval()` runs three independent checks before any consequential action executes:

**Check 1 — Tenant Isolation**
```
proposal.business_id == executing_business_id
```
If different: `TENANT_MISMATCH` error. Cannot approve actions across businesses.

**Check 2 — Actor Authorization**
```
actor_id in authorized_owners[business_id]
Default: actor_id must start with "owner:" or "admin:"
```
If not authorized: `UNAUTHORIZED_ACTOR` error.

**Check 3 — Payload Hash Match (Cryptographic Binding)**
```
SHA-256(json.dumps(execution_payload, sort_keys=True)) == proposal.payload_hash
```
If tampered: `PAYLOAD_HASH_MISMATCH` error. Fresh approval is required.

### Action Risk Classification

| Risk Level | Action Types | Policy Decision |
|---|---|---|
| **LOW** | `classify_task`, `create_internal_task`, `retrieve_information`, `generate_summary`, `create_internal_draft` | `ALLOW` — autonomous execution |
| **HIGH** | `send_external_email`, `send_binding_quotation`, `schedule_appointment`, `create_purchase_order`, `modify_confirmed_fact` | `REQUIRE_APPROVAL` |
| **CRITICAL** | `execute_payment`, `issue_refund` | `REQUIRE_APPROVAL` (highest risk) |
| **UNKNOWN** | Anything not in the above two sets | `DENY` (fail-closed) |

### Production Environment Flag

When `AUTOPILOT_ENV=production`, test-mode header authentication (`X-Autopilot-Actor-Id`) is disabled. Production deployments require proper OAuth-backed owner verification.

### New Security Considerations (commit c3277da)

#### OAuth Callback State Parameter
`auth_routes.py` uses the `state` query parameter to round-trip the `merchant_id` from `/auth/{provider}/login` to `/auth/{provider}/callback`. This is **not** a full CSRF protection mechanism: a proper CSRF defense would require a cryptographically random, server-stored nonce bound to the user's session, compared on callback. The current `state=merchant_id` approach only identifies *which* merchant is connecting, not that the callback originated from the server's own redirect.

#### Auth Router Not Mounted
The `auth_routes.APIRouter` is imported in `web_app.py` but `app.include_router(auth_router)` is never called. The `/auth/*` endpoints do not exist at runtime. The `TokenStore` they would populate is therefore not populated through any active HTTP path.

#### Token Storage Security
- Refresh tokens are encrypted with Fernet AES-128-CBC + HMAC-SHA256 when `TOKEN_ENCRYPTION_KEY` is set.
- Without the encryption key, tokens are stored as `b64:`-prefixed base64 — not encrypted, only encoded. This is flagged in the log with a `WARNING` message.
- Token blobs are written to `autopilot_oauth_tokens` in the same `data/demo.db` shared with domain tables. Database-level encryption (SQLCipher) is not implemented.
- `list_connections()` returns provider/merchant metadata only — token values are never returned by any public API.
- No token expiry column exists. Fernet tokens do not expire server-side; only the OAuth provider's refresh token validity window determines lifetime.
- No automatic token refresh logic is implemented. If a Zoho refresh token expires, the adapter falls back to mock mode silently.

#### Amazon Pay Security Model
Amazon Pay uses RSA-SHA256 signed requests (Signature V2) with a merchant public/private key pair — not OAuth. The private key path is read from `AMAZON_PAY_PRIVATE_KEY_PATH` at startup. No token store is involved. The key is loaded from the filesystem and held in memory for the process lifetime.

#### Payment Operations and the Approval Gate
`execute_payment` and `issue_refund` are classified as `CRITICAL` / `REQUIRE_APPROVAL` in `PermissionEngine`. However, `AmazonPayAdapter.create_charge()` and `create_refund()` are direct Python calls that bypass the permission engine entirely. There is **no integration** between the Amazon Pay adapter and the approval pipeline. A caller with HTTP access to the integration layer could theoretically invoke payment operations without owner approval if a REST endpoint were added without gating.

#### MCP Authentication
The MCP server (`/mcp` and `/sse`) has no built-in authentication. Any process with network access to the FastAPI server can call all 33 MCP tools, including `approve_action_proposal` and `dispatch_action`.

---

## 8. REST API Reference

FastAPI app (`src/server/web_app.py`). MCP is mounted at `/mcp` (Streamable HTTP) and `/sse` (SSE).

> **Endpoint count:** 35 REST endpoints registered in `web_app.py`. The `/auth/*` router is defined but not mounted and therefore not counted.

### Infrastructure

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health probe with db path, version, MCP status |
| GET | `/` | Root info page with endpoint listing |

### Business State (Legacy Profiles)

| Method | Path | Description |
|---|---|---|
| GET | `/api/state` | Live cash/inventory state (adaptive profile or legacy fallback) |
| POST | `/api/evaluate` | Opportunity evaluation with recipe shortage and supplier quote |
| POST | `/api/confirm_plan` | Approve or reject a legacy purchase plan |
| POST | `/api/execute_plan` | Execute an approved legacy purchase plan (simulated) |

### External Integrations

| Method | Path | Description |
|---|---|---|
| GET | `/api/integrations/status` | Status of Google Places, Zoho Books, **Amazon Pay**, and **Meta** |
| POST | `/api/integrations/places/nearby` | Find nearby businesses/suppliers (mock mode) |
| GET | `/api/integrations/zoho/organization` | Zoho Books organization details |
| GET | `/api/integrations/zoho/invoices` | Paginated sales invoices |
| GET | `/api/integrations/zoho/expenses` | Operating expenses and vendor bills |

### Adaptive Business Onboarding

| Method | Path | Description |
|---|---|---|
| POST | `/api/onboarding/chat` | Conversational onboarding message for any business type |
| GET | `/api/business/profiles` | List all onboarded adaptive profiles |
| GET | `/api/business/{business_id}` | Get full profile with fact breakdown |
| PUT | `/api/business/{business_id}/facts` | Update a specific business fact |
| DELETE | `/api/business/{business_id}` | Delete a business profile |
| POST | `/api/orchestrator/query` | General orchestrator query with intent routing |

### Email Ingestion (Phase 1)

| Method | Path | Description |
|---|---|---|
| POST | `/api/emails/ingest` | Persist a normalized inbound email; returns email_id |
| POST | `/api/emails/{email_id}/process` | Trigger supervisor analysis for an ingested email |

### Task Lifecycle (Phase 2)

| Method | Path | Description |
|---|---|---|
| GET | `/api/tasks` | List tasks for a business, optionally filtered by state |
| GET | `/api/tasks/{task_id}` | Get full task with audit log |
| GET | `/api/tasks/{task_id}/actions` | List action proposals for a task |

### Action Proposals and Approval (Phases 2–4)

| Method | Path | Description |
|---|---|---|
| GET | `/api/actions/{action_id}` | Get action proposal with payload hash and approval status |
| POST | `/api/actions/{action_id}/approve` | Owner approval with hash binding verification |
| POST | `/api/actions/{action_id}/reject` | Reject action with documented reason |
| POST | `/api/actions/{action_id}/dispatch` | Execute an approved action via ActionDispatcher |

### Execution and Audit (Phase 4)

| Method | Path | Description |
|---|---|---|
| GET | `/api/executions` | List execution history for a business or task |
| POST | `/api/executions/{action_id}/reconcile` | Owner-directed reconciliation of EXECUTION_UNCERTAIN actions |

### Document Onboarding (Phase 3)

| Method | Path | Description |
|---|---|---|
| POST | `/api/documents/onboard` | Upload and process a business document (PDF/CSV/XLSX/TXT) |
| POST | `/api/documents/verify-fact` | Owner verification of a document-extracted fact |

### OAuth Connection Management — Defined but NOT Mounted

The following routes are implemented in `src/server/auth_routes.py` but are **not reachable** because `app.include_router()` is never called:

| Method | Path | Description |
|---|---|---|
| GET | `/auth/{provider}/login` | Returns OAuth redirect URL for merchant to begin provider authorization |
| GET | `/auth/{provider}/callback` | Receives authorization code, exchanges for refresh token, stores encrypted |
| GET | `/auth/{provider}/status` | Checks whether a merchant has a stored token for a provider |
| DELETE | `/auth/{provider}/disconnect` | Deletes stored token for a merchant+provider pair |
| GET | `/auth/connections` | Lists all connected providers for a merchant (no token values) |

---

## 9. MCP Server and Tools Reference

Uses `FastMCP` from the official `mcp` Python SDK (`mcp>=1.0.0`). Instantiated via `create_mcp_server()` factory for dependency injection in tests.

> **Tool count: 33 — unchanged from Phase 4.** The new integration adapters (Amazon Pay, Meta) are accessible via REST only; no new MCP tools were added in commit `c3277da`.

### Tools 1–10: Business Economics and Procurement (Phase 0)

| # | Tool Name | Description |
|---|---|---|
| 1 | `get_business_state` | Economics, capacity, cash for any business (adaptive or legacy) |
| 2 | `get_upcoming_orders` | Scheduled baseline demand for tomorrow |
| 3 | `get_financial_position` | Liquid cash, safety reserve, usable capital |
| 4 | `get_tiffin_recipe_breakdown` | Multi-ingredient recipe calculation (tiffin-specific) |
| 5 | `get_supplier_quotes` | Simulated supplier pricing catalogue |
| 6 | `evaluate_procurement_decision` | APPROVE/REJECT procurement with cash safety check |
| 7 | `create_purchase_plan` | Two-phase purchase plan requiring approval |
| 8 | `confirm_purchase_plan` | Owner approval or rejection of plan |
| 9 | `execute_purchase_plan` | Execute an approved purchase plan (simulated) |
| 10 | `get_causal_demand_forecast` | Causal demand/marketing/seasonal simulation |

### Tools 11–15: Specialist Agents (Phase 0 extended)

| # | Tool Name | Description |
|---|---|---|
| 11 | `get_finance_analysis` | Cash flow, gross margin, breakeven (FinanceAgent) |
| 12 | `get_supplier_intelligence` | Supplier discovery and risk analysis (SupplierIntelligenceAgent) |
| 13 | `get_customer_acquisition_metrics` | CAC, conversion rate, LTV estimation |
| 14 | `get_inventory_optimization` | EOQ, reorder points, safety stock calculation |
| 15 | `get_market_opportunity_score` | Market sizing for new order opportunities |

### Tools 16–19: External Integrations

| # | Tool Name | Description |
|---|---|---|
| 16 | `get_zoho_organization` | Zoho Books organization and currency details |
| 17 | `get_zoho_invoices` | Paginated sales invoices and AR balances |
| 18 | `get_zoho_expenses_and_bills` | Operating expenses and vendor bills |
| 19 | `get_external_integrations_status` | Google Places, Zoho Books, Amazon Pay, and Meta connection status |

### Tools 20–23: Adaptive Business Profiles

| # | Tool Name | Description |
|---|---|---|
| 20 | `onboard_or_chat_business` | Conversational onboarding for any Indian micro-enterprise |
| 21 | `get_adaptive_business_profile` | Full profile with confirmed/assumed/unknown fact breakdown |
| 22 | `list_adaptive_business_profiles` | List all onboarded businesses |
| 23 | `evaluate_adaptive_opportunity` | Business-agnostic capacity/cash opportunity check |

### Tools 24–33: Phase 4 — Task Lifecycle and Controlled Execution

| # | Tool Name | Description |
|---|---|---|
| 24 | `list_operational_tasks` | Tasks for a business, filtered by lifecycle state |
| 25 | `get_operational_task` | Full task with actions and audit trail |
| 26 | `list_pending_approvals` | All actions awaiting owner approval |
| 27 | `get_action_proposal` | Action proposal with payload hash and status |
| 28 | `approve_action_proposal` | Owner approval with hash binding check |
| 29 | `reject_action_proposal` | Owner rejection with documented reason |
| 30 | `dispatch_action` | Execute via ActionDispatcher (fully simulated) |
| 31 | `list_execution_history` | Execution receipts for business or task |
| 32 | `reconcile_uncertain_execution` | Owner-directed EXECUTION_UNCERTAIN resolution |
| 33 | `process_incoming_email` | Trigger supervisor analysis for an ingested email |

---

## 10. Document Onboarding Workflow

`DocumentOnboardingService` (`src/agent/document_onboarding.py`) provides evidence-backed fact extraction from uploaded documents.

### Processing Pipeline

```
Upload: PDF / CSV / XLSX / TXT (raw bytes + filename)
    |
    v
DocumentParser.parse_*()
    |
    v
List[DocumentEvidence]
  { file_name, format, location, raw_snippet, extracted_at }
    |
    v
FactExtractor.extract_facts_from_evidence()
    |
    v
List[ExtractedFactCandidate]
  { key, value, confidence, evidence, is_conflict, conflict_notes }
    |
    v
Conflict Detection vs existing confirmed facts
    |
    +---> New fact: write to AdaptiveBusinessProfile
    |     FactSource=INFERRED, FactStatus=ASSUMED
    |
    +---> Conflicting fact: flag as conflict, require owner verification
    |
    v
Persist via AdaptiveProfileRepository
    |
    v
Owner verifies via POST /api/documents/verify-fact
    |
    v
Fact promoted to FactStatus.CONFIRMED + FactSource.USER_STATED
```

### Evidence Provenance

Every extracted fact carries a `DocumentEvidence` record. This makes every business fact fully traceable to its source:

| Field | Example |
|---|---|
| `file_name` | `price_list_2024.csv` |
| `format` | `csv` |
| `location` | `Row 12, Col 'Price'` |
| `raw_snippet` | `"500g Basmati Rice, 45.00"` |
| `extracted_at` | `2026-10-18T07:00:00Z` |

### Supported Formats

| Format | Parser | Notes |
|---|---|---|
| TXT | Native Python | Line-by-line extraction |
| CSV | `csv.DictReader` | Row/column provenance |
| XLSX | `zipfile` + XML (no openpyxl) | Sheet/row/column provenance; zero binary deps |
| PDF | Embedded text stream extraction | Page-level provenance; no OCR for scanned images |

---

## 11. Phase 0–4 Completion Summary

### Phase 0 — Business-Agnostic Foundation ✅ Complete

- `AdaptiveBusinessProfile` model with `BusinessFact` provenance tracking
- `AdaptiveProfileRepository` persisting profiles and facts to SQLite
- `AdaptiveBusinessOrchestrator` for chat-based onboarding and opportunity evaluation
- `business_init.schema.json` defining onboarding schema for any vertical
- Legacy `BusinessProfile` simulator preserved without modification
- `to_standard_business_profile()` bridge for backward compatibility
- Phase 0 routing safety tests confirming no tiffin-only defaults leak to other business types

### Phase 1 — Email Ingestion ✅ Complete

- `InboundEmail`, `EmailAddress`, `EmailAttachment` models with `is_untrusted=True` guarantee
- SHA-256 content hash for exact-duplicate detection
- `normalize_subject()` strips Re:/Fwd: for thread correlation
- `EmailRepository` with full CRUD, deduplication, business-scoped queries
- Mock email provider adapter (`src/integrations/email_provider.py`)
- Disposable in-memory test databases via conftest fixtures

### Phase 2 — Durable Task Lifecycle and Permission Engine ✅ Complete

- `TaskState` enum with 12 states and validated `VALID_TRANSITIONS` lookup table
- `OperationalTask` with optimistic concurrency (version column)
- `ActionProposal` with immutable SHA-256 `payload_hash`
- `PermissionEngine` with `evaluate_action()` and `verify_approval()` (three-check)
- `TaskRepository` with full task/action/audit/execution CRUD
- `autopilot_tasks`, `autopilot_action_proposals`, `autopilot_task_audit_log` tables

### Phase 3 — Agent Orchestration and Document Onboarding ✅ Complete

- `EmailOperationalSupervisor` connecting email → task → classification → fact retrieval → action proposal → policy evaluation
- `SupervisorExecutionResult` with full action disposition breakdown
- `DocumentOnboardingService` with `DocumentParser` (PDF/CSV/XLSX/TXT) and `FactExtractor`
- `DocumentEvidence` provenance records with location, snippet, format
- Conflict detection against existing confirmed facts
- Owner verification flow for document-extracted facts
- REST endpoints: `POST /api/emails/ingest`, `POST /api/emails/{id}/process`, `/api/documents/*`

### Phase 4 — Controlled Execution and API/MCP Integration ✅ Complete

- `ActionDispatcher` with policy re-evaluation, hash binding, idempotency, EXECUTION_UNCERTAIN recovery
- Simulated handlers: `ExternalEmailHandler`, `BindingQuotationHandler`, `AppointmentHandler`, `PurchaseOrderHandler`
- `ExecutionReceipt` dataclass persisted to `autopilot_action_executions`
- 10 additional MCP tools (Tools 24–33) for task/action/execution lifecycle
- 10 additional REST endpoints for Phase 4 operations
- `POST /api/executions/{action_id}/reconcile` for owner-directed uncertainty resolution
- End-to-end test: `test_phase4_controlled_execution.py` (40KB, comprehensive scenarios)

### Post-Phase-4 Integration Work (commits dd5be3b + c3277da)

| Capability | Status |
|---|---|
| Amazon Pay `models.py` — dataclasses for Charge, Refund, ChargePermission, Webhook, Summary | Implemented and tested |
| Amazon Pay `mock_data.py` — realistic INR sample data for CI/demo | Implemented and tested |
| Amazon Pay `client.py` — RSA-SHA256 signed HTTP client, retry logic, per-code error mapping | Implemented with mock provider |
| Amazon Pay `adapter.py` — auto-mock fallback, charge/refund/permission/webhook/summary operations | Implemented with mock provider |
| Amazon Pay status in `/api/integrations/status` | Implemented and tested |
| Google Places `place_details.py` — rich single-place lookup (hours, phone, website, rating) | Implemented with mock provider |
| Meta `adapter.py` — status reporting stub, credentials detection | Scaffolded |
| Meta status in `/api/integrations/status` | Implemented and tested |
| `TokenStore` — Fernet-encrypted OAuth refresh token persistence | Implemented and tested |
| `auth_routes.py` — OAuth login URL generation, callback code exchange, status, disconnect | Partially implemented (not mounted) |
| Zoho Books month name parsing fix | Implemented and tested |
| `base.py` `load_dotenv_safe()` — automatic `.env` loading | Implemented and tested |
| `test_amazon_pay.py` — 19 mock tests, 1 live smoke test | Implemented and tested |

**Updated test count: 367 passed, 3 skipped, 0 failed in 20.06 seconds (user-verified)** (Gemini tests + Amazon Pay live smoke test skip without credentials)

---

## 12. Remaining Roadmap Gaps

### Gap Status Update Table

| Feature | Previous Status | Current Status | Evidence | Remaining Work |
|---|---|---|---|---|
| **Amazon Pay integration** | P2 — explicitly out of scope | Partially implemented (mock mode) | `src/integrations/amazon_pay/` package, 19 passing tests | Mount in approval pipeline; live sandbox testing; IPN webhook endpoint |
| **External-provider OAuth token storage** | Not implemented | Implemented (Fernet-encrypted SQLite) | `src/db/token_store.py`, `autopilot_oauth_tokens` table | Mount `auth_routes`; add CSRF nonce; add token refresh logic |
| **OAuth callback routes** | Not implemented | **Fully Implemented & Mounted** | `src/server/auth_routes.py`, `src/server/web_app.py` | Configure live external client secret in production |
| **Meta / social integration** | Not mentioned | Scaffolded only | `src/integrations/meta/adapter.py` — `get_status()` only | All Graph API calls; campaign metrics; post management |
| **Google Places place details** | Not implemented | Implemented with mock provider | `src/integrations/google_places/place_details.py` | Expose via REST endpoint or MCP tool |
| **Real owner authentication** | P0 gap | **Fully Implemented (PyJWT & TrustedPrincipal)** | `src/security/auth_service.py`, `src/models/principal.py`, `test_auth_and_security.py` | Live IdP federation (e.g. Amazon LWA / Cognito) |
| **MCP authentication** | P1 gap | **Fully Implemented (Streamable HTTP + Bearer Auth)** | `src/server/mcp_auth.py`, `src/server/mcp_server.py`, `test_remote_mcp.py` | None — 35 tools audited, scoped, latency verified <50ms |
| **Persistent conversation sessions** | P1 gap | **Fully Implemented (SQLite Schema v4)** | `src/db/session_repository.py`, `src/models/session.py`, `test_conversation_sessions.py` | None — multi-turn restart survival verified |
| **Live Gmail/Outlook** | P1 gap | **Unchanged** | Email provider is still mock | Gmail OAuth adapter (assigned to another developer) |
| **Owner notification on AWAITING_APPROVAL** | P1 gap | **Unchanged** | No notification wired | Push/webhook/SMS on state transition |
| **Amazon Pay → ActionDispatcher integration** | N/A (new) | Not implemented | Adapters are parallel, not connected | Wire payment adapter calls through PermissionEngine + approval gate |
| **Zoho Books live mode** | P1 gap | Partially resolved | Month/scope bugs fixed; auto-.env loading added | Token refresh not implemented; no live credential test in CI |
| **Rate limiting** | P0 gap | **Unchanged** | No rate limiting on any endpoint | FastAPI middleware or API gateway |
| **Attachment size limits** | P0 gap | **Unchanged** | No size cap on `raw_data` | Request body size limit in uvicorn or FastAPI |
| **Task expiry and cleanup** | P1 gap | **Unchanged** | Tasks accumulate indefinitely | TTL or archival policy |
| **Intent classification accuracy** | P0 gap | **Unchanged** | Keyword matching in supervisor | Gemini-powered classification |
| **Fact extraction accuracy** | P0 gap | **Unchanged** | Regex patterns in FactExtractor | Gemini-powered extraction or structured templates |
| **CSRF / PKCE in OAuth flow** | P0 gap | **Fully Implemented (RFC 7636 PKCE S256)** | `src/security/auth_service.py`, `src/server/web_app.py`, `test_alexa_addon.py` | None — RFC 8414 & RFC 9728 metadata active; RFC 9207 iss parameter supported |
| **Token expiry tracking** | N/A (new) | **Implemented (1h JWT & 5m Auth Codes)** | `src/security/auth_service.py`, token revocation blacklist | Periodic database sweep of expired auth codes |
| **Deployment readiness** | P0 gap | **Local Complete, Alexa+ Add-on Configured** | `src/alexa/addon_manifest.json`, `src/alexa/alexa_tool_catalog.md` | Cloud deployment, reverse proxy HTTPS, live Alexa CLI |

### P0 — Security and Production Hardening (Blocks production deployment)

| Gap | Description |
|---|---|
| **Real owner authentication** | `is_authorized_owner()` defaults to checking `actor_id.startswith("owner:")` — easily spoofed. Production needs OAuth2/JWT verification. |
| **Auth router not mounted** | `auth_routes.py` is fully implemented but not registered. Zero-effort fix: add `app.include_router(auth_router)` in `web_app.py`. |
| **OAuth CSRF protection** | OAuth `state` parameter carries only `merchant_id`, not a cryptographic CSRF nonce. A malicious redirect could authorize with a different merchant's identity. |
| **Production environment gate** | Test header auth (`X-Autopilot-Actor-Id`) is still active when `AUTOPILOT_ENV` is not `production`. Needs explicit enforcement. |
| **Token encryption key absent** | Without `TOKEN_ENCRYPTION_KEY`, refresh tokens are stored as base64 only. Warning is logged but execution continues silently. |
| **Secrets management** | `GEMINI_API_KEY`, Zoho OAuth tokens, Amazon Pay private key path, Meta tokens are read from env vars with no rotation or vault integration. |
| **Rate limiting** | No rate limiting on email ingestion or action dispatch endpoints. |
| **Payment operations bypass approval** | `AmazonPayAdapter.create_charge()` is a direct call — not gated by `PermissionEngine`. Any future REST endpoint exposing it would bypass the critical-action approval requirement. |

### P1 — Feature Gaps (Significant missing functionality)

| Gap | Description |
|---|---|
| **Live Gmail/Outlook integration** | Phase 1 implements a mock email provider. Live OAuth integrations are explicitly deferred. |
| **Owner notification on approval required** | When an action reaches `AWAITING_APPROVAL`, the owner is not notified. Needs push/webhook/SMS notification. |
| **Task expiry and cleanup** | Old tasks in terminal states accumulate indefinitely. No TTL or archival policy. |
| **Concurrent task deduplication** | Two simultaneous emails with the same thread_id may create two tasks. Thread-level deduplication is incomplete. |
| **MCP authentication** | The MCP server has no built-in authentication. Any process with network access can call all 33 tools. |
| **Document text extraction quality** | PDF parsing fails for scanned images or complex layouts (no OCR). |
| **Business scope verification** | `category` in `AdaptiveBusinessProfile` is a free-form string; no taxonomy enforcement. |
| **Zoho Books token refresh** | OAuth token refresh is not implemented. Expired tokens cause silent fallback to mock mode. |
| **Amazon Pay → approval pipeline** | Payment operations (charge, refund) do not flow through PermissionEngine or the owner-approval state machine. |
| **PlaceDetailsClient not exposed** | `PlaceDetailsClient` is implemented but not wired to any REST endpoint or MCP tool. |
| **Meta Graph API not called** | `MetaAdapter` logs "live mode initialized" if credentials are set, but no actual API calls are made in any method. |
| **Token refresh logic absent** | `TokenStore` stores refresh tokens but no code refreshes them. Adapters must call the provider's token endpoint themselves. |

### P2 — Enhancement Gaps (Valuable but not blocking)

| Gap | Description |
|---|---|
| **Gemini-powered intent classification** | Replace keyword-based `classify_intent()` with a Gemini API call for better accuracy. |
| **Multi-language support** | Current NLU is English-only; Indian owners communicate in Hindi, Hinglish, regional languages. |
| **Structured onboarding wizard** | Chat-based onboarding is open-ended; a structured wizard with required-field tracking would be more reliable. |
| **Business analytics dashboard** | No visualization of task throughput, approval rates, action outcomes. |
| **Recurring task automation** | No scheduled or recurring operational tasks (e.g., daily stock check at 8 AM). |
| **Webhook/event streaming** | No real-time event stream for task state changes; clients must poll. |
| **Profile bulk import/export** | Onboarding must happen conversationally or via document upload one profile at a time. |
| **Amazon Pay live sandbox testing** | Live smoke test exists (`TestAmazonPayLiveSmoke`) but always skipped — no sandbox credentials in CI. |

---

## 13. Recommended Next Development Phase

### Immediate P0 Fix — Mount the Auth Router (~15 minutes)

One line is missing in `web_app.py`:
```python
from src.server.auth_routes import router as auth_router
app.include_router(auth_router)
```
This would activate the 5 OAuth routes already implemented. This is the highest-value/lowest-effort fix in the codebase.

### Phase 5A — Production Security (P0, ~2–3 days)

1. Mount `auth_routes` router in `web_app.py`.
2. Add CSRF nonce to OAuth `state` parameter (server-generated random, session-stored, verified on callback).
3. Replace `is_authorized_owner()` default with explicit owner list enforcement — reject if unconfigured.
4. Add `AUTOPILOT_ENV=production` check to disable test-mode header auth unconditionally.
5. Enforce `TOKEN_ENCRYPTION_KEY` requirement in non-development environments.
6. Add request size limits and rate limiting on ingestion endpoints.
7. Add `expires_at` column to `autopilot_oauth_tokens`; implement token refresh before expiry.

### Phase 5B — Wire Amazon Pay to Approval Pipeline (P1, ~2 days)

1. Add `execute_amazon_pay_charge` and `issue_amazon_pay_refund` action types to `PermissionEngine`.
2. Implement `AmazonPayChargeHandler` and `AmazonPayRefundHandler` in `ActionDispatcher` that call the adapter.
3. Gate all payment adapter calls through the three-check approval verification.
4. Add corresponding MCP tools and REST endpoints.

### Phase 5C — Live Email and Notifications (P1, ~3–5 days)

1. Implement Gmail OAuth adapter using the existing `EmailProvider` base class interface in `src/integrations/`.
2. Implement owner notification service: when an action reaches `AWAITING_APPROVAL`, send an email or webhook.
3. Wire notification into `EmailOperationalSupervisor.process_email()`.

### Phase 5D — MCP Authentication (P1, ~1–2 days)

1. Add bearer token or API key authentication to the `/mcp` and `/sse` endpoints.
2. Map authenticated callers to `business_id` for tool-level tenant isolation.

### Phase 5E — Expose New Integration Capabilities (P2, ~1 day)

1. Add a REST endpoint and MCP tool for `PlaceDetailsClient.get_place_details()`.
2. Add a REST endpoint for Amazon Pay payment summary: `GET /api/integrations/amazon_pay/summary`.
3. Implement at least one real Meta Graph API call (e.g., `GET /me/accounts` to list pages).

---

## 14. Running the Project Locally

### Prerequisites

```bash
Python >= 3.10
pip install -r requirements.txt
```

For Gemini LLM features (optional):
```
GEMINI_API_KEY=your-key-here
```

For Fernet token encryption (recommended for any stored OAuth tokens):
```
TOKEN_ENCRYPTION_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

### Running Tests

```bash
# Full test suite (Gemini + Amazon Pay live tests auto-skip without credentials)
pytest tests/ -v

# Amazon Pay unit and mock tests only
pytest tests/test_amazon_pay.py -v

# Phase 4 execution tests only
pytest tests/test_phase4_controlled_execution.py -v

# Stop on first failure
pytest tests/ -v -x
```

Expected: **367 passed, 3 skipped, 0 failed in 20.06 seconds**.

### Starting the Server

```bash
# FastAPI with Uvicorn
uvicorn src.server.web_app:app --host 0.0.0.0 --port 8000 --reload

# MCP server standalone (stdio mode, for direct Alexa integration)
python -m src.server.mcp_server
```

After startup:
- `http://localhost:8000/health` — health check
- `http://localhost:8000/docs` — Swagger UI (interactive API explorer)
- `http://localhost:8000/mcp` — Streamable HTTP MCP endpoint
- `http://localhost:8000/sse` — SSE MCP endpoint

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_PATH` | `data/demo.db` | SQLite database file path |
| `AUTOPILOT_ENV` | `development` | Set to `production` to disable test auth headers |
| `GEMINI_API_KEY` | (none) | Required only for `AutopilotAgent` LLM features |
| `GEMINI_MODEL` | `gemini-2.0-flash-001` | Gemini model name override |
| `GOOGLE_MAPS_API_KEY` | (none) | Required for live Places (mock mode if absent) |
| `ZOHO_CLIENT_ID` | (none) | Required for live Zoho Books (mock mode if absent) |
| `ZOHO_CLIENT_SECRET` | (none) | Required for live Zoho Books |
| `ZOHO_REFRESH_TOKEN` | (none) | Required for live Zoho Books |
| `ZOHO_ORG_ID` | (none) | Zoho Books organization ID |
| `ZOHO_ACCOUNTS_URL` | `https://accounts.zoho.in` | Zoho datacenter accounts URL |
| `ZOHO_API_DOMAIN` | (none) | Zoho API domain override |
| `AMAZON_PAY_PUBLIC_KEY_ID` | (none) | Amazon Pay public key ID (e.g. `SANDBOX-XXXX`) — mock mode if absent |
| `AMAZON_PAY_PRIVATE_KEY_PATH` | (none) | Path to Amazon Pay RSA private key `.pem` file |
| `AMAZON_PAY_MERCHANT_ID` | (none) | Amazon Pay Seller Central merchant ID |
| `AMAZON_PAY_SANDBOX` | `true` | `"true"` = sandbox; `"false"` = production |
| `META_APP_ID` | (none) | Meta app ID — mock mode if absent |
| `META_APP_SECRET` | (none) | Meta app secret |
| `META_ACCESS_TOKEN` | (none) | Meta long-lived page/user access token |
| `TOKEN_ENCRYPTION_KEY` | (none) | Fernet key for OAuth token encryption — base64 fallback if absent |
| `MOCK_INTEGRATIONS` | `false` | `"true"` forces all integration adapters into mock mode |

### Quick End-to-End Demo via REST API

```bash
# 1. Ingest an email (business_id is set server-side from trusted context)
curl -X POST http://localhost:8000/api/emails/ingest \
  -H "Content-Type: application/json" \
  -d '{"message_id":"demo-001","business_id":"kiranamart_001","sender":{"email":"supplier@example.com"},"to_recipients":[{"email":"shop@kiranamart.in"}],"subject":"Wholesale Rice Quote","body_text":"500kg Basmati at Rs 40/kg available."}'

# 2. Run supervisor analysis
curl -X POST http://localhost:8000/api/emails/demo-001/process

# 3. List tasks for the business
curl "http://localhost:8000/api/tasks?business_id=kiranamart_001"

# 4. Check integration status (now includes Amazon Pay + Meta)
curl http://localhost:8000/api/integrations/status

# 5. List pending approvals
curl "http://localhost:8000/api/actions?business_id=kiranamart_001&status=PROPOSED"

# 6. Approve an action (replace ACTION_ID with actual UUID)
curl -X POST http://localhost:8000/api/actions/ACTION_ID/approve \
  -H "Content-Type: application/json" \
  -d '{"actor_id":"owner:kiranamart","execution_payload":{}}'

# 7. Dispatch (execute) the approved action
curl -X POST http://localhost:8000/api/actions/ACTION_ID/dispatch \
  -H "Content-Type: application/json" \
  -d '{"actor_id":"owner:kiranamart"}'

# 8. View audit history
curl "http://localhost:8000/api/tasks/TASK_ID"
```

---

## 15. Technical Glossary

| Term | Definition |
|---|---|
| **MSME** | Micro, Small, and Medium Enterprise — the target user segment (Indian kirana, repair, food, services) |
| **AdaptiveBusinessProfile** | A business-agnostic profile containing any number of typed, tracked `BusinessFact` entries with provenance and confidence. Does not assume any specific industry schema. |
| **BusinessFact** | An atomic piece of business information (e.g., `selling_price: 150.0`) with status, source, confidence, and correction history |
| **FactStatus** | Lifecycle status of a fact: `CONFIRMED` (verified by owner), `ASSUMED` (inferred), `UNKNOWN` (missing), `OUTDATED` (superseded) |
| **FactSource** | How a fact was obtained: `USER_STATED` (conversation), `INFERRED` (system), `EXTERNAL_API` (Places/Zoho), `SYSTEM_DEFAULT` (fallback) |
| **OperationalTask** | A persistent work item created for each incoming email. Tracks the full lifecycle from `RECEIVED` to a terminal state. |
| **TaskState** | One of 12 lifecycle states: `RECEIVED → CLASSIFIED → PLANNING → WORKING → AWAITING_INFORMATION → AWAITING_APPROVAL → EXECUTING → COMPLETED / FAILED / REJECTED / CANCELLED / EXECUTION_UNCERTAIN` |
| **ActionProposal** | A structured, immutable proposed action with SHA-256 payload hash. Must be explicitly approved by an authorized owner before execution. |
| **PolicyDecision** | The output of `PermissionEngine.evaluate_action()`: `ALLOW`, `REQUIRE_APPROVAL`, or `DENY` |
| **PermissionEngine** | The deterministic security boundary. Evaluates action risk tier via lookup table. Never calls LLM. Fail-closed on unknown action types. |
| **ActionDispatcher** | The controlled execution layer. Re-evaluates policy, verifies hash binding, checks approval, calls simulated handler, records execution receipt. |
| **ExecutionReceipt** | Durable record of an action execution: status, handler used, timestamp, simulation notice |
| **EXECUTION_UNCERTAIN** | Task/action state indicating the simulated handler ran but outcome is indeterminate. Requires explicit owner reconciliation via the `reconcile_uncertain_execution` endpoint or MCP tool. |
| **Idempotency Key** | UUID on each `ActionProposal`. Prevents double-execution if dispatch is called multiple times. |
| **Payload Hash** | SHA-256 of the canonical JSON serialization of the action payload (keys sorted, ASCII-encoded). Binds approval to the exact payload — any modification invalidates the approval. |
| **MCP** | Model Context Protocol — a standard protocol for AI assistants to call structured tools. This project implements an MCP server using `FastMCP` from the official `mcp` Python SDK. |
| **FastMCP** | The official Python SDK for building MCP servers (`mcp.server.fastmcp`). Used to expose 33 tools over Streamable HTTP and SSE transports. |
| **WAL mode** | SQLite Write-Ahead Logging. Allows concurrent readers while a writer is active. Appropriate for FastAPI's thread pool dispatcher. |
| **Tenant isolation** | Every repository query takes `business_id` as a mandatory filter. No query can accidentally return another business's data. |
| **Fail-closed** | Security default: the permission engine denies any action type it does not explicitly recognize as low-risk or consequential. |
| **Prompt injection** | An attack where malicious text in untrusted input (email body, document) attempts to override AI system behavior. Mitigated here by evaluating policy entirely through deterministic code paths that never read email or document content. |
| **DocumentEvidence** | Precise source reference for a document-extracted fact: `{file_name, format, location, raw_snippet, extracted_at}` |
| **business_init.schema.json** | JSON schema defining expected facts for onboarding any business vertical. Used by the orchestrator to identify missing required fields. |
| **Simulated Handler** | An offline implementation of a consequential action (e.g., `ExternalEmailHandler`) that records what would have been sent without calling any live external API. Every handler appends a `SIMULATION_NOTICE` to its receipt. |
| **AmazonPayAdapter** | High-level orchestration wrapper for Amazon Pay India (v2). Auto-selects mock or live client based on env vars. Provides charge, refund, webhook, and payment summary operations. |
| **AmazonPayClient** | Low-level RSA-SHA256 signed HTTP client for Amazon Pay India REST API v2. Requires `cryptography` package and merchant key pair. |
| **ChargePermission** | A long-lived Amazon Pay authorization granted by a buyer, allowing the merchant to create charges up to a specified limit without re-authorization. |
| **TokenStore** | SQLite-backed encrypted storage for OAuth refresh tokens. Keyed by `(provider, merchant_id)`. Encrypts with Fernet AES when `TOKEN_ENCRYPTION_KEY` is set; base64 fallback otherwise. |
| **Fernet** | A symmetric encryption scheme (AES-128-CBC + HMAC-SHA256) from the Python `cryptography` library. Used to encrypt OAuth refresh tokens at rest. |
| **PlaceDetailsClient** | Google Places API (New) client for fetching rich place data by `place_id`: opening hours, phone, website, rating, editorial summary. |
| **MetaAdapter** | Scaffolded adapter for Meta (Facebook Graph) API. Currently reports connectivity status only; no API calls implemented. |
| **load_dotenv_safe()** | Function in `src/integrations/base.py` that reads `.env` from the project root into `os.environ` on module import, without overwriting existing env vars. |

---

## 16. Latest Repository Updates — Commit c3277da

> **Commits covered:** `dd5be3b` (Zoho fix + auto .env loading) and `c3277da` (Amazon Pay, Meta, OAuth routes, token store, place details).
> **Baseline:** `4428fd5` — feat(autopilot): complete business-agnostic architecture across phases 0-4.

### A. Amazon Pay Integration

The `src/integrations/amazon_pay/` package introduces a complete, independently testable payment integration layer.

#### File responsibilities

**`models.py`** — Five dataclasses matching Amazon Pay India API v2 response shapes:
- `AmazonPayCharge`: single payment capture with `charge_id`, `amount` (string per API spec), `charge_state` (Chargeable / Captured / Declined / Canceled), and optional payment method.
- `AmazonPayRefund`: refund against a captured charge.
- `AmazonPayChargePermission`: long-lived buyer authorization with limit and buyer identity.
- `AmazonPayWebhookEvent`: parsed IPN notification (CHARGE_CAPTURED, REFUND_COMPLETED, CHARGE_DECLINED).
- `AmazonPayPaymentSummary`: aggregated metrics (total captured, refunded, pending, declined counts).

Each model has a `to_dict()` method that produces API-shaped keys (camelCase, matching Amazon Pay response format), plus an `is_mock: bool` field so callers can distinguish simulation from live.

**`mock_data.py`** — Module-level constants for CI and demo use without credentials: four mock charges (two Captured, one Declined, one Chargeable), one mock refund, one mock charge permission, and a pre-built payment summary — all using realistic INR amounts and a `MOCK_MERCHANT_KANPUR` merchant.

**`client.py`** — `AmazonPayClient` is the low-level HTTP layer:
- Validates required credentials on construction; raises `ValidationError` if absent.
- Requires the `cryptography` package for RSA-SHA256 signing. Raises `IntegrationError` if unavailable.
- Builds `AMZN-PAY-RSASSA-PSS-V2` Authorization headers using PKCS1v15 + SHA-256.
- Implements up to 2 retries with exponential back-off for 5xx and network errors.
- Maps HTTP status codes to typed exceptions: 401 → `AuthenticationError`, 422 → `ValidationError`, 429 → `RateLimitError`, 5xx → `ProviderUnavailableError`.
- API methods: `get_charge()`, `create_charge()`, `capture_charge()`, `cancel_charge()`, `create_refund()`, `get_refund()`, `get_charge_permission()`.
- Target URLs: `https://pay-api.amazon.in/sandbox/v2` or `https://pay-api.amazon.in/live/v2`.

**`adapter.py`** — `AmazonPayAdapter` is the high-level orchestration layer:
- Auto-detects live vs mock: if all three of `AMAZON_PAY_PUBLIC_KEY_ID`, `AMAZON_PAY_PRIVATE_KEY_PATH`, `AMAZON_PAY_MERCHANT_ID` are set *and* `MOCK_INTEGRATIONS != true`, it constructs `AmazonPayClient`; otherwise mock mode is engaged.
- Exposes `is_mock` property.
- `create_charge()` in mock mode generates a deterministic `MOCK-CHG-XXXXXX` ID from a hash of the permission ID + amount.
- `create_refund()` in mock mode generates a deterministic `MOCK-REF-XXXXXX` ID.
- `list_recent_charges()` in live mode returns `[]` with a log note — Amazon Pay v2 has no bulk list endpoint; callers must track and look up individual charge IDs.
- `parse_webhook_event()` normalizes IPN payloads into `AmazonPayWebhookEvent`. **Note:** IPN signature verification is not implemented — the docstring states the caller is responsible for this.
- `get_status()` reports mode, merchant ID, and configured API base URL.

**`__init__.py`** — Re-exports `AmazonPayAdapter` and all five model classes.

#### Operation flow

```mermaid
sequenceDiagram
    participant App as Application Code
    participant Adapter as AmazonPayAdapter
    participant Client as AmazonPayClient
    participant API as Amazon Pay API India

    App->>Adapter: create_charge(permission_id, "500.00")
    alt Mock mode (no credentials)
        Adapter-->>App: {"chargeId":"MOCK-CHG-...", "is_mock":true}
    else Live sandbox mode
        Adapter->>Client: create_charge(permission_id, "500.00")
        Client->>Client: _build_auth_header() [RSA-SHA256 sign]
        Client->>API: POST /sandbox/v2/charges
        API-->>Client: {"chargeId":"S02-...", "chargeState":{...}}
        Client-->>Adapter: raw dict
        Adapter-->>App: {**raw, "is_mock":false}
    end
```

#### Connection to owner-approval system

**There is no connection.** `AmazonPayAdapter` is instantiated as a singleton in `web_app.py` (`amazon_pay_adapter = AmazonPayAdapter()`) and its `get_status()` is called from `/api/integrations/status`. However, no REST endpoint or MCP tool exposes `create_charge()` or `create_refund()`. These methods are callable only through internal Python code.

`execute_payment` and `issue_refund` are classified as `CRITICAL` in `PermissionEngine`, but there is no dispatcher handler that calls the Amazon Pay adapter. The adapter and the approval pipeline are entirely parallel.

### B. Google Places Improvements

`src/integrations/google_places/place_details.py` adds single-place rich lookup alongside the existing nearby-search client, without modifying it.

**`PlaceDetailsClient`**:
- Uses the same `GOOGLE_MAPS_API_KEY` as the existing adapter.
- Calls `GET https://places.googleapis.com/v1/places/{place_id}` with a field mask (`X-Goog-FieldMask` header) to control billing and response size.
- Field mask includes: `id`, `displayName`, `formattedAddress`, `location`, `types`, `rating`, `userRatingCount`, `businessStatus`, `regularOpeningHours`, `nationalPhoneNumber`, `websiteUri`, `editorialSummary`, `priceLevel`.
- Normalizes the response into `PlaceDetails` dataclass, including structured `OpeningHoursPeriod` objects (day, open time, close time) and human-readable weekday description strings.
- Mock fallback returns a realistic `Sharma Tiffin Centre` Kanpur competitor.
- Shares the same auth error / rate limit / network error exception mapping as other integration clients.

**Current accessibility:** `PlaceDetailsClient` is implemented but not wired to any REST endpoint or MCP tool. It must be imported and called directly from application code.

### C. Meta Integration

`src/integrations/meta/adapter.py` introduces `MetaAdapter` — a minimal scaffolded adapter for the Meta (Facebook Graph) API.

**Current capabilities:**
- Detects credentials from `META_ACCESS_TOKEN`, `META_APP_ID`, `META_APP_SECRET` environment variables.
- If all three are set and `MOCK_INTEGRATIONS != true`, logs "live mode initialized" — but creates no actual HTTP client.
- `get_status()` returns provider name, mode (`"mock"` or `"live"`), configuration status, and the Graph API base URL.
- That is the **complete** implementation. No Graph API calls exist.

**What is missing:** Page listings, post metrics, engagement data, follower counts, campaign analytics — any actual business intelligence from Meta.

`MetaAdapter` is instantiated in `web_app.py` (`meta_adapter = MetaAdapter()`) and its status is included in `GET /api/integrations/status`. It is accessible via REST only; no MCP tool exposes it.

### D. Authentication Routes

`src/server/auth_routes.py` defines an `APIRouter` at the `/auth` prefix with five endpoints for external provider OAuth connection management.

#### Important limitation

**The router is not mounted.** `web_app.py` imports `AmazonPayAdapter` and `MetaAdapter` from their respective packages but does not call `app.include_router()`. The auth endpoints are unreachable at runtime.

#### Implemented routes (when mounted)

| Route | Purpose |
|---|---|
| `GET /auth/{provider}/login?merchant_id=X` | Returns a `LoginRedirectResponse` with the OAuth URL the merchant should open in a browser |
| `GET /auth/{provider}/callback?code=X&state=merchant_id` | Exchanges authorization code for refresh token; stores encrypted in `TokenStore` |
| `GET /auth/{provider}/status?merchant_id=X` | Returns `ConnectionStatus` (is_connected, scopes) without exposing token values |
| `DELETE /auth/{provider}/disconnect?merchant_id=X` | Deletes stored token for the merchant+provider pair |
| `GET /auth/connections?merchant_id=X` | Lists all connected providers for a merchant |

#### Supported providers

| Provider | OAuth Type | Callback implemented? |
|---|---|---|
| `zoho_books` | Standard OAuth 2.0 authorization code | Yes — code exchange + token storage |
| `google_places` | Server-side API key (no OAuth) | N/A — returns instructions only |
| `amazon_pay` | RSA key pair (no OAuth) | N/A — returns instructions only |
| Any other | — | 404 |

#### OAuth flow for Zoho Books

```mermaid
sequenceDiagram
    participant Owner as Business Owner
    participant App as /auth/zoho_books/login
    participant Zoho as Zoho OAuth Server
    participant CB as /auth/zoho_books/callback
    participant TS as TokenStore

    Owner->>App: GET /auth/zoho_books/login?merchant_id=kiranamart_001
    App-->>Owner: {redirect_url: "https://accounts.zoho.in/oauth/v2/auth?...&state=kiranamart_001"}
    Owner->>Zoho: Browser opens redirect_url; merchant logs in and approves
    Zoho->>CB: GET /callback?code=AUTH_CODE&state=kiranamart_001
    CB->>Zoho: POST /oauth/v2/token (code exchange)
    Zoho-->>CB: {refresh_token: "...", scope: "ZohoBooks.fullaccess.all"}
    CB->>TS: save_token("zoho_books", "kiranamart_001", refresh_token)
    TS->>TS: Fernet-encrypt(refresh_token) → token_blob
    TS->>DB: INSERT INTO autopilot_oauth_tokens
    CB-->>Owner: {"status":"connected","provider":"zoho_books","merchant_id":"kiranamart_001"}
```

#### What this is NOT

The OAuth flows in `auth_routes.py` authorize the **application** to access **external providers** (Zoho, Google) on behalf of a merchant. They do **not**:
- Authenticate the business owner to the autopilot system itself.
- Issue JWT tokens or session cookies for subsequent API calls.
- Replace the `actor_id` / `owner:` prefix check in `PermissionEngine`.
- Protect MCP endpoints.

These are two distinct security problems. External-provider authorization is partially addressed; business-owner authentication remains an open P0 gap.

#### CSRF / State parameter handling

The `state` parameter carries `merchant_id` from login to callback. This provides merchant correlation but is **not** CSRF protection. A proper implementation would use a random server-generated nonce stored in a session and compared on callback.

### E. Token Storage

`src/db/token_store.py` implements `TokenStore` — an SQLite-backed encrypted store for OAuth refresh tokens.

#### Architecture

- Creates `autopilot_oauth_tokens` table lazily on first instantiation (not part of the main DDL migration pipeline).
- Opens its own SQLite connections independently of `connection.py`.
- Keyed by `(provider, merchant_id)` composite primary key. `merchant_id` defaults to `"default"` for single-merchant deployments.

#### Encryption

When `TOKEN_ENCRYPTION_KEY` is set in the environment:
- Loads a Fernet key (`cryptography` package required).
- Encrypts with AES-128-CBC + HMAC-SHA256.
- Stores the Fernet-encrypted blob as a UTF-8 string.

Without the key:
- Stores `"b64:" + base64(token)` — encoded only, **not encrypted**.
- Logs a `WARNING` message. Execution continues.

The `b64:` prefix allows detecting the encoding mode on retrieval: base64 blobs are decoded directly; Fernet blobs require the key. If a Fernet-encrypted blob is present but the key is absent, `_decrypt()` raises `ValueError`.

#### Public API

| Method | Description |
|---|---|
| `save_token(provider, merchant_id, refresh_token, scopes)` | Encrypts and upserts the token (INSERT OR REPLACE) |
| `load_token(provider, merchant_id)` | Decrypts and returns the refresh token string, or `None` if not found |
| `delete_token(provider, merchant_id)` | Hard-deletes the stored token (e.g., on disconnect) |
| `token_exists(provider, merchant_id)` | Returns `True`/`False` without exposing the token |
| `list_connections(merchant_id)` | Returns list of `{provider, merchant_id, scopes, created_at, updated_at}` — **never token values** |

#### Key security limitations

1. **No token expiry column.** Stored tokens are valid indefinitely from the storage perspective.
2. **No automatic refresh.** Callers must handle refresh; `TokenStore` only persists what it is given.
3. **Shared database file.** `autopilot_oauth_tokens` sits in `data/demo.db` alongside all domain tables.
4. **Encryption key from env.** If `TOKEN_ENCRYPTION_KEY` is not set in production, tokens are stored in base64 only.
5. **No cross-tenant isolation enforcement.** `merchant_id` is a filter, but the table has no foreign-key relationship to a `businesses` table. Callers must supply correct `merchant_id` values.
6. `generate_key()` utility is provided for one-time key generation; the key must be stored securely outside the codebase.

### F. Zoho Books Updates (commit dd5be3b)

Two practical fixes to the existing `ZohoBooksAdapter`:

**Month name parsing:** Zoho Books API returns dates with string month names in some locales (e.g., `"15 October 2026"`). The previous parser expected only integer month representations and raised `ValueError`. The updated adapter handles both integer and string month values.

**Missing scope handling:** OAuth token responses from Zoho may omit the `scope` field if the authorization scope is empty or if the token was issued with all scopes by default. The previous adapter crashed on `None` scope. Now handled gracefully.

**Auto `.env` loading:** `src/integrations/base.py` was updated to call `load_dotenv_safe()` at module import time. This means any integration adapter that imports from `base.py` automatically loads `.env` without requiring `python-dotenv` or a manual call. Keys already set in `os.environ` (e.g., by CI) are not overwritten.

### G. Configuration Changes

The following environment variables were added to `.env.example`:

```
# Amazon Pay India
AMAZON_PAY_PUBLIC_KEY_ID=SANDBOX-XXXXXXXXXXXXXXXXXXXXXXXXXX
AMAZON_PAY_PRIVATE_KEY_PATH=/path/to/AmazonPay.pem
AMAZON_PAY_MERCHANT_ID=XXXXXXXXXXXXXX
AMAZON_PAY_SANDBOX=true

# Meta / Instagram Graph API
META_APP_ID=your_meta_app_id_here
META_APP_SECRET=your_meta_app_secret_here
META_ACCESS_TOKEN=your_meta_long_lived_access_token_here

# OAuth Token Encryption
TOKEN_ENCRYPTION_KEY=your_fernet_encryption_key_here
```

`MOCK_INTEGRATIONS=false` was also added to make the global mock override explicit. No existing variables were removed.

### H. Tests

#### `tests/test_amazon_pay.py` — 20 tests

| Class | Tests | Description |
|---|---|---|
| `TestAmazonPayMockAdapter` | 10 | Adapter in forced mock mode: status, get_charge, create_charge, create_refund, list_charges, list_refunds, payment_summary, charge_permission, webhook parsing |
| `TestAmazonPayModels` | 4 | Data model `to_dict()` serialization for Charge, Refund, Summary, ChargePermission |
| `TestAmazonPayMockData` | 5 | Mock data consistency: required fields, refund→charge ID integrity, summary positives, ID lookup, fallback |
| `TestAmazonPayLiveSmoke` | 1 | Live sandbox adapter — **skipped** unless all three Amazon Pay env vars are set |

**Result: 19 passed, 1 skipped.**

All mock tests run without any external credentials or network access. The live smoke test only verifies that the adapter reports `sandbox` mode — it does not make any payment API calls.

#### `tests/test_integrations_live_smoke.py` — Minor update

The live smoke test file was updated to handle the Zoho scope/month parsing fixes. No new live integration paths were added. Live tests continue to skip when provider credentials are absent.

#### Full test suite result

```
367 passed, 3 skipped, 0 failed in 20.06 seconds
```

Skipped tests: Gemini LLM tests (2, require `GEMINI_API_KEY`) + Amazon Pay live smoke (1, requires Amazon Pay credentials).

### Integration Disconnection Summary

```mermaid
graph LR
    subgraph "Approval Pipeline (connected)"
        SUP["EmailSupervisor"] --> POLICY["PermissionEngine"]
        POLICY --> DISPATCH["ActionDispatcher"]
        DISPATCH --> SIM["SimulatedHandlers"]
    end
    subgraph "New Integrations (NOT connected to pipeline)"
        PAY["AmazonPayAdapter"] -.->|"not wired"| DISPATCH
        META["MetaAdapter"] -.->|"not wired"| DISPATCH
    end
    subgraph "Auth (defined but not mounted)"
        AUTH["auth_routes\n/auth/*"] -.->|"app.include_router\nNEVER CALLED"| APP["FastAPI app"]
    end
```

**The new integration adapters are parallel infrastructure, not integrated into the agent's decision pipeline.** This is architecturally correct for an initial implementation and explicit about what is and is not wired.

---

## 17. Vendo Core Backend, Agent Orchestration & Alexa+ Readiness Update

> **Implementation Date**: October 2026
> **Test Suite**: 372 passed, 3 skipped in 13.15s (100% green)

### Key Achievements Across Phases 1–6

1. **Canonical Data Protection**:
   - `src/db/connection.py`: Enforced absolute prohibition on initializing or mutating `data/demo.db` with `is_canonical_demo_db()` exception barriers (`PermissionError`). Default runtime database redirected to `data/runtime_autopilot.sqlite3`.
   - `src/db/token_store.py`: Guarded token store initialization from touching canonical data.

2. **Security & Tenant Isolation Hardening**:
   - `src/decision/policy_engine.py`: Enhanced `is_authorized_owner()` with fail-closed rules for production (`AUTOPILOT_ENV=production`) and strict tenant isolation (cross-tenant actor tokens rejected).
   - `src/server/web_app.py`: Hardened `resolve_actor_id()` to reject anonymous requests (HTTP 401) and unverified headers in production (HTTP 403). Mounted `auth_router` (`/auth/*`).

3. **Gated Payment & Refund Handlers**:
   - `src/decision/action_dispatcher.py`: Registered `SimulatedPaymentHandler` (`execute_payment`) and `SimulatedRefundHandler` (`issue_refund`), ensuring financial mutations obey the 10-step verification contract.

4. **Unified Orchestration & Intelligence**:
   - `src/agent/orchestrator.py`: Connected `TaskRepository`, `EmailRepository`, `EmailOperationalSupervisor`, `ActionDispatcher`, and `PermissionEngine`.
   - Implemented deterministic task priority scoring (0–100) based on state, consequential proposal presence, financial scale, and urgency.
   - Implemented `generate_daily_briefing()` with Alexa+-ready voice summaries and category terminology (retail, repair, salon, catering).
   - Implemented conversational multi-turn handlers (`handle_explain_proposal`, `handle_approve_followup`, `handle_reject_followup`).

5. **REST API & FastMCP Additions**:
   - `src/server/web_app.py`: Added `POST /api/orchestrator/query` and `GET /api/orchestrator/briefing`.
   - `src/server/mcp_server.py`: Preserved all 33 existing FastMCP tools; added Tool 34 (`get_daily_operational_briefing`) and Tool 35 (`query_business_orchestrator`).

6. **Demonstration & Verification**:
   - `src/demo_runner.py`: End-to-end multi-business demonstration runner covering:
     - Scenario 1 (Retail store): Supplier quotation ingestion -> task -> proposal -> voice explain -> owner approval -> simulated execution -> receipt.
     - Scenario 2 (Repair workshop): Proactive Alexa+ daily operational briefing & job card focus.
     - Scenario 3 (Salon & services): Client appointment review & voice-friendly brief.
     - Scenario 4 (Security & Rejection): Cross-tenant rejection, valid approval, payload tampering rejection, and replay protection.
   - `tests/test_vendo_e2e_scenarios.py`: 5 dedicated unit and integration tests confirming zero regressions.

---

*Document updated from live codebase inspection.*
*Previous baseline commit: `4428fd5` — feat(autopilot): complete business-agnostic architecture across phases 0-4*
*Current commit: `c3277da` — feat(integrations): add Amazon Pay, Meta Graph API adapters, OAuth token store, and place details*
*Vendo Core Backend & Alexa+ Readiness: Fully verified and test-backed.*
