"""
Unit and Mocked Integration Tests for Google Places API (New) Integration.
===========================================================================
Tests input validation, normalization, error mapping, retries, secret sanitation,
and offline mock mode.
"""
import io
import json
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
from src.integrations.google_places.adapter import GooglePlacesAdapter
from src.integrations.google_places.client import GooglePlacesClient, PLACES_API_NEW_URL
from src.integrations.google_places.mock_data import (
    DEFAULT_ANCHOR_LAT,
    DEFAULT_ANCHOR_LNG,
    PLACES_DATA_DISCLAIMER,
)
from src.integrations.google_places.models import PlaceLocation, PlaceResult


class TestGooglePlacesUnit(unittest.TestCase):
    """Unit tests for Google Places parameter validation and data structures."""

    def setUp(self):
        self.adapter = GooglePlacesAdapter(force_mock=True)

    def test_parameter_validation_coordinates(self):
        """Rejects latitude and longitude outside valid geographic bounds."""
        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=91.0, longitude=80.0, radius_meters=1000.0)

        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=-91.0, longitude=80.0, radius_meters=1000.0)

        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=26.0, longitude=185.0, radius_meters=1000.0)

        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=26.0, longitude=-185.0, radius_meters=1000.0)

    def test_parameter_validation_radius(self):
        """Rejects non-positive or excessive radius."""
        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=26.0, longitude=80.0, radius_meters=0.0)

        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=26.0, longitude=80.0, radius_meters=-500.0)

        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=26.0, longitude=80.0, radius_meters=55000.0)

    def test_parameter_validation_place_types(self):
        """Rejects invalid place_types argument types."""
        with self.assertRaises(ValidationError):
            self.adapter.validate_search_params(latitude=26.0, longitude=80.0, radius_meters=1000.0, place_types="restaurant")  # type: ignore

    def test_secret_sanitation(self):
        """Verifies API keys are removed from error strings."""
        leak_str = "Error calling https://places.googleapis.com?key=AIzaSyD-SECRET_KEY_123456"
        clean = sanitize_credentials(leak_str)
        self.assertNotIn("AIzaSyD-SECRET_KEY_123456", clean)
        self.assertIn("[REDACTED]", clean)

    def test_client_init_requires_key(self):
        """GooglePlacesClient constructor raises ValidationError if key is blank."""
        with self.assertRaises(ValidationError):
            GooglePlacesClient(api_key="")


class TestGooglePlacesMocked(unittest.TestCase):
    """Tests adapter and client with synthetic mock data and mocked HTTP calls."""

    def test_mock_search_default_anchor(self):
        """Offline mock search returns realistic places around Kakadeo, Kanpur."""
        adapter = GooglePlacesAdapter(force_mock=True)
        resp = adapter.search_nearby_places(
            latitude=DEFAULT_ANCHOR_LAT,
            longitude=DEFAULT_ANCHOR_LNG,
            radius_meters=2000.0,
        )
        self.assertTrue(resp.success)
        self.assertTrue(resp.is_mock)
        self.assertGreater(resp.total_count, 0)
        self.assertIsNotNone(resp.summary)
        self.assertIn("Google Places data reflects registered commercial listings", resp.summary.disclaimer)

        # Confirm proximity sorting
        distances = [p.distance_meters for p in resp.places if p.distance_meters is not None]
        self.assertEqual(distances, sorted(distances))

    def test_mock_search_empty_radius(self):
        """Mock search returns empty list when radius is too small to include any place."""
        adapter = GooglePlacesAdapter(force_mock=True)
        resp = adapter.search_nearby_places(
            latitude=DEFAULT_ANCHOR_LAT,
            longitude=DEFAULT_ANCHOR_LNG,
            radius_meters=10.0,  # 10 meters: no places within this circle
        )
        self.assertTrue(resp.success)
        self.assertEqual(resp.total_count, 0)
        self.assertEqual(len(resp.places), 0)

    def test_mock_search_filter_by_type(self):
        """Filters mock places by place_types."""
        adapter = GooglePlacesAdapter(force_mock=True)
        resp = adapter.search_nearby_places(
            latitude=DEFAULT_ANCHOR_LAT,
            longitude=DEFAULT_ANCHOR_LNG,
            radius_meters=3000.0,
            place_types=["wholesaler"],
        )
        self.assertTrue(resp.success)
        for place in resp.places:
            self.assertIn("wholesaler", place.types)

    @patch("urllib.request.urlopen")
    def test_live_client_success_mocked_http(self, mock_urlopen):
        """Simulates successful HTTP response from Google Places API (New)."""
        mock_payload = {
            "places": [
                {
                    "id": "places/ChIJtest123",
                    "displayName": {"text": "Test Restaurant", "languageCode": "en"},
                    "formattedAddress": "Civil Lines, Kanpur",
                    "location": {"latitude": 26.4700, "longitude": 80.3000},
                    "types": ["restaurant", "food"],
                    "rating": 4.4,
                    "userRatingCount": 50,
                    "businessStatus": "OPERATIONAL",
                    "priceLevel": "PRICE_LEVEL_MODERATE",
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client = GooglePlacesClient(api_key="AIzaSyTEST_KEY", timeout_seconds=5.0)
        result = client.search_nearby(latitude=26.47, longitude=80.30, radius_meters=1000.0)

        self.assertIn("places", result)
        self.assertEqual(len(result["places"]), 1)
        self.assertEqual(result["places"][0]["displayName"]["text"], "Test Restaurant")

    @patch("urllib.request.urlopen")
    def test_live_client_auth_error_mapping(self, mock_urlopen):
        """HTTP 401/403 is mapped to AuthenticationError."""
        err = urllib.error.HTTPError(
            url=PLACES_API_NEW_URL,
            code=403,
            msg="Forbidden",
            hdrs={},  # type: ignore
            fp=io.BytesIO(b'{"error": {"message": "API key not valid"}}'),
        )
        mock_urlopen.side_effect = err

        client = GooglePlacesClient(api_key="AIzaSyBAD_KEY", max_retries=0)
        with self.assertRaises(AuthenticationError) as ctx:
            client.search_nearby(latitude=26.47, longitude=80.30, radius_meters=1000.0)
        self.assertIn("403", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_live_client_rate_limit_error_mapping(self, mock_urlopen):
        """HTTP 429 is mapped to RateLimitError after retries."""
        err = urllib.error.HTTPError(
            url=PLACES_API_NEW_URL,
            code=429,
            msg="Too Many Requests",
            hdrs={},  # type: ignore
            fp=io.BytesIO(b'{"error": {"message": "Resource has been exhausted"}}'),
        )
        mock_urlopen.side_effect = err

        client = GooglePlacesClient(api_key="AIzaSyKEY", max_retries=1)
        with self.assertRaises(RateLimitError):
            client.search_nearby(latitude=26.47, longitude=80.30, radius_meters=1000.0)


if __name__ == "__main__":
    unittest.main()

