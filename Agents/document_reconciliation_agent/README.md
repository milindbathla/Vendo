# Document & Reconciliation Specialist Agent

A standalone, deterministic Python agent for the **Alexa Business Autopilot** project operating against the SQLite database for **Maa Ki Rasoi Cloud Kitchen**.

---

## Capabilities & Implemented Tools

1. **`extract_document_data(doc_id=None, file_ref=None, raw_payload=None)`**
   - Retrieves structured line items, supplier information, invoice dates, and tax breakdowns from ingested business documents (`business_documents`, `document_lines`) or raw payload dictionaries.
   - Categorizes extraction confidence (`HIGH_CONFIDENCE`, `STANDARD_CONFIDENCE`, `UNCERTAIN_REVIEW_REQUIRED`, `LOW_CONFIDENCE_UNRELIABLE`) without fabricating missing fields.
   - Segregates grounded source facts from uncertain values and flags missing fields.

2. **`reconcile_invoice_against_po(doc_id, po_id=None)`**
   - Performs automated 2-way and 3-way matching between vendor invoice lines, purchase order baselines (`purchase_orders`, `purchase_order_lines`), and received goods receipts (`purchase_history`).
   - Compares ordered vs billed quantities, agreed unit prices vs charged rates, and tax calculations.
   - Calculates financial variances and returns structured reconciliation status (`MATCHED`, `DISCREPANCY_DETECTED`, `PARTIALLY_MATCHED`, `FAILED`).

3. **`detect_transaction_discrepancies(doc_id=None, supplier_id=None)`**
   - Evaluates discrepancies against verified ground truth (`doc_ground_truth`).
   - Flags quantity overbillings (e.g. billed +20 pcs above ordered quantity), tax rate mismatches (e.g. 28% GST charged instead of 18%), missing line items, and duplicate invoices.
   - Computes net financial variance and highlights excess expenditure risks.

4. **`verify_and_record_transaction(doc_id, reconciliation_status, approval_token=None)`**
   - Enforces approval-gated safeguards before committing ledger entries.
   - Records verified accounts payable entries in `supplier_business_records` upon discrepancy resolution or clean match.
   - Maintains audit trails and ensures idempotency for recorded financial adjustments.

---

## Directory Layout

```
document_reconciliation_agent/
├── data/
│   └── demo.db                    # Reference / demo database
├── src/
│   └── document_reconciliation/
│       ├── __init__.py            # Package exports
│       ├── agent.py               # DocumentReconciliationAgent implementation
│       ├── config.py              # Database path resolution & configuration
│       ├── db.py                  # Parameterized SQLite database connector
│       ├── engine.py              # Reconciliation & matching engine
│       ├── models.py              # Typed dataclasses and enums
│       └── repository.py          # SQL queries and persistence operations
├── tests/
│   ├── __init__.py
│   └── test_document_reconciliation.py # Unit tests for engine, models, and agent workflows
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Testing & Verification

Unit tests test extraction confidence tiers, fact separation, line comparison, discrepancy detection, and end-to-end agent workflows using isolated synthetic fixtures and in-memory mock repositories:

```bash
python -m pytest Agents/document_reconciliation_agent/tests/ -q
```
