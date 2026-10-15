"""
Synthetic mock data for Google Places API (New) integration.
============================================================
Provides realistic, grounded place listings for Kanpur (Kakadeo area)
where Maa Ki Rasoi Cloud Kitchen operates.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from src.integrations.google_places.models import PlaceLocation, PlaceResult

# Anchor location: Kakadeo, Kanpur (Pin: 208025)
DEFAULT_ANCHOR_LAT = 26.4727
DEFAULT_ANCHOR_LNG = 80.3015

# Disclaimer explicitly clarifying data limitations
PLACES_DATA_DISCLAIMER = (
    "NOTICE: Google Places data reflects registered commercial listings and public ratings. "
    "It does not represent private customer purchase history, verified footfall, or guaranteed customer demand."
)

MOCK_PLACES_DATABASE: List[Dict[str, Any]] = [
    {
        "id": "places/ChIJw2F3zN4BkDkR001",
        "displayName": {"text": "Shukla Bhojnalaya & Tiffin"},
        "formattedAddress": "128/45 B-Block, Kakadeo, Kanpur, UP 208025",
        "location": {"latitude": 26.4740, "longitude": 80.3028},
        "types": ["restaurant", "meal_takeaway", "food"],
        "rating": 4.2,
        "userRatingCount": 142,
        "businessStatus": "OPERATIONAL",
        "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    },
    {
        "id": "places/ChIJy3G4aO5CkDkR002",
        "displayName": {"text": "Annapurna Tiffin Center"},
        "formattedAddress": "Dev Nagar, Near Coaching Hub, Kakadeo, Kanpur 208025",
        "location": {"latitude": 26.4715, "longitude": 80.3002},
        "types": ["meal_delivery", "meal_takeaway", "food"],
        "rating": 4.5,
        "userRatingCount": 88,
        "businessStatus": "OPERATIONAL",
        "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    },
    {
        "id": "places/ChIJz4H5bP6DkDkR003",
        "displayName": {"text": "Kakadeo Student Mess & Fast Food"},
        "formattedAddress": "Main Road, Opp. Coaching Center, Kakadeo, Kanpur 208025",
        "location": {"latitude": 26.4755, "longitude": 80.3045},
        "types": ["restaurant", "fast_food_restaurant", "food"],
        "rating": 3.9,
        "userRatingCount": 210,
        "businessStatus": "OPERATIONAL",
        "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    },
    {
        "id": "places/ChIJa5I6cQ7EkDkR004",
        "displayName": {"text": "Swadist Thali & Cloud Kitchen"},
        "formattedAddress": "Sharda Nagar, Kakadeo, Kanpur, UP 208025",
        "location": {"latitude": 26.4702, "longitude": 80.2985},
        "types": ["meal_delivery", "restaurant", "food"],
        "rating": 4.3,
        "userRatingCount": 95,
        "businessStatus": "OPERATIONAL",
        "priceLevel": "PRICE_LEVEL_MODERATE",
    },
    {
        "id": "places/ChIJb6J7dR8FkDkR005",
        "displayName": {"text": "Kanpur Daily Tiffin Service"},
        "formattedAddress": "Geeta Nagar Crossing, Kakadeo, Kanpur 208025",
        "location": {"latitude": 26.4768, "longitude": 80.3060},
        "types": ["meal_delivery", "food"],
        "rating": 4.1,
        "userRatingCount": 64,
        "businessStatus": "OPERATIONAL",
        "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    },
    {
        "id": "places/ChIJc7K8eS9GkDkR006",
        "displayName": {"text": "Gupta Packaging & Essentials"},
        "formattedAddress": "Shop 12, Mandi Gate, Kakadeo, Kanpur 208025",
        "location": {"latitude": 26.4735, "longitude": 80.3010},
        "types": ["store", "wholesaler"],
        "rating": 4.6,
        "userRatingCount": 51,
        "businessStatus": "OPERATIONAL",
        "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    },
]


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates approximate distance between two lat/lon coordinates in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)


def get_mock_places_raw(
    latitude: float,
    longitude: float,
    radius_meters: float = 1500.0,
    place_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Returns raw mock Google Places API (New) response dictionary."""
    normalized_types = [t.lower().strip() for t in place_types] if place_types else []
    matching_places = []

    for item in MOCK_PLACES_DATABASE:
        loc = item["location"]
        dist = haversine_distance_meters(latitude, longitude, loc["latitude"], loc["longitude"])
        if dist > radius_meters:
            continue

        item_types = [t.lower() for t in item.get("types", [])]
        if normalized_types:
            if not any(req_t in item_types for req_t in normalized_types):
                continue

        # Clone and annotate distance
        clone = dict(item)
        clone["_distance_meters"] = dist
        matching_places.append(clone)

    # Sort by distance
    matching_places.sort(key=lambda p: p["_distance_meters"])
    return {"places": matching_places}

