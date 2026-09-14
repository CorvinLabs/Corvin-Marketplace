"""Workers for Video Producer Plugin."""

from typing import Protocol, Any


class WorkerProtocol(Protocol):
    """Contract all workers must implement."""

    @property
    def name(self) -> str:
        """Worker identifier."""
        ...

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute worker task.

        Never raises unhandled exceptions (error handling is mandatory).
        Should raise WorkerError with fallback info on failure.
        """
        ...


__all__ = ["WorkerProtocol"]
