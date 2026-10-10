"""Domain models, enums, and exceptions for Document & Reconciliation Agent."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReconciliationStatus(str, Enum):
    """Categorized status of invoice-to-purchase-order matching."""
    CLEAN_MATCH = "CLEAN_MATCH"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    PO_NOT_FOUND = "PO_NOT_FOUND"
    NO_PO_REFERENCE = "NO_PO_REFERENCE"
    SUPPLIER_MISMATCH = "SUPPLIER_MISMATCH"


class DiscrepancyType(str, Enum):
    """Types of discrepancies discovered between invoice and PO/receipt."""
    QUANTITY = "quantity"
    PRICE = "price"
    TAX_RATE = "tax_rate"
    AMOUNT = "amount"
    IDENTITY = "identity"
    DATE = "date"
    DUPLICATE = "duplicate"
    NONE = "none"


class DiscrepancySeverity(str, Enum):
    """Severity rating for flagged transaction discrepancies."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TransactionRecordStatus(str, Enum):
    """Outcome status of an attempt to verify and record a financial transaction."""
    RECORDED = "RECORDED"
    DUPLICATE_ALREADY_RECORDED = "DUPLICATE_ALREADY_RECORDED"
    BLOCKED_DISCREPANCIES = "BLOCKED_DISCREPANCIES"
    UNAUTHORIZED_APPROVAL_REQUIRED = "UNAUTHORIZED_APPROVAL_REQUIRED"
    INVALID_INPUT = "INVALID_INPUT"


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------
class ReconciliationError(Exception):
    """Base exception for reconciliation operations."""
    pass


class ValidationError(ReconciliationError):
    """Raised when input parameters fail domain validation rules."""
    pass


class ResourceNotFoundError(ReconciliationError):
    """Raised when a requested document, PO, or supplier does not exist."""
    pass


class DiscrepancyError(ReconciliationError):
    """Raised when an unverified or disputed document is processed illegally."""
    pass


class AuthorizationError(ReconciliationError):
    """Raised when approval tokens or credentials are invalid or expired."""
    pass


class DuplicateTransactionError(ReconciliationError):
    """Raised when an identical invoice has already been committed to ledgers."""
    pass


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------
@dataclass
class ExtractedLineItem:
    line_no: int
    item_id: str
    description: str
    billed_qty: float
    unit: str
    unit_price: float
    taxable_amount: float
    gst_rate_pct: float
    gst_amount: float
    line_total: float
    hsn_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentParty:
    supplier_id: Optional[str]
    name: str
    gstin: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentMetadata:
    doc_id: str
    doc_type: str
    file_ref: str
    extraction_confidence: float
    source_type: str = "database"  # database, fixture, payload
    authenticity_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentExtractionResponse:
    doc_id: str
    doc_type: str
    invoice_number: str
    invoice_date: str
    due_date: Optional[str]
    po_reference: Optional[str]
    currency: str
    payment_terms: Optional[str]
    supplier: DocumentParty
    buyer: DocumentParty
    line_items: List[ExtractedLineItem]
    total_taxable: float
    total_tax: float
    total_amount: float
    source_facts: Dict[str, Any]
    uncertain_values: Dict[str, Any]
    missing_fields: List[str]
    metadata: DocumentMetadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "due_date": self.due_date,
            "po_reference": self.po_reference,
            "currency": self.currency,
            "payment_terms": self.payment_terms,
            "supplier": self.supplier.to_dict(),
            "buyer": self.buyer.to_dict(),
            "line_items": [li.to_dict() for li in self.line_items],
            "total_taxable": round(self.total_taxable, 2),
            "total_tax": round(self.total_tax, 2),
            "total_amount": round(self.total_amount, 2),
            "source_facts": self.source_facts,
            "uncertain_values": self.uncertain_values,
            "missing_fields": self.missing_fields,
            "metadata": self.metadata.to_dict(),
        }


@dataclass
class LineMatchComparison:
    line_no: int
    item_id: str
    description: str
    billed_qty: float
    ordered_qty: float
    received_qty: Optional[float]
    billed_unit_price: float
    po_unit_price: float
    billed_gst_pct: float
    po_gst_pct: float
    billed_line_total: float
    po_line_total: float
    qty_variance: float
    price_variance: float
    tax_variance_pct: float
    amount_variance: float
    status: str  # MATCH, QUANTITY_MISMATCH, PRICE_MISMATCH, TAX_MISMATCH, UNORDERED_ITEM

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReconciliationResponse:
    doc_id: str
    po_id: Optional[str]
    supplier_id: str
    supplier_name: str
    match_status: ReconciliationStatus
    is_clean_match: bool
    line_comparisons: List[LineMatchComparison]
    total_billed: float
    total_expected_po: float
    total_amount_variance: float
    goods_receipt_matched: bool
    discrepancies_count: int
    summary_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "po_id": self.po_id,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "match_status": self.match_status.value,
            "is_clean_match": self.is_clean_match,
            "line_comparisons": [lc.to_dict() for lc in self.line_comparisons],
            "total_billed": round(self.total_billed, 2),
            "total_expected_po": round(self.total_expected_po, 2),
            "total_amount_variance": round(self.total_amount_variance, 2),
            "goods_receipt_matched": self.goods_receipt_matched,
            "discrepancies_count": self.discrepancies_count,
            "summary_notes": self.summary_notes,
        }


@dataclass
class DiscrepancyItem:
    discrepancy_type: DiscrepancyType
    field_name: str
    expected_value: str
    actual_value: str
    difference_amount: float
    severity: DiscrepancySeverity
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "discrepancy_type": self.discrepancy_type.value,
            "field_name": self.field_name,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "difference_amount": round(self.difference_amount, 2),
            "severity": self.severity.value,
            "description": self.description,
        }


@dataclass
class DiscrepancyDetectionResponse:
    doc_id: str
    discrepancies_found: int
    has_discrepancies: bool
    discrepancies: List[DiscrepancyItem]
    net_excess_amount: float
    ground_truth_matched: bool
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "discrepancies_found": self.discrepancies_found,
            "has_discrepancies": self.has_discrepancies,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "net_excess_amount": round(self.net_excess_amount, 2),
            "ground_truth_matched": self.ground_truth_matched,
            "recommendation": self.recommendation,
        }


@dataclass
class RecordTransactionResponse:
    success: bool
    status: TransactionRecordStatus
    entry_id: Optional[str]
    doc_id: str
    supplier_id: str
    amount_recorded: float
    previous_balance_due: float
    new_balance_due: float
    audit_log_id: Optional[int]
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value,
            "entry_id": self.entry_id,
            "doc_id": self.doc_id,
            "supplier_id": self.supplier_id,
            "amount_recorded": round(self.amount_recorded, 2),
            "previous_balance_due": round(self.previous_balance_due, 2),
            "new_balance_due": round(self.new_balance_due, 2),
            "audit_log_id": self.audit_log_id,
            "notes": self.notes,
        }
