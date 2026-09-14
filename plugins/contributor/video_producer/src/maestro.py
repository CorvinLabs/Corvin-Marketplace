"""Maestro Orchestrator for Video Producer Skill 2.0 (WAVE 1)

Orchestrates 5 Worker Skills with phase gates and feedback loops.

Load-bearing constraints:
- Phase 2 (asset analysis) is mandatory
- Preconditions are hard (enforce sequential phases)
- Per-scene feedback drives learning (ADR-0314)
- YouTube async (non-blocking, separate Skill)

ADR-0692: Video Producer Orchestration Architecture
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Precondition:
    """Worker precondition (file must exist, max age, etc.)"""
    path: str
    must_exist: bool = True
    max_age_hours: Optional[int] = None


@dataclass
class WorkerConfig:
    """Configuration for a Worker Skill."""
    name: str
    module: str
    preconditions: List[Precondition]
    depends_on: List[str]  # e.g., ["asset_analyzer"] means analyze before voice


@dataclass
class SceneRenderedEvent:
    """Per-scene feedback event (ADR-0314 compatible)."""
    timestamp: str
    scene_id: str
    worker: str
    feedback: str  # e.g., "screenshot_cropped_too_tight"
    quality_score: float  # 0.0–1.0
    metadata: Dict = None

    def to_dict(self):
        return asdict(self)


class MaestroOrchestrator:
    """Coordinates Video Producer Workers with phase gates and feedback (WAVE 1).

    Enforces:
    - Phase 2 (asset analysis) mandatory
    - Preconditions hard (phase gates)
    - Per-scene feedback for learning
    """

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir)
        self.state_dir = self.project_dir / ".video-producer-state"
        self.state_dir.mkdir(exist_ok=True)

        # Worker registry
        self.workers: Dict[str, WorkerConfig] = {}
        self.feedback_log = self.state_dir / "feedback.jsonl"
        self.execution_log = self.state_dir / "execution.jsonl"

    def register_worker(
        self,
        name: str,
        module: str,
        preconditions: List[Precondition],
        depends_on: List[str],
    ):
        """Register a Worker Skill with preconditions."""
        self.workers[name] = WorkerConfig(
            name=name,
            module=module,
            preconditions=preconditions,
            depends_on=depends_on,
        )
        logger.info(f"Registered Worker: {name}")

    def _check_preconditions(self, worker_name: str) -> bool:
        """Verify all preconditions for a Worker."""
        worker = self.workers.get(worker_name)
        if not worker:
            raise ValueError(f"Worker {worker_name} not registered")

        for precond in worker.preconditions:
            path = self.project_dir / precond.path
            if precond.must_exist and not path.exists():
                raise PreconditionNotMetError(
                    f"Precondition failed for {worker_name}: {precond.path} does not exist"
                )

            # Check age if specified
            if precond.max_age_hours and path.exists():
                age_hours = (datetime.utcnow().timestamp() - path.stat().st_mtime) / 3600
                if age_hours > precond.max_age_hours:
                    raise PreconditionNotMetError(
                        f"Precondition failed for {worker_name}: {precond.path} is {age_hours:.1f}h old (max {precond.max_age_hours}h)"
                    )

        return True

    def _check_phase_gates(self) -> bool:
        """Gate 1: Asset analysis must be complete before proceeding."""
        analysis_file = self.state_dir / "analysis.json"

        if not analysis_file.exists():
            raise AnalysisIncompleteError(
                "Phase 2 (Asset Analysis) not complete. "
                "Run asset_analyzer first."
            )

        try:
            with open(analysis_file) as f:
                analysis = json.load(f)

            if not analysis.get("ready_for_narration", False):
                raise AnalysisIncompleteError(
                    "Asset analysis incomplete: ready_for_narration != true"
                )

            return True
        except json.JSONDecodeError as e:
            raise AnalysisIncompleteError(f"Invalid analysis.json: {e}")

    def call_worker(
        self,
        worker_name: str,
        input_data: Dict,
    ) -> Dict:
        """Call a Worker Skill with precondition checks."""
        logger.info(f"Calling Worker: {worker_name}")

        # Check preconditions
        self._check_preconditions(worker_name)

        # Log execution
        execution_event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "worker": worker_name,
            "input_hash": hash(json.dumps(input_data, sort_keys=True)),
            "status": "started",
        }
        self._log_execution(execution_event)

        # For now, workers are imported and called directly
        # In production, these would be async via Skill 2.0 runtime
        worker = self.workers[worker_name]

        # Try importing as module name directly (for stubs)
        try:
            worker_module = __import__(worker.module)
        except ImportError:
            # If not found, try with video_producer prefix
            worker_module = __import__(f"video_producer.{worker.module}", fromlist=[worker.module])

        try:
            result = worker_module.execute(input_data, self.state_dir)
            execution_event["status"] = "success"
            self._log_execution(execution_event)
            return result
        except Exception as e:
            execution_event["status"] = "failed"
            execution_event["error"] = str(e)
            self._log_execution(execution_event)
            raise

    def emit_feedback(
        self,
        scene_id: str,
        worker: str,
        feedback: str,
        quality_score: float,
    ):
        """Emit per-scene feedback event (ADR-0314)."""
        event = SceneRenderedEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            scene_id=scene_id,
            worker=worker,
            feedback=feedback,
            quality_score=quality_score,
        )
        self._log_feedback(event)
        logger.info(f"Feedback: {scene_id} ({worker}) = {quality_score:.2f}")

    def _log_feedback(self, event: SceneRenderedEvent):
        """Append feedback to audit trail."""
        with open(self.feedback_log, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def _log_execution(self, event: Dict):
        """Append execution to audit trail."""
        with open(self.execution_log, "a") as f:
            f.write(json.dumps(event) + "\n")

    def orchestrate_video_production(
        self,
        ppt_file: str,
        console_url: str,
        output_dir: str,
    ) -> str:
        """
        Full video production pipeline (WAVE 1: orchestrator + stub workers).

        Phases:
        1. Asset Analysis (deep-read, no invention)
        2. Storyboard generation (LLM, constrained to analysis.json)
        3. Voice Synthesis (Phase 4)
        4. Screenshot Capture (Phase 4)
        5. Slide Rendering (Phase 5)
        6. Video Assembly (Phase 6–7)
        7. (Optional, async) YouTube Upload

        Returns: path to output.mp4
        """
        logger.info(f"Starting video production: {ppt_file}")

        # Phase 1: Call asset_analyzer
        logger.info("Phase 1: Asset Analysis")
        analysis = self.call_worker(
            "asset_analyzer",
            {
                "ppt_file": ppt_file,
                "output_dir": str(self.state_dir),
            },
        )

        # Gate check: analysis must be ready
        self._check_phase_gates()

        # Phase 2: Storyboard generation (LLM, constrained to analysis.json)
        logger.info("Phase 2: Storyboard Generation (constrained to analysis.json)")
        storyboard = self._generate_storyboard(analysis)

        # Phase 3–5: Parallel workers (voice, screenshots, slides)
        logger.info("Phase 3–5: Parallel worker execution")
        voice_result = self.call_worker("voice_synthesizer", storyboard)
        screenshot_result = self.call_worker(
            "screenshot_capturer",
            {"console_url": console_url, "storyboard": storyboard},
        )
        slides_result = self.call_worker(
            "slide_renderer",
            {"ppt_file": ppt_file, "storyboard": storyboard},
        )

        # Phase 6–7: Video assembly
        logger.info("Phase 6–7: Video Assembly")
        output_mp4 = self.call_worker(
            "video_assembler",
            {
                "storyboard": storyboard,
                "audio_file": voice_result.get("audio_path"),
                "screenshots_dir": screenshot_result.get("dir"),
                "slides_dir": slides_result.get("dir"),
                "output_dir": output_dir,
            },
        )

        logger.info(f"Video production complete: {output_mp4}")
        return output_mp4

    def _generate_storyboard(self, analysis: Dict) -> Dict:
        """
        Generate storyboard from analysis.json (LLM constrained).

        Load-bearing constraint: ONLY source from analysis.json, never invent.
        In production, this calls Claude with a constrained prompt.
        """
        # Stub: return fixed storyboard for k=1
        return {
            "title": "CorvinOS Overview",
            "scenes": [
                {
                    "id": "s1",
                    "title": "What is CorvinOS?",
                    "narration": analysis.get("sections", [{}])[0].get("title", "Introduction"),
                    "duration_sec": 10,
                },
            ],
        }


class PreconditionNotMetError(Exception):
    """Raised when a Worker precondition is not met."""
    pass


class AnalysisIncompleteError(Exception):
    """Raised when Phase 2 analysis is incomplete or missing."""
    pass
