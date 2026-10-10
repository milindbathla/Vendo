"""Database repository mapping Document & Reconciliation queries to SQLite schema."""

import json
from typing import Any, Dict, List, Optional

from .db import Database


class DocumentRepository:
    """Encapsulates parameterized SQL queries for business documents, POs, and ledgers."""

    def __init__(self, db: Database):
        self.db = db

    # -------------------------------------------------------------------------
    # 1. System Metadata & Clock
    # -------------------------------------------------------------------------
    def get_meta_value(self, key: str) -> Optional[str]:
        """Fetch system meta value by key."""
        return self.db.fetch_val("SELECT value FROM meta WHERE key = ?;", (key,))

    def get_as_of_date(self) -> str:
        """Fetch system frozen anchor date or fallback."""
        as_of = self.get_meta_value("as_of")
        if as_of:
            return as_of.split("T")[0]
        today = self.get_meta_value("today_date")
        return today or "2026-10-10"

    # -------------------------------------------------------------------------
    # 2. Business Documents & Extraction
    # -------------------------------------------------------------------------
    def get_business_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch document header joined with supplier information."""
        query = """
            SELECT
                bd.doc_id,
                bd.doc_type,
                bd.supplier_id,
                s.name AS supplier_name,
                s.gstin AS supplier_gstin,
                s.locality AS supplier_locality,
                s.contact_phone AS supplier_phone,
                bd.po_id,
                bd.doc_date,
                bd.file_ref,
                bd.extracted_json,
                bd.extraction_confidence
            FROM business_documents bd
            JOIN suppliers s ON bd.supplier_id = s.supplier_id
            WHERE bd.doc_id = ?;
        """
        return self.db.fetch_one(query, (doc_id,))

    def get_document_lines(self, doc_id: str) -> List[Dict[str, Any]]:
        """Fetch line items for a document joined with item metadata."""
        query = """
            SELECT
                dl.doc_line_id,
                dl.doc_id,
                dl.item_id,
                i.name AS item_name,
                i.unit AS item_unit,
                dl.billed_qty,
                dl.unit_price,
                dl.taxable_amount,
                dl.gst_rate_pct,
                dl.gst_amount,
                dl.total_line_amount
            FROM document_lines dl
            JOIN items i ON dl.item_id = i.item_id
            WHERE dl.doc_id = ?
            ORDER BY dl.doc_line_id ASC;
        """
        return self.db.fetch_all(query, (doc_id,))

    def get_doc_ground_truth(self, doc_id: str) -> List[Dict[str, Any]]:
        """Fetch ground-truth discrepancy records for a document."""
        query = """
            SELECT
                truth_id,
                doc_id,
                discrepancy_type,
                field_name,
                expected_value,
                actual_value,
                difference_amount,
                description
            FROM doc_ground_truth
            WHERE doc_id = ?
            ORDER BY truth_id ASC;
        """
        return self.db.fetch_all(query, (doc_id,))

    # -------------------------------------------------------------------------
    # 3. Purchase Orders & Goods Receipt
    # -------------------------------------------------------------------------
    def get_purchase_order(self, po_id: str) -> Optional[Dict[str, Any]]:
        """Fetch purchase order header joined with supplier."""
        query = """
            SELECT
                po.po_id,
                po.supplier_id,
                s.name AS supplier_name,
                s.gstin AS supplier_gstin,
                po.order_date,
                po.expected_delivery_date,
                po.status,
                po.total_taxable,
                po.total_tax,
                po.total_amount,
                po.notes
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.supplier_id
            WHERE po.po_id = ?;
        """
        return self.db.fetch_one(query, (po_id,))

    def get_purchase_order_lines(self, po_id: str) -> List[Dict[str, Any]]:
        """Fetch line items for a purchase order."""
        query = """
            SELECT
                pol.line_id,
                pol.po_id,
                pol.item_id,
                i.name AS item_name,
                i.unit AS item_unit,
                pol.ordered_qty,
                pol.unit_price,
                pol.tax_rate_pct,
                pol.taxable_amount,
                pol.tax_amount,
                pol.line_total
            FROM purchase_order_lines pol
            JOIN items i ON pol.item_id = i.item_id
            WHERE pol.po_id = ?
            ORDER BY pol.line_id ASC;
        """
        return self.db.fetch_all(query, (po_id,))

    def get_purchase_history_by_po(self, po_id: str) -> List[Dict[str, Any]]:
        """Fetch physical goods receipt fulfillment records for a purchase order."""
        query = """
            SELECT
                purchase_id,
                po_id,
                supplier_id,
                item_id,
                purchase_date,
                qty AS received_qty,
                unit_price,
                total_paid,
                payment_mode,
                notes
            FROM purchase_history
            WHERE po_id = ?;
        """
        return self.db.fetch_all(query, (po_id,))

    # -------------------------------------------------------------------------
    # 4. Supplier Business Records & Duplicates
    # -------------------------------------------------------------------------
    def get_supplier_business_record_by_doc(self, reference_doc: str) -> Optional[Dict[str, Any]]:
        """Check if an invoice document has already been recorded in supplier ledger."""
        query = """
            SELECT
                entry_id,
                supplier_id,
                date,
                entry_type,
                reference_doc,
                amount,
                balance_due,
                notes
            FROM supplier_business_records
            WHERE reference_doc = ? AND entry_type = 'invoice';
        """
        return self.db.fetch_one(query, (reference_doc,))

    def get_latest_supplier_balance(self, supplier_id: str) -> float:
        """Fetch the latest running balance due for a supplier."""
        query = """
            SELECT balance_due
            FROM supplier_business_records
            WHERE supplier_id = ?
            ORDER BY date DESC, entry_id DESC
            LIMIT 1;
        """
        val = self.db.fetch_val(query, (supplier_id,))
        return float(val) if val is not None else 0.0

    def record_supplier_business_entry(
        self,
        entry_id: str,
        supplier_id: str,
        date: str,
        entry_type: str,
        reference_doc: str,
        amount: float,
        balance_due: float,
        notes: Optional[str] = None,
    ) -> int:
        """Insert verified ledger transaction into supplier_business_records."""
        query = """
            INSERT INTO supplier_business_records (
                entry_id, supplier_id, date, entry_type, reference_doc, amount, balance_due, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        return self.db.execute(
            query,
            (entry_id, supplier_id, date, entry_type, reference_doc, amount, balance_due, notes),
        )

    # -------------------------------------------------------------------------
    # 5. Approvals, Audit Log & Business Memory
    # -------------------------------------------------------------------------
    def get_approval(self, token: str) -> Optional[Dict[str, Any]]:
        """Fetch approval token details."""
        query = "SELECT token, plan_id, total, expires_at, used FROM approvals WHERE token = ?;"
        return self.db.fetch_one(query, (token,))

    def mark_approval_used(self, token: str) -> int:
        """Mark approval token as consumed."""
        return self.db.execute("UPDATE approvals SET used = 1 WHERE token = ?;", (token,))

    def insert_audit_log(self, action: str, actor: str, payload: str, timestamp: str) -> int:
        """Insert audit log entry and return generated log_id."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO audit_log (action, actor, payload, timestamp) VALUES (?, ?, ?, ?);",
                (action, actor, payload, timestamp),
            )
            conn.commit()
            return cursor.lastrowid

    def insert_business_memory(
        self, key: str, value: str, source: str, timestamp: str, confidence: float
    ) -> int:
        """Insert verified fact into business_memory."""
        query = """
            INSERT INTO business_memory (key, value, source, timestamp, confidence)
            VALUES (?, ?, ?, ?, ?);
        """
        return self.db.execute(query, (key, value, source, timestamp, confidence))
