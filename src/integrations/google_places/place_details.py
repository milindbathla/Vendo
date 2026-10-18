"""
Google Places API (New) — Place Details.
=========================================
Fetches rich details for a single place by place_id:
  opening hours, phone number, website, editorial summary, reviews.

Uses the same GOOGLE_MAPS_API_KEY as the existing Nearby Search client.
GET https://places.googleapis.com/v1/places/{place_id}

This is a standalone addition — it does NOT modify the existing client.py.
Import directly where needed:

    from src.integrations.google_places.place_details import PlaceDetailsClient, get_place_details_mock
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.integrations.base import (
    AuthenticationError,
    IntegrationConfig,
    IntegrationError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    sanitize_credentials,
)

logger = logging.getLogger(__name__)

PLACE_DETAILS_BASE = "https://places.googleapis.com/v1/places"

# Fields requested — controls billing; only fetch what we use
DETAILS_FIELD_MASK = (
    "id,"
    "displayName,"
    "formattedAddress,"
    "location,"
    "types,"
    "rating,"
    "userRatingCount,"
    "businessStatus,"
    "regularOpeningHours,"
    "nationalPhoneNumber,"
    "websiteUri,"
    "editorialSummary,"
    "priceLevel"
)


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OpeningHoursPeriod:
    open_day: int       # 0=Sunday … 6=Saturday
    open_time: str      # "HH:MM"
    close_day: int
    close_time: str     # "HH:MM"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlaceDetails:
    """Rich place details returned by GET /v1/places/{place_id}."""
    place_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    types: List[str] = field(default_factory=list)
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    business_status: str = "OPERATIONAL"
    phone: Optional[str] = None
    website: Optional[str] = None
    editorial_summary: Optional[str] = None
    price_level: Optional[str] = None
    opening_hours_periods: List[OpeningHoursPeriod] = field(default_factory=list)
    opening_hours_text: List[str] = field(default_factory=list)  # human-readable weekday strings
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["opening_hours_periods"] = [p.to_dict() for p in self.opening_hours_periods]
        return d


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Client
# ─────────────────────────────────────────────────────────────────────────────

class PlaceDetailsClient:
    """Fetches place details from Google Places API (New) using a server API key."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: float = 10.0,
        force_mock: Optional[bool] = None,
    ):
        self._api_key = api_key or IntegrationConfig.get_google_maps_api_key()
        self.timeout_seconds = timeout_seconds
        self.force_mock = IntegrationConfig.is_mock_enabled(force_mock)

        if not self.force_mock and not self._api_key:
            logger.info("PlaceDetailsClient: no API key — using mock mode.")
            self.force_mock = True

    @property
    def is_mock(self) -> bool:
        return self.force_mock or not self._api_key

    def get_place_details(self, place_id: str) -> PlaceDetails:
        """Fetches place details for the given place_id."""
        if self.is_mock:
            return get_place_details_mock(place_id)

        # Normalise place_id — API expects "places/ChIJ..." format
        if not place_id.startswith("places/"):
            place_id_path = f"places/{place_id}"
        else:
            place_id_path = place_id

        url = f"{PLACE_DETAILS_BASE}/{place_id_path.lstrip('places/')}"
        # Use the full resource name format
        url = f"{PLACE_DETAILS_BASE}/{place_id}" if not place_id.startswith("places/") else \
              f"https://places.googleapis.com/v1/{place_id}"

        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": DETAILS_FIELD_MASK,
        }
        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                return self._normalize(raw, is_mock=False)
        except urllib.error.HTTPError as exc:
            body = sanitize_credentials(exc.read().decode("utf-8", errors="replace"))
            if exc.code == 401 or exc.code == 403:
                raise AuthenticationError(
                    f"Google Places auth error {exc.code}: {body}", provider="google_places"
                )
            if exc.code == 429:
                raise RateLimitError("Google Places rate limit", provider="google_places")
            if exc.code >= 500:
                raise ProviderUnavailableError(
                    f"Google Places server error {exc.code}", provider="google_places"
                )
            raise IntegrationError(
                f"Google Places HTTP {exc.code}: {body}", provider="google_places"
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderUnavailableError(
                f"Google Places network error: {exc}", provider="google_places"
            )

    def _normalize(self, raw: Dict[str, Any], is_mock: bool = False) -> PlaceDetails:
        """Converts raw Places API (New) place details response into PlaceDetails."""
        display_obj = raw.get("displayName", {})
        name = display_obj.get("text", "") if isinstance(display_obj, dict) else str(display_obj)

        loc = raw.get("location", {})
        lat = float(loc.get("latitude", 0.0))
        lng = float(loc.get("longitude", 0.0))

        summary_obj = raw.get("editorialSummary", {})
        summary_text = summary_obj.get("text") if isinstance(summary_obj, dict) else None

        # Opening hours
        oh = raw.get("regularOpeningHours", {})
        periods_raw = oh.get("periods", [])
        periods = []
        for p in periods_raw:
            try:
                periods.append(OpeningHoursPeriod(
                    open_day=p["open"]["day"],
                    open_time=f"{p['open'].get('hour', 0):02d}:{p['open'].get('minute', 0):02d}",
                    close_day=p.get("close", p["open"])["day"],
                    close_time=f"{p.get('close', p['open']).get('hour', 23):02d}:"
                               f"{p.get('close', p['open']).get('minute', 59):02d}",
                ))
            except (KeyError, TypeError):
                continue

        weekday_descriptions = oh.get("weekdayDescriptions", [])

        return PlaceDetails(
            place_id=raw.get("id", ""),
            name=name,
            address=raw.get("formattedAddress", ""),
            latitude=lat,
            longitude=lng,
            types=raw.get("types", []),
            rating=float(raw["rating"]) if raw.get("rating") is not None else None,
            user_rating_count=int(raw["userRatingCount"]) if raw.get("userRatingCount") else None,
            business_status=raw.get("businessStatus", "OPERATIONAL"),
            phone=raw.get("nationalPhoneNumber"),
            website=raw.get("websiteUri"),
            editorial_summary=summary_text,
            price_level=raw.get("priceLevel"),
            opening_hours_periods=periods,
            opening_hours_text=weekday_descriptions,
            is_mock=is_mock,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mock data
# ─────────────────────────────────────────────────────────────────────────────

def get_place_details_mock(place_id: str = "mock_place_001") -> PlaceDetails:
    """Returns realistic mock place details for a Kanpur tiffin business competitor."""
    return PlaceDetails(
        place_id=place_id,
        name="Sharma Tiffin Centre",
        address="Shop 14, Kakadeo Market, Kanpur, Uttar Pradesh 208025",
        latitude=26.4731,
        longitude=80.3021,
        types=["restaurant", "meal_delivery", "meal_takeaway"],
        rating=4.2,
        user_rating_count=318,
        business_status="OPERATIONAL",
        phone="+91 98765 43210",
        website=None,
        editorial_summary="Popular neighbourhood tiffin service known for home-style dal-rice meals.",
        price_level="PRICE_LEVEL_INEXPENSIVE",
        opening_hours_periods=[
            OpeningHoursPeriod(open_day=1, open_time="07:00", close_day=1, close_time="20:00"),
            OpeningHoursPeriod(open_day=2, open_time="07:00", close_day=2, close_time="20:00"),
            OpeningHoursPeriod(open_day=3, open_time="07:00", close_day=3, close_time="20:00"),
            OpeningHoursPeriod(open_day=4, open_time="07:00", close_day=4, close_time="20:00"),
            OpeningHoursPeriod(open_day=5, open_time="07:00", close_day=5, close_time="20:00"),
            OpeningHoursPeriod(open_day=6, open_time="08:00", close_day=6, close_time="16:00"),
        ],
        opening_hours_text=[
            "Monday: 7:00 AM – 8:00 PM",
            "Tuesday: 7:00 AM – 8:00 PM",
            "Wednesday: 7:00 AM – 8:00 PM",
            "Thursday: 7:00 AM – 8:00 PM",
            "Friday: 7:00 AM – 8:00 PM",
            "Saturday: 8:00 AM – 4:00 PM",
            "Sunday: Closed",
        ],
        is_mock=True,
    )
