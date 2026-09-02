"""L16 consent management gate - GDPR Art. 6/7 compliance.

Implements user consent validation for telemetry, learning, healing traces, and geo-tracking.
Enforces fail-closed default-deny semantics - users must explicitly grant consent.

Reference: ADR-0232, ADR-0233, L16 (Consent Gate), GDPR Art. 6, 7, 21
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import threading

# Import the user_backend provider
try:
    from core.plugins.corvin_plugins.providers import user_backend
except ImportError:
    user_backend = None

_logger = logging.getLogger(__name__)


# Valid consent types (GDPR)
VALID_CONSENT_TYPES = {
    "telemetry",  # Instance-count ping + environment data
    "learning",  # ADR-0314 feedback loop
    "healing_traces",  # Error telemetry
    "geo_tracking_tier1",  # Country-level geolocation
    "geo_tracking_tier2",  # Region-level geolocation
    "geo_tracking_tier3",  # City-level geolocation (10km grid)
}

# Default TTL for each consent type (in hours)
DEFAULT_CONSENT_TTL = {
    "telemetry": 2160,  # 90 days
    "learning": 168,  # 7 days
    "healing_traces": 168,  # 7 days
    "geo_tracking_tier1": 720,  # 30 days
    "geo_tracking_tier2": 360,  # 15 days
    "geo_tracking_tier3": 168,  # 7 days
}


class ConsentGate:
    """L16 consent gate plugin - GDPR-compliant consent validation (fail-closed)."""

    def __init__(self):
        """Initialize the consent gate."""
        self.enabled = True
        self._user_backend = None
        self._lock = threading.Lock()

    async def initialize(self, context):
        """Initialize the plugin with context.

        Args:
            context: Plugin context (may include user_backend reference)
        """
        try:
            # Get user_backend provider
            if user_backend:
                self._user_backend = user_backend.get_active()
            _logger.info("ConsentGate initialized")
        except Exception as e:
            _logger.error(f"Initialization failed: {e}")
            self._user_backend = None

    async def grant_consent(
        self, user_id: str, tenant_id: str, consent_type: str, ttl_hours: Optional[int] = None
    ) -> bool:
        """Grant user consent for a feature (GDPR Art. 7).

        Args:
            user_id: The user granting consent
            tenant_id: The tenant context
            consent_type: Type of consent (must be in VALID_CONSENT_TYPES)
            ttl_hours: Optional custom TTL (default per consent_type)

        Returns:
            True if consent granted, False if validation failed
        """
        try:
            # Validate consent type
            if consent_type not in VALID_CONSENT_TYPES:
                _logger.warning(f"Invalid consent type requested: {consent_type}")
                return False

            # Use default TTL if not specified
            if ttl_hours is None:
                ttl_hours = DEFAULT_CONSENT_TTL.get(consent_type, 168)

            # Calculate expiration
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=ttl_hours)

            # Grant consent via user_backend
            if self._user_backend:
                from core.plugins.corvin_plugins.providers.user_backend import UserConsent
                consent = UserConsent(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    consent_type=consent_type,
                    granted=True,
                    granted_at=now.isoformat(),
                    expires_at=expires_at.isoformat()
                )
                result = await self._user_backend.grant_consent(consent)
                if result:
                    _logger.info(f"Consent granted: {user_id}/{consent_type} (TTL: {ttl_hours}h)")
                return result

            return False
        except Exception as e:
            _logger.error(f"Failed to grant consent: {e}")
            return False

    async def check_consent(self, user_id: str, tenant_id: str, consent_type: str) -> bool:
        """Check if user has granted valid consent (fail-closed, default-deny).

        Args:
            user_id: The user
            tenant_id: The tenant context
            consent_type: Type of consent to check

        Returns:
            True if consent granted and not expired, False otherwise
        """
        try:
            # Validate consent type
            if consent_type not in VALID_CONSENT_TYPES:
                _logger.warning(f"Unknown consent type checked: {consent_type}")
                return False

            # Check via user_backend (fail-closed if backend unavailable)
            if self._user_backend:
                result = await self._user_backend.check_consent(user_id, tenant_id, consent_type)
                if not result:
                    _logger.debug(f"Consent denied: {user_id}/{consent_type}")
                return result

            # No backend = deny (fail-closed)
            _logger.warning(f"Consent check failed: no user_backend available")
            return False
        except Exception as e:
            _logger.error(f"Consent check failed: {e}")
            return False  # Fail-closed

    async def revoke_consent(self, user_id: str, tenant_id: str, consent_type: str) -> bool:
        """Revoke user consent (GDPR Art. 7 & 21).

        Args:
            user_id: The user revoking consent
            tenant_id: The tenant context
            consent_type: Type of consent to revoke

        Returns:
            True if revoked successfully
        """
        try:
            if self._user_backend:
                result = await self._user_backend.revoke_consent(user_id, tenant_id, consent_type)
                if result:
                    _logger.info(f"Consent revoked: {user_id}/{consent_type}")
                return result
            return False
        except Exception as e:
            _logger.error(f"Failed to revoke consent: {e}")
            return False

    async def execute(self, operation: str, **kwargs) -> dict:
        """Execute consent gate operations.

        Args:
            operation: "grant", "check", "revoke"
            **kwargs: Operation-specific arguments

        Returns:
            Operation result
        """
        try:
            if operation == "grant":
                user_id = kwargs.get("user_id")
                tenant_id = kwargs.get("tenant_id")
                consent_type = kwargs.get("consent_type")

                if not all([user_id, tenant_id, consent_type]):
                    return {"success": False, "error": "user_id, tenant_id, consent_type required"}

                ttl_hours = kwargs.get("ttl_hours")
                result = await self.grant_consent(user_id, tenant_id, consent_type, ttl_hours)
                return {
                    "granted": result,
                    "user_id": user_id,
                    "consent_type": consent_type,
                    "success": result
                }

            elif operation == "check":
                user_id = kwargs.get("user_id")
                tenant_id = kwargs.get("tenant_id")
                consent_type = kwargs.get("consent_type")

                if not all([user_id, tenant_id, consent_type]):
                    return {"success": False, "error": "user_id, tenant_id, consent_type required"}

                result = await self.check_consent(user_id, tenant_id, consent_type)
                return {
                    "granted": result,
                    "user_id": user_id,
                    "consent_type": consent_type,
                    "success": True
                }

            elif operation == "revoke":
                user_id = kwargs.get("user_id")
                tenant_id = kwargs.get("tenant_id")
                consent_type = kwargs.get("consent_type")

                if not all([user_id, tenant_id, consent_type]):
                    return {"success": False, "error": "user_id, tenant_id, consent_type required"}

                result = await self.revoke_consent(user_id, tenant_id, consent_type)
                return {
                    "revoked": result,
                    "user_id": user_id,
                    "consent_type": consent_type,
                    "success": result
                }

            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            _logger.error(f"Execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """Check plugin health."""
        try:
            if self._user_backend:
                return await self._user_backend.health_check()
            return False
        except Exception:
            return False

    async def shutdown(self):
        """Shutdown the plugin."""
        _logger.info("ConsentGate shutting down")
