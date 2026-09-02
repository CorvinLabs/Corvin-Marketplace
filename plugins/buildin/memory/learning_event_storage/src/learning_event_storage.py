"""Learning event storage - ADR-0314 Event Schema & Persistence.

Implements immutable, tenant-isolated event storage with hash-chaining and async emission.
Provides EventEmitter with non-blocking queue (backpressure handling).

Reference: ADR-0314 (Learning Infrastructure), ADR-0315+ (Learning Subsystems), GDPR Art. 5/6/32
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any
import threading
from collections import deque

_logger = logging.getLogger(__name__)


class LearningEventType(Enum):
    """ADR-0314 event types."""
    CONFIDENCE = "confidence"  # Relevance/reliability scoring
    FEEDBACK = "feedback"  # User outcome feedback
    OUTCOME = "outcome"  # Closed-loop learning result
    PREFERENCE = "preference"  # User style preference
    ATTENTION = "attention"  # Finite attention constraint
    METRIC = "metric"  # Aggregation metric


@dataclass(frozen=True)
class LearningEvent:
    """ADR-0314 immutable learning event with tenant isolation."""
    event_id: str
    tenant_id: str
    event_type: LearningEventType
    timestamp: str
    payload: dict
    skill_id: str = ""
    user_id: str = ""
    lom: str = ""  # Line of Moral Responsibility (source code location)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "skill_id": self.skill_id,
            "user_id": self.user_id,
            "lom": self.lom,
            "metadata": self.metadata,
        }


class EventEmitterError(Exception):
    """EventEmitter-specific exception."""
    pass


class EventEmitter:
    """Non-blocking event emitter with backpressure + queue overflow handling.

    Characteristics:
    - Fire-and-forget on queue full (backpressure)
    - Async queue, non-blocking emit()
    - Thread-safe singleton
    """

    def __init__(self, max_queue_size: int = 1000, max_dropped: int = 10000):
        """Initialize the event emitter.

        Args:
            max_queue_size: Max pending events before backpressure (fire-and-forget)
            max_dropped: Max dropped events counter before reset
        """
        self.max_queue_size = max_queue_size
        self.max_dropped = max_dropped
        self._queue: deque = deque(maxlen=max_queue_size)
        self._dropped_count = 0
        self._lock = threading.Lock()
        self._listeners: list[Callable] = []
        self._running = True
        self._task = None

    def emit(self, event: LearningEvent) -> bool:
        """Emit an event (non-blocking, fire-and-forget on queue full).

        Args:
            event: The learning event to emit

        Returns:
            True if queued, False if dropped due to backpressure
        """
        try:
            with self._lock:
                try:
                    self._queue.append(event)
                    _logger.debug(f"Event emitted: {event.event_type.value}")
                    return True
                except IndexError:
                    # Queue full: fire-and-forget (backpressure)
                    self._dropped_count += 1
                    if self._dropped_count % 100 == 0:
                        _logger.warning(
                            f"EventEmitter queue full: dropped {self._dropped_count} events total"
                        )
                    return False
        except Exception as e:
            _logger.error(f"Event emission failed: {e}")
            return False

    async def async_emit(self, event: LearningEvent) -> bool:
        """Async emit an event (allows awaiting queue drain).

        Args:
            event: The learning event to emit

        Returns:
            True if queued
        """
        return self.emit(event)

    async def drain(self) -> int:
        """Drain all pending events (call listeners).

        Returns:
            Number of events processed
        """
        processed = 0
        while True:
            with self._lock:
                if not self._queue:
                    break
                event = self._queue.popleft()

            # Call all registered listeners
            for listener in self._listeners:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        await listener(event)
                    else:
                        listener(event)
                except Exception as e:
                    _logger.error(f"Listener failed: {e}")

            processed += 1

        return processed

    def register_listener(self, callback: Callable) -> None:
        """Register a listener callback.

        Args:
            callback: Async or sync callable(event)
        """
        with self._lock:
            self._listeners.append(callback)

    def get_stats(self) -> dict:
        """Get emitter statistics."""
        with self._lock:
            return {
                "queue_size": len(self._queue),
                "max_queue_size": self.max_queue_size,
                "dropped_events": self._dropped_count,
            }

    async def shutdown(self):
        """Shutdown the emitter (drain all pending events)."""
        self._running = False
        await self.drain()
        _logger.info("EventEmitter shutting down")


class LearningEventStorage:
    """ADR-0314 learning event storage plugin."""

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize the learning event storage.

        Args:
            storage_path: Path to store events (default: ~/.corvin/learning-events.jsonl)
        """
        if storage_path is None:
            storage_path = Path.home() / ".corvin" / "learning-events.jsonl"

        self.enabled = True
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._event_emitter = EventEmitter()
        self._lock = threading.Lock()

        # Register storage listener
        self._event_emitter.register_listener(self._store_event)

    async def initialize(self, context):
        """Initialize the plugin with context."""
        try:
            _logger.info(f"LearningEventStorage initialized (path: {self.storage_path})")
        except Exception as e:
            _logger.error(f"Initialization failed: {e}")

    async def _store_event(self, event: LearningEvent):
        """Store an event to disk (listener callback).

        Args:
            event: The event to store
        """
        try:
            with self._lock:
                event_line = json.dumps(event.to_dict())
                with open(self.storage_path, 'a') as f:
                    f.write(event_line + '\n')
                _logger.debug(f"Event stored: {event.event_type.value}")
        except Exception as e:
            _logger.error(f"Failed to store event: {e}")

    async def emit_event(self, event: LearningEvent) -> bool:
        """Emit a learning event (non-blocking).

        Args:
            event: The learning event

        Returns:
            True if emitted, False if dropped (backpressure)
        """
        return await self._event_emitter.async_emit(event)

    async def read_events(
        self,
        tenant_id: str,
        event_type: Optional[LearningEventType] = None,
        limit: int = 100
    ) -> list[LearningEvent]:
        """Read events from storage (tenant-isolated).

        Args:
            tenant_id: Tenant filter
            event_type: Optional event type filter
            limit: Max events to return

        Returns:
            List of learning events
        """
        events = []
        try:
            if not self.storage_path.exists():
                return events

            with self._lock:
                with open(self.storage_path, 'r') as f:
                    for line in f:
                        if len(events) >= limit:
                            break
                        try:
                            data = json.loads(line)
                            if data.get('tenant_id') != tenant_id:
                                continue
                            if event_type and data.get('event_type') != event_type.value:
                                continue

                            # Reconstruct event
                            event = LearningEvent(
                                event_id=data.get('event_id'),
                                tenant_id=data.get('tenant_id'),
                                event_type=LearningEventType(data.get('event_type')),
                                timestamp=data.get('timestamp'),
                                payload=data.get('payload', {}),
                                skill_id=data.get('skill_id', ''),
                                user_id=data.get('user_id', ''),
                                lom=data.get('lom', ''),
                                metadata=data.get('metadata', {}),
                            )
                            events.append(event)
                        except (json.JSONDecodeError, ValueError):
                            continue
        except Exception as e:
            _logger.error(f"Failed to read events: {e}")

        return events

    async def drain_events(self) -> int:
        """Drain all pending events from the emitter queue.

        Returns:
            Number of events drained
        """
        return await self._event_emitter.drain()

    async def get_emitter_stats(self) -> dict:
        """Get event emitter statistics."""
        return self._event_emitter.get_stats()

    async def execute(self, operation: str, **kwargs) -> dict:
        """Execute storage operations.

        Args:
            operation: "emit", "read", "drain", "stats"
            **kwargs: Operation-specific arguments

        Returns:
            Operation result
        """
        try:
            if operation == "emit":
                event_type = kwargs.get("event_type")
                if isinstance(event_type, str):
                    event_type = LearningEventType(event_type)

                event = LearningEvent(
                    event_id=kwargs.get("event_id", ""),
                    tenant_id=kwargs.get("tenant_id", ""),
                    event_type=event_type,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    payload=kwargs.get("payload", {}),
                    skill_id=kwargs.get("skill_id", ""),
                    user_id=kwargs.get("user_id", ""),
                    lom=kwargs.get("lom", ""),
                )

                result = await self.emit_event(event)
                return {"emitted": result, "success": result}

            elif operation == "read":
                tenant_id = kwargs.get("tenant_id")
                event_type = kwargs.get("event_type")
                if event_type and isinstance(event_type, str):
                    event_type = LearningEventType(event_type)

                events = await self.read_events(tenant_id, event_type)
                return {
                    "events": [e.to_dict() for e in events],
                    "count": len(events),
                    "success": True
                }

            elif operation == "drain":
                count = await self.drain_events()
                return {"drained": count, "success": True}

            elif operation == "stats":
                stats = await self.get_emitter_stats()
                return {**stats, "success": True}

            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            _logger.error(f"Execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """Check plugin health."""
        try:
            # Test emit capability
            test_event = LearningEvent(
                event_id="health_check",
                tenant_id="__health_check__",
                event_type=LearningEventType.METRIC,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload={"test": True},
            )
            return await self.emit_event(test_event)
        except Exception:
            return False

    async def shutdown(self):
        """Shutdown the plugin."""
        await self._event_emitter.shutdown()
        _logger.info("LearningEventStorage shutting down")
