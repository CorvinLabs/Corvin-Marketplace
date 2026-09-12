"""Video Producer Plugin — Task-Orchestration UI for Corvin Skills 2.0."""

# Support both relative and absolute imports
try:
    from models import Scene, Storyboard, VideoJob, VideoOutput
    from storage import VideoStorage, get_storage
except ImportError:
    from .models import Scene, Storyboard, VideoJob, VideoOutput
    from .storage import VideoStorage, get_storage

__all__ = [
    "Scene",
    "Storyboard", 
    "VideoJob",
    "VideoOutput",
    "VideoStorage",
    "get_storage"
]
