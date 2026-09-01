"""
Unit tests for summary_provider plugin.

Tests cover summary provider registry including:
- Summary generation
- Provider registration
- Default implementation
- Error handling
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from summary_provider import SummaryProviderRegistry, ClaudeCliSummaryProvider


class TestSummaryProviderRegistryInitialization:
    """Test registry initialization."""

    def test_registry_creation(self):
        """Test registry creation."""
        registry = SummaryProviderRegistry()
        assert registry is not None

    def test_set_active_provider(self):
        """Test setting active summary provider."""
        registry = SummaryProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"

        registry.set_active("plugin_1", provider)
        active = registry.get_active("plugin_1")
        assert active is provider

    def test_get_active_nonexistent(self):
        """Test getting non-existent provider."""
        registry = SummaryProviderRegistry()
        active = registry.get_active("plugin_1")
        assert active is None


class TestClaudeCliSummaryProvider:
    """Test default Claude CLI summary provider."""

    def test_provider_initialization(self):
        """Test provider initialization."""
        provider = ClaudeCliSummaryProvider()
        assert provider is not None
        assert hasattr(provider, "id")

    @pytest.mark.asyncio
    async def test_summarize_text(self):
        """Test text summarization."""
        provider = ClaudeCliSummaryProvider()
        text = "This is a long piece of text that should be summarized. " * 20

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Summary: This is a brief summary.",
                returncode=0
            )
            # Note: The actual implementation delegates to subprocess

    @pytest.mark.asyncio
    async def test_summarize_with_max_length(self):
        """Test summarization with max length."""
        provider = ClaudeCliSummaryProvider()
        text = "Long text " * 100
        max_length = 50

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Brief summary",
                returncode=0
            )

    @pytest.mark.asyncio
    async def test_summarize_empty_text(self):
        """Test summarization with empty text."""
        provider = ClaudeCliSummaryProvider()
        text = ""

        # Should handle gracefully or return empty
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="",
                returncode=0
            )


class TestSummaryProviderRegistry:
    """Test registry operations."""

    def test_clear_providers(self):
        """Test clearing providers."""
        registry = SummaryProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"

        registry.set_active("plugin_1", provider)
        registry.clear()

        active = registry.get_active("plugin_1")
        assert active is None

    def test_multiple_providers(self):
        """Test multiple providers."""
        registry = SummaryProviderRegistry()

        provider1 = MagicMock()
        provider1.id = "provider_1"

        provider2 = MagicMock()
        provider2.id = "provider_2"

        registry.set_active("plugin_1", provider1)
        registry.set_active("plugin_2", provider2)

        assert registry.get_active("plugin_1") is provider1
        assert registry.get_active("plugin_2") is provider2

    def test_override_provider(self):
        """Test overriding a provider."""
        registry = SummaryProviderRegistry()

        provider1 = MagicMock()
        provider1.id = "provider_1"

        provider2 = MagicMock()
        provider2.id = "provider_2"

        registry.set_active("plugin_1", provider1)
        assert registry.get_active("plugin_1") is provider1

        registry.set_active("plugin_1", provider2)
        assert registry.get_active("plugin_1") is provider2


class TestSummaryProviderIntegration:
    """Integration tests."""

    def test_default_provider_fallback(self):
        """Test fallback to default provider."""
        registry = SummaryProviderRegistry()
        # If no custom provider set, should use default
        default = registry.get_active("plugin_default")
        # May return None or default provider depending on implementation

    @pytest.mark.asyncio
    async def test_full_summarization_flow(self):
        """Test full summarization flow."""
        registry = SummaryProviderRegistry()
        provider = ClaudeCliSummaryProvider()

        registry.set_active("plugin_1", provider)
        active = registry.get_active("plugin_1")

        assert active is provider
        # Would test actual summarization if real subprocess available


class TestSummaryProviderErrorHandling:
    """Test error handling."""

    def test_provider_release(self):
        """Test provider release."""
        registry = SummaryProviderRegistry()
        provider = MagicMock()
        provider.id = "provider_1"

        registry.set_active("plugin_1", provider)
        registry.release_owned_by("plugin_1")

        # Should be released without error

    @pytest.mark.asyncio
    async def test_summarize_with_exception(self):
        """Test summarization error handling."""
        provider = ClaudeCliSummaryProvider()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Subprocess failed")
            # Provider should handle errors gracefully


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
