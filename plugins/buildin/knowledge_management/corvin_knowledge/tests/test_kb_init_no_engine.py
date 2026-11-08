"""`kb_init.py --no-engine [--no-git]`: a knowledge-base scaffold WITHOUT its own engine copy.

A project's `docs/` (CorvinOS projects, ADR-2315/2316) is read and written by the engine of the
tenant's bound knowledge base (`kb.py --repo <docs>`); the path gate lets an agent session run
`kb.py` only from the pinned engine locations, so an engine copy inside a project would only be
refused and would drift. Driven as real subprocesses against the real engine.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
INIT = SRC / "kb_init.py"
ENGINE = SRC / "kb_engine" / "kb.py"


def run(*a, cwd=None, env=None):
    return subprocess.run([str(x) for x in a], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def init(target: Path, *flags: str) -> tuple[int, dict]:
    r = run(sys.executable, INIT, "--target", target, *flags)
    return r.returncode, json.loads(r.stdout)


def kb(repo: Path, *a) -> tuple[int, dict | str]:
    # the engine of the BOUND knowledge base, pointed at the scaffold with --repo
    r = run(sys.executable, ENGINE, "--repo", repo, *a, env={"KB_ACTOR": "human:tester"})
    out = r.stdout.strip()
    return r.returncode, (json.loads(out) if out.startswith("{") else out + r.stderr)


def test_no_engine_scaffold_has_no_scripts_and_a_marker_saying_so(tmp_path):
    target = tmp_path / "docs"
    rc, out = init(target, "--no-engine")
    assert rc == 0 and out["status"] == "created" and out["engine"] == "external", out
    assert not (target / "scripts").exists(), "an engine copy was written"
    for p in ("kb/_meta/sources.yaml", "kb/_meta/autonomy.yaml", "kb/_meta/tenant_kb.json", ".gitignore", "README.md"):
        assert (target / p).is_file(), p
    marker = json.loads((target / "kb/_meta/tenant_kb.json").read_text(encoding="utf-8"))
    assert marker["engine"] == "external" and "engine_commit" not in marker
    log = run("git", "-C", target, "log", "--oneline").stdout
    assert log.count("\n") == 1 and "initialise" in log


def test_the_bound_engine_runs_the_whole_pipeline_on_it(tmp_path):
    target = tmp_path / "docs"
    assert init(target, "--no-engine")[0] == 0
    rc, i = kb(target, "new", "initiative", "--title", "Project")
    assert rc == 0, i
    rc, e = kb(target, "new", "epic", "--title", "Setup", "--initiative", i["id"])
    assert rc == 0, e
    rc, t = kb(target, "new", "task", "--title", "First", "--epic", e["id"], "--dod", "done")
    assert rc == 0, t
    rc, chk = kb(target, "check")
    assert rc == 0 and chk["blocking"] == 0, chk
    assert not (target / "scripts").exists()


def test_second_run_is_ok_and_writes_nothing_even_after_an_engine_update(tmp_path):
    target = tmp_path / "docs"
    assert init(target, "--no-engine")[0] == 0
    log = run("git", "-C", target, "log", "--oneline").stdout
    rc, out = init(target, "--no-engine")
    assert rc == 0 and out["status"] == "ok", out
    # without the flag the same directory is not "upgraded" either: there is no engine to refresh
    rc, out = init(target)
    assert rc == 0 and out["status"] == "ok", out
    assert not (target / "scripts").exists()
    assert run("git", "-C", target, "log", "--oneline").stdout == log


def test_no_git_leaves_version_control_to_the_caller(tmp_path):
    target = tmp_path / "docs"
    rc, out = init(target, "--no-engine", "--no-git")
    assert rc == 0 and out["status"] == "created" and out["git"] is False, out
    assert not (target / ".git").exists()
    assert (target / "kb/_meta/sources.yaml").is_file()


def test_default_mode_is_unchanged_and_still_ships_the_engine(tmp_path):
    target = tmp_path / "knowledge"
    rc, out = init(target)
    assert rc == 0 and out["status"] == "created", out
    assert (target / "scripts" / "kb.py").is_file()
    marker = json.loads((target / "kb/_meta/tenant_kb.json").read_text(encoding="utf-8"))
    assert "engine_commit" in marker and "engine" not in marker


def test_a_directory_this_plugin_did_not_create_is_still_refused(tmp_path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "mine.txt").write_text("x", encoding="utf-8")
    rc, out = init(target, "--no-engine")
    assert rc == 2 and out["status"] == "refused", out
    assert [p.name for p in target.iterdir()] == ["mine.txt"]
