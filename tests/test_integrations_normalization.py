"""
Unit and Integration Tests for Normalization Layer and Provider Connections.
=============================================================================
Verifies conversion of external payloads into domain data structures,
accounting reconciliation rules, and database provider connection tracking.
"""
from decimal import Decimal
import sqlite3
import unittest

from src.db.connection import (
    get_provider_connection,
    initialize_database,
    upsert_provider_connection,
)
from src.integrations.google_places.models import PlaceLocation, PlaceResult
from src.integrations.normalization import BusinessDataNormalizer, to_currency_decimal
from src.integrations.zoho_books.models import ZohoAccountingSummary, ZohoBill, ZohoInvoice


class TestNormalizationAndDomainMapping(unittest.TestCase):
    """Tests normalization functions and domain mapping safeguards."""

    def test_decimal_currency_rounding(self):
        """Verifies exact half-up rounding to two decimal places."""
        self.assertEqual(to_currency_decimal(100.456), Decimal("100.46"))
        self.assertEqual(to_currency_decimal("250.104"), Decimal("250.10"))
        self.assertEqual(to_currency_decimal(50.0), Decimal("50.00"))

    def test_google_places_normalization(self):
        """Maps PlaceResult to internal market competitor format."""
        place = PlaceResult(
            place_id="places/ChIJtest99",
            name="Kakadeo Sweets & Tiffin",
            address="Kakadeo, Kanpur",
            location=PlaceLocation(latitude=26.47, longitude=80.30),
            types=["restaurant", "food"],
            rating=4.5,
            user_rating_count=120,
            business_status="OPERATIONAL",
            price_level="PRICE_LEVEL_INEXPENSIVE",
            distance_meters=450.0,
        )
        comp = BusinessDataNormalizer.map_place_to_market_competitor(place)
        self.assertEqual(comp["external_id"], "places/ChIJtest99")
        self.assertEqual(comp["provider"], "google_places")
        self.assertEqual(comp["name"], "Kakadeo Sweets & Tiffin")
        self.assertEqual(comp["distance_meters"], 450.0)
        self.assertTrue(comp["is_operational"])

    def test_zoho_invoice_normalization_and_financial_separation(self):
        """Maps Zoho Invoice to internal receivable record, separating revenue from cash."""
        inv = ZohoInvoice(
            invoice_id="inv_1234",
            invoice_number="INV-2026-0099",
            customer_id="cust_88",
            customer_name="Hostel Mess",
            date="2026-10-10",
            due_date="2026-10-17",
            status="partially_paid",
            total_amount=5000.0,
            balance=2000.0,  # 3000 collected, 2000 still receivable
            currency_code="INR",
            line_items=[],
            is_payment_complete=False,
        )
        rec = BusinessDataNormalizer.map_zoho_invoice_to_receivable_record(inv, business_type="home_tiffin")
        self.assertEqual(rec["external_id"], "inv_1234")
        self.assertEqual(rec["total_amount"], 5000.0)
        self.assertEqual(rec["cash_collected"], 3000.0)
        self.assertEqual(rec["balance_receivable"], 2000.0)
        self.assertFalse(rec["is_settled"])

    def test_zoho_bill_normalization(self):
        """Maps Zoho Bill to internal accounts payable format."""
        bill = ZohoBill(
            bill_id="bill_555",
            bill_number="BILL-GUPTA-101",
            vendor_id="SUP-01",
            vendor_name="Gupta Oil Agency",
            date="2026-10-09",
            due_date="2026-10-16",
            status="open",
            total_amount=2100.0,
            balance_due=2100.0,
            currency_code="INR",
            reference_number="INV-GUPTA-0912",
        )
        rec = BusinessDataNormalizer.map_zoho_bill_to_payable_record(bill)
        self.assertEqual(rec["external_id"], "bill_555")
        self.assertEqual(rec["vendor_id"], "SUP-01")
        self.assertEqual(rec["balance_payable"], 2100.0)
        self.assertEqual(rec["amount_paid"], 0.0)

    def test_reconciliation_with_internal_state(self):
        """Calculates cash and payables discrepancies between internal and Zoho books."""
        summary = ZohoAccountingSummary(
            total_invoiced_revenue=15000.0,
            cash_collected=10000.0,
            outstanding_receivables=5000.0,
            overdue_receivables=1500.0,
            total_bills_payable=6000.0,
            unpaid_bills_balance=4000.0,
            invoices_count=5,
            bills_count=3,
        )
        # Internal cash is 10,000, unpaid bills are 4,200
        rec = BusinessDataNormalizer.reconcile_summary_with_internal(
            internal_cash=10000.0,
            internal_unpaid_bills=4200.0,
            zoho_summary=summary,
        )
        self.assertEqual(rec["cash_discrepancy"], 0.0)  # exact match on cash
        self.assertEqual(rec["payables_discrepancy"], 200.0)  # 4200 internal vs 4000 in Zoho


class TestProviderConnectionsDatabase(unittest.TestCase):
    """Tests autopilot_provider_connections table CRUD operations."""

    def setUp(self):
        # Open in-memory URI database with shared cache for connection isolation
        self.db_path = "/tmp/test_autopilot_integrations.db"
        initialize_database(self.db_path)

    def test_upsert_and_retrieve_provider_connections(self):
        """Records provider connection metadata and retrieves it correctly."""
        upsert_provider_connection(
            provider="google_places",
            business_type="home_tiffin",
            status="mock",
            metadata={"anchor": "Kanpur", "max_radius": 50000},
            db_path=self.db_path,
        )
        upsert_provider_connection(
            provider="zoho_books",
            business_type="home_tiffin",
            status="connected",
            org_id="org_892341",
            api_domain="https://www.zohoapis.in",
            scopes="ZohoBooks.invoices.READ",
            metadata={"datacenter": "IN"},
            db_path=self.db_path,
        )

        places_conn = get_provider_connection("google_places", "home_tiffin", db_path=self.db_path)
        self.assertIsNotNone(places_conn)
        self.assertEqual(places_conn["status"], "mock")
        self.assertEqual(places_conn["metadata"]["anchor"], "Kanpur")

        zoho_conn = get_provider_connection("zoho_books", "home_tiffin", db_path=self.db_path)
        self.assertIsNotNone(zoho_conn)
        self.assertEqual(zoho_conn["status"], "connected")
        self.assertEqual(zoho_conn["org_id"], "org_892341")
        self.assertEqual(zoho_conn["api_domain"], "https://www.zohoapis.in")


if __name__ == "__main__":
    unittest.main()

