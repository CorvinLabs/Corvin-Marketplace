"""Video Producer Plugin bootstrap."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .models import DesignSystem
from .quality_scorer import QualityScorer
from .quality_gates import QualityGateEnforcer

logger = logging.getLogger(__name__)


class VideoProducerPlugin:
    """Video Producer Plugin entry point.

    Orchestrates Workers to generate high-quality demo videos from storyboards.
    Enforces quality gates (DRAFT/PRODUCTION/BROADCAST).
    Integrates with learning infrastructure (ADR-0314).
    """

    plugin_id = "video-producer-orchestrator"
    version = "1.0.0"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize plugin.

        Args:
            config: Plugin configuration dict
        """
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)

        # State (initialized in bootstrap)
        self.design_system: Optional[DesignSystem] = None
        self.quality_scorer: Optional[QualityScorer] = None
        self.audit_backend = None

    async def bootstrap(self) -> None:
        """Initialize plugin (called once at boot).

        Loads design system, initializes workers, registers Skill,
        logs bootstrap event to audit trail.
        """
        self.logger.info(f"Bootstrapping {self.plugin_id} v{self.version}...")

        try:
            # 1. Load design system
            self.design_system = self._load_design_system()
            self.logger.info("Design system loaded")

            # 2. Initialize quality scorer
            self.quality_scorer = QualityScorer(self.design_system)
            self.logger.info("Quality scorer initialized")

            # 3. Verify quality gate thresholds (fail-closed)
            QualityGateEnforcer.verify_gate_thresholds()
            self.logger.info("Quality gate thresholds verified")

            # 4. Log bootstrap success
            await self._audit_event("plugin_bootstrap", {
                "plugin_id": self.plugin_id,
                "version": self.version,
                "timestamp": datetime.now().isoformat(),
                "status": "success",
                "design_system_version": self.design_system.metadata.get("version", "unknown")
            })

            self.logger.info(f"{self.plugin_id} bootstrap complete")

        except Exception as e:
            self.logger.error(f"Bootstrap failed: {e}", exc_info=True)
            await self._audit_event("plugin_bootstrap", {
                "plugin_id": self.plugin_id,
                "version": self.version,
                "timestamp": datetime.now().isoformat(),
                "status": "failed",
                "error": str(e)
            })
            raise

    async def shutdown(self) -> None:
        """Cleanup (called at unload)."""
        self.logger.info(f"Shutting down {self.plugin_id}...")
        await self._audit_event("plugin_shutdown", {
            "plugin_id": self.plugin_id,
            "timestamp": datetime.now().isoformat()
        })

    def _load_design_system(self) -> DesignSystem:
        """Load design system from JSON file.

        Returns:
            DesignSystem object

        Raises:
            FileNotFoundError if design_system.json not found
            ValueError if design system is invalid
        """
        path_str = self.config.get("design_system_path", "design_system.json")
        path = Path(path_str)

        if not path.exists():
            # Try relative to plugin directory
            plugin_dir = Path(__file__).parent.parent
            path = plugin_dir / "design_system.json"

        if not path.exists():
            raise FileNotFoundError(f"Design system not found: {path}")

        with open(path) as f:
            data = json.load(f)

        self.logger.info(f"Loaded design system from {path}")

        # Add metadata field if not present
        if "metadata" not in data:
            data["metadata"] = {}

        return DesignSystem.from_dict(data)

    async def _audit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit audit event (placeholder).

        In production, this would integrate with ADR-0314 audit backend.
        For now, just log to console.

        Args:
            event_type: Type of event (e.g., "plugin_bootstrap")
            payload: Event payload dict
        """
        event = {
            "event_type": event_type,
            "plugin_id": self.plugin_id,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
        self.logger.info(f"Audit event: {json.dumps(event, indent=2)}")

        # TODO: Wire to actual audit_backend when available
        # await self.audit_backend.write_event(event)


def get_plugin() -> VideoProducerPlugin:
    """Factory function for plugin instantiation."""
    return VideoProducerPlugin()
