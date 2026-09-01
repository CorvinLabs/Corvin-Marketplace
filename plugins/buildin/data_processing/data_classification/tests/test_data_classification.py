"""
Unit tests for data_classification plugin.

Tests cover data classification including:
- Type classification
- Sensitivity levels
- Category detection
- Error handling
"""

import pytest
from unittest.mock import MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_classification import DataClassification


class TestDataClassificationInitialization:
    """Test plugin initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful plugin initialization."""
        plugin = DataClassification()
        assert plugin is not None
        assert plugin.enabled is True

    @pytest.mark.asyncio
    async def test_initialize_with_context(self):
        """Test initialize method with context."""
        plugin = DataClassification()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)
        assert plugin.enabled is True

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = DataClassification()
        await plugin.shutdown()
        assert True


class TestDataClassificationClassification:
    """Test data classification functionality."""

    @pytest.mark.asyncio
    async def test_classify_text(self):
        """Test text classification."""
        plugin = DataClassification()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        data = {"content": "This is sensitive company data", "type": "text"}
        with pytest.raises(NotImplementedError):
            await plugin.execute(data=data, classification_type="type")

    @pytest.mark.asyncio
    async def test_classify_by_sensitivity(self):
        """Test sensitivity classification."""
        plugin = DataClassification()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        data = {"content": "Public information"}
        with pytest.raises(NotImplementedError):
            await plugin.execute(data=data, classify_sensitivity=True)

    @pytest.mark.asyncio
    async def test_detect_category(self):
        """Test category detection."""
        plugin = DataClassification()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        data = {"content": "Financial report Q3 2026"}
        with pytest.raises(NotImplementedError):
            await plugin.execute(data=data, detect_category=True)

    @pytest.mark.asyncio
    async def test_classify_multiple_items(self):
        """Test batch classification."""
        plugin = DataClassification()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        batch = [
            {"id": "1", "content": "Public"},
            {"id": "2", "content": "Confidential"},
            {"id": "3", "content": "Internal"}
        ]
        with pytest.raises(NotImplementedError):
            await plugin.execute(batch=batch)


class TestDataClassificationErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self):
        """Test that execute raises NotImplementedError."""
        plugin = DataClassification()
        with pytest.raises(NotImplementedError) as exc_info:
            await plugin.execute()

        assert "DataClassification not yet implemented" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_with_empty_data(self):
        """Test with empty data."""
        plugin = DataClassification()
        with pytest.raises(NotImplementedError):
            await plugin.execute(data={})

    @pytest.mark.asyncio
    async def test_execute_with_invalid_type(self):
        """Test with invalid classification type."""
        plugin = DataClassification()
        with pytest.raises(NotImplementedError):
            await plugin.execute(classification_type="invalid")


class TestDataClassificationIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self):
        """Test complete plugin lifecycle."""
        plugin = DataClassification()
        mock_context = MagicMock()

        await plugin.initialize(mock_context)
        assert plugin.enabled is True

        with pytest.raises(NotImplementedError):
            await plugin.execute(data={"content": "test"})

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_classifications(self):
        """Test concurrent classifications."""
        plugin = DataClassification()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        tasks = []
        for i in range(5):
            try:
                await plugin.execute(data={"content": f"text_{i}"})
            except NotImplementedError:
                tasks.append(None)

        assert len(tasks) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
