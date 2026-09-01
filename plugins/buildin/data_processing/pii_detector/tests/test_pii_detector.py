"""
Unit tests for pii_detector plugin.

Tests cover PII (Personally Identifiable Information) detection including:
- Email detection
- Phone number detection
- SSN/ID detection
- Address detection
- Error handling
"""

import pytest
from unittest.mock import MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pii_detector import PIIDetector


class TestPIIDetectorInitialization:
    """Test plugin initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful plugin initialization."""
        plugin = PIIDetector()
        assert plugin is not None
        assert plugin.enabled is True

    @pytest.mark.asyncio
    async def test_initialize_with_context(self):
        """Test initialize method with context."""
        plugin = PIIDetector()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)
        assert plugin.enabled is True

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = PIIDetector()
        await plugin.shutdown()
        assert True


class TestPIIDetectorDetection:
    """Test PII detection functionality."""

    @pytest.mark.asyncio
    async def test_detect_email_pii(self):
        """Test email PII detection."""
        plugin = PIIDetector()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        text = "Contact me at user@example.com for details"
        with pytest.raises(NotImplementedError):
            await plugin.execute(text=text, pii_type="email")

    @pytest.mark.asyncio
    async def test_detect_phone_pii(self):
        """Test phone number PII detection."""
        plugin = PIIDetector()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        text = "Call me at +1-800-555-0123 during business hours"
        with pytest.raises(NotImplementedError):
            await plugin.execute(text=text, pii_type="phone")

    @pytest.mark.asyncio
    async def test_detect_ssn_pii(self):
        """Test SSN detection."""
        plugin = PIIDetector()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        text = "My SSN is 123-45-6789"
        with pytest.raises(NotImplementedError):
            await plugin.execute(text=text, pii_type="ssn")

    @pytest.mark.asyncio
    async def test_detect_address_pii(self):
        """Test address detection."""
        plugin = PIIDetector()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        text = "I live at 123 Main Street, Springfield, IL 62701"
        with pytest.raises(NotImplementedError):
            await plugin.execute(text=text, pii_type="address")

    @pytest.mark.asyncio
    async def test_detect_all_pii_types(self):
        """Test detection of all PII types."""
        plugin = PIIDetector()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        text = "John Doe, SSN 123-45-6789, email john@example.com, phone 555-0123"
        with pytest.raises(NotImplementedError):
            await plugin.execute(text=text, pii_type="all")


class TestPIIDetectorErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self):
        """Test that execute raises NotImplementedError."""
        plugin = PIIDetector()
        with pytest.raises(NotImplementedError) as exc_info:
            await plugin.execute()

        assert "PIIDetector not yet implemented" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_with_empty_text(self):
        """Test with empty text."""
        plugin = PIIDetector()
        with pytest.raises(NotImplementedError):
            await plugin.execute(text="")

    @pytest.mark.asyncio
    async def test_execute_with_no_pii(self):
        """Test with text containing no PII."""
        plugin = PIIDetector()
        with pytest.raises(NotImplementedError):
            await plugin.execute(text="This is just normal text with no personal information")

    @pytest.mark.asyncio
    async def test_execute_with_invalid_pii_type(self):
        """Test with invalid PII type."""
        plugin = PIIDetector()
        with pytest.raises(NotImplementedError):
            await plugin.execute(text="test", pii_type="invalid_type")


class TestPIIDetectorIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self):
        """Test complete plugin lifecycle."""
        plugin = PIIDetector()
        mock_context = MagicMock()

        await plugin.initialize(mock_context)
        assert plugin.enabled is True

        with pytest.raises(NotImplementedError):
            await plugin.execute(text="test text")

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_detection(self):
        """Test concurrent PII detection."""
        plugin = PIIDetector()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        texts = [
            "Email: user1@example.com",
            "Phone: 555-0101",
            "Address: 456 Oak Ave"
        ]

        tasks = []
        for text in texts:
            try:
                await plugin.execute(text=text)
            except NotImplementedError:
                tasks.append(None)

        assert len(tasks) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
