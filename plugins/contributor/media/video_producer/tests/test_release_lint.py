"""scripts/release_lint.py (ADR-2247 doc_claims, PLAN-0946 R5, T-0094).

Positive controls: the three historical release defects - a version that differs between plugin.json
and the index / provider.py / plugin.yaml, a RESULTS_PLACEHOLDER in the notes, a release note naming a
test that does not exist - are reproduced in tests/fixtures/release_lint/ and each must be caught by
its own check. Negative controls: a consistent fixture passes, and so does this plugin as committed
(the same command the GitHub workflow runs). Real CLI subprocesses, no import shortcut."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "scripts" / "release_lint.py"
FIX = ROOT / "tests" / "fixtures" / "release_lint"
INDEX = ROOT.parents[3] / "index" / "plugins.json"


def lint(*args):
    r = subprocess.run([sys.executable, str(LINT), "--json", *args], capture_output=True, text=True, timeout=60)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None), r


@pytest.mark.parametrize("case", ["version_index", "version_provider", "placeholder", "missing_test"])
def test_each_historical_defect_is_caught_by_its_check(case):
    expected = (FIX / case / "EXPECTED").read_text().strip()
    code, out, r = lint("--plugin-dir", str(FIX / case / "plugin"), "--index", str(FIX / case / "index" / "plugins.json"))
    assert code == 1, r.stdout + r.stderr
    assert {f["check"] for f in out["findings"]} == {expected}, out


def test_the_fixtures_say_what_they_reproduce():
    out = {c: lint("--plugin-dir", str(FIX / c / "plugin"), "--index", str(FIX / c / "index" / "plugins.json"))[1]
           for c in ("version_index", "version_provider", "placeholder", "missing_test")}
    assert len(out["version_index"]["findings"]) == 4  # all four index blocks said 1.0.0
    assert {f["where"] for f in out["version_provider"]["findings"]} == {"plugin.yaml", "provider.py"}
    assert out["placeholder"]["findings"][0]["what"] == "RESULTS_PLACEHOLDER"
    assert "test_video_job_end_to_end" in out["missing_test"]["findings"][0]["what"]


def test_a_consistent_plugin_passes():
    code, out, r = lint("--plugin-dir", str(FIX / "clean" / "plugin"), "--index", str(FIX / "clean" / "index" / "plugins.json"))
    assert code == 0 and out["findings"] == [], r.stdout


def test_this_plugin_as_committed_passes():
    assert INDEX.is_file(), "the marketplace index is next to the plugin in this repository"
    code, out, r = lint("--index", str(INDEX))
    assert code == 0, json.dumps(out, indent=1)


def test_older_release_sections_are_history_but_unreleased_and_current_are_checked(tmp_path):
    import shutil
    p = tmp_path / "plugin"
    shutil.copytree(FIX / "clean" / "plugin", p)
    notes = p / "RELEASE-NOTES.md"
    notes.write_text(notes.read_text() + "\n## Version 1.0.0\n\n- `tests/test_gone.py` (deleted since)\n")
    assert lint("--plugin-dir", str(p), "--index", str(FIX / "clean" / "index" / "plugins.json"))[0] == 0
    notes.write_text("# Notes\n\n## Unreleased (toward 1.3.0)\n\n- proof: `test_nobody_wrote_this`; TODO\n\n" + notes.read_text().split("\n", 1)[1])
    code, out, _ = lint("--plugin-dir", str(p), "--index", str(FIX / "clean" / "index" / "plugins.json"))
    assert code == 1 and {f["check"] for f in out["findings"]} == {"placeholder", "reference"}


def test_a_missing_index_entry_is_a_finding(tmp_path):
    idx = tmp_path / "plugins.json"
    data = json.loads((FIX / "clean" / "index" / "plugins.json").read_text())
    data["by_tier"] = {}
    idx.write_text(json.dumps(data))
    code, out, _ = lint("--plugin-dir", str(FIX / "clean" / "plugin"), "--index", str(idx))
    assert code == 1 and "3 index blocks" in out["findings"][0]["what"]
