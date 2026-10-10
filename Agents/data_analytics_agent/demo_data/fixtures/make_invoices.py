"""
Invoice PDF Generator for Alexa Business Autopilot.
Generates:
  - demo_data/fixtures/INV-GUPTA-0912.pdf (Clean Invoice)
  - demo_data/fixtures/INV-PKG-0245.pdf   (Discrepant Invoice)

Uses reportlab if available; otherwise falls back to a built-in standard PDF 1.4 generator
to ensure zero external dependencies are required.
"""

from __future__ import annotations

import os
from typing import List, Tuple


def generate_raw_pdf(filename: str, title: str, lines: List[str]) -> None:
    """Generates a valid, standards-compliant PDF 1.4 document using pure Python."""
    content_lines = ["BT"]
    # Header title
    content_lines.append("/F2 16 Tf")
    content_lines.append("50 780 Td")
    content_lines.append(f"({title}) Tj")
    
    # Body lines
    content_lines.append("/F1 10 Tf")
    y_pos = 750
    content_lines.append(f"0 -30 Td")
    
    for line in lines:
        sanitized = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if line.startswith("==="):
            content_lines.append("0 -16 Td")
            content_lines.append(f"({sanitized}) Tj")
        elif line.startswith("[") or line.startswith("TOTAL") or line.startswith("INVOICE"):
            content_lines.append("/F2 10 Tf")
            content_lines.append("0 -16 Td")
            content_lines.append(f"({sanitized}) Tj")
            content_lines.append("/F1 10 Tf")
        else:
            content_lines.append("0 -14 Td")
            content_lines.append(f"({sanitized}) Tj")
            
    content_lines.append("ET")
    stream_content = "\n".join(content_lines).encode("latin-1")
    stream_len = len(stream_content)

    objects: List[bytes] = []
    # 1 0 obj: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # 2 0 obj: Pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    # 3 0 obj: Page
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> "
        b"/MediaBox [0 0 595 842] /Contents 6 0 R >>\nendobj\n"
    )
    # 4 0 obj: Font Regular
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    # 5 0 obj: Font Bold
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n")
    # 6 0 obj: Stream
    stream_obj = (
        f"6 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("latin-1")
        + stream_content
        + b"\nendstream\nendobj\n"
    )
    objects.append(stream_obj)

    out = bytearray(b"%PDF-1.4\n")
    xref_offsets = [0]
    for obj in objects:
        xref_offsets.append(len(out))
        out.extend(obj)

    xref_start = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for off in xref_offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    )
    out.extend(trailer.encode("latin-1"))

    with open(filename, "wb") as f:
        f.write(out)


def build_gupta_clean_invoice(target_path: str) -> None:
    lines = [
        "TAX INVOICE - GUPTA OIL AGENCY",
        "GSTIN: 09CCCCC3333C1Z3 | State: Uttar Pradesh (09)",
        "Address: Shop 14, Transport Nagar, Kanpur, UP",
        "Phone: +91 XXXXXX3303 | Email: accounts@guptaoilagency.synthetic",
        "================================================================================",
        "Billed To: Maa Ki Rasoi Cloud Kitchen (Prop: Sunita Sharma)",
        "GSTIN: 09ZZZZZ9999Z1Z5 | Locality: Kakadeo, Kanpur, UP",
        "Invoice No: INV-GUPTA-0912          Date: 2026-09-28",
        "PO Ref:     PO-20260926-01          Payment Mode: UPI / Credit (15 Days)",
        "================================================================================",
        "ITEM DESCRIPTION                   QTY    UNIT RATE   TAXABLE   GST%    TOTAL",
        "--------------------------------------------------------------------------------",
        "Refined Sunflower Oil 1L Pouch     10 L   Rs 146.00   1460.00    5%   1533.00",
        "--------------------------------------------------------------------------------",
        "SUBTOTAL (TAXABLE):                Rs 1,460.00",
        "CGST (2.5%):                       Rs    36.50",
        "SGST (2.5%):                       Rs    36.50",
        "TOTAL INVOICE AMOUNT:              Rs 1,533.00",
        "================================================================================",
        "Amount in Words: One Thousand Five Hundred Thirty-Three Rupees Only.",
        "Goods received in good condition. Matched with PO-20260926-01.",
        "Authorised Signatory: Gupta Oil Agency"
    ]
    generate_raw_pdf(target_path, "TAX INVOICE: INV-GUPTA-0912", lines)


def build_pkg_mismatch_invoice(target_path: str) -> None:
    lines = [
        "TAX INVOICE - KANPUR PACKAGING MART",
        "GSTIN: 09BBBBB2222B1Z2 | State: Uttar Pradesh (09)",
        "Address: Plot 88, Fazalganj Industrial Area, Kanpur, UP",
        "Phone: +91 XXXXXX2202 | Email: billing@kanpurpackaging.synthetic",
        "================================================================================",
        "Billed To: Maa Ki Rasoi Cloud Kitchen (Prop: Sunita Sharma)",
        "GSTIN: 09ZZZZZ9999Z1Z5 | Locality: Kakadeo, Kanpur, UP",
        "Invoice No: INV-PKG-0245            Date: 2026-10-05",
        "PO Ref:     PO-20261004-02          Payment Mode: Immediate / Net Banking",
        "================================================================================",
        "ITEM DESCRIPTION                   QTY    UNIT RATE   TAXABLE   GST%    TOTAL",
        "--------------------------------------------------------------------------------",
        "Tiffin Container 750ml (Meal Box) 120 pcs Rs   3.20    384.00   28%    491.52",
        "--------------------------------------------------------------------------------",
        "SUBTOTAL (TAXABLE):                Rs   384.00",
        "CGST (14.0%):                      Rs    53.76",
        "SGST (14.0%):                      Rs    53.76",
        "TOTAL INVOICE AMOUNT:              Rs   491.52",
        "================================================================================",
        "Amount in Words: Four Hundred Ninety-One Rupees and Fifty-Two Paise Only.",
        "DISCREPANCY AUDIT NOTES (Ground Truth):",
        " 1. Quantity overbilled: 120 pcs billed vs 100 pcs ordered & received (+20 pcs).",
        " 2. Tax rate discrepancy: Billed at 28% GST instead of agreed 18% packaging rate.",
        " Total overbilling difference: Rs 113.92 (Billed Rs 491.52 vs PO Rs 377.60).",
        "Authorised Signatory: Kanpur Packaging Mart"
    ]
    generate_raw_pdf(target_path, "TAX INVOICE: INV-PKG-0245", lines)


def main() -> None:
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    gupta_pdf = os.path.join(curr_dir, "INV-GUPTA-0912.pdf")
    pkg_pdf = os.path.join(curr_dir, "INV-PKG-0245.pdf")

    build_gupta_clean_invoice(gupta_pdf)
    build_pkg_mismatch_invoice(pkg_pdf)

    print(f"Generated clean invoice: {gupta_pdf} (bytes: {os.path.getsize(gupta_pdf)})")
    print(f"Generated discrepant invoice: {pkg_pdf} (bytes: {os.path.getsize(pkg_pdf)})")


if __name__ == "__main__":
    main()

