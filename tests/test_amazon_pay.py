"""
Unit and Mock Tests for Amazon Pay Integration.
================================================
All tests run in mock mode (no live credentials required).
Live smoke tests are skipped unless AMAZON_PAY_PUBLIC_KEY_ID etc. are set.
"""
import os
import unittest

from src.integrations.amazon_pay.adapter import AmazonPayAdapter
from src.integrations.amazon_pay.models import (
    AmazonPayCharge,
    AmazonPayChargePermission,
    AmazonPayPaymentSummary,
    AmazonPayRefund,
    AmazonPayWebhookEvent,
)
from src.integrations.amazon_pay.mock_data import (
    MOCK_CHARGES,
    MOCK_CHARGE_PERMISSION,
    MOCK_PAYMENT_SUMMARY,
    MOCK_REFUNDS,
    get_mock_charge,
    get_mock_charges_list,
    get_mock_refunds_list,
)


class TestAmazonPayMockAdapter(unittest.TestCase):
    """Tests for AmazonPayAdapter running in mock mode (no credentials needed)."""

    def setUp(self):
        self.adapter = AmazonPayAdapter(force_mock=True)

    def test_adapter_is_in_mock_mode(self):
        self.assertTrue(self.adapter.is_mock)

    def test_adapter_status(self):
        status = self.adapter.get_status()
        self.assertEqual(status["provider"], "amazon_pay")
        self.assertEqual(status["mode"], "mock")
        self.assertFalse(status["is_configured"])

    def test_get_charge_returns_mock(self):
        result = self.adapter.get_charge("S02-1234567-1234567-C001")
        self.assertIn("chargeId", result)
        self.assertTrue(result["is_mock"])
        self.assertIn("chargeAmount", result)
        self.assertEqual(result["chargeAmount"]["currencyCode"], "INR")

    def test_create_charge_mock(self):
        result = self.adapter.create_charge(
            charge_permission_id="S02-1234567-1234567",
            amount="500.00",
        )
        self.assertIn("chargeId", result)
        self.assertTrue(result["is_mock"])
        self.assertEqual(result["chargeState"]["state"], "Captured")

    def test_create_refund_mock(self):
        result = self.adapter.create_refund(
            charge_id="S02-1234567-1234567-C001",
            refund_amount="100.00",
        )
        self.assertIn("refundId", result)
        self.assertTrue(result["is_mock"])
        self.assertEqual(result["refundState"]["state"], "Refunded")
        self.assertEqual(result["refundAmount"]["amount"], "100.00")

    def test_list_charges_returns_all_mock(self):
        charges = self.adapter.list_recent_charges()
        self.assertIsInstance(charges, list)
        self.assertGreater(len(charges), 0)
        for c in charges:
            self.assertTrue(c["is_mock"])

    def test_list_refunds_mock(self):
        refunds = self.adapter.list_recent_refunds()
        self.assertIsInstance(refunds, list)
        self.assertGreater(len(refunds), 0)

    def test_payment_summary_mock(self):
        summary = self.adapter.get_payment_summary()
        self.assertIn("total_charges", summary)
        self.assertIn("total_amount_captured", summary)
        self.assertGreater(summary["total_amount_captured"], 0)
        self.assertEqual(summary["currency"], "INR")
        self.assertTrue(summary["is_mock"])

    def test_charge_permission_mock(self):
        result = self.adapter.get_charge_permission("S02-1234567-1234567")
        self.assertIn("chargePermissionId", result)
        self.assertEqual(result["chargePermissionState"]["state"], "Chargeable")
        self.assertTrue(result["is_mock"])

    def test_webhook_parsing(self):
        raw = {
            "NotificationType": "CHARGE_CAPTURED",
            "ObjectType": "CHARGE",
            "ChargeId": "S02-1234567-1234567-C001",
            "MerchantId": "MOCK_MERCHANT",
            "EventTime": "2026-10-10T19:10:00Z",
        }
        event = self.adapter.parse_webhook_event(raw)
        self.assertIsInstance(event, AmazonPayWebhookEvent)
        self.assertEqual(event.notification_type, "CHARGE_CAPTURED")
        self.assertEqual(event.object_id, "S02-1234567-1234567-C001")


