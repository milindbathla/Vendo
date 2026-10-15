"""
Normalization and Domain Mapping Layer for External Integrations.
=================================================================
Safely maps external data structures (Google Places, Zoho Books) to internal
business representations without creating competing sources of truth or
overwriting user-verified records.

Enforces:
- Strict financial separation (Billed Revenue vs Cash Collected vs Receivables).
- Idempotent duplicate detection.
- Decimal/exact rounding for monetary accounting.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict, List, Optional

from src.integrations.google_places.models import PlaceResult
from src.integrations.zoho_books.models import ZohoAccountingSummary, ZohoBill, ZohoInvoice
from src.db.connection import DEFAULT_DB_PATH, get_connection, upsert_provider_connection

logger = logging.getLogger(__name__)


def to_currency_decimal(amount: float | str | Decimal) -> Decimal:
    """Converts a monetary figure to a 2-decimal rounded Decimal."""
    d = Decimal(str(amount))
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class BusinessDataNormalizer:
    """Provides read-only transformations and audit-safe database mappings."""

    @staticmethod
    def map_place_to_market_competitor(place: PlaceResult) -> Dict[str, Any]:
        """Maps Google Places PlaceResult to an internal market competitor record."""
        return {
            "external_id": place.place_id,
            "provider": "google_places",
            "name": place.name,
            "address": place.address,
            "latitude": place.location.latitude,
            "longitude": place.location.longitude,
            "distance_meters": place.distance_meters,
            "rating": place.rating,
            "reviews_count": place.user_rating_count,
            "types": place.types,
            "is_operational": place.business_status == "OPERATIONAL",
            "price_level": place.price_level,
        }

    @staticmethod
    def map_zoho_invoice_to_receivable_record(
        invoice: ZohoInvoice,
        business_type: str = "home_tiffin",
    ) -> Dict[str, Any]:
        """Maps a Zoho Books Invoice to internal receivable ledger schema."""
        total = to_currency_decimal(invoice.total_amount)
        balance = to_currency_decimal(invoice.balance)
        collected = to_currency_decimal(total - balance)

        return {
            "external_id": invoice.invoice_id,
            "invoice_number": invoice.invoice_number,
            "provider": "zoho_books",
            "business_type": business_type,
            "customer_name": invoice.customer_name,
            "customer_id": invoice.customer_id,
            "date": invoice.date,
            "due_date": invoice.due_date,
            "status": invoice.status,
            "total_amount": float(total),
            "cash_collected": float(collected),
            "balance_receivable": float(balance),
            "is_settled": invoice.is_payment_complete,
            "currency": invoice.currency_code,
        }

    @staticmethod
    def map_zoho_bill_to_payable_record(
        bill: ZohoBill,
        business_type: str = "home_tiffin",
    ) -> Dict[str, Any]:
        """Maps a Zoho Books Bill to internal accounts payable representation."""
        total = to_currency_decimal(bill.total_amount)
        balance = to_currency_decimal(bill.balance_due)
        paid = to_currency_decimal(total - balance)

        return {
            "external_id": bill.bill_id,
            "bill_number": bill.bill_number,
            "reference_number": bill.reference_number,
            "provider": "zoho_books",
            "business_type": business_type,
            "vendor_name": bill.vendor_name,
            "vendor_id": bill.vendor_id,
            "date": bill.date,
            "due_date": bill.due_date,
            "status": bill.status,
            "total_amount": float(total),
            "amount_paid": float(paid),
            "balance_payable": float(balance),
            "currency": bill.currency_code,
        }

    @staticmethod
    def reconcile_summary_with_internal(
        internal_cash: float,
        internal_unpaid_bills: float,
        zoho_summary: ZohoAccountingSummary,
    ) -> Dict[str, Any]:
        """Compares internal system state with external Zoho Books accounting state."""
        int_cash = to_currency_decimal(internal_cash)
        ext_collected = to_currency_decimal(zoho_summary.cash_collected)

        int_bills = to_currency_decimal(internal_unpaid_bills)
        ext_bills = to_currency_decimal(zoho_summary.unpaid_bills_balance)

        return {
            "internal_cash": float(int_cash),
            "zoho_collected_cash": float(ext_collected),
            "cash_discrepancy": float(int_cash - ext_collected),
            "internal_unpaid_bills": float(int_bills),
            "zoho_unpaid_bills": float(ext_bills),
            "payables_discrepancy": float(int_bills - ext_bills),
            "total_invoiced_revenue": zoho_summary.total_invoiced_revenue,
            "outstanding_receivables": zoho_summary.outstanding_receivables,
            "overdue_receivables": zoho_summary.overdue_receivables,
            "status": "ANALYZED",
        }

