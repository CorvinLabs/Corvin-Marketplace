"""The Style section of sources.md and the copy into Corvin-Videos/<video>/source/style (PLAN-0945 P5)."""

import subprocess
import sys
from pathlib import Path

from src.style_store import write_style_snapshot
from tests.test_style_pack import make_style

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "style_sources_section.py"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, check=True).stdout


def test_section_describes_the_style_and_copies_it(tmp_path):
    st = make_style()
    st.source = {"kind": "pptx", "sha256": "a" * 64, "deck_aspect": "16:9", "imported_at": "2026-10-10T00:00:00+00:00"}
    st.fonts = [{"from": "Calibri", "to": "Instrument Sans", "reason": "sans-serif family"}]
    st.warnings = ["The deck uses the default Office colours."]
    snap, dest = tmp_path / "videos" / "job_1" / "style", tmp_path / "Corvin-Videos" / "v" / "source" / "style"
    write_style_snapshot(st, snap)
    out = _run(snap, "--copy-to", dest)
    assert "## Style" in out and st.id in out and "a" * 64 in out and "Calibri -> Instrument Sans" in out
    assert "#3ba3ff" in out and "default Office colours" in out and "rights stay with its owner" in out
    assert (dest / "style.json").is_file() and (dest / "logo.png").is_file()


def test_video_without_a_snapshot_is_the_builtin_look(tmp_path):
    out = _run(tmp_path / "none")
    assert "Built-in CorvinOS look" in out
