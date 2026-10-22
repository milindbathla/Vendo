"""
Seed a few demo sales invoices into the connected Zoho Books org.

Purpose: the live Zoho org is empty, so the Alexa+ simulator's invoice panel has
nothing live to fetch. This one-off utility creates a demo customer and a handful
of invoices (tiffin sales) via the Zoho Books API, using the OAuth refresh token
already configured in .env, so the demo shows genuinely live-fetched Zoho data.

It is WRITE-only against an external account. Run intentionally:

    python3 scripts/seed_zoho_demo.py          # create the demo data
    python3 scripts/seed_zoho_demo.py --list   # just list what's there now

If the OAuth scope is read-only, the create calls return HTTP 401 and the script
reports that clearly — the app then falls back to the seeded demo.db invoices.
"""
from __future__ import annotations

import sys
import json
import requests

from src.integrations.zoho_books.adapter import ZohoBooksAdapter

CUSTOMER_NAME = "Kakadeo Coaching Center"

# (customer-facing) tiffin sales invoices for Maa Ki Rasoi Cloud Kitchen
INVOICES = [
    {"date": "2026-10-05", "qty": 60, "rate": 85.0, "name": "Standard Veg Tiffin"},
    {"date": "2026-10-08", "qty": 30, "rate": 90.0, "name": "Standard Veg Tiffin (premium)"},
    {"date": "2026-10-10", "qty": 100, "rate": 85.0, "name": "Standard Veg Tiffin"},
]


def main() -> int:
    z = ZohoBooksAdapter()
    if z.is_mock or not z.oauth_manager.is_configured:
        print("Zoho is in MOCK mode or not configured — check .env. Nothing seeded.")
        return 2

    token = z.oauth_manager.get_access_token()
    domain = z.oauth_manager.api_domain.rstrip("/")
    org = z.org_id
    base = f"{domain}/books/v3"
    headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
    params = {"organization_id": org}

    def get(path, extra=None):
        p = dict(params); p.update(extra or {})
        return requests.get(f"{base}{path}", headers=headers, params=p, timeout=30)

    def post(path, body):
        return requests.post(f"{base}{path}", headers=headers, params=params,
                             data=json.dumps(body), timeout=30)

    if "--list" in sys.argv:
        r = get("/invoices", {"per_page": 50})
        print("GET /invoices ->", r.status_code)
        for inv in r.json().get("invoices", []):
            print("   ", inv.get("invoice_number"), inv.get("customer_name"),
                  inv.get("status"), inv.get("total"))
        return 0

    # 1) find or create the customer
    customer_id = None
    r = get("/contacts", {"contact_name": CUSTOMER_NAME})
    if r.status_code == 200:
        for c in r.json().get("contacts", []):
            if c.get("contact_name") == CUSTOMER_NAME:
                customer_id = c.get("contact_id"); break
    if not customer_id:
        r = post("/contacts", {"contact_name": CUSTOMER_NAME, "contact_type": "customer"})
        if r.status_code not in (200, 201):
            print(f"Could not create customer (HTTP {r.status_code}). Scope likely read-only.")
            print("   ", r.text[:300])
            print("App will fall back to the seeded demo.db invoices.")
            return 1
        customer_id = r.json().get("contact", {}).get("contact_id")
    print(f"Customer '{CUSTOMER_NAME}' -> {customer_id}")

    # 2) create the invoices
    created = 0
    for spec in INVOICES:
        body = {
            "customer_id": customer_id,
            "date": spec["date"],
            "line_items": [{
                "name": spec["name"],
                "description": "Daily tiffin supply",
                "rate": spec["rate"],
                "quantity": spec["qty"],
            }],
        }
        r = post("/invoices", body)
        if r.status_code in (200, 201):
            inv = r.json().get("invoice", {})
            print(f"  + invoice {inv.get('invoice_number')}  {spec['qty']} x Rs {spec['rate']}  = Rs {inv.get('total')}")
            created += 1
        else:
            print(f"  ! invoice create failed (HTTP {r.status_code}): {r.text[:200]}")

    print(f"\nDone. Created {created}/{len(INVOICES)} invoices in org {org}.")
    return 0 if created else 1


if __name__ == "__main__":
    raise SystemExit(main())
