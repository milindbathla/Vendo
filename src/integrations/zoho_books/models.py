"""
Data models for Zoho Books API accounting entities and normalized responses.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class ZohoOrganization:
    organization_id: str
    name: str
    currency_code: str = "INR"
    currency_symbol: str = "₹"
    country: str = "India"
    fiscal_year_start_month: int = 4  # April for India
    is_active: bool = True
    tax_registered: bool = True
    tax_id: Optional[str] = None  # GSTIN

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ZohoInvoiceLine:
    line_item_id: str
    name: str
    quantity: float
    rate: float
    item_total: float
    hsn_code: Optional[str] = None
    tax_percentage: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ZohoInvoice:
    invoice_id: str
    invoice_number: str
    customer_id: str
    customer_name: str
    date: str
    due_date: str
    status: str  # draft, sent, paid, overdue, partially_paid, void
    total_amount: float
    balance: float  # unpaid amount
    currency_code: str = "INR"
    line_items: List[ZohoInvoiceLine] = field(default_factory=list)
    is_payment_complete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["line_items"] = [li.to_dict() for li in self.line_items]
        return d


@dataclass
class ZohoBill:
    bill_id: str
    bill_number: str
    vendor_id: str
    vendor_name: str
    date: str
    due_date: str
    status: str  # paid, open, overdue, void
    total_amount: float
    balance_due: float
    currency_code: str = "INR"
    reference_number: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ZohoExpense:
    expense_id: str
    date: str
    account_name: str  # e.g., "Kitchen Utilities", "Packaging Supplies"
    amount: float
    paid_through: str  # e.g., "Petty Cash", "HDFC Bank"
    vendor_name: Optional[str] = None
    reference_number: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ZohoAccountingSummary:
    """Distinct financial concepts: billed revenue != cash received, unpaid != bad debt."""
    total_invoiced_revenue: float
    cash_collected: float
    outstanding_receivables: float
    overdue_receivables: float
    total_bills_payable: float
    unpaid_bills_balance: float
    invoices_count: int
    bills_count: int
    currency: str = "INR"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ZohoPaginatedResponse:
    success: bool
    data: List[Any]
    page: int
    per_page: int
    has_more_page: bool
    total_records: int
    is_mock: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": [item.to_dict() if hasattr(item, "to_dict") else item for item in self.data],
            "page": self.page,
            "per_page": self.per_page,
            "has_more_page": self.has_more_page,
            "total_records": self.total_records,
            "is_mock": self.is_mock,
            "error": self.error,
        }

