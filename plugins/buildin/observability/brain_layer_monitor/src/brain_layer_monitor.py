"""
Individual Brain layer performance monitor.

Tracks per-layer:
- Execution time histograms
- Error rates & recovery
- State transitions
- Output statistics

ADR-0532: OS-Skills Architecture — Deterministic observability layer.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import deque

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier


@dataclass
class LayerState:
    """State snapshot for a single layer."""
    layer_name: str
    state: str  # "idle", "processing", "error", "blocked"
    execution_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_state_change: datetime = field(default_factory=datetime.utcnow)


class BrainLayerMonitor(DeterministicPlugin):
    """
    Per-layer Brain performance tracker.

    Monitors:
    - Individual layer latencies & errors
    - State transitions
    - Output sizes
    - Sub-millisecond overhead (<1ms)
    """

    def __init__(self):
        """Initialize the monitor."""
        self.layers: Dict[str, LayerState] = {}
        self.latency_samples: Dict[str, deque] = {}
        self.state_changes: List[Dict] = []

    def get_tier(self) -> PluginTier:
        return PluginTier.GENERAL

    def get_max_latency_ms(self) -> int:
        return 1

    async def initialize(self, context):
        """Initialize with Brain context."""
        self.context = context
        self.start_time = datetime.utcnow()

    async def on_layer_start(self, layer_name: str):
        """Record layer execution start."""
        if layer_name not in self.layers:
            self.layers[layer_name] = LayerState(layer_name=layer_name, state="idle")
            self.latency_samples[layer_name] = deque(maxlen=100)

        self.layers[layer_name].state = "processing"

    async def on_layer_complete(self, layer_name: str, latency_ms: float, error: Optional[str] = None):
        """Record layer completion."""
        if layer_name not in self.layers:
            self.layers[layer_name] = LayerState(layer_name=layer_name, state="idle")
            self.latency_samples[layer_name] = deque(maxlen=100)

        layer = self.layers[layer_name]
        layer.state = "error" if error else "idle"
        layer.execution_count += 1

        if error:
            layer.error_count += 1

        # Update latency stats
        self.latency_samples[layer_name].append(latency_ms)
        samples = self.latency_samples[layer_name]
        if samples:
            layer.avg_latency_ms = sum(samples) / len(samples)
            layer.max_latency_ms = max(samples)

        self._record_state_change(layer_name, layer.state, latency_ms, error)

    async def get_layer_status(self, layer_name: str) -> Optional[Dict]:
        """Get current status for a layer."""
        if layer_name not in self.layers:
            return None

        layer = self.layers[layer_name]
        error_rate = (layer.error_count / layer.execution_count * 100) if layer.execution_count > 0 else 0.0

        return {
            "layer": layer_name,
            "state": layer.state,
            "executions": layer.execution_count,
            "errors": layer.error_count,
            "error_rate_percent": round(error_rate, 2),
            "avg_latency_ms": round(layer.avg_latency_ms, 2),
            "max_latency_ms": round(layer.max_latency_ms, 2),
        }

    async def get_diagnostics(self) -> Dict:
        """Return all layers diagnostic snapshot (unified interface)."""
        return await self.get_all_layers_status()

    async def get_all_layers_status(self) -> Dict[str, Dict]:
        """Get status for all layers."""
        return {
            name: await self.get_layer_status(name)
            for name in self.layers.keys()
        }

    async def on_health_check(self):
        """Report health status."""
        from corvin_plugins.protocol import HealthStatus

        if not self.layers:
            return HealthStatus(ok=True, message="No layers tracked yet")

        unhealthy_layers = [
            name for name, layer in self.layers.items()
            if layer.state == "error"
        ]

        ok = len(unhealthy_layers) == 0
        message = f"Layers: {len(self.layers)}, Healthy: {len(self.layers) - len(unhealthy_layers)}"

        return HealthStatus(ok=ok, message=message)

    def _record_state_change(self, layer_name: str, new_state: str, latency_ms: float, error: Optional[str]):
        """Record a layer state change."""
        self.state_changes.append({
            "layer": layer_name,
            "state": new_state,
            "latency_ms": latency_ms,
            "error": error[:50] if error else None,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Keep only last 1000 changes
        if len(self.state_changes) > 1000:
            self.state_changes = self.state_changes[-1000:]

    async def shutdown(self):
        """Graceful shutdown."""
        pass
