"""measure_engagement reports a skip, never a number, when numpy is missing (PLAN-0946 R0)."""

import builtins
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "measure_engagement.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_engagement", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_numpy_is_declared():
    root = SCRIPT.parent.parent
    assert "numpy" in (root / "requirements.txt").read_text()
    assert "numpy" in (root / "setup.py").read_text()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg needed to build a clip")
def test_missing_numpy_is_a_skip_through_the_cli(tmp_path, monkeypatch):
    me = _load()
    job = tmp_path / "videos" / "job_x"
    (job / "scenes").mkdir(parents=True)
    (job / "metadata.json").write_text(json.dumps({"metadata": {}}))
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2:r=10",
                    "-pix_fmt", "yuv420p", str(job / "scenes" / "scene_001.mp4")], check=True)
    real_import = builtins.__import__

    def no_numpy(name, *a, **k):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("No module named 'numpy'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_numpy)
    out = tmp_path / "out.json"
    assert me.main([str(tmp_path / "videos"), "job_x", "--json", str(out)]) == 0
    monkeypatch.undo()
    data = json.loads(out.read_text())
    assert data["summary"]["still"] == {"verdict": "skip", "reason": "numpy missing"}
    assert data["summary"]["dead_share"] is None and data["summary"]["longest_still_max"] is None
    assert data["jobs"][0]["dead_share"] is None
    assert data["jobs"][0]["scenes"][0]["dead_s"] is None
    assert "frozen_share" in data["summary"]  # the ffmpeg-only measure still reports
