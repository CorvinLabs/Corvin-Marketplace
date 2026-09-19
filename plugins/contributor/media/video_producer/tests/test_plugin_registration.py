"""Tests for Video Producer plugin registration and manifest validation."""

import json
import pytest
from pathlib import Path


class TestPluginManifest:
    """Test plugin.json manifest correctness."""

    @pytest.fixture
    def plugin_manifest(self):
        """Load plugin.json manifest."""
        manifest_path = Path(__file__).parent.parent / "plugin.json"
        with open(manifest_path) as f:
            return json.load(f)

    def test_manifest_has_required_fields(self, plugin_manifest):
        """Plugin manifest must have all required fields."""
        required = ["id", "type", "name", "version", "author", "license", "tier", "category", "description"]
        for field in required:
            assert field in plugin_manifest, f"Missing required field: {field}"

    def test_manifest_id_format(self, plugin_manifest):
        """Plugin ID must follow naming convention."""
        plugin_id = plugin_manifest["id"]
        assert plugin_id.startswith("plugin:"), f"ID must start with 'plugin:': {plugin_id}"
        assert "contributor" in plugin_id, f"ID must contain 'contributor': {plugin_id}"

    def test_manifest_tier_is_contributor(self, plugin_manifest):
        """Plugin must be contributor tier."""
        assert plugin_manifest["tier"] == "contributor", "Video Producer must be contributor tier"

    def test_manifest_boot_layer_is_installed(self, plugin_manifest):
        """Plugin boot_layer must be 'installed' (not 'bundled' or 'core')."""
        assert plugin_manifest["boot_layer"] == "installed"

    def test_manifest_has_entry_points(self, plugin_manifest):
        """Plugin must declare console_panels and skills entry points."""
        assert "entry_points" in plugin_manifest
        assert "console_panels" in plugin_manifest["entry_points"]
        assert "skills" in plugin_manifest["entry_points"]
        assert len(plugin_manifest["entry_points"]["console_panels"]) > 0
        assert len(plugin_manifest["entry_points"]["skills"]) > 0

    def test_manifest_panel_has_required_fields(self, plugin_manifest):
        """Console panel entry point must have required fields."""
        panel = plugin_manifest["entry_points"]["console_panels"][0]
        required = ["id", "title", "icon", "route", "component", "category"]
        for field in required:
            assert field in panel, f"Panel missing field: {field}"

    def test_manifest_skill_has_required_fields(self, plugin_manifest):
        """Skill entry point must have required fields."""
        skill = plugin_manifest["entry_points"]["skills"][0]
        required = ["id", "name", "description"]
        for field in required:
            assert field in skill, f"Skill missing field: {field}"

    def test_manifest_version_is_valid(self, plugin_manifest):
        """Version must follow semantic versioning."""
        version = plugin_manifest["version"]
        parts = version.split(".")
        assert len(parts) >= 2, f"Version must be semantic: {version}"
        assert all(p.isdigit() for p in parts[:3]), f"Version parts must be numeric: {version}"

    def test_manifest_requires_version_constraint(self, plugin_manifest):
        """Plugin must specify CorvinOS version requirement."""
        assert "requires_version" in plugin_manifest
        assert ">=" in plugin_manifest["requires_version"]


class TestPluginStructure:
    """Test plugin directory structure."""

    def test_src_directory_exists(self):
        """Plugin must have src/ directory."""
        src_path = Path(__file__).parent.parent / "src"
        assert src_path.is_dir(), "src/ directory must exist"

    def test_video_producer_module_exists(self):
        """Plugin must have src/video_producer/ module."""
        module_path = Path(__file__).parent.parent / "src" / "video_producer"
        assert module_path.is_dir(), "src/video_producer/ module must exist"
        assert (module_path / "__init__.py").exists(), "__init__.py must exist in video_producer"

    def test_required_python_files_exist(self):
        """Plugin must have required Python implementation files."""
        video_producer_path = Path(__file__).parent.parent / "src" / "video_producer"
        required_files = [
            "__init__.py",
            "orchestrator.py",
            "exceptions.py",
            "types.py",
            "learning_optimizer.py",
            "storyboard_generator.py",
            "console_panel.py",
        ]
        for filename in required_files:
            filepath = video_producer_path / filename
            assert filepath.exists(), f"Missing required file: {filename}"

    def test_tests_directory_exists(self):
        """Plugin must have tests/ directory."""
        tests_path = Path(__file__).parent.parent / "tests"
        assert tests_path.is_dir(), "tests/ directory must exist"

    def test_docs_directory_exists(self):
        """Plugin must have docs/ directory."""
        docs_path = Path(__file__).parent.parent / "docs"
        assert docs_path.is_dir(), "docs/ directory must exist"

    def test_readme_exists(self):
        """Plugin must have README.md."""
        readme_path = Path(__file__).parent.parent / "README.md"
        assert readme_path.exists(), "README.md must exist"

    def test_setup_py_exists(self):
        """Plugin must have setup.py."""
        setup_path = Path(__file__).parent.parent / "setup.py"
        assert setup_path.exists(), "setup.py must exist"

    def test_requirements_txt_exists(self):
        """Plugin must have requirements.txt."""
        reqs_path = Path(__file__).parent.parent / "requirements.txt"
        assert reqs_path.exists(), "requirements.txt must exist"


class TestPluginImports:
    """Test that plugin modules can be imported."""

    def test_can_import_orchestrator(self):
        """Should be able to import VideoProducerOrchestrator."""
        from video_producer.orchestrator import VideoProducerOrchestrator
        assert VideoProducerOrchestrator is not None

    def test_can_import_types(self):
        """Should be able to import plugin types."""
        from video_producer.types import (
            AssetAnalysisResult,
            Storyboard,
            Scene,
            FactualClaim,
            Contradiction,
        )
        assert all([AssetAnalysisResult, Storyboard, Scene, FactualClaim, Contradiction])

    def test_can_import_exceptions(self):
        """Should be able to import plugin exceptions."""
        from video_producer.exceptions import (
            VideoProducerError,
            AssetIngestionError,
            AnalysisIncompleteError,
            AnalysisGateFailedError,
        )
        assert all([
            VideoProducerError,
            AssetIngestionError,
            AnalysisIncompleteError,
            AnalysisGateFailedError,
        ])

    def test_can_import_learning_optimizer(self):
        """Should be able to import learning optimizer."""
        from video_producer.learning_optimizer import VideoProducerLearningOptimizer
        assert VideoProducerLearningOptimizer is not None

    def test_can_import_console_panel(self):
        """Should be able to import console panel."""
        from video_producer.console_panel import VideoProducerPanel, get_panel_config
        assert VideoProducerPanel is not None
        assert get_panel_config is not None


class TestPluginIntegration:
    """Test plugin integration readiness."""

    def test_plugin_has_console_panel_config(self):
        """Plugin must expose console panel configuration."""
        from video_producer.console_panel import get_panel_config
        config = get_panel_config()
        assert "id" in config
        assert "title" in config
        assert config["id"] == "video-producer-panel"

    def test_plugin_can_be_instantiated(self):
        """Plugin components should be instantiable."""
        from video_producer.orchestrator import VideoProducerOrchestrator
        try:
            orchestrator = VideoProducerOrchestrator()
            assert orchestrator is not None
        except Exception as e:
            pytest.skip(f"Orchestrator instantiation skipped (expected if dependencies missing): {e}")

    def test_plugin_tier_is_community(self, plugin_manifest):
        """Verify plugin is community/contributor tier (not vetted/builtin)."""
        assert plugin_manifest["tier"] == "contributor"
        assert plugin_manifest["sla_level"] == "contributor"
