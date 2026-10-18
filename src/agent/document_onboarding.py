"""
Evidence-Backed Document Onboarding Engine
===========================================
Ingests PDF, CSV, XLSX, and TXT documents for small-business onboarding.
Preserves exact source provenance (file, page, sheet, row), detects contradictions,
and guards against silently overwriting confirmed business facts.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field, asdict
import io
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET
import zipfile

from src.db.profile_repository import AdaptiveProfileRepository
from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactStatus,
    FactSource,
)

logger = logging.getLogger(__name__)


@dataclass
class DocumentEvidence:
    """Precise source location and context of an extracted business detail."""
    file_name: str
    format: str  # "pdf", "csv", "xlsx", "txt"
    location: str  # e.g., "Page 1, Line 4", "Row 12, Col 'Price'", "Sheet: Services, Row 5"
    raw_snippet: str
    extracted_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedFactCandidate:
    """Candidate fact extracted from document with provenance and confidence."""
    key: str
    value: Any
    value_type: str
    evidence: DocumentEvidence
    confidence: float = 0.85
    category_hint: Optional[str] = None
    is_conflict: bool = False
    conflict_notes: str = ""


class DocumentParser:
    """Parses text and structured tables from PDF, CSV, XLSX, and TXT files."""

    @staticmethod
    def parse_txt(content: Union[str, bytes], filename: str = "document.txt") -> List[DocumentEvidence]:
        """Extracts lines and paragraphs from plain text content."""
        if isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
        else:
            text = content

        snippets = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for idx, line in enumerate(lines, start=1):
            snippets.append(
                DocumentEvidence(
                    file_name=filename,
                    format="txt",
                    location=f"Line {idx}",
                    raw_snippet=line,
                )
            )
        return snippets

    @staticmethod
    def parse_csv(content: Union[str, bytes], filename: str = "data.csv") -> List[DocumentEvidence]:
        """Extracts structured rows and cells from CSV content."""
        if isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
        else:
            text = content

        snippets = []
        reader = csv.reader(io.StringIO(text))
        header: Optional[List[str]] = None

        for row_idx, row in enumerate(reader, start=1):
            if not row or not any(c.strip() for c in row):
                continue
            if header is None:
                header = [c.strip() for c in row]
                continue

            row_data = {}
            for col_idx, val in enumerate(row):
                col_name = header[col_idx] if col_idx < len(header) else f"Col_{col_idx}"
                if val.strip():
                    row_data[col_name] = val.strip()

            snippet_str = "; ".join(f"{k}: {v}" for k, v in row_data.items())
            snippets.append(
                DocumentEvidence(
                    file_name=filename,
                    format="csv",
                    location=f"Row {row_idx}",
                    raw_snippet=snippet_str,
                )
            )
        return snippets

    @staticmethod
    def parse_xlsx(content: bytes, filename: str = "workbook.xlsx") -> List[DocumentEvidence]:
        """
        Extracts sheets and cell values from an XLSX archive using standard library
        zipfile and XML parser (zero external C-extension or openpyxl dependency).
        """
        snippets = []
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                # 1. Load shared strings
                shared_strings = []
                if "xl/sharedStrings.xml" in z.namelist():
                    ss_xml = z.read("xl/sharedStrings.xml")
                    root = ET.fromstring(ss_xml)
                    # Namespace-agnostic element search for <t>
                    for elem in root.iter():
                        if elem.tag.endswith("t") and elem.text:
                            shared_strings.append(elem.text)

                # 2. Parse worksheets
                sheet_files = [f for f in z.namelist() if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")]
                for s_file in sheet_files:
                    sheet_name = os.path.splitext(os.path.basename(s_file))[0]
                    sheet_xml = z.read(s_file)
                    s_root = ET.fromstring(sheet_xml)

                    for row in s_root.iter():
                        if row.tag.endswith("row"):
                            r_num = row.attrib.get("r", "Unknown")
                            cell_values = []
                            for c in row.iter():
                                if c.tag.endswith("c"):
                                    c_type = c.attrib.get("t")
                                    v_elem = None
                                    for child in c:
                                        if child.tag.endswith("v"):
                                            v_elem = child
                                            break
                                    if v_elem is not None and v_elem.text:
                                        if c_type == "s":
                                            idx = int(v_elem.text)
                                            val = shared_strings[idx] if idx < len(shared_strings) else v_elem.text
                                        else:
                                            val = v_elem.text
                                        cell_values.append(val.strip())

                            if cell_values:
                                snippets.append(
                                    DocumentEvidence(
                                        file_name=filename,
                                        format="xlsx",
                                        location=f"Sheet {sheet_name}, Row {r_num}",
                                        raw_snippet=" | ".join(cell_values),
                                    )
                                )
        except Exception as e:
            logger.warning(f"Failed to parse XLSX file {filename}: {e}")
            # Fallback text representation
            snippets.append(
                DocumentEvidence(
                    file_name=filename,
                    format="xlsx",
                    location="Root",
                    raw_snippet=f"[Binary XLSX Spreadsheet: {filename}]",
                )
            )
        return snippets

    @staticmethod
    def parse_pdf(content: bytes, filename: str = "document.pdf") -> List[DocumentEvidence]:
        """
        Extracts readable text from PDF streams.
        Supports standard textual PDF streams and text blocks.
        """
        snippets = []
        try:
            # Check for pypdf if available
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(content))
                for page_num, page in enumerate(reader.pages, start=1):
                    p_text = page.extract_text() or ""
                    for line_idx, line in enumerate(p_text.splitlines(), start=1):
                        if line.strip():
                            snippets.append(
                                DocumentEvidence(
                                    file_name=filename,
                                    format="pdf",
                                    location=f"Page {page_num}, Line {line_idx}",
                                    raw_snippet=line.strip(),
                                )
                            )
                if snippets:
                    return snippets
            except ImportError:
                pass

            # Robust standard-library stream scanner for PDF BT ... ET text blocks
            stream_pattern = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
            text_chunks = []
            for match in stream_pattern.finditer(content):
                chunk = match.group(1)
                # Attempt zlib decompress if compressed
                try:
                    import zlib
                    decompressed = zlib.decompress(chunk)
                except Exception:
                    decompressed = chunk

                # Extract strings inside ( ... ) Tj or [( ... )] TJ
                extracted = re.findall(rb"\((.*?)\)\s*T[jJ]", decompressed)
                if extracted:
                    text_line = " ".join(t.decode("utf-8", errors="replace") for t in extracted)
                    if text_line.strip():
                        text_chunks.append(text_line.strip())

            if text_chunks:
                for idx, chunk in enumerate(text_chunks, start=1):
                    snippets.append(
                        DocumentEvidence(
                            file_name=filename,
                            format="pdf",
                            location=f"Text Section {idx}",
                            raw_snippet=chunk,
                        )
                    )
            else:
                # If pure text stream not found, extract readable ASCII strings
                ascii_strings = re.findall(rb"[A-Za-z0-9\s.,:\-$#/()]{5,}", content)
                lines = [s.decode("utf-8", errors="replace").strip() for s in ascii_strings if len(s.strip()) > 8]
                for idx, line in enumerate(lines[:50], start=1):
                    snippets.append(
                        DocumentEvidence(
                            file_name=filename,
                            format="pdf",
                            location=f"Block {idx}",
                            raw_snippet=line,
                        )
                    )
        except Exception as e:
            logger.warning(f"Error parsing PDF {filename}: {e}")

        if not snippets:
            snippets.append(
                DocumentEvidence(
                    file_name=filename,
                    format="pdf",
                    location="Page 1",
                    raw_snippet=f"[PDF Document: {filename}]",
                )
            )
        return snippets


class DocumentFactExtractor:
    """Extracts structured MSME business facts and catalog items from parsed snippets."""

    # Patterns for small business entities
    PRICE_PATTERNS = [
        re.compile(r"(?:price|rate|fee|cost|mrp|charge|ticket)\s*(?:is|:|-)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)", re.IGNORECASE),
        re.compile(r"(?:rs\.?|inr|₹)\s*(\d+(?:,\d+)*(?:\.\d+)?)", re.IGNORECASE),
    ]
    CAPACITY_PATTERNS = [
        re.compile(r"(?:capacity|limit|can handle|servicing|max)\s*(?:is|:|-)?\s*(\d+)\s*(?:orders|clients|units|jobs|repairs|dresses|items|patients|appointments)?", re.IGNORECASE),
        re.compile(r"(\d+)\s*(?:chairs|beds|bays|mechanics|tailors|staff|technicians)", re.IGNORECASE),
    ]
    FIXED_EXPENSE_PATTERNS = [
        re.compile(r"(?:rent|overhead|fixed expense|salary|salaries|electricity|utility)\s*(?:is|:|-)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)", re.IGNORECASE),
    ]
    INVENTORY_PATTERNS = [
        re.compile(r"(?:in stock|inventory|stock|available|kits?)\s*(?:is|:|-)?\s*(\d+)\s*(?:units|meters|pcs|pieces|items)?", re.IGNORECASE),
    ]
    SUPPLIER_PATTERNS = [
        re.compile(r"(?:lead time|delivery time)\s*(?:is|:|-)?\s*(\d+)\s*(?:days?|hrs?|hours?|weeks?)", re.IGNORECASE),
        re.compile(r"(?:preferred supplier|primary supplier|vendor)\s*(?:is|:|-)?\s*([A-Za-z0-9\s\-&]{3,40})", re.IGNORECASE),
    ]
    POLICY_PATTERNS = [
        re.compile(r"(?:advance|deposit)\s*(?:is|:|-)?\s*(\d+)\s*%", re.IGNORECASE),
        re.compile(r"(?:cancellation fee|cancellation charge)\s*(?:is|:|-)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)", re.IGNORECASE),
    ]
    CONSTRAINT_PATTERNS = [
        re.compile(r"(?:moq|minimum order|min order)\s*(?:is|:|-)?\s*(\d+)\s*(?:units|pcs|pieces|items|meters)?", re.IGNORECASE),
        re.compile(r"(?:service radius|delivery radius)\s*(?:is|:|-)?\s*(\d+)\s*(?:km|kms|kilometers)", re.IGNORECASE),
    ]

    @classmethod
    def extract_candidates(cls, snippets: List[DocumentEvidence]) -> List[ExtractedFactCandidate]:
        candidates: List[ExtractedFactCandidate] = []
        discovered_catalog: List[Dict[str, Any]] = []

        for snip in snippets:
            text = snip.raw_snippet

            # 1. Check for structured table row (e.g. "Item: Cotton Kurti Stitching; Price: 450; ...")
            table_match = re.search(
                r"(?:item|product|service|description|title)\s*:\s*([^;]+?)\s*;\s*(?:price|rate|cost|fee|mrp)\s*:\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)",
                text,
                re.IGNORECASE,
            )
            if table_match:
                item_name = table_match.group(1).strip()
                item_price = float(table_match.group(2).replace(",", ""))
                discovered_catalog.append({"name": item_name, "price": item_price, "source": snip.location})
                candidates.append(
                    ExtractedFactCandidate(
                        key=f"item_{re.sub(r'[^a-z0-9_]', '', item_name.lower().replace(' ', '_'))}_price",
                        value=item_price,
                        value_type="float",
                        evidence=snip,
                        confidence=0.95,
                    )
                )
            else:
                # Fallback to key-value line pattern (e.g. "Cotton Cambric: Rs 120" or "Oil Change: Rs 850")
                catalog_match = re.search(r"([A-Za-z0-9\s\-&]{3,40}?)\s*(?::|-|–|=|\|)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)", text, re.IGNORECASE)
                if catalog_match:
                    item_name = catalog_match.group(1).strip()
                    item_price = float(catalog_match.group(2).replace(",", ""))
                    # Filter out generic keys
                    if item_name.lower() not in {"rent", "total", "subtotal", "tax", "gst", "discount", "balance", "amount", "price", "item", "cost", "fee", "hourly rate", "hourly_rate", "minimum order", "daily capacity"}:
                        discovered_catalog.append({"name": item_name, "price": item_price, "source": snip.location})
                        candidates.append(
                            ExtractedFactCandidate(
                                key=f"item_{re.sub(r'[^a-z0-9_]', '', item_name.lower().replace(' ', '_'))}_price",
                                value=item_price,
                                value_type="float",
                                evidence=snip,
                                confidence=0.90,
                            )
                        )

            # 2. Check hourly rate explicitly
            hourly_match = re.search(
                r"(?:hourly\s*rate|per\s*hour|rate\s*per\s*hour)\s*(?:is|:|-)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)",
                text,
                re.IGNORECASE,
            )
            if hourly_match:
                val = float(hourly_match.group(1).replace(",", ""))
                candidates.append(
                    ExtractedFactCandidate(
                        key="hourly_rate",
                        value=val,
                        value_type="float",
                        evidence=snip,
                        confidence=0.90,
                    )
                )

            # 3. Check general selling price (if not hourly rate)
            if not hourly_match:
                for p_pat in cls.PRICE_PATTERNS:
                    m = p_pat.search(text)
                    if m and any(w in text.lower() for w in ["average", "unit", "standard", "selling price", "rate"]):
                        val = float(m.group(1).replace(",", ""))
                        candidates.append(
                            ExtractedFactCandidate(
                                key="selling_price",
                                value=val,
                                value_type="float",
                                evidence=snip,
                                confidence=0.85,
                            )
                        )
                        break

            # 3. Check fixed expenses (rent, overhead, monthly expenses)
            for f_pat in cls.FIXED_EXPENSE_PATTERNS:
                m = f_pat.search(text)
                if m:
                    val = float(m.group(1).replace(",", ""))
                    candidates.append(
                        ExtractedFactCandidate(
                            key="daily_fixed_cost" if "daily" in text.lower() else "monthly_fixed_cost",
                            value=val,
                            value_type="float",
                            evidence=snip,
                            confidence=0.85,
                        )
                    )
                    break

            # 4. Check capacity / staff
            for c_pat in cls.CAPACITY_PATTERNS:
                m = c_pat.search(text)
                if m:
                    val = float(m.group(1))
                    candidates.append(
                        ExtractedFactCandidate(
                            key="daily_capacity",
                            value=val,
                            value_type="float",
                            evidence=snip,
                            confidence=0.80,
                        )
                    )
                    break

            # 5. Check inventory / stock
            for i_pat in cls.INVENTORY_PATTERNS:
                m = i_pat.search(text)
                if m:
                    val = float(m.group(1))
                    candidates.append(
                        ExtractedFactCandidate(
                            key="current_inventory",
                            value=val,
                            value_type="float",
                            evidence=snip,
                            confidence=0.85,
                        )
                    )
                    break

            # 6. Check supplier details
            for s_pat in cls.SUPPLIER_PATTERNS:
                m = s_pat.search(text)
                if m:
                    key = "procurement_lead_time_days" if "lead" in text.lower() or "delivery" in text.lower() else "primary_supplier_name"
                    raw_val = m.group(1).strip()
                    val = float(raw_val) if key == "procurement_lead_time_days" else raw_val
                    candidates.append(
                        ExtractedFactCandidate(
                            key=key,
                            value=val,
                            value_type="float" if isinstance(val, (int, float)) else "str",
                            evidence=snip,
                            confidence=0.85,
                        )
                    )
                    break

            # 7. Check business policies
            for pol_pat in cls.POLICY_PATTERNS:
                m = pol_pat.search(text)
                if m:
                    key = "advance_required_percent" if "%" in text else "cancellation_fee"
                    val = float(m.group(1).replace(",", ""))
                    candidates.append(
                        ExtractedFactCandidate(
                            key=key,
                            value=val,
                            value_type="float",
                            evidence=snip,
                            confidence=0.85,
                        )
                    )
                    break

            # 8. Check operational constraints
            for con_pat in cls.CONSTRAINT_PATTERNS:
                m = con_pat.search(text)
                if m:
                    key = "minimum_order_quantity" if "order" in text.lower() or "moq" in text.lower() else "service_radius_km"
                    val = float(m.group(1))
                    candidates.append(
                        ExtractedFactCandidate(
                            key=key,
                            value=val,
                            value_type="float",
                            evidence=snip,
                            confidence=0.85,
                        )
                    )
                    break

        if discovered_catalog:
            # Record combined service/product catalog
            candidates.append(
                ExtractedFactCandidate(
                    key="offered_catalog",
                    value=discovered_catalog,
                    value_type="list",
                    evidence=snippets[0],
                    confidence=0.95,
                )
            )

        return candidates


class DocumentOnboardingService:
    """
    Coordinates multi-document ingestion, contradiction detection, and fact updates.
    Guarantees:
      - Never silently overwrites confirmed business facts.
      - Flags conflicting document values and retains uncertain facts pending verification.
      - Multi-tenant business isolation.
    """

    def __init__(self, repo: AdaptiveProfileRepository) -> None:
        self.repo = repo

    def ingest_document(
        self,
        business_id: str,
        filename: str,
        content: Union[str, bytes],
        doc_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingests a document for a business profile, extracts facts with provenance,
        detects contradictions, and saves unconfirmed facts for owner verification.
        """
        profile = self.repo.get_profile(business_id)
        if not profile:
            raise ValueError(f"Business profile '{business_id}' not found.")

        # Determine format
        fmt = (doc_format or os.path.splitext(filename)[1].lstrip(".")).lower()
        if fmt == "pdf":
            snippets = DocumentParser.parse_pdf(content if isinstance(content, bytes) else content.encode("utf-8"), filename)
        elif fmt in ("csv", "tsv"):
            snippets = DocumentParser.parse_csv(content, filename)
        elif fmt in ("xlsx", "xls"):
            snippets = DocumentParser.parse_xlsx(content if isinstance(content, bytes) else content.encode("utf-8"), filename)
        else:
            snippets = DocumentParser.parse_txt(content, filename)

        candidates = DocumentFactExtractor.extract_candidates(snippets)

        extracted_facts: List[Dict[str, Any]] = []
        conflicts_detected: List[Dict[str, Any]] = []
        follow_up_questions: List[str] = []

        for cand in candidates:
            existing_fact = profile.get_fact(cand.key)

            # Check 1: Contradiction against an existing CONFIRMED fact
            if existing_fact and existing_fact.status == FactStatus.CONFIRMED:
                if existing_fact.value != cand.value:
                    cand.is_conflict = True
                    cand.conflict_notes = (
                        f"Conflict: Document '{filename}' specifies {cand.value} at {cand.evidence.location}, "
                        f"but confirmed fact is {existing_fact.value}."
                    )
                    conflicts_detected.append({
                        "key": cand.key,
                        "existing_confirmed_value": existing_fact.value,
                        "candidate_value": cand.value,
                        "evidence": cand.evidence.to_dict(),
                        "conflict_notes": cand.conflict_notes,
                    })
                    follow_up_questions.append(
                        f"For '{cand.key}': Your confirmed value is {existing_fact.value}, but {filename} ({cand.evidence.location}) lists {cand.value}. Which is correct?"
                    )
                    continue  # Never overwrite confirmed fact!

            # Check 2: Contradiction against an existing ASSUMED fact from prior document
            if existing_fact and existing_fact.status == FactStatus.ASSUMED:
                if existing_fact.value != cand.value:
                    cand.is_conflict = True
                    cand.conflict_notes = (
                        f"Contradiction between documents: Previous source had {existing_fact.value}, "
                        f"while {filename} has {cand.value}."
                    )
                    conflicts_detected.append({
                        "key": cand.key,
                        "previous_assumed_value": existing_fact.value,
                        "candidate_value": cand.value,
                        "evidence": cand.evidence.to_dict(),
                        "conflict_notes": cand.conflict_notes,
                    })
                    follow_up_questions.append(
                        f"Conflicting values detected for '{cand.key}': {existing_fact.value} vs {cand.value} in {filename}. Please confirm the accurate amount."
                    )
                    # Mark existing fact with conflict note and keep status ASSUMED
                    existing_fact.notes = f"{existing_fact.notes} || CONFLICT: {cand.conflict_notes}"
                    self.repo.set_fact(business_id, existing_fact)
                    continue

            # No contradiction -> Save candidate fact as ASSUMED pending owner verification
            provenance_note = f"Extracted from {filename} ({cand.evidence.location})"
            fact = BusinessFact(
                key=cand.key,
                value=cand.value,
                value_type=cand.value_type,
                status=FactStatus.ASSUMED,  # Strictly pending owner verification
                source=FactSource.INFERRED,
                confidence=cand.confidence,
                notes=provenance_note,
            )
            self.repo.set_fact(business_id, fact)
            extracted_facts.append({
                "key": cand.key,
                "value": cand.value,
                "confidence": cand.confidence,
                "evidence": cand.evidence.to_dict(),
                "status": "pending_owner_verification",
            })

        return {
            "business_id": business_id,
            "filename": filename,
            "snippets_count": len(snippets),
            "extracted_facts_count": len(extracted_facts),
            "conflicts_count": len(conflicts_detected),
            "extracted_facts": extracted_facts,
            "conflicts_detected": conflicts_detected,
            "follow_up_questions": follow_up_questions,
        }
