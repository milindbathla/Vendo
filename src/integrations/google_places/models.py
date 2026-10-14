"""
Data models for Google Places API (New) integration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlaceLocation:
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, float]:
        return {"latitude": self.latitude, "longitude": self.longitude}


@dataclass
class PlaceResult:
    place_id: str
    name: str
    address: str
    location: PlaceLocation
    types: List[str] = field(default_factory=list)
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    business_status: str = "OPERATIONAL"
    price_level: Optional[str] = None
    distance_meters: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["location"] = self.location.to_dict()
        return d


@dataclass
class CompetitorAnalysisSummary:
    total_found: int
    direct_competitors_count: int
    average_competitor_rating: Optional[float]
    top_competitors: List[PlaceResult]
    disclaimer: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_found": self.total_found,
            "direct_competitors_count": self.direct_competitors_count,
            "average_competitor_rating": self.average_competitor_rating,
            "top_competitors": [p.to_dict() for p in self.top_competitors],
            "disclaimer": self.disclaimer,
        }


@dataclass
class NearbySearchResponse:
    success: bool
    places: List[PlaceResult]
    total_count: int
    center_latitude: float
    center_longitude: float
    radius_meters: float
    is_mock: bool
    summary: Optional[CompetitorAnalysisSummary] = None
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "total_count": self.total_count,
            "places": [p.to_dict() for p in self.places],
            "center_latitude": self.center_latitude,
            "center_longitude": self.center_longitude,
            "radius_meters": self.radius_meters,
            "is_mock": self.is_mock,
            "summary": self.summary.to_dict() if self.summary else None,
            "warning": self.warning,
        }

