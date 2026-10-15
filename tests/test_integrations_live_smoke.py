"""
Optional Live Smoke Tests for Google Places (New) and Zoho Books APIs.
======================================================================
These tests execute real HTTP calls against provider endpoints ONLY when
live API credentials are explicitly present in the environment:
- GOOGLE_MAPS_API_KEY
- ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN, ZOHO_ORG_ID

If credentials are absent, tests are cleanly SKIPPED without failing.
Standard CI and local test suites run in mock mode and do not require live keys.
"""
import os
import unittest

from src.integrations.google_places import GooglePlacesAdapter
from src.integrations.zoho_books import ZohoBooksAdapter


class TestGooglePlacesLiveSmoke(unittest.TestCase):
    """Live smoke test for Google Places API (New)."""

    def setUp(self):
        self.api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
        if not self.api_key:
            raise unittest.SkipTest(
                "GOOGLE_MAPS_API_KEY not set in environment. Skipping live Google Places smoke test."
            )

    def test_live_nearby_search_kanpur(self):
        """Executes a real validated searchNearby request against Google Places API (New)."""
        adapter = GooglePlacesAdapter(api_key=self.api_key, force_mock=False)
        self.assertFalse(adapter.is_mock)

        # Search nearby restaurants in Kakadeo, Kanpur
        resp = adapter.search_nearby_places(
            latitude=26.4727,
            longitude=80.3015,
            radius_meters=1500.0,
            place_types=["restaurant"],
            max_results=5,
        )
        self.assertTrue(resp.success)
        self.assertFalse(resp.is_mock)
        print(f"\n[LIVE Google Places] Found {resp.total_count} live places in Kakadeo, Kanpur:")
        for p in resp.places[:3]:
            print(f"  * {p.name} - Rating: {p.rating} ({p.user_rating_count} reviews) - {p.address}")


class TestZohoBooksLiveSmoke(unittest.TestCase):
    """Live smoke test for Zoho Books OAuth and REST APIs."""

    def setUp(self):
        self.client_id = os.environ.get("ZOHO_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "").strip()
        self.refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN", "").strip()
        self.org_id = os.environ.get("ZOHO_ORG_ID", "").strip()

        if not (self.client_id and self.client_secret and self.refresh_token):
            raise unittest.SkipTest(
                "Zoho OAuth credentials (ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN) "
                "not fully configured. Skipping live Zoho Books smoke test."
            )

    def test_live_zoho_organization_and_invoices(self):
        """Executes real OAuth token refresh and reads organization details."""
        adapter = ZohoBooksAdapter(
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=self.refresh_token,
            org_id=self.org_id,
            force_mock=False,
        )
        self.assertFalse(adapter.is_mock)

        org = adapter.get_organization()
        self.assertTrue(len(org.name) > 0)
        print(f"\n[LIVE Zoho Books] Successfully connected to Org: {org.name} ({org.currency_code})")

        invoices_resp = adapter.get_invoices(page=1, per_page=5)
        self.assertTrue(invoices_resp.success)
        print(f"[LIVE Zoho Books] Retrieved {len(invoices_resp.data)} live invoice(s)")


if __name__ == "__main__":
    unittest.main()

