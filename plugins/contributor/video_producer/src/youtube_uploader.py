"""YouTube upload integration using ADR-0695 YouTube Uploader Skill."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class YouTubeUploadManager:
    """Manages YouTube uploads via ADR-0695 async skill."""

    def __init__(self):
        self.upload_tasks: Dict[str, Dict[str, Any]] = {}

    async def enqueue_upload(
        self,
        job_id: str,
        video_path: str,
        srt_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enqueue a video for YouTube upload (async, non-blocking).

        Returns immediately with task_id.
        Actual upload happens in background.

        Integrates with ADR-0695 YouTube Uploader Skill.
        """

        if not metadata:
            metadata = {}

        # Prepare upload payload
        upload_request = {
            "video_path": video_path,
            "srt_path": srt_path,
            "metadata": {
                "title": metadata.get("title", f"Video {job_id}"),
                "description": metadata.get("description", "Created with Corvin Video Producer"),
                "tags": metadata.get("tags", ["corvin", "video"]),
                "privacy_status": metadata.get("privacy_status", "public"),
                "playlist_id": metadata.get("playlist_id"),
            }
        }

        # Phase 3.1: Call ADR-0695 YouTube Uploader Skill
        # result = await call_skill(
        #     "worker.youtube_uploader",
        #     **upload_request
        # )

        # Mock result for Phase 3.0 (until Skill 2.0 integration)
        task_id = f"yt_upload_{job_id[:8]}"

        self.upload_tasks[task_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "video_path": video_path,
            "srt_path": srt_path,
            "metadata": metadata,
        }

        logger.info(f"[{job_id}] YouTube upload queued: {task_id}")

        return {
            "task_id": task_id,
            "status": "queued",
            "video_path": video_path,
            "message": "Upload queued. Check status via Task API."
        }

    async def get_upload_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a YouTube upload task."""

        if task_id not in self.upload_tasks:
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": "Upload task not found"
            }

        task = self.upload_tasks[task_id]

        # Phase 3.1: Poll actual YouTube Uploader Skill via Task API
        # actual_status = await get_task_status(task_id)

        return {
            "task_id": task_id,
            "job_id": task[" job_id"],
            "status": task["status"],
            "created_at": task["created_at"],
            "progress_percent": task.get("progress_percent", 0),
            "estimated_time_remaining_seconds": task.get("eta_seconds"),
            "error": task.get("error"),
        }

    async def cancel_upload(self, task_id: str) -> Dict[str, Any]:
        """Cancel a queued upload."""

        if task_id not in self.upload_tasks:
            return {"success": False, "error": "Task not found"}

        task = self.upload_tasks[task_id]

        if task["status"] not in ["queued", "uploading"]:
            return {
                "success": False,
                "error": f"Cannot cancel task in status: {task['status']}"
            }

        task["status"] = "cancelled"
        task["cancelled_at"] = datetime.now().isoformat()

        logger.info(f"[{task['job_id']}] Upload cancelled: {task_id}")

        return {"success": True, "task_id": task_id}


# Global upload manager instance
_upload_manager: Optional[YouTubeUploadManager] = None


def get_upload_manager() -> YouTubeUploadManager:
    """Get or create global upload manager instance."""
    global _upload_manager
    if _upload_manager is None:
        _upload_manager = YouTubeUploadManager()
    return _upload_manager
