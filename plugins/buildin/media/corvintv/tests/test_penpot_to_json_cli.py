"""The JSON converter through its real process boundary: a subprocess, a file on disk, stdout/stderr/exit code."""
import json
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "scripts" / "penpot_to_json.py"
BOARD = PLUGIN / "tests" / "fixtures" / "penpot_board.svg"


def run(path):
    return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, timeout=60)


def test_real_export_becomes_json_on_stdout_with_exit_0():
    r = run(BOARD)
    assert r.returncode == 0, r.stderr
    model = json.loads(r.stdout)
    assert len(model["shapes"]) == 8 and model["canvas"]["width"] == 1920.0
    assert "localhost" not in r.stdout and "<svg" not in r.stdout


def test_hostile_doctype_is_refused_with_exit_2(tmp_path):
    bad = tmp_path / "bomb.svg"
    bad.write_bytes(b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"/>')
    r = run(bad)
    assert r.returncode == 2 and r.stdout == ""
    assert "document type" in r.stderr


def test_generic_svg_is_refused_with_the_structure_message(tmp_path):
    plain = tmp_path / "figma.svg"
    plain.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="9" height="9" fill="#ff0000"/></svg>')
    r = run(plain)
    assert r.returncode == 2 and "Unknown Penpot structure" in r.stderr


def test_missing_file_is_a_clean_refusal(tmp_path):
    r = run(tmp_path / "nope.svg")
    assert r.returncode == 2 and "cannot read" in r.stderr
