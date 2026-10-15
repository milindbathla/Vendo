"""Unit tests for Document & Reconciliation specialist agent and deterministic engine."""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock

# Ensure agent src directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from document_reconciliation.agent import DocumentReconciliationAgent
from document_reconciliation.engine import (
    categorize_extraction_confidence,
    compare_lines,
    detect_all_discrepancies,
    identify_source_facts_and_uncertainties,
)
from document_reconciliation.models import (
    DiscrepancyItem,
    DiscrepancySeverity,
    DiscrepancyType,
    DocumentExtractionResponse,
    DocumentMetadata,
    DocumentParty,
    ExtractedLineItem,
    LineMatchComparison,
    ReconciliationStatus,
    RecordTransactionResponse,
    ResourceNotFoundError,
    TransactionRecordStatus,
    ValidationError,
)


class TestReconciliationEngine(unittest.TestCase):
    """Test deterministic confidence categorization, fact extraction, and line comparison."""

    def test_categorize_extraction_confidence(self):
        self.assertEqual(categorize_extraction_confidence(0.98), "HIGH_CONFIDENCE")
        self.assertEqual(categorize_extraction_confidence(0.95), "HIGH_CONFIDENCE")
        self.assertEqual(categorize_extraction_confidence(0.91), "STANDARD_CONFIDENCE")
        self.assertEqual(categorize_extraction_confidence(0.90), "STANDARD_CONFIDENCE")
        self.assertEqual(categorize_extraction_confidence(0.85), "UNCERTAIN_REVIEW_REQUIRED")
        self.assertEqual(categorize_extraction_confidence(0.70), "UNCERTAIN_REVIEW_REQUIRED")
        self.assertEqual(categorize_extraction_confidence(0.65), "LOW_CONFIDENCE_UNRELIABLE")
        self.assertEqual(categorize_extraction_confidence(0.10), "LOW_CONFIDENCE_UNRELIABLE")

    def test_identify_source_facts_and_uncertainties_high_confidence(self):
        data = {
            "invoice_number": "INV-2026-001",
            "invoice_date": "2026-10-01",
            "due_date": "2026-10-15",
            "purchase_order_reference": "PO-100",
            "currency": "INR",
            "supplier_id": "SUPP-01",
            "supplier_name": "Agro Fresh Co",
            "supplier_gstin": "09AAAAA0000A1Z5",
            "total_taxable_amount": 1000.0,
            "total_tax_amount": 50.0,
            "total_amount_payable": 1050.0,
        }
        facts, uncertain, missing = identify_source_facts_and_uncertainties(data, confidence=0.96)
        self.assertEqual(len(missing), 0)
        self.assertEqual(len(uncertain), 0)
        self.assertIn("invoice_number", facts)
        self.assertEqual(facts["invoice_number"], "INV-2026-001")

    def test_identify_source_facts_and_uncertainties_low_confidence(self):
        data = {
            "invoice_number": "INV-2026-002",
            "invoice_date": "2026-10-01",
            "due_date": None,
            "purchase_order_reference": "",
            "currency": "INR",
        }
        facts, uncertain, missing = identify_source_facts_and_uncertainties(data, confidence=0.75)
        self.assertIn("due_date", missing)
        self.assertIn("purchase_order_reference", missing)
        self.assertIn("invoice_number", uncertain)
        self.assertEqual(uncertain["invoice_number"]["value"], "INV-2026-002")

    def test_compare_lines_exact_match(self):
        inv_lines = [
            ExtractedLineItem(
                line_no=1,
                item_id="ING-001",
                description="Basmati Rice",
                billed_qty=50.0,
                unit="kg",
                unit_price=80.0,
                taxable_amount=4000.0,
                gst_rate_pct=5.0,
                gst_amount=200.0,
                line_total=4200.0,
            )
        ]
        po_lines = [
            {
                "item_id": "ING-001",
                "item_name": "Basmati Rice",
                "ordered_qty": 50.0,
                "unit": "kg",
                "unit_price": 80.0,
                "tax_rate_pct": 5.0,
                "line_total": 4200.0,
            }
        ]
        comparisons = compare_lines(inv_lines, po_lines)
        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0].status, "MATCH")
        self.assertEqual(comparisons[0].qty_variance, 0.0)
        self.assertEqual(comparisons[0].price_variance, 0.0)

    def test_compare_lines_discrepancy(self):
        inv_lines = [
            ExtractedLineItem(
                line_no=1,
                item_id="ING-001",
                description="Basmati Rice",
                billed_qty=60.0,  # 10 extra
                unit="kg",
                unit_price=90.0,  # 10 higher
                taxable_amount=5400.0,
                gst_rate_pct=5.0,
                gst_amount=270.0,
                line_total=5670.0,
            )
        ]
        po_lines = [
            {
                "item_id": "ING-001",
                "item_name": "Basmati Rice",
                "ordered_qty": 50.0,
                "unit": "kg",
                "unit_price": 80.0,
                "tax_rate_pct": 5.0,
                "line_total": 4200.0,
            }
        ]
        comparisons = compare_lines(inv_lines, po_lines)
        self.assertEqual(len(comparisons), 1)
        self.assertIn("MISMATCH", comparisons[0].status)
        self.assertEqual(comparisons[0].qty_variance, 10.0)
        self.assertEqual(comparisons[0].price_variance, 10.0)

    def test_detect_all_discrepancies_unapproved_item(self):
        inv_lines = [
            ExtractedLineItem(
                line_no=1,
                item_id="ING-EXTRA",
                description="Unknown Spice",
                billed_qty=5.0,
                unit="kg",
                unit_price=200.0,
                taxable_amount=1000.0,
                gst_rate_pct=5.0,
                gst_amount=50.0,
                line_total=1050.0,
            )
        ]
        po_lines = []
        comparisons = compare_lines(inv_lines, po_lines)
        po_data = {"po_id": "PO-100", "supplier_id": "SUPP-01"}

        discrepancies, net_excess = detect_all_discrepancies(
            doc_id="DOC-999",
            invoice_date="2026-10-14",
            invoice_supplier_id="SUPP-01",
            po_data=po_data,
            line_comparisons=comparisons,
        )
        self.assertTrue(len(discrepancies) > 0)
        # Unapproved items have a quantity variance exceeding PO ordered quantity (0.0)
        self.assertTrue(any(d.discrepancy_type == DiscrepancyType.QUANTITY for d in discrepancies))


