# Vendo FastMCP Tool Catalog for Alexa+ MCP Integration

This document audits all 35 tools exposed by Vendo's FastMCP server, specifying their operational scope, required identity principles, tenant authorization, required OAuth scopes, execution semantics, and Alexa voice-formatting guidelines.

---

## 1. High-Value Alexa+ Voice Tools (Recommended for Primary Voice Interface)

| Tool Name | Operation Type | Required Identity | Scopes | Approval Required | External Consequences | Voice Output Format |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `generate_daily_briefing` | Read-only | Authenticated Owner | `read:business` | No | None | Concise 3-4 sentence spoken brief: pending approvals, urgent tasks, and usable liquid capital. No raw UUIDs. |
| `list_pending_approvals` | Read-only | Authenticated Owner | `read:business` | No | None | Numbered list of proposals with item descriptions and amounts. Binds session ordinal index. |
| `explain_action_proposal` | Read-only | Authenticated Owner | `read:business` | No | None | Explains the exact referenced proposal, purpose, cost, and safety buffer check. Asks for voice confirmation. |
| `approve_proposal_followup` | State-Changing | Authenticated Owner | `approve:consequential` | **Yes (Deterministic Policy)** | Executes approved action (PO dispatch, quotation send, payment trigger) in simulation mode. Generates audit receipt. | Spoken confirmation of execution with receipt code and simulation notice. |
| `reject_proposal_followup` | State-Changing | Authenticated Owner | `write:actions` | No (Owner action) | Transitions action to REJECTED. Prevents dispatch. | Spoken confirmation that proposal was declined. |
| `get_urgent_operational_tasks` | Read-only | Authenticated Owner | `read:business` | No | None | Summarizes open operational tasks and deadline risks. |
| `analyze_business_profitability` | Read-only | Authenticated Owner | `read:finances` | No | None | Spoken gross margin %, break-even unit count, and safety buffer runway. |
| `evaluate_order_opportunity` | Read-only | Authenticated Owner | `read:business` | No | None | Feasibility check against daily capacity and working capital limits. |

---

## 2. Complete 35-Tool Comprehensive Audit

### Suite A: Core Business State & Profile Tools (Tools 1–6)
1. **`get_business_state(business_id: str)`**
   - *Scope:* `read:business`
   - *Behavior:* Read-only. Returns adaptive profile, liquid cash, capacity limits, and term conventions.
   - *Access Control:* Caller principal must be an authorized owner of `business_id`.
   - *Consequences:* None (read-only).

2. **`save_business_profile(profile_data: dict)`**
   - *Scope:* `write:business`
   - *Behavior:* State-changing. Saves or updates adaptive business facts, overhead, and operating margins.
   - *Access Control:* Strict authenticated owner check.
   - *Consequences:* Updates persistent profile facts.

3. **`list_business_profiles()`**
   - *Scope:* `read:business`
   - *Behavior:* Read-only. Lists business IDs managed by the authenticated principal.
   - *Access Control:* Returns only profiles owned by current principal.

4. **`get_profile_by_id(business_id: str)`**
   - *Scope:* `read:business`
   - *Behavior:* Read-only. Fetches detailed profile schema.
   - *Access Control:* Owner check.

5. **`update_profile_field(business_id: str, field_name: str, value: Any)`**
   - *Scope:* `write:business`
   - *Behavior:* State-changing. Modifies specific profile parameters (e.g. `safety_reserve_ratio`, `fixed_overhead_monthly`).
   - *Access Control:* Strict owner verification.

6. **`delete_business_profile(business_id: str)`**
   - *Scope:* `admin:business`
   - *Behavior:* High-risk state-changing. Deletes tenant profile.
   - *Access Control:* Requires explicit owner authentication and confirmation.

---

### Suite B: Financial & Value Chain Simulators (Tools 7–12)
7. **`simulate_order_economics(business_id: str, quantity: float, unit_price: float)`**
   - *Scope:* `read:finances`
   - *Behavior:* Read-only calculation using tenant unit economics.
   - *Access Control:* Owner check.

8. **`check_cash_reserve_safety(business_id: str, disbursement_amount: float)`**
   - *Scope:* `read:finances`
   - *Behavior:* Evaluates if spending `disbursement_amount` violates the liquidity safety buffer floor.
   - *Access Control:* Owner check.

9. **`calculate_breakeven_point(business_id: str)`**
   - *Scope:* `read:finances`
   - *Behavior:* Deterministic break-even analysis based on fixed costs and contribution margin.

