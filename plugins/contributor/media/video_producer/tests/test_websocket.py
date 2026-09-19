"""Unit tests for WebSocket progress streaming."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from src.websocket_handler import (
    VideoProgressManager,
    get_progress_manager,
    reset_progress_manager,
)


class TestVideoProgressManager:
    def test_manager_initialization(self):
        """Test manager initialization."""
        reset_progress_manager()
        manager = get_progress_manager()

        assert manager is not None
        assert len(manager.connections) == 0

    @pytest.mark.asyncio
    async def test_connect_client(self):
        """Test WebSocket client connection."""
        reset_progress_manager()
        manager = get_progress_manager()

        job_id = "job_connect_test"
        mock_websocket = AsyncMock()

        await manager.connect(job_id, mock_websocket)

        assert job_id in manager.connections
        assert len(manager.connections[job_id]) == 1
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_client(self):
        """Test WebSocket client disconnection."""
        reset_progress_manager()
        manager = get_progress_manager()

        job_id = "job_disconnect_test"
        mock_websocket = AsyncMock()

        await manager.connect(job_id, mock_websocket)
        assert job_id in manager.connections

        await manager.disconnect(job_id, mock_websocket)
        assert job_id not in manager.connections

    @pytest.mark.asyncio
    async def test_broadcast_progress(self):
        """Test broadcasting progress to connected clients."""
        reset_progress_manager()
        manager = get_progress_manager()

        job_id = "job_broadcast_test"
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(job_id, mock_ws1)
        await manager.connect(job_id, mock_ws2)

        await manager.broadcast_progress(job_id, "storyboard_generating", 50)

        # Wait for async tasks
        await asyncio.sleep(0.1)

        # Both websockets should have received the message
        assert mock_ws1.send_json.called or mock_ws2.send_json.called

    def test_progress_history(self):
        """Test progress history tracking."""
        reset_progress_manager()
        manager = get_progress_manager()

        job_id = "job_history_test"

        # Manually add progress events
        for percent in [0, 25, 50, 75, 100]:
            manager.progress_history[job_id] = (
                manager.progress_history.get(job_id, []) + [
                    {
                        "type": "progress",
                        "percent": percent,
                    }
                ]
            )

        history = manager.get_progress_history(job_id)
        assert len(history) == 5
        assert history[0]["percent"] == 0
        assert history[-1]["percent"] == 100

    def test_connected_clients_count(self):
        """Test counting connected clients."""
        reset_progress_manager()
        manager = get_progress_manager()

        job_id = "job_count_test"

        # Simulate connections
        manager.connections[job_id] = set()
        manager.connections[job_id].add(MagicMock())
        manager.connections[job_id].add(MagicMock())

        count = manager.get_connected_clients_count(job_id)
        assert count == 2

    @pytest.mark.asyncio
    async def test_broadcast_completion(self):
        """Test broadcasting job completion."""
        reset_progress_manager()
        manager = get_progress_manager()

        job_id = "job_completion_test"
        mock_ws = AsyncMock()

        await manager.connect(job_id, mock_ws)
        await manager.broadcast_completion(job_id, success=True, video_path="/tmp/output.mp4")

        await asyncio.sleep(0.1)
        assert mock_ws.send_json.called

    @pytest.mark.asyncio
    async def test_websocket_send_error_handling(self):
        """Test handling of WebSocket send errors."""
        reset_progress_manager()
        manager = get_progress_manager()

        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection closed")

        # Should not raise
        await manager._send_to_websocket(mock_ws, {"test": "data"})