class TestDocumentReconciliationAgent(unittest.TestCase):
    """Test agent-level extraction, reconciliation, discrepancy detection, and recording."""

    def setUp(self):
        self.mock_repo = MagicMock()
        self.agent = DocumentReconciliationAgent(self.mock_repo)

    def test_extract_document_data_no_args_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self.agent.extract_document_data()

    def test_extract_document_data_raw_payload(self):
        payload = {
            "document_metadata": {
                "doc_id": "INV-TEST-99",
                "doc_type": "invoice",
                "extraction_confidence": 0.96,
            },
            "invoice_details": {
                "invoice_number": "INV-TEST-99",
                "invoice_date": "2026-10-14",
                "currency": "INR",
            },
            "supplier": {
                "supplier_id": "SUPP-01",
                "legal_name": "Fresh Farms Ltd",
                "gstin": "09ABCDE1234F1Z5",
            },
            "line_items": [
                {
                    "line_no": 1,
                    "item_id": "TOMATO",
                    "description": "Red Tomatoes",
                    "billed_qty": 20.0,
                    "unit": "kg",
                    "unit_price": 40.0,
                    "taxable_amount": 800.0,
                    "gst_rate_pct": 5.0,
                    "gst_amount": 40.0,
                    "line_total": 840.0,
                }
            ],
            "financial_summary": {
                "total_taxable_amount": 800.0,
                "total_tax_amount": 40.0,
                "total_amount_payable": 840.0,
            },
        }

        res = self.agent.extract_document_data(raw_payload=json.dumps(payload))
        self.assertIsInstance(res, DocumentExtractionResponse)
        self.assertEqual(res.doc_id, "INV-TEST-99")
        self.assertEqual(len(res.line_items), 1)
        self.assertEqual(res.line_items[0].billed_qty, 20.0)

    def test_reconcile_invoice_against_po_clean_match(self):
        self.mock_repo.get_business_document.return_value = {
            "doc_id": "DOC-101",
            "doc_type": "invoice",
            "doc_date": "2026-10-14",
            "supplier_id": "SUPP-01",
            "supplier_name": "Agro Fresh Co",
            "supplier_gstin": "09ABCDE1234F1Z5",
            "supplier_locality": "Kanpur",
            "supplier_phone": "9876543210",
            "po_id": "PO-101",
            "total_taxable_amount": 1000.0,
            "total_tax_amount": 50.0,
            "total_amount_payable": 1050.0,
            "extraction_confidence": 0.95,
        }
        self.mock_repo.get_document_lines.return_value = [
            {
                "item_id": "ING-001",
                "item_name": "Basmati Rice",
                "billed_qty": 50.0,
                "item_unit": "kg",
                "unit_price": 20.0,
                "taxable_amount": 1000.0,
                "gst_rate_pct": 5.0,
                "gst_amount": 50.0,
                "total_line_amount": 1050.0,
            }
        ]
        self.mock_repo.get_purchase_order.return_value = {
            "po_id": "PO-101",
            "supplier_id": "SUPP-01",
            "order_date": "2026-10-10",
            "total_amount": 1050.0,
            "status": "APPROVED",
        }
        self.mock_repo.get_purchase_order_lines.return_value = [
            {
                "item_id": "ING-001",
                "item_name": "Basmati Rice",
                "ordered_qty": 50.0,
                "unit": "kg",
                "unit_price": 20.0,
                "tax_rate_pct": 5.0,
                "line_total": 1050.0,
            }
        ]
        self.mock_repo.get_purchase_history_by_po.return_value = []
        self.mock_repo.get_supplier_business_record_by_doc.return_value = None
        self.mock_repo.get_ground_truth.return_value = []

        res = self.agent.reconcile_invoice_against_po(doc_id="DOC-101", po_id="PO-101")
        self.assertEqual(res.match_status, ReconciliationStatus.CLEAN_MATCH)
        self.assertTrue(res.is_clean_match)
        self.assertEqual(res.discrepancies_count, 0)

    def test_reconcile_invoice_missing_document_raises_not_found(self):
        self.mock_repo.get_business_document.return_value = None
        with self.assertRaises(ResourceNotFoundError):
            self.agent.reconcile_invoice_against_po(doc_id="NONEXISTENT")

    def test_verify_and_record_transaction_clean_match(self):
        dummy_doc = DocumentExtractionResponse(
            doc_id="DOC-101",
            doc_type="invoice",
            invoice_number="INV-101",
            invoice_date="2026-10-14",
            due_date=None,
            po_reference="PO-101",
            currency="INR",
            payment_terms=None,
            supplier=DocumentParty(supplier_id="SUPP-01", name="Agro Fresh Co"),
            buyer=DocumentParty(supplier_id=None, name="Maa Ki Rasoi"),
            line_items=[],
            total_taxable=1000.0,
            total_tax=50.0,
            total_amount=1050.0,
            source_facts={},
            uncertain_values={},
            missing_fields=[],
            metadata=DocumentMetadata(
                doc_id="DOC-101",
                doc_type="invoice",
                file_ref="test.json",
                extraction_confidence=0.95,
            ),
        )

        self.mock_repo.get_supplier_business_record_by_doc.return_value = None
        self.mock_repo.get_latest_supplier_balance.return_value = 5000.0
        self.mock_repo.get_as_of_date.return_value = "2026-10-14"
        self.mock_repo.record_supplier_business_entry.return_value = None
        self.mock_repo.insert_audit_log.return_value = 1

        self.agent.detect_transaction_discrepancies = MagicMock()
        mock_disc_response = MagicMock()
        mock_disc_response.has_discrepancies = False
        mock_disc_response.discrepancies_found = 0
        self.agent.detect_transaction_discrepancies.return_value = mock_disc_response

        res = self.agent.verify_and_record_transaction(
            doc_id="DOC-101",
            extracted_doc=dummy_doc,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.status, TransactionRecordStatus.RECORDED)
        self.assertEqual(res.amount_recorded, 1050.0)
        self.assertEqual(res.new_balance_due, 6050.0)


if __name__ == "__main__":
    unittest.main()
