"""Document & Reconciliation specialist agent implementation."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from .config import resolve_db_path
from .db import Database
from .engine import (
    categorize_extraction_confidence,
    compare_lines,
    detect_all_discrepancies,
    identify_source_facts_and_uncertainties,
)
from .models import (
    DiscrepancyDetectionResponse,
    DiscrepancyItem,
    DiscrepancySeverity,
    DiscrepancyType,
    DocumentExtractionResponse,
    DocumentMetadata,
    DocumentParty,
    ExtractedLineItem,
    LineMatchComparison,
    ReconciliationResponse,
    ReconciliationStatus,
    RecordTransactionResponse,
    ResourceNotFoundError,
    TransactionRecordStatus,
    ValidationError,
)
from .repository import DocumentRepository


class DocumentReconciliationAgent:
    """Specialist agent for multi-way document extraction, reconciliation, and audit-verified recording."""

    def __init__(self, repository: DocumentRepository):
        self.repo = repository

    @classmethod
    def from_db_path(cls, db_path: Optional[str] = None) -> "DocumentReconciliationAgent":
        """Instantiate agent from an SQLite database path or configured default."""
        resolved = resolve_db_path(db_path)
        db = Database(resolved)
        repo = DocumentRepository(db)
        return cls(repo)

    # -------------------------------------------------------------------------
    # 1. extract_document_data
    # -------------------------------------------------------------------------
    def extract_document_data(
        self,
        doc_id: Optional[str] = None,
        file_ref: Optional[str] = None,
        raw_payload: Optional[str] = None,
    ) -> DocumentExtractionResponse:
        """Extracts structured invoice and document fields.

        Explicitly separates grounded source facts, uncertain values (< 0.90 confidence),
        and missing information without fabricating fields.
        """
        if not doc_id and not file_ref and not raw_payload:
            raise ValidationError("At least one of 'doc_id', 'file_ref', or 'raw_payload' must be provided.")

        doc_dict: Optional[Dict[str, Any]] = None
        source_type = "database"
        confidence = 0.95

        # Path A: Fetch from database
        if doc_id:
            db_doc = self.repo.get_business_document(doc_id)
            if db_doc:
                doc_dict = db_doc
                confidence = float(db_doc.get("extraction_confidence", 0.95))
                source_type = "database"
            elif not file_ref and not raw_payload:
                raise ResourceNotFoundError(f"Business document '{doc_id}' not found in database.")

        # Path B: Parse raw payload
        if not doc_dict and raw_payload:
            try:
                parsed = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                doc_dict = parsed
                source_type = "payload"
                meta_block = parsed.get("document_metadata", {})
                confidence = float(meta_block.get("extraction_confidence", 0.95))
            except Exception as e:
                raise ValidationError(f"Failed to parse raw_payload as JSON: {e}")

        # Path C: Load from file_ref fixture
        if not doc_dict and file_ref:
            resolved_file = Path(file_ref)
            if not resolved_file.exists():
                # Check repo data fixtures
                agent_root = Path(__file__).resolve().parent.parent.parent
                repo_root = agent_root.parent.parent
                candidate_1 = repo_root / "data" / file_ref
                candidate_2 = repo_root / "data" / "fixtures" / Path(file_ref).name
                if candidate_1.exists():
                    resolved_file = candidate_1
                elif candidate_2.exists():
                    resolved_file = candidate_2
                else:
                    raise ResourceNotFoundError(f"Referenced file '{file_ref}' not found on disk.")

            if resolved_file.suffix == ".json":
                with open(resolved_file, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                    doc_dict = parsed
                    source_type = "fixture"
                    meta_block = parsed.get("document_metadata", {})
                    confidence = float(meta_block.get("extraction_confidence", 0.95))

        if not doc_dict:
            raise ResourceNotFoundError("Could not resolve document data from provided inputs.")

        # Extract structured fields depending on format (DB row vs JSON fixture)
        return self._build_extraction_response(doc_dict, source_type, confidence)

    def _build_extraction_response(
        self,
        raw: Dict[str, Any],
        source_type: str,
        confidence: float,
    ) -> DocumentExtractionResponse:
        """Internal helper to parse normalized DocumentExtractionResponse from DB or JSON payload."""
        # Detect if schema is standard nested JSON fixture or DB row
        is_fixture = "invoice_details" in raw or "document_metadata" in raw

        if is_fixture:
            meta = raw.get("document_metadata", {})
            inv = raw.get("invoice_details", {})
            supp = raw.get("supplier", {})
            buyer = raw.get("buyer", {})
            lines_raw = raw.get("line_items", [])
            fin = raw.get("financial_summary", {})

            doc_id = meta.get("doc_id") or inv.get("invoice_number", "DOC-UNKNOWN")
            doc_type = meta.get("doc_type", "invoice")
            file_ref = meta.get("file_name") or raw.get("file_ref", "")
            invoice_num = inv.get("invoice_number", doc_id)
            inv_date = inv.get("invoice_date", "")
            due_date = inv.get("due_date")
            po_ref = inv.get("purchase_order_reference")
            currency = inv.get("currency", "INR")
            payment_terms = inv.get("payment_terms")

            supplier_party = DocumentParty(
                supplier_id=supp.get("supplier_id"),
                name=supp.get("legal_name") or supp.get("name", "Unknown Supplier"),
                gstin=supp.get("gstin"),
                address=supp.get("address"),
                phone=supp.get("phone"),
            )
            buyer_party = DocumentParty(
                supplier_id=None,
                name=buyer.get("legal_name", "Maa Ki Rasoi Cloud Kitchen"),
                gstin=buyer.get("gstin"),
                address=buyer.get("address"),
                phone=buyer.get("phone"),
            )

            lines: List[ExtractedLineItem] = []
            for idx, li in enumerate(lines_raw, start=1):
                lines.append(
                    ExtractedLineItem(
                        line_no=int(li.get("line_no", idx)),
                        item_id=li.get("item_id", ""),
                        description=li.get("description", ""),
                        billed_qty=float(li.get("billed_qty", 0.0)),
                        unit=li.get("unit", "units"),
                        unit_price=float(li.get("unit_price", 0.0)),
                        taxable_amount=float(li.get("taxable_amount", 0.0)),
                        gst_rate_pct=float(li.get("gst_rate_pct", 0.0)),
                        gst_amount=float(li.get("gst_amount", 0.0)),
                        line_total=float(li.get("line_total", 0.0)),
                        hsn_code=li.get("hsn_code"),
                    )
                )

            tot_taxable = float(fin.get("total_taxable_amount", sum(l.taxable_amount for l in lines)))
            tot_tax = float(fin.get("total_tax_amount", sum(l.gst_amount for l in lines)))
            tot_amount = float(fin.get("total_amount_payable", sum(l.line_total for l in lines)))

        else:
            # DB row structure
            doc_id = raw["doc_id"]
            doc_type = raw["doc_type"]
            file_ref = raw.get("file_ref", "")
            invoice_num = raw["doc_id"]
            inv_date = raw["doc_date"]
            due_date = None
            po_ref = raw.get("po_id")
            currency = "INR"
            payment_terms = None

            supplier_party = DocumentParty(
                supplier_id=raw.get("supplier_id"),
                name=raw.get("supplier_name", "Unknown Supplier"),
                gstin=raw.get("supplier_gstin"),
                address=raw.get("supplier_locality"),
                phone=raw.get("supplier_phone"),
            )
            buyer_party = DocumentParty(
                supplier_id=None,
                name="Maa Ki Rasoi Cloud Kitchen",
                gstin="09ZZZZZ9999Z1Z5",
                address="Kakadeo, Kanpur",
            )

            # Query lines from document_lines table
            db_lines = self.repo.get_document_lines(doc_id)
            lines = []
            for idx, dl in enumerate(db_lines, start=1):
                lines.append(
                    ExtractedLineItem(
                        line_no=idx,
                        item_id=dl["item_id"],
                        description=dl.get("item_name") or dl["item_id"],
                        billed_qty=float(dl["billed_qty"]),
                        unit=dl.get("item_unit", "units"),
                        unit_price=float(dl["unit_price"]),
                        taxable_amount=float(dl["taxable_amount"]),
                        gst_rate_pct=float(dl["gst_rate_pct"]),
                        gst_amount=float(dl["gst_amount"]),
                        line_total=float(dl["total_line_amount"]),
                    )
                )

            tot_taxable = sum(l.taxable_amount for l in lines)
            tot_tax = sum(l.gst_amount for l in lines)
            tot_amount = sum(l.line_total for l in lines)

        # Distinguish facts, uncertainties, and missing fields
        flattened = {
            "invoice_number": invoice_num,
            "invoice_date": inv_date,
            "due_date": due_date,
            "purchase_order_reference": po_ref,
            "currency": currency,
            "supplier_id": supplier_party.supplier_id,
            "supplier_name": supplier_party.name,
            "supplier_gstin": supplier_party.gstin,
            "total_taxable_amount": tot_taxable,
            "total_tax_amount": tot_tax,
            "total_amount_payable": tot_amount,
        }
        facts, uncertain, missing = identify_source_facts_and_uncertainties(flattened, confidence)

        return DocumentExtractionResponse(
            doc_id=doc_id,
            doc_type=doc_type,
            invoice_number=invoice_num,
            invoice_date=inv_date,
            due_date=due_date,
            po_reference=po_ref,
            currency=currency,
            payment_terms=payment_terms,
            supplier=supplier_party,
            buyer=buyer_party,
            line_items=lines,
            total_taxable=tot_taxable,
            total_tax=tot_tax,
            total_amount=tot_amount,
            source_facts=facts,
            uncertain_values=uncertain,
            missing_fields=missing,
            metadata=DocumentMetadata(
                doc_id=doc_id,
                doc_type=doc_type,
                file_ref=file_ref,
                extraction_confidence=confidence,
                source_type=source_type,
                authenticity_verified=False,
            ),
        )

    # -------------------------------------------------------------------------
    # 2. reconcile_invoice_against_po
    # -------------------------------------------------------------------------
    def reconcile_invoice_against_po(
        self,
        doc_id: Optional[str] = None,
        po_id: Optional[str] = None,
        extracted_doc: Optional[DocumentExtractionResponse] = None,
    ) -> ReconciliationResponse:
        """Compares invoice lines against purchase orders and physical goods receipts.

        Performs deterministic 3-way matching when goods receipt records exist.
        """
        # Resolve document
        doc = extracted_doc or self.extract_document_data(doc_id=doc_id)

        target_po_id = po_id or doc.po_reference
        if not target_po_id:
            return ReconciliationResponse(
                doc_id=doc.doc_id,
                po_id=None,
                supplier_id=doc.supplier.supplier_id or "UNKNOWN",
                supplier_name=doc.supplier.name,
                match_status=ReconciliationStatus.NO_PO_REFERENCE,
                is_clean_match=False,
                line_comparisons=[],
                total_billed=doc.total_amount,
                total_expected_po=0.0,
                total_amount_variance=doc.total_amount,
                goods_receipt_matched=False,
                discrepancies_count=1,
                summary_notes="No purchase order reference linked to this invoice. Manual authorization required.",
            )

        po = self.repo.get_purchase_order(target_po_id)
        if not po:
            return ReconciliationResponse(
                doc_id=doc.doc_id,
                po_id=target_po_id,
                supplier_id=doc.supplier.supplier_id or "UNKNOWN",
                supplier_name=doc.supplier.name,
                match_status=ReconciliationStatus.PO_NOT_FOUND,
                is_clean_match=False,
                line_comparisons=[],
                total_billed=doc.total_amount,
                total_expected_po=0.0,
                total_amount_variance=doc.total_amount,
                goods_receipt_matched=False,
                discrepancies_count=1,
                summary_notes=f"Purchase order '{target_po_id}' was not found in the database.",
            )

        po_lines = self.repo.get_purchase_order_lines(target_po_id)
        goods_receipts = self.repo.get_purchase_history_by_po(target_po_id)

        comparisons = compare_lines(doc.line_items, po_lines, goods_receipts)

        expected_total = float(po.get("total_amount", 0.0))
        amt_variance = round(doc.total_amount - expected_total, 2)

        has_line_discrepancies = any(lc.status != "MATCH" for lc in comparisons)
        supplier_mismatch = bool(
            doc.supplier.supplier_id and po.get("supplier_id") and doc.supplier.supplier_id != po["supplier_id"]
        )

        if supplier_mismatch:
            match_status = ReconciliationStatus.SUPPLIER_MISMATCH
            is_clean = False
            notes = f"Supplier identity mismatch: Invoice ({doc.supplier.supplier_id}) vs PO ({po['supplier_id']})."
        elif has_line_discrepancies or abs(amt_variance) > 0.01:
            match_status = ReconciliationStatus.DISCREPANCY_DETECTED
            is_clean = False
            notes = f"Reconciliation detected line-item or tax discrepancies (Net variance: Rs.{amt_variance:,.2f})."
        else:
            match_status = ReconciliationStatus.CLEAN_MATCH
            is_clean = True
            notes = "Clean match: Invoice line items, quantities, prices, and taxes match PO and goods receipts."

        discrepancies_count = sum(1 for lc in comparisons if lc.status != "MATCH")
        if abs(amt_variance) > 0.01 and discrepancies_count == 0:
            discrepancies_count = 1

        return ReconciliationResponse(
            doc_id=doc.doc_id,
            po_id=target_po_id,
            supplier_id=po.get("supplier_id", doc.supplier.supplier_id or "UNKNOWN"),
            supplier_name=po.get("supplier_name", doc.supplier.name),
            match_status=match_status,
            is_clean_match=is_clean,
            line_comparisons=comparisons,
            total_billed=doc.total_amount,
            total_expected_po=expected_total,
            total_amount_variance=amt_variance,
            goods_receipt_matched=len(goods_receipts) > 0,
            discrepancies_count=discrepancies_count,
            summary_notes=notes,
        )

    # -------------------------------------------------------------------------
    # 3. detect_transaction_discrepancies
    # -------------------------------------------------------------------------
    def detect_transaction_discrepancies(
        self,
        doc_id: Optional[str] = None,
        supplier_id: Optional[str] = None,
        extracted_doc: Optional[DocumentExtractionResponse] = None,
    ) -> DiscrepancyDetectionResponse:
        """Detects amount, quantity, tax, identity, date, and duplicate submission discrepancies.

        Cross-references against verified ground-truth records when available.
        """
        doc = extracted_doc or self.extract_document_data(doc_id=doc_id)

        target_po_id = doc.po_reference
        po = self.repo.get_purchase_order(target_po_id) if target_po_id else None
        po_lines = self.repo.get_purchase_order_lines(target_po_id) if target_po_id else []
        goods_receipts = self.repo.get_purchase_history_by_po(target_po_id) if target_po_id else []

        comparisons = compare_lines(doc.line_items, po_lines, goods_receipts) if po else []

        # Check for duplicate submission
        dup_entry = self.repo.get_supplier_business_record_by_doc(doc.doc_id)

        # Ground truth cross-reference
        ground_truth = self.repo.get_doc_ground_truth(doc.doc_id)

        discrepancies, net_excess = detect_all_discrepancies(
            doc_id=doc.doc_id,
            invoice_date=doc.invoice_date,
            invoice_supplier_id=doc.supplier.supplier_id or supplier_id,
            po_data=po,
            line_comparisons=comparisons,
            goods_receipts=goods_receipts,
            duplicate_record=dup_entry,
            ground_truth_records=ground_truth,
        )

        has_disc = len(discrepancies) > 0

        if not has_disc:
            recommendation = "CLEAN_TO_PAY: Invoice matches purchase order and receipt cleanly. Ready for verification."
        elif any(d.discrepancy_type == DiscrepancyType.DUPLICATE for d in discrepancies):
            recommendation = "REJECT_DUPLICATE: Invoice has already been recorded in ledgers. Do not pay again."
        elif net_excess > 0:
            recommendation = (
                f"HOLD_PAYMENT: Discrepancies detected resulting in Rs.{net_excess:,.2f} excess billing. "
                "Require credit note or corrected invoice before settlement."
            )
        else:
            recommendation = "REVIEW_REQUIRED: Unresolved mismatches detected. Require explicit owner approval."

        return DiscrepancyDetectionResponse(
            doc_id=doc.doc_id,
            discrepancies_found=len(discrepancies),
            has_discrepancies=has_disc,
            discrepancies=discrepancies,
            net_excess_amount=net_excess,
            ground_truth_matched=len(ground_truth) > 0,
            recommendation=recommendation,
        )

    # -------------------------------------------------------------------------
    # 4. verify_and_record_transaction
    # -------------------------------------------------------------------------
    def verify_and_record_transaction(
        self,
        doc_id: str,
        po_id: Optional[str] = None,
        approval_token: Optional[str] = None,
        notes: Optional[str] = None,
        extracted_doc: Optional[DocumentExtractionResponse] = None,
    ) -> RecordTransactionResponse:
        """Enforces reconciliation verification, duplicate prevention, and authorization gates

        before atomically recording verified accounts payable entries in supplier_business_records.
        """
        doc = extracted_doc or self.extract_document_data(doc_id=doc_id)
        supp_id = doc.supplier.supplier_id
        if not supp_id:
            raise ValidationError(f"Cannot record transaction for document '{doc_id}' without supplier_id.")

        # 1. Duplicate Prevention Check
        existing = self.repo.get_supplier_business_record_by_doc(doc.doc_id)
        if existing:
            return RecordTransactionResponse(
                success=False,
                status=TransactionRecordStatus.DUPLICATE_ALREADY_RECORDED,
                entry_id=existing["entry_id"],
                doc_id=doc.doc_id,
                supplier_id=supp_id,
                amount_recorded=float(existing["amount"]),
                previous_balance_due=float(existing["balance_due"]),
                new_balance_due=float(existing["balance_due"]),
                audit_log_id=None,
                notes=f"Duplicate rejected: Document '{doc.doc_id}' was already recorded in ledger on {existing['date']}.",
            )

        # 2. Discrepancy Gate
        disc_report = self.detect_transaction_discrepancies(doc_id=doc.doc_id, extracted_doc=doc)

        if disc_report.has_discrepancies:
            # If discrepancies exist, an approval token is mandatory
            if not approval_token:
                return RecordTransactionResponse(
                    success=False,
                    status=TransactionRecordStatus.BLOCKED_DISCREPANCIES,
                    entry_id=None,
                    doc_id=doc.doc_id,
                    supplier_id=supp_id,
                    amount_recorded=0.0,
                    previous_balance_due=self.repo.get_latest_supplier_balance(supp_id),
                    new_balance_due=self.repo.get_latest_supplier_balance(supp_id),
                    audit_log_id=None,
                    notes=(
                        f"Blocked by {disc_report.discrepancies_found} unresolved discrepancies "
                        f"(Excess: Rs.{disc_report.net_excess_amount:,.2f}). Explicit approval token required."
                    ),
                )

            # Validate approval token
            approval = self.repo.get_approval(approval_token)
            if not approval:
                return RecordTransactionResponse(
                    success=False,
                    status=TransactionRecordStatus.UNAUTHORIZED_APPROVAL_REQUIRED,
                    entry_id=None,
                    doc_id=doc.doc_id,
                    supplier_id=supp_id,
                    amount_recorded=0.0,
                    previous_balance_due=self.repo.get_latest_supplier_balance(supp_id),
                    new_balance_due=self.repo.get_latest_supplier_balance(supp_id),
                    audit_log_id=None,
                    notes=f"Invalid approval token '{approval_token}'.",
                )

            if int(approval["used"]) == 1:
                return RecordTransactionResponse(
                    success=False,
                    status=TransactionRecordStatus.UNAUTHORIZED_APPROVAL_REQUIRED,
                    entry_id=None,
                    doc_id=doc.doc_id,
                    supplier_id=supp_id,
                    amount_recorded=0.0,
                    previous_balance_due=self.repo.get_latest_supplier_balance(supp_id),
                    new_balance_due=self.repo.get_latest_supplier_balance(supp_id),
                    audit_log_id=None,
                    notes=f"Approval token '{approval_token}' has already been consumed.",
                )

        # 3. Atomic Ledger Recording
        prev_balance = self.repo.get_latest_supplier_balance(supp_id)
        record_amount = round(doc.total_amount, 2)
        new_balance = round(prev_balance + record_amount, 2)
        entry_id = f"SBR-{uuid.uuid4().hex[:8].upper()}"
        record_date = doc.invoice_date or self.repo.get_as_of_date()
        timestamp = self.repo.get_as_of_date() + "T19:10:00+05:30"

        with self.repo.db.transaction():
            # Consume token if used
            if approval_token:
                self.repo.mark_approval_used(approval_token)

            # Insert supplier business record
            entry_notes = notes or (
                f"Verified invoice recording for {doc.doc_id} (Net: Rs.{record_amount:,.2f})"
            )
            self.repo.record_supplier_business_entry(
                entry_id=entry_id,
                supplier_id=supp_id,
                date=record_date,
                entry_type="invoice",
                reference_doc=doc.doc_id,
                amount=record_amount,
                balance_due=new_balance,
                notes=entry_notes,
            )

            # Insert audit log
            audit_payload = json.dumps({
                "entry_id": entry_id,
                "doc_id": doc.doc_id,
                "supplier_id": supp_id,
                "amount": record_amount,
                "new_balance": new_balance,
                "approval_token": approval_token,
                "discrepancies_overridden": disc_report.discrepancies_found,
            })
            log_id = self.repo.insert_audit_log(
                action="RECORD_VERIFIED_INVOICE",
                actor="document_reconciliation_agent",
                payload=audit_payload,
                timestamp=timestamp,
            )

            # Record verified fact into business memory
            self.repo.insert_business_memory(
                key=f"supplier.{supp_id}.last_verified_invoice",
                value=f"{doc.doc_id} (Rs.{record_amount})",
                source="verified_record",
                timestamp=timestamp,
                confidence=1.0,
            )

        return RecordTransactionResponse(
            success=True,
            status=TransactionRecordStatus.RECORDED,
            entry_id=entry_id,
            doc_id=doc.doc_id,
            supplier_id=supp_id,
            amount_recorded=record_amount,
            previous_balance_due=prev_balance,
            new_balance_due=new_balance,
            audit_log_id=log_id,
            notes=f"Transaction verified and recorded into supplier ledger with entry {entry_id}.",
        )
