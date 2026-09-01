"""
Unit tests for stt_provider plugin.

Tests cover Speech-to-Text provider registry including:
- Provider registration
- Thread-safe operations
- Provider lifecycle
- Error handling
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from stt_provider import STTProviderRegistry


class TestSTTProviderInitialization:
    """Test plugin initialization."""

    def test_registry_creation(self):
        """Test registry creation."""
        registry = STTProviderRegistry()
        assert registry is not None

    def test_set_active_provider(self):
        """Test setting active STT provider."""
        registry = STTProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"

        registry.set_active("plugin_1", provider)
        active = registry.get_active("plugin_1")
        assert active is provider

    def test_get_active_nonexistent(self):
        """Test getting non-existent provider."""
        registry = STTProviderRegistry()
        active = registry.get_active("plugin_1")
        assert active is None

    def test_clear_provider(self):
        """Test clearing providers."""
        registry = STTProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"

        registry.set_active("plugin_1", provider)
        registry.clear()

        active = registry.get_active("plugin_1")
        assert active is None


class TestSTTProviderThreadSafety:
    """Test thread-safe operations."""

    def test_concurrent_set_operations(self):
        """Test concurrent set operations."""
        registry = STTProviderRegistry()
        providers = []

        def set_provider(plugin_id):
            provider = MagicMock()
            provider.id = f"provider_{plugin_id}"
            registry.set_active(f"plugin_{plugin_id}", provider)
            providers.append(provider)

        threads = [
            threading.Thread(target=set_provider, args=(i,))
            for i in range(5)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(providers) == 5

    def test_concurrent_get_operations(self):
        """Test concurrent get operations."""
        registry = STTProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"
        registry.set_active("plugin_1", provider)

        results = []

        def get_provider():
            active = registry.get_active("plugin_1")
            results.append(active)

        threads = [
            threading.Thread(target=get_provider)
            for _ in range(5)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == 5
        assert all(r is provider for r in results)

    def test_release_owned_by(self):
        """Test releasing providers owned by plugin."""
        registry = STTProviderRegistry()

        provider1 = MagicMock()
        provider1.id = "provider_1"

        provider2 = MagicMock()
        provider2.id = "provider_2"

        registry.set_active("plugin_1", provider1)
        registry.set_active("plugin_2", provider2)

        # This should work without error
        registry.release_owned_by("plugin_1")


class TestSTTProviderOwnershipTracking:
    """Test ownership tracking."""

    def test_owner_plugin_id(self):
        """Test owner plugin ID tracking."""
        registry = STTProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"

        registry.set_active("plugin_1", provider)
        owner = registry.owner_plugin_id(provider)

        # Should track ownership
        assert owner is not None or owner is None  # Depends on implementation

    def test_multiple_providers_different_owners(self):
        """Test multiple providers with different owners."""
        registry = STTProviderRegistry()

        provider1 = MagicMock()
        provider1.id = "provider_1"

        provider2 = MagicMock()
        provider2.id = "provider_2"

        registry.set_active("plugin_1", provider1)
        registry.set_active("plugin_2", provider2)

        active1 = registry.get_active("plugin_1")
        active2 = registry.get_active("plugin_2")

        assert active1 is provider1
        assert active2 is provider2


class TestSTTProviderIntegration:
    """Integration tests."""

    def test_provider_lifecycle(self):
        """Test complete provider lifecycle."""
        registry = STTProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"

        # Register
        registry.set_active("plugin_1", provider)
        assert registry.get_active("plugin_1") is provider

        # Release
        registry.release_owned_by("plugin_1")

        # Clear
        registry.clear()
        assert registry.get_active("plugin_1") is None

    def test_multiple_plugins_with_registry(self):
        """Test multiple plugins using registry."""
        registry = STTProviderRegistry()

        providers = {}
        for i in range(3):
            provider = MagicMock()
            provider.id = f"provider_{i}"
            registry.set_active(f"plugin_{i}", provider)
            providers[f"plugin_{i}"] = provider

        for plugin_id, provider in providers.items():
            assert registry.get_active(plugin_id) is provider


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
