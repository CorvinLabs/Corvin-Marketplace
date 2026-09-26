"""Video Producer Skill 2.0: Orchestrated video production system.

Main components:
- Orchestrator: 7-phase pipeline (analysis -> storyboard -> workers ->
  assembly -> YouTube upload -> feedback -> learning optimization)
- AssetAnalyzer: Deep-read asset analysis (worker)
- StoryboardGenerator: LLM-constrained storyboard creation
- BlenderHeadlessOrchestrator: real 3D-scene rendering via headless Blender
- WorkerRegistry/WorkerSkillBase: reusable worker-skill contract

Note: ``blender_scene_kit`` is intentionally NOT imported here -- it needs
``bpy`` (Blender's embedded interpreter only) and would break every
non-Blender caller of this package. Import it only from inside a running
Blender process (see ``blender_cli.py`` / ``blender_orchestrator.py``).
"""

from .orchestrator import VideoProducerOrchestrator
from .storyboard_generator import StoryboardGenerator
from .types import AssetAnalysisResult, Storyboard, Scene, FactualClaim, Contradiction
from .exceptions import (
    VideoProducerError,
    AssetIngestionError,
    AnalysisIncompleteError,
    AnalysisGateFailedError,
)
from .worker_base import WorkerManifest, WorkerResult, WorkerSkillBase, WorkerRegistry
from .blender_orchestrator import BlenderHeadlessOrchestrator, RenderConfig

__all__ = [
    "VideoProducerOrchestrator",
    "StoryboardGenerator",
    "AssetAnalysisResult",
    "Storyboard",
    "Scene",
    "FactualClaim",
    "Contradiction",
    "VideoProducerError",
    "AssetIngestionError",
    "AnalysisIncompleteError",
    "AnalysisGateFailedError",
    "WorkerManifest",
    "WorkerResult",
    "WorkerSkillBase",
    "WorkerRegistry",
    "BlenderHeadlessOrchestrator",
    "RenderConfig",
]
