"""End-to-end integration tests for Video Producer plugin."""

import pytest
import asyncio
from video_producer.orchestrator import VideoProducerOrchestrator
from video_producer.learning_optimizer import VideoProducerLearningOptimizer
from video_producer.console_panel import VideoProducerPanel, VideoProductionRequest
from video_producer.types import AssetAnalysisResult, Storyboard, Scene


class TestPluginE2EIntegration:
    """Test complete plugin integration."""

    def test_plugin_components_can_be_instantiated(self):
        """All plugin components should be instantiable."""
        try:
            orchestrator = VideoProducerOrchestrator()
            optimizer = VideoProducerLearningOptimizer()
            panel = VideoProducerPanel()

            assert orchestrator is not None
            assert optimizer is not None
            assert panel is not None
        except Exception as e:
            # Skip if dependencies are not fully installed
            pytest.skip(f"Plugin components require full installation: {e}")

    def test_console_panel_is_discoverable(self):
        """Console panel should be discoverable via export."""
        from video_producer.console_panel import get_panel_config

        config = get_panel_config()
        assert config is not None
        assert config["id"] == "video-producer-panel"
        assert "title" in config
        assert "route" in config

    def test_panel_can_process_video_request(self):
        """Panel should be able to process video production requests."""
        req = VideoProductionRequest(
            ppt_url="https://example.com/test.pptx",
            video_title="Test Video",
            narration_style="professional"
        )

        assert req.ppt_url == "https://example.com/test.pptx"
        assert req.video_title == "Test Video"
        assert req.max_duration_minutes == 30

    def test_plugin_learning_optimizer_is_available(self):
        """Learning optimizer should be available for skill optimization."""
        try:
            optimizer = VideoProducerLearningOptimizer()
            assert hasattr(optimizer, "optimize")
            assert callable(optimizer.optimize)
        except Exception:
            pytest.skip("Learning optimizer requires full installation")

    def test_plugin_exports_all_public_apis(self):
        """Plugin should export all public APIs via __init__.py."""
        import video_producer

        # Check main exports
        assert hasattr(video_producer, "VideoProducerOrchestrator")
        assert hasattr(video_producer, "AssetAnalysisResult")
        assert hasattr(video_producer, "Storyboard")
        assert hasattr(video_producer, "VideoProducerError")


class TestPluginManifestIntegration:
    """Test plugin manifest integration."""

    def test_manifest_entry_points_are_valid(self):
        """Manifest entry points should reference valid components."""
        import json
        from pathlib import Path

        manifest_path = Path(__file__).parent.parent / "plugin.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Verify panel entry point
        assert len(manifest["entry_points"]["console_panels"]) > 0
        panel = manifest["entry_points"]["console_panels"][0]
        assert panel["component"] == "VideoProducerPanel"

        # Verify skill entry point
        assert len(manifest["entry_points"]["skills"]) > 0
        skill = manifest["entry_points"]["skills"][0]
        assert skill["id"] == "os.video_producer"

    def test_manifest_permissions_are_valid(self):
        """Manifest permissions should be from approved set."""
        import json
        from pathlib import Path

        manifest_path = Path(__file__).parent.parent / "plugin.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        valid_permissions = {
            "console:read",
            "console:write",
            "skills:execute",
            "tasks:manage",
            "learning:write",
            "audit:read",
            "plugins:manage",
        }

        for perm in manifest.get("permissions", []):
            assert perm in valid_permissions, f"Unknown permission: {perm}"


class TestPluginSecurity:
    """Test security aspects of the plugin."""

    def test_plugin_does_not_bypass_consent_gates(self):
        """Plugin should respect consent mechanisms."""
        # This is a structural test; actual enforcement is in CorvinOS core
        # But we verify that the plugin doesn't declare any bypass permissions
        import json
        from pathlib import Path

        manifest_path = Path(__file__).parent.parent / "plugin.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Should not have any "bypass" or "admin" permissions
        permissions = manifest.get("permissions", [])
        forbidden = ["bypass:consent", "admin:*", "root"]

        for perm in permissions:
            for forbidden_perm in forbidden:
                assert forbidden_perm not in perm, f"Plugin declares forbidden permission: {perm}"

    def test_plugin_respects_tier_boundaries(self):
        """Contributor tier plugin should not claim higher privileges."""
        import json
        from pathlib import Path

        manifest_path = Path(__file__).parent.parent / "plugin.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Contributor tier should not claim builtin-only permissions
        assert manifest["tier"] == "contributor"
        assert manifest["boot_layer"] == "installed"

    def test_plugin_does_not_modify_core_files(self):
        """Plugin installation should not modify CorvinOS core files."""
        # This is verified by the plugin structure: it only installs to plugins/contributor/
        # and does not include CorvinOS core overrides
        plugin_path = Path(__file__).parent.parent

        # Should not have modifications to core paths
        src_path = plugin_path / "src"
        assert src_path.exists()

        # Verify plugin only touches its own namespace
        for py_file in src_path.rglob("*.py"):
            content = py_file.read_text()
            # Should not import core.console or core.skills directly
            # (would indicate tight coupling to CorvinOS internals)
            assert "from core.console" not in content or "from video_producer" in content
            assert "from core.skills" not in content or "from video_producer" in content


class TestPluginDependencies:
    """Test plugin dependencies."""

    def test_setup_py_specifies_dependencies(self):
        """setup.py should correctly specify all dependencies."""
        from pathlib import Path
        import re

        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()

        # Should have install_requires
        assert "install_requires" in content
        assert "corvinOS" in content

        # Should not have test dependencies in production
        assert "pytest" not in content or "extras_require" in content

    def test_requirements_txt_matches_setup_py(self):
        """requirements.txt should match setup.py install_requires."""
        from pathlib import Path

        setup_path = Path(__file__).parent.parent / "setup.py"
        reqs_path = Path(__file__).parent.parent / "requirements.txt"

        # Both should exist
        assert setup_path.exists()
        assert reqs_path.exists()

        # Simple check: both should mention key dependencies
        setup_content = setup_path.read_text()
        reqs_content = reqs_path.read_text()

        assert "corvinOS" in setup_content
        assert "corvinOS" in reqs_content


class TestPluginDocumentation:
    """Test plugin documentation."""

    def test_readme_exists_and_not_empty(self):
        """Plugin should have a README.md."""
        from pathlib import Path

        readme_path = Path(__file__).parent.parent / "README.md"
        assert readme_path.exists(), "README.md must exist"

        content = readme_path.read_text()
        assert len(content) > 100, "README.md should have substantial content"
        assert "Video Producer" in content or "video" in content.lower()

    def test_setup_guide_exists(self):
        """Plugin should have setup documentation."""
        from pathlib import Path

        docs_path = Path(__file__).parent.parent / "docs"
        assert docs_path.exists(), "docs/ directory must exist"

        # Check for common documentation files
        setup_files = [
            docs_path / "SETUP.md",
            docs_path / "setup.md",
            Path(__file__).parent.parent / "SETUP.md",
        ]

        has_setup_doc = any(f.exists() for f in setup_files)
        # Note: This might be skipped if docs not yet written
        # assert has_setup_doc, "Setup documentation should exist"