class TestAmazonPayModels(unittest.TestCase):
    """Unit tests for data model serialisation."""

    def test_charge_to_dict(self):
        charge = AmazonPayCharge(
            charge_id="CHG-001",
            charge_permission_id="PERM-001",
            merchant_id="MERCH-001",
            amount="1200.00",
        )
        d = charge.to_dict()
        self.assertEqual(d["chargeId"], "CHG-001")
        self.assertEqual(d["chargeAmount"]["amount"], "1200.00")
        self.assertEqual(d["chargeAmount"]["currencyCode"], "INR")

    def test_refund_to_dict(self):
        refund = AmazonPayRefund(
            refund_id="REF-001",
            charge_id="CHG-001",
            refund_amount="200.00",
        )
        d = refund.to_dict()
        self.assertEqual(d["refundId"], "REF-001")
        self.assertEqual(d["refundAmount"]["amount"], "200.00")
        self.assertEqual(d["refundState"]["state"], "Refunded")

    def test_payment_summary_to_dict(self):
        summary = AmazonPayPaymentSummary(
            merchant_id="M1",
            total_charges=5,
            total_amount_captured=3000.0,
            total_refunded=500.0,
            pending_charges=1,
            declined_charges=0,
        )
        d = summary.to_dict()
        self.assertEqual(d["total_charges"], 5)
        self.assertEqual(d["currency"], "INR")

    def test_charge_permission_to_dict(self):
        perm = AmazonPayChargePermission(
            charge_permission_id="PERM-001",
            merchant_id="MERCH-001",
            state="Chargeable",
        )
        d = perm.to_dict()
        self.assertEqual(d["chargePermissionState"]["state"], "Chargeable")


class TestAmazonPayMockData(unittest.TestCase):
    """Tests for mock data completeness and consistency."""

    def test_mock_charges_have_required_fields(self):
        for c in MOCK_CHARGES:
            d = c.to_dict()
            self.assertIn("chargeId", d)
            self.assertIn("chargeAmount", d)
            self.assertIn("chargeState", d)
            self.assertTrue(d["is_mock"])

    def test_mock_refunds_reference_valid_charge_ids(self):
        charge_ids = {c.charge_id for c in MOCK_CHARGES}
        for r in MOCK_REFUNDS:
            self.assertIn(r.charge_id, charge_ids)

    def test_mock_summary_totals_are_positive(self):
        s = MOCK_PAYMENT_SUMMARY
        self.assertGreater(s.total_amount_captured, 0)
        self.assertGreaterEqual(s.total_refunded, 0)

    def test_get_mock_charge_by_id(self):
        result = get_mock_charge("S02-1234567-1234567-C002")
        self.assertEqual(result["chargeId"], "S02-1234567-1234567-C002")

    def test_get_mock_charge_fallback(self):
        # Non-existent ID should fall back to first charge
        result = get_mock_charge("NONEXISTENT")
        self.assertIn("chargeId", result)


class TestAmazonPayLiveSmoke(unittest.TestCase):
    """Live smoke test — skipped unless full credentials are set."""

    def setUp(self):
        self.public_key_id    = os.environ.get("AMAZON_PAY_PUBLIC_KEY_ID", "").strip()
        self.private_key_path = os.environ.get("AMAZON_PAY_PRIVATE_KEY_PATH", "").strip()
        self.merchant_id      = os.environ.get("AMAZON_PAY_MERCHANT_ID", "").strip()

        if not (self.public_key_id and self.private_key_path and self.merchant_id):
            raise unittest.SkipTest(
                "AMAZON_PAY_PUBLIC_KEY_ID, AMAZON_PAY_PRIVATE_KEY_PATH, and "
                "AMAZON_PAY_MERCHANT_ID not set. Skipping live Amazon Pay smoke test."
            )

    def test_live_adapter_not_mock(self):
        adapter = AmazonPayAdapter(
            public_key_id=self.public_key_id,
            private_key_path=self.private_key_path,
            merchant_id=self.merchant_id,
            sandbox=True,
            force_mock=False,
        )
        self.assertFalse(adapter.is_mock)
        status = adapter.get_status()
        self.assertEqual(status["mode"], "sandbox")
        print(f"\n[LIVE Amazon Pay] Adapter status: {status}")


if __name__ == "__main__":
    unittest.main()
