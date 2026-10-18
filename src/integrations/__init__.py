"""
External Integrations Package for Alexa Business Autopilot.
===========================================================
Exports Google Places and Zoho Books adapters, normalization helpers,
and configuration management.
"""
from src.integrations.base import (
    AuthenticationError,
    IntegrationConfig,
    IntegrationError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    sanitize_credentials,
)
from src.integrations.google_places import (
    CompetitorAnalysisSummary,
    GooglePlacesAdapter,
    GooglePlacesClient,
    NearbySearchResponse,
    PlaceLocation,
    PlaceResult,
)
from src.integrations.normalization import BusinessDataNormalizer, to_currency_decimal
from src.integrations.zoho_books import (
    ZohoAccountingSummary,
    ZohoBill,
    ZohoBooksAdapter,
    ZohoBooksClient,
    ZohoExpense,
    ZohoInvoice,
    ZohoInvoiceLine,
    ZohoOAuthManager,
    ZohoOrganization,
    ZohoPaginatedResponse,
)

__all__ = [
    "IntegrationError",
    "ValidationError",
    "AuthenticationError",
    "RateLimitError",
    "ProviderUnavailableError",
    "sanitize_credentials",
    "IntegrationConfig",
    "GooglePlacesAdapter",
    "GooglePlacesClient",
    "PlaceLocation",
    "PlaceResult",
    "NearbySearchResponse",
    "CompetitorAnalysisSummary",
    "ZohoBooksAdapter",
    "ZohoBooksClient",
    "ZohoOAuthManager",
    "ZohoOrganization",
    "ZohoInvoice",
    "ZohoInvoiceLine",
    "ZohoBill",
    "ZohoExpense",
    "ZohoAccountingSummary",
    "ZohoPaginatedResponse",
    "BusinessDataNormalizer",
    "to_currency_decimal",
    "BaseEmailProvider",
    "MockEmailProvider",
    "EmailIngestionService",
]

from src.integrations.email_provider import (
    BaseEmailProvider,
    MockEmailProvider,
    EmailIngestionService,
)