10. **`scout_competitors_summary(business_id: str)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Simulated local market radar for price benchmarks and competitive positioning.

11. **`get_accounting_ledger_status(business_id: str)`**
    - *Scope:* `read:finances`
    - *Behavior:* Read-only. Summarizes pending invoices, accounts payable, and accounts receivable.

12. **`forecast_cashflow_runway(business_id: str, days: int)`**
    - *Scope:* `read:finances`
    - *Behavior:* Read-only projection of liquidity based on current burn and expected receivables.

---

### Suite C: Operational Tasks & Proposals (Tools 13–23)
13. **`list_operational_tasks(business_id: str, status: Optional[str] = None)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Retrieves open tasks prioritized by urgency.

14. **`get_task_details(task_id: str, business_id: str)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Retrieves task context, state history, and linked proposals.

15. **`create_operational_task(business_id: str, task_data: dict)`**
    - *Scope:* `write:actions`
    - *Behavior:* State-changing. Enqueues a new business task.

16. **`update_task_state(task_id: str, business_id: str, new_state: str)`**
    - *Scope:* `write:actions`
    - *Behavior:* State-changing. Progresses task lifecycle (e.g. `IN_PROGRESS` -> `COMPLETED`).

17. **`propose_action_for_task(task_id: str, business_id: str, proposal_data: dict)`**
    - *Scope:* `write:actions`
    - *Behavior:* State-changing. Creates an `ActionProposal` requiring owner review.
    - *Approval:* Enforces cryptographic payload hashing (`compute_payload_hash`).

18. **`get_action_proposal(action_id: str, business_id: str)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Fetches action payload, hash, and approval status.

19. **`list_pending_action_proposals(business_id: str)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Lists all pending approval proposals for the tenant.

20. **`approve_action_proposal(action_id: str, business_id: str, actor_id: Optional[str] = None)`**
    - *Scope:* `approve:consequential`
    - *Behavior:* High-risk state-changing. Evaluates deterministic permission policy, transitions state to `APPROVED`, dispatches execution.
    - *Access Control:* Strict authenticated principal verification; caller-supplied `actor_id` is validated against trusted token principal.

21. **`reject_action_proposal(action_id: str, business_id: str, actor_id: Optional[str] = None)`**
    - *Scope:* `write:actions`
    - *Behavior:* State-changing. Marks action as `REJECTED`.

22. **`get_action_execution_receipt(action_id: str, business_id: str)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Retrieves audit execution receipt.

23. **`list_audit_logs(business_id: str, limit: int = 50)`**
    - *Scope:* `read:audit`
    - *Behavior:* Read-only. Retrieves tamper-evident action audit trail.

---

### Suite D: Orchestration, Conversational & Alexa+ Endpoints (Tools 24–35)
24. **`orchestrator_handle_message(business_id: str, message: str, session_id: Optional[str] = None)`**
    - *Scope:* `read:business`, `write:actions`
    - *Behavior:* Hybrid operational dispatch. Manages persistent multi-turn sessions across restarts.
    - *Security:* Principal verified at transport; actor forced to authenticated subject.

25. **`generate_daily_briefing(business_id: str, session_id: Optional[str] = None)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only executive summary formatted for voice synthesis.

26. **`list_pending_approvals(business_id: str, session_id: Optional[str] = None)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Formats proposals and updates session ordinal reference cache.

27. **`explain_action_proposal(business_id: str, query: str, session_id: Optional[str] = None)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only conversational explanation. Sets `focused_action_id` in session metadata.

28. **`approve_proposal_followup(business_id: str, query: str, session_id: Optional[str] = None)`**
    - *Scope:* `approve:consequential`
    - *Behavior:* State-changing. Unambiguously resolves focused or ordinal proposal, checks fresh DB state, executes deterministic approval.

29. **`reject_proposal_followup(business_id: str, query: str, session_id: Optional[str] = None)`**
    - *Scope:* `write:actions`
    - *Behavior:* State-changing. Resolves proposal reference and rejects proposal.

30. **`get_urgent_operational_tasks(business_id: str)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only. Prioritizes tasks with imminent deadlines or high-impact operational blockers.

31. **`analyze_business_profitability(business_id: str)`**
    - *Scope:* `read:finances`
    - *Behavior:* Read-only unit economics and cash safety runway analysis.

32. **`evaluate_order_opportunity(business_id: str, order_description: str, quantity: float = 1.0)`**
    - *Scope:* `read:business`
    - *Behavior:* Read-only capacity and profitability check for incoming orders.

33. **`process_inbound_supplier_quote(business_id: str, quote_text: str, session_id: Optional[str] = None)`**
    - *Scope:* `write:actions`
    - *Behavior:* State-changing. Parses supplier quotation, generates task and proposal, checks cash buffer.

34. **`create_conversation_session(business_id: str)`**
    - *Scope:* `write:session`
    - *Behavior:* State-changing. Initializes a persisted SQLite session bound to principal and tenant.

35. **`get_conversation_session_history(session_id: str, business_id: str)`**
    - *Scope:* `read:session`
    - *Behavior:* Read-only. Returns recent turns and context version.
