"""
Google Places Adapter: Normalization, Validation, and Mock Orchestration.
========================================================================
Implements search_nearby_places, input validation, competitor analysis,
and data disclaimer safeguards.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.integrations.base import (
    AuthenticationError,
    IntegrationConfig,
    IntegrationError,
    RateLimitError,
    ValidationError,
)
from src.integrations.google_places.client import GooglePlacesClient
from src.integrations.google_places.mock_data import (
    DEFAULT_ANCHOR_LAT,
    DEFAULT_ANCHOR_LNG,
    PLACES_DATA_DISCLAIMER,
    get_mock_places_raw,
    haversine_distance_meters,
)
from src.integrations.google_places.models import (
    CompetitorAnalysisSummary,
    NearbySearchResponse,
    PlaceLocation,
    PlaceResult,
)

logger = logging.getLogger(__name__)

# Standard place types commonly relevant to Indian food, retail & services
FOOD_COMPETITOR_TYPES = {"restaurant", "meal_delivery", "meal_takeaway", "fast_food_restaurant", "cafe", "food"}


class GooglePlacesAdapter:
    """High-level adapter providing validated nearby searches and competitor analysis."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        force_mock: Optional[bool] = None,
        timeout_seconds: float = 10.0,
    ):
        self._configured_key = api_key or IntegrationConfig.get_google_maps_api_key()
        self.force_mock = IntegrationConfig.is_mock_enabled(force_mock)
        self.timeout_seconds = timeout_seconds

        self._client: Optional[GooglePlacesClient] = None
        if not self.force_mock and self._configured_key:
            try:
                self._client = GooglePlacesClient(api_key=self._configured_key, timeout_seconds=timeout_seconds)
            except Exception as e:
                logger.warning("Could not initialize live Google Places client: %s. Falling back to mock.", e)
                self.force_mock = True
        else:
            self.force_mock = True

    @property
    def is_mock(self) -> bool:
        return self.force_mock or self._client is None

    def validate_search_params(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float,
        place_types: Optional[List[str]] = None,
    ) -> None:
        """Validates geographic coordinates and search bounds."""
        if not isinstance(latitude, (int, float)) or not (-90.0 <= latitude <= 90.0):
            raise ValidationError(
                f"Invalid latitude: {latitude}. Must be a float between -90.0 and 90.0.",
                provider="google_places",
            )
        if not isinstance(longitude, (int, float)) or not (-180.0 <= longitude <= 180.0):
            raise ValidationError(
                f"Invalid longitude: {longitude}. Must be a float between -180.0 and 180.0.",
                provider="google_places",
            )
        if not isinstance(radius_meters, (int, float)) or radius_meters <= 0.0:
            raise ValidationError(
                f"Invalid radius: {radius_meters}. Must be greater than 0 meters.",
                provider="google_places",
            )
        if radius_meters > 50000.0:
            raise ValidationError(
                f"Radius {radius_meters}m exceeds Google Places API limit of 50,000 meters (50 km).",
                provider="google_places",
            )
        if place_types is not None and not isinstance(place_types, list):
            raise ValidationError(
                "place_types must be a list of strings if provided.",
                provider="google_places",
            )

    def search_nearby_places(
        self,
        latitude: float = DEFAULT_ANCHOR_LAT,
        longitude: float = DEFAULT_ANCHOR_LNG,
        radius_meters: float = 1500.0,
        place_types: Optional[List[str]] = None,
        max_results: int = 20,
    ) -> NearbySearchResponse:
        """Searches nearby places, normalizes results, and computes competitor metrics."""
        self.validate_search_params(latitude, longitude, radius_meters, place_types)

        is_mock_run = self.is_mock
        raw_response: Dict[str, Any]

        if is_mock_run:
            raw_response = get_mock_places_raw(
                latitude=latitude,
                longitude=longitude,
                radius_meters=radius_meters,
                place_types=place_types,
            )
        else:
            assert self._client is not None
            raw_response = self._client.search_nearby(
                latitude=latitude,
                longitude=longitude,
                radius_meters=radius_meters,
                place_types=place_types,
                max_result_count=max_results,
            )

        places = self._normalize_places(raw_response.get("places", []), center_lat=latitude, center_lng=longitude)
        summary = self._build_competitor_summary(places)

        return NearbySearchResponse(
            success=True,
            places=places,
            total_count=len(places),
            center_latitude=latitude,
            center_longitude=longitude,
            radius_meters=radius_meters,
            is_mock=is_mock_run,
            summary=summary,
        )

    def _normalize_places(
        self,
        raw_places: List[Dict[str, Any]],
        center_lat: float,
        center_lng: float,
    ) -> List[PlaceResult]:
        """Converts raw Places API (New) dictionaries into normalized PlaceResult objects."""
        normalized: List[PlaceResult] = []

        for p in raw_places:
            place_id = p.get("id") or p.get("place_id") or "places/unknown"

            # Display name in Places New is a localized object: {"text": "Name", "languageCode": "en"}
            display_obj = p.get("displayName")
            if isinstance(display_obj, dict):
                name = display_obj.get("text", "Unnamed Place")
            else:
                name = str(display_obj or p.get("name") or "Unnamed Place")

            address = p.get("formattedAddress") or p.get("address") or "Address unavailable"

            # Location
            loc_dict = p.get("location") or {}
            plat = float(loc_dict.get("latitude", center_lat))
            plng = float(loc_dict.get("longitude", center_lng))
            loc = PlaceLocation(latitude=plat, longitude=plng)

            # Distance
            dist = p.get("_distance_meters")
            if dist is None:
                dist = haversine_distance_meters(center_lat, center_lng, plat, plng)

            types = p.get("types", [])
            rating = float(p["rating"]) if p.get("rating") is not None else None
            user_rating_count = int(p["userRatingCount"]) if p.get("userRatingCount") is not None else None
            business_status = p.get("businessStatus", "OPERATIONAL")
            price_level = p.get("priceLevel")

            normalized.append(
                PlaceResult(
                    place_id=place_id,
                    name=name,
                    address=address,
                    location=loc,
                    types=types,
                    rating=rating,
                    user_rating_count=user_rating_count,
                    business_status=business_status,
                    price_level=price_level,
                    distance_meters=dist,
                )
            )

        # Sort by distance ascending
        normalized.sort(key=lambda x: (x.distance_meters if x.distance_meters is not None else 999999.0))
        return normalized

    def _build_competitor_summary(self, places: List[PlaceResult]) -> CompetitorAnalysisSummary:
        """Aggregates competitive metrics (ratings, density, category overlap)."""
        competitors = [
            p for p in places if any(t.lower() in FOOD_COMPETITOR_TYPES for t in p.types)
        ]
        rated_competitors = [c.rating for c in competitors if c.rating is not None]
        avg_rating = round(sum(rated_competitors) / len(rated_competitors), 2) if rated_competitors else None

        # Top 3 competitors sorted by user ratings count
        sorted_by_popularity = sorted(
            competitors,
            key=lambda c: (c.user_rating_count or 0, c.rating or 0.0),
            reverse=True,
        )

        return CompetitorAnalysisSummary(
            total_found=len(places),
            direct_competitors_count=len(competitors),
            average_competitor_rating=avg_rating,
            top_competitors=sorted_by_popularity[:3],
            disclaimer=PLACES_DATA_DISCLAIMER,
        )

