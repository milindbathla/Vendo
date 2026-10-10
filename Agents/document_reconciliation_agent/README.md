# Document & Reconciliation Specialist Agent

A standalone, deterministic Python agent for the **Business MCP Server** project operating against the seeded SQLite database for **Maa Ki Rasoi Cloud Kitchen**.

---

## Capabilities & Planned Tools

1. **`extract_document_data(doc_id=None, file_ref=None, raw_payload=None)`**
   - Retrieves structured line items, supplier information, invoice dates, and tax breakdowns from ingested business documents (`business_documents`, `document_lines`).
   - Supports validation of extraction confidence scores and schema conformity without inventing missing fields.

2. **`reconcile_invoice_against_po(doc_id, po_id=None)`**
   - Performs automated 2-way and 3-way matching between vendor invoice lines, purchase order baselines (`purchase_orders`, `purchase_order_lines`), and actual received goods (`purchase_history`).
   - Compares ordered vs billed quantities, agreed unit prices vs charged rates, and tax calculations.

3. **`detect_transaction_discrepancies(doc_id=None, supplier_id=None)`**
   - Evaluates discrepancies against verified ground truth (`doc_ground_truth`).
   - Flags quantity overbillings (e.g. billed +20 pcs above ordered quantity), tax rate mismatches (e.g. 28% GST charged instead of 18%), and duplicate invoices.
   - Calculates the net financial variance and highlights excess expenditure risks.

4. **`verify_and_record_transaction(doc_id, reconciliation_status, approval_token=None)`**
   - Implements approval-gated safeguards before committing ledger entries.
   - Records verified accounts payable entries in `supplier_business_records` upon discrepancy resolution or clean match.
   - Maintains audit trails and ensures idempotency for all recorded financial adjustments.

---

## Directory Layout

```
document_reconciliation_agent/
├── data/
│   └── demo.db                    # Seeded demo database (reference / shared)
├── src/
│   └── document_reconciliation/
│       ├── __init__.py            # Package exports
│       ├── agent.py               # DocumentReconciliationAgent implementation (to be added)
│       ├── config.py              # Database path resolution (to be added)
│       ├── db.py                  # Parameterized SQLite connector (to be added)
│       ├── engine.py              # Reconciliation & matching engine (to be added)
│       ├── models.py              # Typed dataclass models (to be added)
│       └── repository.py          # Parameterized SQL queries & writes (to be added)
├── tests/
│   ├── __init__.py
│   └── test_document_reconciliation.py # Unit & integration tests (to be added)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Status & Implementation Notes

- **Folder Structure & Documentation:** Established per repository conventions.
- **Business Logic Implementation:** Scheduled for implementation in subsequent phase.
- **Database Tables Referenced:** `business_documents`, `document_lines`, `doc_ground_truth`, `purchase_orders`, `purchase_order_lines`, `purchase_history`, `supplier_business_records`.
