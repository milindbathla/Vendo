"""
HTTP Client for Google Maps Platform: Places API (New).
======================================================
Implements POST /v1/places:searchNearby with field masking, timeouts,
bounded retries, and sanitized exception handling.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from src.integrations.base import (
    AuthenticationError,
    IntegrationError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    sanitize_credentials,
)

logger = logging.getLogger(__name__)

PLACES_API_NEW_URL = "https://places.googleapis.com/v1/places:searchNearby"
DEFAULT_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.types,"
    "places.rating,"
    "places.userRatingCount,"
    "places.businessStatus,"
    "places.priceLevel"
)


class GooglePlacesClient:
    """Low-level HTTP client executing authorized requests against Places API (New)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = PLACES_API_NEW_URL,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
    ):
        if not api_key or not api_key.strip():
            raise ValidationError("API key is required for live Google Places API requests", provider="google_places")
        self._api_key = api_key.strip()
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def search_nearby(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float,
        place_types: Optional[List[str]] = None,
        max_result_count: int = 20,
    ) -> Dict[str, Any]:
        """Executes searchNearby against Places API (New)."""
        payload: Dict[str, Any] = {
            "maxResultCount": min(max(1, max_result_count), 20),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_meters),
                }
            },
        }
        if place_types:
            payload["includedTypes"] = place_types

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=body_bytes, headers=headers, method="POST")

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    raw_data = response.read().decode("utf-8")
                    if not raw_data.strip():
                        return {"places": []}
                    return json.loads(raw_data)

            except urllib.error.HTTPError as e:
                status_code = e.code
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    pass
                sanitized_msg = sanitize_credentials(f"HTTP {status_code}: {e.reason} - {error_body}")

                if status_code in (401, 403):
                    raise AuthenticationError(
                        f"Google Places authentication failed ({status_code}): {sanitized_msg}",
                        provider="google_places",
                        status_code=status_code,
                    )
                elif status_code == 429:
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (2 ** attempt))
                        continue
                    raise RateLimitError(
                        f"Google Places quota or rate limit exceeded: {sanitized_msg}",
                        provider="google_places",
                        status_code=429,
                    )
                elif 400 <= status_code < 500:
                    raise ValidationError(
                        f"Invalid Google Places request ({status_code}): {sanitized_msg}",
                        provider="google_places",
                        status_code=status_code,
                    )
                elif status_code >= 500:
                    last_error = ProviderUnavailableError(
                        f"Google Places server error ({status_code}): {sanitized_msg}",
                        provider="google_places",
                        status_code=status_code,
                    )
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (2 ** attempt))
                        continue
                    raise last_error
                else:
                    raise IntegrationError(sanitized_msg, provider="google_places", status_code=status_code)

            except (urllib.error.URLError, TimeoutError, OSError) as e:
                sanitized_msg = sanitize_credentials(str(e))
                last_error = ProviderUnavailableError(
                    f"Google Places network connection failed: {sanitized_msg}",
                    provider="google_places",
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise last_error

        if last_error:
            raise last_error
        return {"places": []}

