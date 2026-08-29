"""Example Router Backend Plugin

Demonstrates best practices for building a router backend plugin:
- Implementing the plugin contract (on_load, on_unload, health_check)
- Handling messages safely (never raise, return None on error)
- Registering with the layer
- Health check that completes within 2 seconds

ADR-0233 (plugin-system), ADR-0030 (lifecycle contract)
"""

import logging
from typing import Optional

# These imports would come from CorvinOS
# In testing, they're mocked
try:
    from corvin_plugins.protocol import PluginContext, HealthStatus
except ImportError:
    # Fallback for testing/development
    class HealthStatus:
        def __init__(self, ok: bool, message: str = ""):
            self.ok = ok
            self.message = message


logger = logging.getLogger(__name__)


class ExampleRouterBackend:
    """Example router backend plugin.

    This plugin routes messages based on simple keyword matching.
    It demonstrates:
    - Required plugin contract (lifecycle + capability)
    - Fail-safe routing (never raises, always returns None or handler name)
    - Health check (fast, local only)
    - Proper logging (no PII)
    """

    # ─── Plugin Contract (ADR-0030) ───────────────────────────────────

    plugin_id = "com.corvinlabs.example-router"
    plugin_type = "router_backend"
    version = "1.0.0"
    display_name = "Example Router Backend"

    def __init__(self):
        """Initialize plugin instance."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def on_load(self, ctx: PluginContext) -> None:
        """Called when plugin loads. Register with the router layer.

        Args:
            ctx: PluginContext with access to registries and config
        """
        try:
            # Register self as the active router
            ctx.router_registry.set_active(self)
            self.logger.info(
                f"Plugin loaded: {self.plugin_id} v{self.version}"
            )
        except Exception as e:
            self.logger.error(f"Failed to load plugin: {e}")
            raise

    def on_unload(self) -> None:
        """Called when plugin unloads. Clean up resources.

        In this example, there are no resources to clean up.
        In real plugins, you might close database connections, flush queues, etc.
        """
        self.logger.info(f"Plugin unloaded: {self.plugin_id}")

    def health_check(self) -> HealthStatus:
        """Return plugin health status. Must complete within 2 seconds.

        Returns:
            HealthStatus indicating whether plugin is operational
        """
        # Example: simple local check (no network, no I/O)
        try:
            # In a real plugin, you might check:
            # - Database connection is alive
            # - Required config is present
            # - Resources are allocated
            # But always keep it <100ms and never block on network/I/O

            return HealthStatus(ok=True, message="ok")
        except Exception as e:
            return HealthStatus(ok=False, message=f"health check failed: {e}")

    # ─── Capability: Message Routing (ADR-0233) ───────────────────────

    def route(
        self,
        message: str,
        context: Optional[dict] = None
    ) -> Optional[str]:
        """Route a message to a handler.

        CRITICAL INVARIANT (ADR-0233):
        This method must NEVER raise an exception.
        Always return None on error or no-match.
        Never let an exception propagate.

        Args:
            message: The message to route (user input, untrusted)
            context: Optional context dict with metadata

        Returns:
            Handler name (string) if this plugin handles the message,
            None if no match or on error (never raise)
        """
        try:
            # Safely handle the message
            handler = self._match_handler(message)
            if handler:
                self.logger.debug(f"Routed to {handler}")
                return handler
            # No match → return None
            return None
        except Exception as e:
            # Log error, but never raise
            self.logger.error(f"Router error: {e}", exc_info=True)
            return None

    # ─── Helper Methods ──────────────────────────────────────────────

    def _match_handler(self, message: str) -> Optional[str]:
        """Match message to a handler based on simple keyword logic.

        Args:
            message: Message text to analyze

        Returns:
            Handler name or None if no match
        """
        # Simple keyword matching
        message_lower = message.lower()

        # Example routing rules
        if "database" in message_lower or "sql" in message_lower:
            return "database-handler"

        if "email" in message_lower or "mail" in message_lower:
            return "email-handler"

        if "api" in message_lower or "rest" in message_lower:
            return "api-handler"

        # No match
        return None


# ─── Module-level validation ──────────────────────────────────────

# This allows the entry point to work via importlib:
#   entry_point.load() → ExampleRouterBackend

__all__ = ["ExampleRouterBackend"]
