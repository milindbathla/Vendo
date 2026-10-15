"""
Unit and Mocked Integration Tests for Zoho Books API Integration.
==================================================================
Tests OAuth token refresh, token caching, concurrency locking, normalization,
pagination, error mapping, and offline mock mode.
"""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from src.integrations.base import (
    AuthenticationError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    sanitize_credentials,
)
from src.integrations.zoho_books.adapter import ZohoBooksAdapter
from src.integrations.zoho_books.client import ZohoBooksClient
from src.integrations.zoho_books.models import (
    ZohoAccountingSummary,
    ZohoBill,
    ZohoInvoice,
    ZohoOrganization,
)
from src.integrations.zoho_books.oauth import ZohoOAuthManager


class TestZohoOAuthUnit(unittest.TestCase):
    """Unit tests for Zoho Books OAuth 2.0 manager."""

    def test_secret_sanitation(self):
        """Ensures refresh tokens, access tokens, and secrets are sanitized."""
        leak = "GET /books/v3/invoices with Authorization: Zoho-oauthtoken 1000.abc123def456 and refresh_token=1000.xyz789"
        clean = sanitize_credentials(leak)
        self.assertNotIn("1000.abc123def456", clean)
        self.assertNotIn("1000.xyz789", clean)
        self.assertIn("[REDACTED]", clean)

    @patch("urllib.request.urlopen")
    def test_oauth_refresh_token_exchange(self, mock_urlopen):
        """Simulates successful token refresh from Zoho Accounts."""
        mock_resp = MagicMock()
        mock_payload = {
            "access_token": "1000.mock_access_token_123",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
            "token_type": "Bearer",
        }
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = ZohoOAuthManager(
            client_id="1000.CLIENT_ID",
            client_secret="CLIENT_SECRET",
            refresh_token="1000.REFRESH_TOKEN",
            accounts_url="https://accounts.zoho.in",
        )

        token = mgr.get_access_token()
        self.assertEqual(token, "1000.mock_access_token_123")
        self.assertEqual(mgr.api_domain, "https://www.zohoapis.in")

        # Second call should use cache without hitting network
        mock_urlopen.reset_mock()
        cached_token = mgr.get_access_token()
        self.assertEqual(cached_token, "1000.mock_access_token_123")
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_oauth_concurrency_race_prevention(self, mock_urlopen):
        """Multiple concurrent threads only trigger 1 network token refresh."""
        mock_resp = MagicMock()
        mock_payload = {
            "access_token": "1000.concurrent_token",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        }
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = ZohoOAuthManager(
            client_id="1000.CLIENT_ID",
            client_secret="CLIENT_SECRET",
            refresh_token="1000.REFRESH_TOKEN",
        )

        # Execute 5 concurrent calls
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(mgr.get_access_token) for _ in range(5)]
            results = [f.result() for f in futures]

        self.assertEqual(len(set(results)), 1)
        self.assertEqual(results[0], "1000.concurrent_token")
        # Urlopen should only be called once because of the thread lock
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_oauth_error_mapping_invalid_client(self, mock_urlopen):
        """Maps invalid_client or invalid_grant response to AuthenticationError."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"error": "invalid_client"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = ZohoOAuthManager(
            client_id="1000.BAD_CLIENT",
            client_secret="BAD_SECRET",
            refresh_token="1000.BAD_TOKEN",
        )

        with self.assertRaises(AuthenticationError) as ctx:
            mgr.get_access_token()
        self.assertIn("invalid_client", str(ctx.exception))


class TestZohoBooksMocked(unittest.TestCase):
    """Tests Zoho Books adapter and client in mock mode and with mocked HTTP."""

    def test_mock_get_organization(self):
        """Mock organization returns Maa Ki Rasoi Cloud Kitchen profile."""
        adapter = ZohoBooksAdapter(force_mock=True)
        org = adapter.get_organization()
        self.assertEqual(org.name, "Maa Ki Rasoi Cloud Kitchen")
        self.assertEqual(org.currency_code, "INR")
        self.assertEqual(org.tax_id, "09ZZZZZ9999Z1Z5")

    def test_mock_get_invoices_and_financial_rules(self):
        """Invoices strictly differentiate billed revenue from cash collected."""
        adapter = ZohoBooksAdapter(force_mock=True)
        resp = adapter.get_invoices(page=1, per_page=10)
        self.assertTrue(resp.success)
        self.assertEqual(len(resp.data), 4)

        summary = adapter.get_accounting_summary()
        # Verify financial principles:
        # Total invoiced revenue > cash collected because of outstanding unpaid invoices
        self.assertGreater(summary.total_invoiced_revenue, summary.cash_collected)
        self.assertEqual(
            round(summary.cash_collected + summary.outstanding_receivables, 2),
            round(summary.total_invoiced_revenue, 2),
        )
        self.assertGreater(summary.overdue_receivables, 0.0)

    def test_mock_get_bills(self):
        """Vendor bills match data/demo.db suppliers (Gupta Oil, Packaging Mart)."""
        adapter = ZohoBooksAdapter(force_mock=True)
        resp = adapter.get_bills(page=1, per_page=10)
        self.assertTrue(resp.success)
        self.assertEqual(len(resp.data), 3)

        vendor_names = [b.vendor_name for b in resp.data]
        self.assertTrue(any("Gupta Oil" in vn for vn in vendor_names))
        self.assertTrue(any("Packaging Mart" in vn for vn in vendor_names))

    def test_pagination_validation(self):
        """Validates page and per_page bounds."""
        adapter = ZohoBooksAdapter(force_mock=True)
        with self.assertRaises(ValidationError):
            adapter.get_invoices(page=0)
        with self.assertRaises(ValidationError):
            adapter.get_invoices(per_page=0)
        with self.assertRaises(ValidationError):
            adapter.get_invoices(per_page=250)

    @patch("urllib.request.urlopen")
    def test_live_client_success_mocked_http(self, mock_urlopen):
        """Simulates successful HTTP GET /books/v3/invoices."""
        mock_payload = {
            "code": 0,
            "message": "success",
            "invoices": [
                {
                    "invoice_id": "inv_test_101",
                    "invoice_number": "INV-101",
                    "customer_name": "Test Customer",
                    "total": 5000.0,
                    "balance": 2000.0,
                    "status": "partially_paid",
                }
            ],
            "page_context": {"page": 1, "per_page": 20, "has_more_page": False, "total": 1},
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = ZohoBooksClient(token_provider=lambda: "MOCK_TOKEN", api_domain="https://www.zohoapis.in")
        res = client.get_invoices(organization_id="org_123")
        self.assertEqual(res["code"], 0)
        self.assertEqual(len(res["invoices"]), 1)

    @patch("urllib.request.urlopen")
    def test_live_client_auth_failure_mapping(self, mock_urlopen):
        """Maps HTTP 401 on Zoho Books API call to AuthenticationError."""
        err = urllib.error.HTTPError(
            url="https://www.zohoapis.in/books/v3/invoices",
            code=401,
            msg="Unauthorized",
            hdrs={},  # type: ignore
            fp=io.BytesIO(b'{"code": 14, "message": "Invalid OAuth token"}'),
        )
        mock_urlopen.side_effect = err

        client = ZohoBooksClient(token_provider=lambda: "EXPIRED_TOKEN", max_retries=0)
        with self.assertRaises(AuthenticationError):
            client.get_invoices(organization_id="org_123")


if __name__ == "__main__":
    unittest.main()

