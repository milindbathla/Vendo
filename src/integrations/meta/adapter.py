from __future__ import annotations

import os
import logging
from typing import Dict, Any, Optional

from src.integrations.base import IntegrationConfig, IntegrationError, ValidationError

logger = logging.getLogger(__name__)


def _get_meta_config() -> Dict[str, str]:
    """Load Meta (Facebook) API credentials from environment variables."""
    return {
        "access_token": os.environ.get("META_ACCESS_TOKEN", "").strip(),
        "app_id": os.environ.get("META_APP_ID", "").strip(),
        "app_secret": os.environ.get("META_APP_SECRET", "").strip(),
    }


class MetaAdapter:
    """Simple adapter for Meta (Facebook Graph) API.

    Currently provides only status information and mock fallback.
    """

    def __init__(self, access_token: Optional[str] = None, app_id: Optional[str] = None,
                 app_secret: Optional[str] = None, force_mock: Optional[bool] = None):
        cfg = _get_meta_config()
        self.access_token = access_token or cfg["access_token"]
        self.app_id = app_id or cfg["app_id"]
        self.app_secret = app_secret or cfg["app_secret"]
        self.force_mock = IntegrationConfig.is_mock_enabled(force_mock)
        # In a full implementation a client would be created here.
        if not self.force_mock and self.access_token and self.app_id and self.app_secret:
            # Assume real client would be initialized.
            logger.info("MetaAdapter: live mode initialized")
        else:
            self.force_mock = True
            logger.info("MetaAdapter: mock mode (missing credentials or forced)")

    @property
    def is_mock(self) -> bool:
        return self.force_mock

    def get_status(self) -> Dict[str, Any]:
        """Return connectivity and mode status for Meta integration."""
        return {
            "provider": "meta",
            "mode": "mock" if self.is_mock else "live",
            "is_configured": bool(self.access_token and self.app_id and self.app_secret),
            "api_base_url": "https://graph.facebook.com" if not self.is_mock else "MOCK",
        }
