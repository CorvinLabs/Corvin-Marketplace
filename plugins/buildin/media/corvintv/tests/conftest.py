"""Shared pytest fixtures for Video Producer plugin tests."""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# tests/fixtures/ holds data, not tests: the release_lint fixtures carry historical test_*.py files
collect_ignore_glob = ["fixtures/*"]

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

FIXTURE_ASSETS_BASE = str(Path(__file__).parent / "fixtures" / "assets_tenant")


@pytest.fixture(autouse=True)
def _fixture_asset_store():
    """Every test sees the committed fixture tenant's uploaded image (ADR-2249 D3) through the same
    binding a job uses, so the shared template contract (SAMPLES, goldens) covers `still`. Both import
    spellings of the module are bound (``src.asset_store`` and ``asset_store``)."""
    import importlib

    tokens = []
    for name in ("src.asset_store", "asset_store"):
        mod = importlib.import_module(name)
        tokens.append((mod, mod._BOUND.set(mod.AssetStore(FIXTURE_ASSETS_BASE))))
    yield
    for mod, tok in reversed(tokens):
        mod._BOUND.reset(tok)


@pytest.fixture
def mock_fastapi_app():
    """Create a mock FastAPI app for testing routes."""
    class MockApp:
        def __init__(self):
            self.routes = {}

        def post(self, path):
            def decorator(func):
                self.routes[f"POST {path}"] = func
                return func
            return decorator

        def get(self, path):
            def decorator(func):
                self.routes[f"GET {path}"] = func
                return func
            return decorator

        def delete(self, path):
            def decorator(func):
                self.routes[f"DELETE {path}"] = func
                return func
            return decorator

    return MockApp()


@pytest.fixture
def sample_video_production_request():
    """Sample VideoProductionRequest for testing."""
    from video_producer.console_panel import VideoProductionRequest
    return VideoProductionRequest(
        ppt_url="https://example.com/test.pptx",
        video_title="Test Video",
        narration_style="professional",
        max_duration_minutes=30
    )


@pytest.fixture
def sample_video_status():
    """Sample VideoProductionStatus for testing."""
    from datetime import datetime
    from video_producer.console_panel import VideoProductionStatus
    return VideoProductionStatus(
        job_id="test-job-123",
        status="analyzing",
        progress_percent=25,
        current_phase="analyzing",
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )


@pytest.fixture
def sample_metrics():
    """Sample VideoProductionMetrics for testing."""
    from video_producer.console_panel import VideoProductionMetrics
    return VideoProductionMetrics(
        total_videos_created=5,
        total_duration_minutes=120.5,
        average_processing_time_seconds=1800.0,
        success_rate_percent=95.0,
        total_scenes_narrated=32,
        learning_optimizer_score=0.85
    )


@pytest.fixture
def plugin_root():
    """Return the root path of the plugin."""
    return Path(__file__).parent.parent


@pytest.fixture
def plugin_manifest_dict(plugin_root):
    """Load and return plugin.json as dict."""
    import json
    manifest_path = plugin_root / "plugin.json"
    with open(manifest_path) as f:
        return json.load(f)


# Markers for organizing tests
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "security: mark test as a security test"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end"
    )


@pytest.fixture
def run_orchestrate(tmp_path, monkeypatch):
    """Drive the real ``orchestrate_video`` on an operator storyboard with only the
    network/slow edges replaced: TTS writes 1.2 s of real silence (ffmpeg), web slides off.
    Returns ``run(scenes, spies_for=(), replace=None) -> (result, spies)`` where spies records what the pipeline called."""
    import asyncio
    import shutil
    import subprocess

    from src import skill
    from src.models import VideoJob
    from src.storage import get_storage

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH — needed to drive orchestrate_video for real")

    def _record(log, fn):
        if asyncio.iscoroutinefunction(fn):
            async def w(*a, **k):
                log.append((a, k))
                return await fn(*a, **k)
        else:
            def w(*a, **k):
                log.append((a, k))
                return fn(*a, **k)
        return w

    def fake_tts(text, out_path, lang):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", "1.2", "-q:a", "9", str(out_path)], check=True)

    def native_stand_in(text, out_path, lang):
        fake_tts(text, out_path, lang)
        return "edge"  # what the CorvinOS chain reports when its edge tier spoke

    monkeypatch.setattr(skill, "_TTS_CHAIN", (("native", native_stand_in),))

    def run(scenes, spies_for=(), replace=None, tts_engine="auto"):
        spies = {}
        for name, fn in (replace or {}).items():  # stands in for the edge; the call is still recorded
            spies[name] = []
            monkeypatch.setattr(skill, name, _record(spies[name], fn))
        for name in spies_for:
            real = getattr(skill, name)
            spies[name] = []

            def make(name=name, real=real):
                if asyncio.iscoroutinefunction(real):
                    async def spy(*a, **k):
                        spies[name].append((a, k))
                        return await real(*a, **k)
                else:
                    def spy(*a, **k):
                        spies[name].append((a, k))
                        return real(*a, **k)
                return spy
            monkeypatch.setattr(skill, name, make())
        base = str(tmp_path / "store")
        get_storage(base).save_job(VideoJob(id="job_callsite", task="t", status="pending"))
        result = asyncio.run(skill.orchestrate_video(
            job_id="job_callsite", task="t", storage_base=base, web_slides=False, tts_engine=tts_engine,
            storyboard={"id": "sb_callsite", "didactic_strategy": "rich_visual", "scenes": scenes}))
        return result, spies

    return run


# ── the Claude Code CLI stand-in (1.8.0: the only storyboard engine) ──────────────────────────────

_COROS_WIN_SHIM = (Path(__file__).resolve().parents[6] / "CorvinOS" / "corvin_operator" / "bridges" / "shared"
                   / "agents" / "_win_shim.py")


def install_fake_claude_bin(script: Path, monkeypatch) -> Path:
    """Pin ``CORVIN_CLAUDE_BIN`` to a test stand-in for the Claude Code CLI written as a Python
    script. POSIX runs it directly (shebang). Windows cannot exec a script, so - exactly like an
    npm-installed ``claude.cmd`` - a ``.cmd`` shim wraps it and the job spawns it through CorvinOS's
    cmd.exe-safe launcher (``agents/_win_shim.py``, loaded from the sibling CorvinOS checkout);
    without that checkout the test is skipped rather than faked further."""
    import importlib.util
    import os
    import sys

    if os.name != "nt":
        monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(script))
        return script
    if not _COROS_WIN_SHIM.is_file():
        pytest.skip("Windows: a fake claude needs CorvinOS's _win_shim.py (sibling CorvinOS checkout)")
    spec = importlib.util.spec_from_file_location("_vp_test_win_shim", _COROS_WIN_SHIM)
    shim_mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, shim_mod)  # dataclasses resolve their module by name
    spec.loader.exec_module(shim_mod)
    from src import corvinos_native

    monkeypatch.setattr(corvinos_native, "_win_shim_module", lambda: shim_mod)
    cmd = script.with_name("claude.cmd")
    cmd.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(cmd))
    return cmd
