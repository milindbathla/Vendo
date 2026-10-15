"""
Realistic synthetic mock data for Zoho Books API.
=================================================
Matches the business context of Maa Ki Rasoi Cloud Kitchen (Kakadeo, Kanpur).
Vendor bills explicitly match the anchor suppliers in data/demo.db.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MOCK_ORGANIZATION_DATA: Dict[str, Any] = {
    "organization_id": "org_in_892341",
    "name": "Maa Ki Rasoi Cloud Kitchen",
    "currency_code": "INR",
    "currency_symbol": "₹",
    "country": "India",
    "fiscal_year_start_month": 4,
    "is_active": True,
    "tax_registered": True,
    "tax_id": "09ZZZZZ9999Z1Z5",
    "address": "128/45 B-Block, Kakadeo, Kanpur, Uttar Pradesh 208025",
    "phone": "+91 9839000000",
}

MOCK_INVOICES_DATA: List[Dict[str, Any]] = [
    {
        "invoice_id": "inv_9001",
        "invoice_number": "INV-2026-00101",
        "customer_id": "cust_01",
        "customer_name": "Kakadeo Student Hostel A",
        "date": "2026-10-08",
        "due_date": "2026-10-15",
        "status": "paid",
        "total": 4500.0,
        "balance": 0.0,
        "currency_code": "INR",
        "line_items": [
            {
                "line_item_id": "li_01",
                "name": "Standard Veg Tiffin (Weekly Package)",
                "quantity": 50.0,
                "rate": 90.0,
                "item_total": 4500.0,
                "tax_percentage": 5.0,
                "hsn_code": "996331",
            }
        ],
    },
    {
        "invoice_id": "inv_9002",
        "invoice_number": "INV-2026-00102",
        "customer_id": "cust_02",
        "customer_name": "Tech Hub Coaching Center Faculty",
        "date": "2026-10-09",
        "due_date": "2026-10-16",
        "status": "sent",
        "total": 8500.0,
        "balance": 8500.0,
        "currency_code": "INR",
        "line_items": [
            {
                "line_item_id": "li_02",
                "name": "Executive Veg Meal Subscription",
                "quantity": 100.0,
                "rate": 85.0,
                "item_total": 8500.0,
                "tax_percentage": 5.0,
                "hsn_code": "996331",
            }
        ],
    },
    {
        "invoice_id": "inv_9003",
        "invoice_number": "INV-2026-00103",
        "customer_id": "cust_03",
        "customer_name": "Arya Coaching Mess",
        "date": "2026-10-02",
        "due_date": "2026-10-09",
        "status": "overdue",
        "total": 3200.0,
        "balance": 3200.0,
        "currency_code": "INR",
        "line_items": [
            {
                "line_item_id": "li_03",
                "name": "Standard Veg Tiffin",
                "quantity": 40.0,
                "rate": 80.0,
                "item_total": 3200.0,
                "tax_percentage": 5.0,
                "hsn_code": "996331",
            }
        ],
    },
    {
        "invoice_id": "inv_9004",
        "invoice_number": "INV-2026-00104",
        "customer_id": "cust_04",
        "customer_name": "Daily Individual App Orders (Batch)",
        "date": "2026-10-10",
        "due_date": "2026-10-10",
        "status": "paid",
        "total": 1700.0,
        "balance": 0.0,
        "currency_code": "INR",
        "line_items": [
            {
                "line_item_id": "li_04",
                "name": "Standard Veg Tiffin (Single Day)",
                "quantity": 20.0,
                "rate": 85.0,
                "item_total": 1700.0,
                "tax_percentage": 5.0,
                "hsn_code": "996331",
            }
        ],
    },
]

# Vendor bills matching data/demo.db suppliers (Gupta Oil, Packaging Mart, Wholesale Mandi)
MOCK_BILLS_DATA: List[Dict[str, Any]] = [
    {
        "bill_id": "bill_8001",
        "bill_number": "BILL-GUPTA-0912",
        "vendor_id": "SUP-01",
        "vendor_name": "Gupta Oil Agency",
        "date": "2026-10-09",
        "due_date": "2026-10-16",
        "status": "paid",
        "total": 2100.0,
        "balance": 0.0,
        "currency_code": "INR",
        "reference_number": "INV-GUPTA-0912",
    },
    {
        "bill_id": "bill_8002",
        "bill_number": "BILL-PKG-0245",
        "vendor_id": "SUP-02",
        "vendor_name": "Packaging Mart Kanpur",
        "date": "2026-10-10",
        "due_date": "2026-10-17",
        "status": "open",
        "total": 1500.0,
        "balance": 1500.0,
        "currency_code": "INR",
        "reference_number": "INV-PKG-0245",
    },
    {
        "bill_id": "bill_8003",
        "bill_number": "BILL-MANDI-1001",
        "vendor_id": "SUP-03",
        "vendor_name": "Wholesale Mandi Atta & Dal",
        "date": "2026-10-07",
        "due_date": "2026-10-14",
        "status": "open",
        "total": 4200.0,
        "balance": 4200.0,
        "currency_code": "INR",
        "reference_number": "MANDI-OCT-07",
    },
]

MOCK_EXPENSES_DATA: List[Dict[str, Any]] = [
    {
        "expense_id": "exp_7001",
        "date": "2026-10-08",
        "account_name": "Kitchen Commercial LPG",
        "amount": 2200.0,
        "paid_through": "HDFC Current Account",
        "vendor_name": "Bharat Gas Agency",
        "reference_number": "LPG-9921",
        "description": "2x 19kg commercial cylinders",
    },
    {
        "expense_id": "exp_7002",
        "date": "2026-10-09",
        "account_name": "Delivery Logistics OPEX",
        "amount": 650.0,
        "paid_through": "Petty Cash",
        "vendor_name": "Local Delivery Boys Pool",
        "reference_number": "PETTY-FUEL-09",
        "description": "Daily delivery bike fuel allowances",
    },
    {
        "expense_id": "exp_7003",
        "date": "2026-10-10",
        "account_name": "Kitchen Hygiene & Supplies",
        "amount": 450.0,
        "paid_through": "UPI Payment",
        "vendor_name": "Kanpur General Mart",
        "reference_number": "UPI-HYG-10",
        "description": "Food safety gloves, hair nets, sanitizers",
    },
]


def get_mock_zoho_invoices_raw(
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """Simulates paginated Zoho Books GET /books/v3/invoices."""
    filtered = MOCK_INVOICES_DATA
    if status:
        filtered = [inv for inv in filtered if inv.get("status") == status.lower()]

    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]
    has_more = end < len(filtered)

    return {
        "code": 0,
        "message": "success",
        "invoices": page_items,
        "page_context": {
            "page": page,
            "per_page": per_page,
            "has_more_page": has_more,
            "total": len(filtered),
        },
    }


def get_mock_zoho_bills_raw(
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """Simulates paginated Zoho Books GET /books/v3/bills."""
    start = (page - 1) * per_page
    end = start + per_page
    page_items = MOCK_BILLS_DATA[start:end]
    has_more = end < len(MOCK_BILLS_DATA)

    return {
        "code": 0,
        "message": "success",
        "bills": page_items,
        "page_context": {
            "page": page,
            "per_page": per_page,
            "has_more_page": has_more,
            "total": len(MOCK_BILLS_DATA),
        },
    }


def get_mock_zoho_expenses_raw(
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """Simulates paginated Zoho Books GET /books/v3/expenses."""
    start = (page - 1) * per_page
    end = start + per_page
    page_items = MOCK_EXPENSES_DATA[start:end]
    has_more = end < len(MOCK_EXPENSES_DATA)

    return {
        "code": 0,
        "message": "success",
        "expenses": page_items,
        "page_context": {
            "page": page,
            "per_page": per_page,
            "has_more_page": has_more,
            "total": len(MOCK_EXPENSES_DATA),
        },
    }

