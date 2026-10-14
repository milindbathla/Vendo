"""
Zoho Books Adapter: Normalization, Accounting Rules, and Mock Orchestration.
============================================================================
Provides read-only access to Zoho Books organizations, invoices, bills, and
expenses with financial separation of revenue, cash collected, and receivables.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.integrations.base import (
    AuthenticationError,
    IntegrationConfig,
    IntegrationError,
    RateLimitError,
    ValidationError,
)
from src.integrations.zoho_books.client import ZohoBooksClient
from src.integrations.zoho_books.mock_data import (
    MOCK_BILLS_DATA,
    MOCK_EXPENSES_DATA,
    MOCK_INVOICES_DATA,
    MOCK_ORGANIZATION_DATA,
    get_mock_zoho_bills_raw,
    get_mock_zoho_expenses_raw,
    get_mock_zoho_invoices_raw,
)
from src.integrations.zoho_books.models import (
    ZohoAccountingSummary,
    ZohoBill,
    ZohoExpense,
    ZohoInvoice,
    ZohoInvoiceLine,
    ZohoOrganization,
    ZohoPaginatedResponse,
)
from src.integrations.zoho_books.oauth import ZohoOAuthManager

logger = logging.getLogger(__name__)


class ZohoBooksAdapter:
    """High-level adapter for Zoho Books read-only accounting operations."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        org_id: Optional[str] = None,
        accounts_url: Optional[str] = None,
        api_domain: Optional[str] = None,
        force_mock: Optional[bool] = None,
        timeout_seconds: float = 12.0,
    ):
        cfg = IntegrationConfig.get_zoho_config()
        self.client_id = client_id or cfg["client_id"]
        self.client_secret = client_secret or cfg["client_secret"]
        self.refresh_token = refresh_token or cfg["refresh_token"]
        self.org_id = org_id or cfg["org_id"] or "org_in_892341"
        self.accounts_url = accounts_url or cfg["accounts_url"]
        self.api_domain = api_domain or cfg["api_domain"]

        self.force_mock = IntegrationConfig.is_mock_enabled(force_mock)

        # Initialize OAuth Manager
        self.oauth_manager = ZohoOAuthManager(
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=self.refresh_token,
            accounts_url=self.accounts_url,
            api_domain=self.api_domain,
            force_mock=self.force_mock,
        )

        self._client: Optional[ZohoBooksClient] = None
        if not self.force_mock and self.oauth_manager.is_configured:
            try:
                self._client = ZohoBooksClient(
                    token_provider=self.oauth_manager.get_access_token,
                    api_domain=self.oauth_manager.api_domain,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as e:
                logger.warning("Failed to initialize Zoho Books client: %s. Falling back to mock.", e)
                self.force_mock = True
        else:
            self.force_mock = True

    @property
    def is_mock(self) -> bool:
        return self.force_mock or self._client is None

    # -------------------------------------------------------------------------
    # 1. Organization Information
    # -------------------------------------------------------------------------
    def get_organization(self, organization_id: Optional[str] = None) -> ZohoOrganization:
        """Retrieves organization metadata and currency parameters."""
        target_org_id = organization_id or self.org_id

        if self.is_mock:
            raw = dict(MOCK_ORGANIZATION_DATA)
            if target_org_id:
                raw["organization_id"] = target_org_id
            return self._normalize_organization(raw)

        assert self._client is not None
        if target_org_id:
            resp = self._client.get_organization_details(target_org_id)
            org_data = resp.get("organization", {})
        else:
            resp = self._client.get_organizations()
            orgs = resp.get("organizations", [])
            org_data = orgs[0] if orgs else {}

        if not org_data:
            raise ValidationError(f"Zoho Organization '{target_org_id}' not found", provider="zoho_books")
        return self._normalize_organization(org_data)

    def _normalize_organization(self, data: Dict[str, Any]) -> ZohoOrganization:
        return ZohoOrganization(
            organization_id=data.get("organization_id", "unknown"),
            name=data.get("name") or data.get("organization_name", "Unnamed Organization"),
            currency_code=data.get("currency_code", "INR"),
            currency_symbol=data.get("currency_symbol", "₹"),
            country=data.get("country", "India"),
            fiscal_year_start_month=int(data.get("fiscal_year_start_month", 4)),
            is_active=bool(data.get("is_active", True)),
            tax_registered=bool(data.get("tax_registered", True)),
            tax_id=data.get("tax_id") or data.get("gstin"),
        )

    # -------------------------------------------------------------------------
    # 2. Invoices & Receivables
    # -------------------------------------------------------------------------
    def get_invoices(
        self,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> ZohoPaginatedResponse:
        """Retrieves and normalizes invoices."""
        if page < 1:
            raise ValidationError("page must be >= 1", provider="zoho_books")
        if per_page < 1 or per_page > 200:
            raise ValidationError("per_page must be between 1 and 200", provider="zoho_books")

        if self.is_mock:
            raw = get_mock_zoho_invoices_raw(status=status, page=page, per_page=per_page)
        else:
            assert self._client is not None
            raw = self._client.get_invoices(
                organization_id=self.org_id,
                status=status,
                page=page,
                per_page=per_page,
            )

        invoices = [self._normalize_invoice(inv) for inv in raw.get("invoices", [])]
        ctx = raw.get("page_context", {})

        return ZohoPaginatedResponse(
            success=True,
            data=invoices,
            page=int(ctx.get("page", page)),
            per_page=int(ctx.get("per_page", per_page)),
            has_more_page=bool(ctx.get("has_more_page", False)),
            total_records=int(ctx.get("total", len(invoices))),
            is_mock=self.is_mock,
        )

    def _normalize_invoice(self, data: Dict[str, Any]) -> ZohoInvoice:
        lines: List[ZohoInvoiceLine] = []
        for li in data.get("line_items", []):
            lines.append(
                ZohoInvoiceLine(
                    line_item_id=str(li.get("line_item_id", "")),
                    name=li.get("name") or li.get("item_name", "Item"),
                    quantity=float(li.get("quantity", 1.0)),
                    rate=float(li.get("rate", 0.0)),
                    item_total=float(li.get("item_total", 0.0)),
                    hsn_code=li.get("hsn_code"),
                    tax_percentage=float(li.get("tax_percentage", 0.0)),
                )
            )

        total_amount = float(data.get("total", sum(l.item_total for l in lines)))
        balance = float(data.get("balance", 0.0))
        status_val = data.get("status", "sent").lower()
        is_paid = (status_val == "paid") or (balance <= 0.001 and total_amount > 0)

        return ZohoInvoice(
            invoice_id=str(data.get("invoice_id", "")),
            invoice_number=str(data.get("invoice_number", "")),
            customer_id=str(data.get("customer_id", "")),
            customer_name=data.get("customer_name", "Customer"),
            date=data.get("date", ""),
            due_date=data.get("due_date", ""),
            status=status_val,
            total_amount=round(total_amount, 2),
            balance=round(balance, 2),
            currency_code=data.get("currency_code", "INR"),
            line_items=lines,
            is_payment_complete=is_paid,
        )

    # -------------------------------------------------------------------------
    # 3. Bills & Accounts Payable
    # -------------------------------------------------------------------------
    def get_bills(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> ZohoPaginatedResponse:
        """Retrieves and normalizes vendor bills."""
        if page < 1:
            raise ValidationError("page must be >= 1", provider="zoho_books")
        if per_page < 1 or per_page > 200:
            raise ValidationError("per_page must be between 1 and 200", provider="zoho_books")

        if self.is_mock:
            raw = get_mock_zoho_bills_raw(page=page, per_page=per_page)
        else:
            assert self._client is not None
            raw = self._client.get_bills(
                organization_id=self.org_id,
                page=page,
                per_page=per_page,
            )

        bills = [self._normalize_bill(b) for b in raw.get("bills", [])]
        ctx = raw.get("page_context", {})

        return ZohoPaginatedResponse(
            success=True,
            data=bills,
            page=int(ctx.get("page", page)),
            per_page=int(ctx.get("per_page", per_page)),
            has_more_page=bool(ctx.get("has_more_page", False)),
            total_records=int(ctx.get("total", len(bills))),
            is_mock=self.is_mock,
        )

    def _normalize_bill(self, data: Dict[str, Any]) -> ZohoBill:
        return ZohoBill(
            bill_id=str(data.get("bill_id", "")),
            bill_number=str(data.get("bill_number", "")),
            vendor_id=str(data.get("vendor_id", "")),
            vendor_name=data.get("vendor_name", "Vendor"),
            date=data.get("date", ""),
            due_date=data.get("due_date", ""),
            status=data.get("status", "open").lower(),
            total_amount=round(float(data.get("total", 0.0)), 2),
            balance_due=round(float(data.get("balance", 0.0)), 2),
            currency_code=data.get("currency_code", "INR"),
            reference_number=data.get("reference_number"),
        )

    # -------------------------------------------------------------------------
    # 4. Expenses
    # -------------------------------------------------------------------------
    def get_expenses(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> ZohoPaginatedResponse:
        """Retrieves and normalizes operating expenses."""
        if page < 1:
            raise ValidationError("page must be >= 1", provider="zoho_books")
        if per_page < 1 or per_page > 200:
            raise ValidationError("per_page must be between 1 and 200", provider="zoho_books")

        if self.is_mock:
            raw = get_mock_zoho_expenses_raw(page=page, per_page=per_page)
        else:
            assert self._client is not None
            raw = self._client.get_expenses(
                organization_id=self.org_id,
                page=page,
                per_page=per_page,
            )

        expenses = [self._normalize_expense(e) for e in raw.get("expenses", [])]
        ctx = raw.get("page_context", {})

        return ZohoPaginatedResponse(
            success=True,
            data=expenses,
            page=int(ctx.get("page", page)),
            per_page=int(ctx.get("per_page", per_page)),
            has_more_page=bool(ctx.get("has_more_page", False)),
            total_records=int(ctx.get("total", len(expenses))),
            is_mock=self.is_mock,
        )

    def _normalize_expense(self, data: Dict[str, Any]) -> ZohoExpense:
        return ZohoExpense(
            expense_id=str(data.get("expense_id", "")),
            date=data.get("date", ""),
            account_name=data.get("account_name", "General Expense"),
            amount=round(float(data.get("amount", 0.0)), 2),
            paid_through=data.get("paid_through", "Petty Cash"),
            vendor_name=data.get("vendor_name"),
            reference_number=data.get("reference_number"),
            description=data.get("description"),
        )

    # -------------------------------------------------------------------------
    # 5. Financial Summary (Preserving Accounting Distinctions)
    # -------------------------------------------------------------------------
    def get_accounting_summary(self) -> ZohoAccountingSummary:
        """Aggregates revenue, cash collected, receivables, and payables.

        CRITICAL FINANCIAL RULE:
        * Billed revenue is NOT cash collected.
        * Outstanding receivables are separated into active vs overdue.
        """
        invoices_resp = self.get_invoices(page=1, per_page=100)
        bills_resp = self.get_bills(page=1, per_page=100)

        invoices: List[ZohoInvoice] = invoices_resp.data
        bills: List[ZohoBill] = bills_resp.data

        total_invoiced = sum(inv.total_amount for inv in invoices)
        unpaid_receivables = sum(inv.balance for inv in invoices)
        cash_collected = total_invoiced - unpaid_receivables
        overdue_receivables = sum(inv.balance for inv in invoices if inv.status == "overdue")

        total_bills = sum(b.total_amount for b in bills)
        unpaid_bills = sum(b.balance_due for b in bills)

        return ZohoAccountingSummary(
            total_invoiced_revenue=round(total_invoiced, 2),
            cash_collected=round(cash_collected, 2),
            outstanding_receivables=round(unpaid_receivables, 2),
            overdue_receivables=round(overdue_receivables, 2),
            total_bills_payable=round(total_bills, 2),
            unpaid_bills_balance=round(unpaid_bills, 2),
            invoices_count=len(invoices),
            bills_count=len(bills),
            currency="INR",
        )

