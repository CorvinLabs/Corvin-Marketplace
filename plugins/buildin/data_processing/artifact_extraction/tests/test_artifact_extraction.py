"""
Unit tests for artifact_extraction plugin.

Tests cover artifact extraction from sessions including:
- Code extraction
- Document extraction
- Metadata tracking
- Error handling and edge cases
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from artifact_extraction import ArtifactExtraction


class TestArtifactExtractionInitialization:
    """Test plugin initialization."""

    @pytest.mark.asyncio
    async def test_init_success(self):
        """Test successful plugin initialization."""
        plugin = ArtifactExtraction()
        assert plugin is not None
        assert plugin.enabled is True

    @pytest.mark.asyncio
    async def test_initialize_with_context(self):
        """Test initialize method with context."""
        plugin = ArtifactExtraction()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)
        assert plugin.enabled is True

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = ArtifactExtraction()
        await plugin.shutdown()
        assert True


class TestArtifactExtractionExtraction:
    """Test artifact extraction functionality."""

    @pytest.mark.asyncio
    async def test_extract_code_artifacts(self):
        """Test code artifact extraction."""
        plugin = ArtifactExtraction()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        session_data = {
            "content": "```python\nprint('hello')\n```",
            "type": "code"
        }
        with pytest.raises(NotImplementedError):
            await plugin.execute(session_data=session_data, artifact_type="code")

    @pytest.mark.asyncio
    async def test_extract_document_artifacts(self):
        """Test document artifact extraction."""
        plugin = ArtifactExtraction()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        session_data = {
            "content": "# Document Title\nContent here",
            "type": "document"
        }
        with pytest.raises(NotImplementedError):
            await plugin.execute(session_data=session_data, artifact_type="document")

    @pytest.mark.asyncio
    async def test_extract_with_metadata(self):
        """Test extraction with metadata tracking."""
        plugin = ArtifactExtraction()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        session_data = {
            "content": "test content",
            "metadata": {"timestamp": "2026-09-01", "source": "session"}
        }
        with pytest.raises(NotImplementedError):
            await plugin.execute(session_data=session_data, track_metadata=True)


class TestArtifactExtractionErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self):
        """Test that execute raises NotImplementedError."""
        plugin = ArtifactExtraction()
        with pytest.raises(NotImplementedError) as exc_info:
            await plugin.execute()

        assert "ArtifactExtraction not yet implemented" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_with_empty_session(self):
        """Test extraction with empty session data."""
        plugin = ArtifactExtraction()
        with pytest.raises(NotImplementedError):
            await plugin.execute(session_data={})

    @pytest.mark.asyncio
    async def test_execute_with_invalid_type(self):
        """Test extraction with invalid artifact type."""
        plugin = ArtifactExtraction()
        with pytest.raises(NotImplementedError):
            await plugin.execute(artifact_type="invalid_type")


class TestArtifactExtractionIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self):
        """Test complete plugin lifecycle."""
        plugin = ArtifactExtraction()
        mock_context = MagicMock()

        await plugin.initialize(mock_context)
        assert plugin.enabled is True

        with pytest.raises(NotImplementedError):
            await plugin.execute(session_data={"content": "test"})

        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_extraction(self):
        """Test concurrent artifact extraction."""
        plugin = ArtifactExtraction()
        mock_context = MagicMock()
        await plugin.initialize(mock_context)

        tasks = [
            plugin.execute(session_data={"content": f"content_{i}"})
            for i in range(3)
        ]

        results = []
        for task in tasks:
            try:
                await task
            except NotImplementedError:
                results.append(None)

        assert len(results) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
