"""E2E Test: Orchestrator + Asset Analyzer Stub (WAVE 1 k=1)

Tests the orchestrator pattern with stub workers.
Verifies: phase gates, preconditions, feedback logging.

ADR-0692: Video Producer Orchestration Architecture
"""

import json
import tempfile
from pathlib import Path
import pytest
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from maestro import (
    MaestroOrchestrator,
    Precondition,
    PreconditionNotMetError,
    AnalysisIncompleteError,
)
import asset_analyzer_stub


class TestOrchestratorStub:
    """Test Maestro Orchestrator with stub workers."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def orchestrator(self, temp_project):
        """Create an orchestrator instance."""
        return MaestroOrchestrator(project_dir=str(temp_project))

    def test_orchestrator_initialization(self, orchestrator):
        """Verify orchestrator initializes with state directory."""
        assert orchestrator.state_dir.exists()
        assert orchestrator.feedback_log.parent.exists()

    def test_worker_registration(self, orchestrator):
        """Verify worker registration."""
        orchestrator.register_worker(
            name="asset_analyzer",
            module="asset_analyzer_stub",
            preconditions=[],
            depends_on=[],
        )

        assert "asset_analyzer" in orchestrator.workers
        assert orchestrator.workers["asset_analyzer"].name == "asset_analyzer"

    def test_precondition_check_missing_file(self, orchestrator, temp_project):
        """Verify precondition check fails when file is missing."""
        orchestrator.register_worker(
            name="voice_synthesizer",
            module="voice_stub",
            preconditions=[
                Precondition(path=".video-producer-state/storyboard.json", must_exist=True)
            ],
            depends_on=["asset_analyzer"],
        )

        # Try to call worker without storyboard.json
        with pytest.raises(PreconditionNotMetError):
            orchestrator._check_preconditions("voice_synthesizer")

    def test_precondition_check_success(self, orchestrator, temp_project):
        """Verify precondition check passes when file exists."""
        storyboard_file = orchestrator.state_dir / "storyboard.json"
        storyboard_file.write_text("{}")

        orchestrator.register_worker(
            name="voice_synthesizer",
            module="voice_stub",
            preconditions=[
                Precondition(path=".video-producer-state/storyboard.json", must_exist=True)
            ],
            depends_on=["asset_analyzer"],
        )

        # Precondition should pass
        assert orchestrator._check_preconditions("voice_synthesizer") is True

    def test_phase_gate_missing_analysis(self, orchestrator):
        """Verify phase gate fails when analysis.json is missing."""
        with pytest.raises(AnalysisIncompleteError):
            orchestrator._check_phase_gates()

    def test_phase_gate_analysis_not_ready(self, orchestrator):
        """Verify phase gate fails when analysis.ready_for_narration is false."""
        analysis_file = orchestrator.state_dir / "analysis.json"
        analysis_file.write_text(json.dumps({"ready_for_narration": False}))

        with pytest.raises(AnalysisIncompleteError):
            orchestrator._check_phase_gates()

    def test_phase_gate_analysis_ready(self, orchestrator):
        """Verify phase gate passes when analysis.ready_for_narration is true."""
        analysis_file = orchestrator.state_dir / "analysis.json"
        analysis_file.write_text(json.dumps({"ready_for_narration": True}))

        assert orchestrator._check_phase_gates() is True

    def test_stub_asset_analyzer(self, temp_project):
        """Verify stub asset analyzer creates analysis.json."""
        state_dir = temp_project / ".video-producer-state"
        state_dir.mkdir()

        result = asset_analyzer_stub.execute(
            {
                "ppt_file": "test.pptx",
                "output_dir": str(state_dir),
            },
            state_dir,
        )

        # Verify output
        assert result["ready_for_narration"] is True
        assert "sections" in result
        assert len(result["sections"]) >= 2

        # Verify analysis.json was written
        analysis_file = state_dir / "analysis.json"
        assert analysis_file.exists()

        # Verify content
        analysis = json.loads(analysis_file.read_text())
        assert analysis["ready_for_narration"] is True

    def test_feedback_emission(self, orchestrator):
        """Verify feedback event logging."""
        orchestrator.emit_feedback(
            scene_id="s1",
            worker="asset_analyzer",
            feedback="content_sourced_correctly",
            quality_score=0.95,
        )

        # Verify feedback was logged
        assert orchestrator.feedback_log.exists()
        lines = orchestrator.feedback_log.read_text().strip().split("\n")
        assert len(lines) >= 1

        # Verify first event
        event = json.loads(lines[0])
        assert event["scene_id"] == "s1"
        assert event["worker"] == "asset_analyzer"
        assert event["quality_score"] == 0.95

    def test_execution_logging(self, orchestrator):
        """Verify execution event logging."""
        orchestrator._log_execution({
            "timestamp": "2026-09-14T00:00:00Z",
            "worker": "test_worker",
            "status": "started",
        })

        assert orchestrator.execution_log.exists()
        event = json.loads(orchestrator.execution_log.read_text().strip())
        assert event["worker"] == "test_worker"
        assert event["status"] == "started"

    def test_storyboard_generation(self, orchestrator):
        """Verify storyboard generation from analysis.json."""
        analysis = {
            "ready_for_narration": True,
            "sections": [
                {"title": "Introduction"},
                {"title": "Features"},
            ],
        }

        storyboard = orchestrator._generate_storyboard(analysis)

        # Verify storyboard structure
        assert "title" in storyboard
        assert "scenes" in storyboard
        assert len(storyboard["scenes"]) >= 1

        # Verify first scene is sourced from analysis (not invented)
        first_scene = storyboard["scenes"][0]
        assert "narration" in first_scene
        # Narration should come from analysis, not be made up
        assert any(
            analysis["sections"][0].get("title", "") in first_scene.get("narration", "")
            for _ in [None]
        )

    def test_orchestrator_full_pipeline_stub(self, orchestrator, temp_project):
        """E2E test: orchestrator -> asset_analyzer stub -> phase gate -> storyboard."""
        # Register stub worker
        orchestrator.register_worker(
            name="asset_analyzer",
            module="asset_analyzer_stub",
            preconditions=[],
            depends_on=[],
        )

        # Call asset_analyzer stub (this will create analysis.json)
        analysis = orchestrator.call_worker(
            "asset_analyzer",
            {
                "ppt_file": "test.pptx",
                "output_dir": str(orchestrator.state_dir),
            },
        )

        # Verify analysis.json was created
        assert (orchestrator.state_dir / "analysis.json").exists()

        # Verify phase gate passes
        assert orchestrator._check_phase_gates() is True

        # Verify storyboard can be generated
        storyboard = orchestrator._generate_storyboard(analysis)
        assert storyboard is not None
        assert len(storyboard["scenes"]) > 0

        # Verify execution was logged
        assert orchestrator.execution_log.exists()


class TestWAVE1Constraints:
    """Test WAVE 1 load-bearing constraints."""

    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield MaestroOrchestrator(project_dir=str(tmpdir))

    def test_constraint_phase_2_mandatory(self, orchestrator):
        """Constraint: Phase 2 (asset analysis) is mandatory."""
        # Without analysis.json, phase gate should fail
        with pytest.raises(AnalysisIncompleteError):
            orchestrator._check_phase_gates()

    def test_constraint_preconditions_hard(self, orchestrator):
        """Constraint: Preconditions are hard (enforce sequential execution)."""
        orchestrator.register_worker(
            name="worker_b",
            module="stub",
            preconditions=[
                Precondition(path=".video-producer-state/required_input.json", must_exist=True)
            ],
            depends_on=["worker_a"],
        )

        # Calling worker_b without precondition should fail
        with pytest.raises(PreconditionNotMetError):
            orchestrator._check_preconditions("worker_b")

    def test_constraint_feedback_per_scene(self, orchestrator):
        """Constraint: Per-scene feedback for learning loop (ADR-0314)."""
        # Emit per-scene feedback
        orchestrator.emit_feedback(
            scene_id="s5",
            worker="voice_synthesizer",
            feedback="narration_too_fast",
            quality_score=0.65,
        )

        # Verify feedback includes scene_id (not global)
        lines = orchestrator.feedback_log.read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert "scene_id" in event
        assert event["scene_id"] == "s5"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
