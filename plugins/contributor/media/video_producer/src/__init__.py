"""Video Producer Plugin — Task-Orchestration UI for Corvin Skills 2.0."""

# Package-relative first: an unrelated top-level module named "models" or
# "storage" elsewhere in the host process must never be picked up instead.
try:
    from .models import Scene, Storyboard, VideoJob, VideoOutput
    from .storage import VideoStorage, get_storage
except ImportError:  # standalone script use (no package context)
    from models import Scene, Storyboard, VideoJob, VideoOutput
    from storage import VideoStorage, get_storage

__all__ = [
    "Scene",
    "Storyboard", 
    "VideoJob",
    "VideoOutput",
    "VideoStorage",
    "get_storage"
]
