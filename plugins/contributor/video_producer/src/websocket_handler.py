"""WebSocket handler for live video production progress streaming."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional
import threading

try:
    from fastapi import WebSocket
except ImportError:
    WebSocket = None

logger = logging.getLogger(__name__)


class VideoProgressManager:
    """Manages WebSocket connections for live job progress updates."""

    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.lock = threading.Lock()
        self.progress_history: Dict[str, list] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        """Register a WebSocket client for a job."""
        if not websocket:
            return

        await websocket.accept()

        with self.lock:
            if job_id not in self.connections:
                self.connections[job_id] = set()
            self.connections[job_id].add(websocket)

        logger.info(f"[{job_id}] WebSocket client connected ({len(self.connections[job_id])} total)")

        # Send initial message
        await self._send_to_websocket(
            websocket,
            {
                "type": "connected",
                "job_id": job_id,
                "timestamp": datetime.now().isoformat()
            }
        )

    async def disconnect(self, job_id: str, websocket: WebSocket):
        """Unregister a WebSocket client."""
        with self.lock:
            if job_id in self.connections:
                self.connections[job_id].discard(websocket)
                if not self.connections[job_id]:
                    del self.connections[job_id]
                    logger.info(f"[{job_id}] Last WebSocket client disconnected")

    async def broadcast_progress(
        self,
        job_id: str,
        status: str,
        percent: int,
        message: str = None,
        error: str = None
    ):
        """Broadcast progress to all connected clients for a job."""
        event = {
            "type": "progress",
            "job_id": job_id,
            "status": status,
            "percent": percent,
            "message": message,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }

        # Store in history
        with self.lock:
            if job_id not in self.progress_history:
                self.progress_history[job_id] = []
            self.progress_history[job_id].append(event)
            # Keep only last 100 events per job
            if len(self.progress_history[job_id]) > 100:
                self.progress_history[job_id] = self.progress_history[job_id][-100:]

        # Broadcast to all connected clients
        with self.lock:
            if job_id not in self.connections:
                logger.debug(f"[{job_id}] No WebSocket clients for progress event")
                return

            websockets = list(self.connections[job_id])

        # Send to each client (non-blocking)
        for websocket in websockets:
            asyncio.create_task(self._send_to_websocket(websocket, event))

    async def _send_to_websocket(self, websocket: WebSocket, data: dict):
        """Send JSON data to a WebSocket (with error handling)."""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.warning(f"WebSocket send error: {e}")
            # Client disconnected; will be cleaned up on next connection attempt

    def get_progress_history(self, job_id: str, limit: int = 50) -> list:
        """Get progress history for a job."""
        with self.lock:
            history = self.progress_history.get(job_id, [])
            return history[-limit:] if history else []

    def get_connected_clients_count(self, job_id: str) -> int:
        """Get number of connected clients for a job."""
        with self.lock:
            return len(self.connections.get(job_id, set()))

    async def broadcast_completion(self, job_id: str, success: bool, video_path: str = None):
        """Broadcast job completion event."""
        event = {
            "type": "completion",
            "job_id": job_id,
            "success": success,
            "video_path": video_path,
            "timestamp": datetime.now().isoformat()
        }

        with self.lock:
            if job_id in self.connections:
                websockets = list(self.connections[job_id])
            else:
                websockets = []

        for websocket in websockets:
            asyncio.create_task(self._send_to_websocket(websocket, event))

        logger.info(f"[{job_id}] Completion broadcast to {len(websockets)} clients")


# Global progress manager instance
_progress_manager: Optional[VideoProgressManager] = None
_manager_lock = threading.Lock()


def get_progress_manager() -> VideoProgressManager:
    """Get or create global progress manager instance (singleton)."""
    global _progress_manager

    if _progress_manager is None:
        with _manager_lock:
            if _progress_manager is None:
                _progress_manager = VideoProgressManager()
                logger.info("VideoProgressManager initialized")

    return _progress_manager


def reset_progress_manager():
    """Reset global progress manager (for testing)."""
    global _progress_manager
    _progress_manager = None
