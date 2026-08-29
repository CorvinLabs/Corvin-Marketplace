"""Unit tests for ExampleRouterBackend plugin.

Tests core routing logic and error handling.
"""

import pytest
from unittest.mock import Mock
from plugin import ExampleRouterBackend, HealthStatus


class TestExampleRouterBackend:
    """Test suite for ExampleRouterBackend."""

    @pytest.fixture
    def router(self):
        """Create a fresh router instance for each test."""
        return ExampleRouterBackend()

    @pytest.fixture
    def mock_context(self):
        """Create a mock PluginContext."""
        context = Mock()
        context.router_registry = Mock()
        context.router_registry.set_active = Mock()
        return context

    # ─── Plugin Contract Tests ───────────────────────────────────────

    def test_plugin_has_required_attributes(self, router):
        """Plugin implements required contract attributes."""
        assert hasattr(router, "plugin_id")
        assert hasattr(router, "plugin_type")
        assert hasattr(router, "version")
        assert hasattr(router, "display_name")

    def test_plugin_has_required_methods(self, router):
        """Plugin implements required contract methods."""
        assert callable(getattr(router, "on_load", None))
        assert callable(getattr(router, "on_unload", None))
        assert callable(getattr(router, "health_check", None))
        assert callable(getattr(router, "route", None))

    def test_on_load_registers_with_context(self, router, mock_context):
        """on_load registers router with context."""
        router.on_load(mock_context)
        mock_context.router_registry.set_active.assert_called_once_with(router)

    def test_on_unload_completes(self, router):
        """on_unload completes without error."""
        # Should not raise
        router.on_unload()

    def test_health_check_returns_status(self, router):
        """health_check returns HealthStatus."""
        health = router.health_check()
        assert isinstance(health, HealthStatus)
        assert health.ok is True

    # ─── Routing Tests ──────────────────────────────────────────────

    def test_route_database_query(self, router):
        """Route matches 'database' keyword."""
        result = router.route("I need to query my database")
        assert result == "database-handler"

    def test_route_sql_query(self, router):
        """Route matches 'sql' keyword."""
        result = router.route("Can you run an SQL query?")
        assert result == "database-handler"

    def test_route_email_query(self, router):
        """Route matches 'email' keyword."""
        result = router.route("Send me an email")
        assert result == "email-handler"

    def test_route_mail_query(self, router):
        """Route matches 'mail' keyword."""
        result = router.route("Please mail this to Bob")
        assert result == "email-handler"

    def test_route_api_query(self, router):
        """Route matches 'api' keyword."""
        result = router.route("Call the REST API")
        assert result == "api-handler"

    def test_route_rest_query(self, router):
        """Route matches 'rest' keyword."""
        result = router.route("Make a REST request")
        assert result == "api-handler"

    def test_route_case_insensitive(self, router):
        """Route matching is case-insensitive."""
        result = router.route("QUERY MY DATABASE")
        assert result == "database-handler"

        result = router.route("Send an EMAIL please")
        assert result == "email-handler"

    def test_route_no_match(self, router):
        """Route returns None on no match."""
        result = router.route("Tell me a joke")
        assert result is None

    def test_route_empty_message(self, router):
        """Route handles empty message gracefully."""
        result = router.route("")
        assert result is None

    def test_route_never_raises_on_invalid_input(self, router):
        """Route never raises, even with invalid input."""
        # These would normally crash, but route should handle gracefully
        assert router.route(None) is None
        assert router.route(123) is None
        assert router.route([]) is None
        assert router.route({}) is None

    def test_route_with_context_parameter(self, router):
        """Route accepts optional context parameter."""
        # Context can be None or a dict
        result = router.route("Query database", context=None)
        assert result == "database-handler"

        result = router.route("Query database", context={"tenant_id": "test"})
        assert result == "database-handler"

    # ─── Error Handling & Safety ────────────────────────────────────

    def test_router_never_raises_on_route(self, router):
        """Critical: route() must never raise an exception.

        This is a core invariant for router backends (ADR-0233).
        If route() raises, it can crash the entire message-handling pipeline.
        """
        # Test with various invalid inputs
        test_cases = [
            None,
            123,
            [],
            {},
            object(),
            lambda x: x,
        ]

        for invalid_input in test_cases:
            try:
                result = router.route(invalid_input)
                # Should return None, not raise
                assert result is None
            except Exception as e:
                pytest.fail(f"route() raised {type(e).__name__}: {e}")

    def test_health_check_completes_quickly(self, router):
        """health_check must complete within 2 seconds."""
        import time
        start = time.time()
        health = router.health_check()
        elapsed = time.time() - start

        # Should complete in <1 second (well under 2s requirement)
        assert elapsed < 1.0
        assert health.ok is True

    # ─── Integration-like Tests ─────────────────────────────────────

    def test_full_lifecycle(self, router, mock_context):
        """Test full plugin lifecycle: load → health → route → unload."""
        # Load
        router.on_load(mock_context)
        mock_context.router_registry.set_active.assert_called_once()

        # Health check
        health = router.health_check()
        assert health.ok is True

        # Route a message
        result = router.route("Query my database")
        assert result == "database-handler"

        # Unload
        router.on_unload()

        # Should be idempotent (can call multiple times)
        router.on_unload()

    def test_multiple_instances_independent(self):
        """Multiple plugin instances are independent."""
        router1 = ExampleRouterBackend()
        router2 = ExampleRouterBackend()

        # Both route independently
        assert router1.route("database") == "database-handler"
        assert router2.route("email") == "email-handler"

        # Unloading one doesn't affect the other
        router1.on_unload()
        assert router2.route("api") == "api-handler"
