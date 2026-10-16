"""Tenant knowledge base: `src/kb_init.py` + the vendored engine, driven as subprocesses.

What a fresh CorvinOS install relies on: the host runs `kb_init.py --target <tenant>/knowledge`
once the plugin is enabled, then runs `scripts/kb.py` in that directory every two seconds.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
INIT = SRC / "kb_init.py"


def run(*a, cwd=None, env=None):
    return subprocess.run([str(x) for x in a], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def init(target: Path) -> tuple[int, dict]:
    r = run(sys.executable, INIT, "--target", target)
    return r.returncode, json.loads(r.stdout)


def kb(repo: Path, *a) -> tuple[int, dict | str]:
    r = run(sys.executable, repo / "scripts" / "kb.py", "--repo", repo, *a, env={"KB_ACTOR": "human:tester"})
    out = r.stdout.strip()
    return r.returncode, (json.loads(out) if out.startswith("{") else out + r.stderr)


def test_vendored_engine_matches_its_manifest():
    m = json.loads((SRC / "kb_engine" / "ENGINE.json").read_text())
    assert set(m["files"]) == {"kb.py", "kb_lib.py", "kb_model.py"}
    assert len(m["source_commit"]) == 40
    for name, digest in m["files"].items():
        assert hashlib.sha256((SRC / "kb_engine" / name).read_bytes()).hexdigest() == digest, name


def test_create_then_idempotent(tmp_path):
    target = tmp_path / "tenants" / "_default" / "knowledge"
    rc, out = init(target)
    assert rc == 0 and out["status"] == "created", out
    for p in ("scripts/kb.py", "kb/_meta/sources.yaml", "kb/_meta/autonomy.yaml", "kb/_meta/tenant_kb.json",
              ".gitignore", "README.md"):
        assert (target / p).is_file(), p
    log = run("git", "-C", target, "log", "--oneline").stdout
    assert log.count("\n") == 1 and "initialise" in log
    assert run("git", "-C", target, "status", "--porcelain").stdout == ""
    rc, out = init(target)
    assert rc == 0 and out["status"] == "ok", out
    assert run("git", "-C", target, "log", "--oneline").stdout == log    # second run wrote nothing


def test_gates_work_in_a_fresh_tenant_kb(tmp_path):
    repo = tmp_path / "knowledge"
    assert init(repo)[0] == 0
    rc, res = kb(repo, "check")
    assert rc == 0 and res["blocking"] == 0 and res["entities"] == 0
    assert kb(repo, "new", "initiative", "--title", "Onboarding")[0] == 0
    assert kb(repo, "new", "concept", "--title", "Sign-in flow")[0] == 0
    assert kb(repo, "new", "decision", "--title", "Sign in with OIDC", "--link", "formalized_as=CONCEPT-0001")[0] == 0
    assert kb(repo, "new", "epic", "--title", "Build OIDC sign-in", "--initiative", "I-01",
              "--link", "implements=ADR-0001")[0] == 0
    assert kb(repo, "new", "task", "--title", "Callback route", "--epic", "E-001", "--dod", "route answers 200")[0] == 0
    kb(repo, "check", "--json", tmp_path / "c.json")
    issues = json.loads((tmp_path / "c.json").read_text())["issues"]
    gates = {k for k in issues if k.startswith("G")}
    assert "G1_no_concept" not in gates            # concept gate holds: the decision names its concept
    assert {"G2_no_backedge", "G3_no_path_overlap"} <= gates   # not yet: back-edge, shared paths
    rc, exp = kb(repo, "export")
    assert rc == 0 and exp["ok"] is True
    assert [(i["id"], i["kind"]) for i in exp["items"]] == [("I-01", "initiative"), ("E-001", "epic"),
                                                            ("T-0001", "task")]
    epic = exp["items"][1]
    assert epic["implements"] == ["ADR-0001"] and epic["implementation_ready"] is False
    assert kb(repo, "index")[0] == 0 and (repo / "kb" / "graph" / "entities.jsonl").is_file()
    assert run("git", "-C", repo, "status", "--porcelain").stdout == ""   # graph/lock are ignored


def test_engine_upgrade_replaces_only_the_engine(tmp_path):
    repo = tmp_path / "knowledge"
    init(repo)
    kb(repo, "new", "concept", "--title", "Keep me")
    (repo / "scripts" / "kb_lib.py").write_text("# stale engine\n")
    run("git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "stale")
    rc, out = init(repo)
    assert rc == 0 and out["status"] == "upgraded", out
    assert (repo / "concepts" / "CONCEPT-0001-keep-me.md").is_file()
    assert run("git", "-C", repo, "status", "--porcelain").stdout == ""
    assert kb(repo, "check")[0] == 0


@pytest.mark.parametrize("prepare", ["foreign_files", "symlink"])
def test_refuses_what_it_did_not_create(tmp_path, prepare):
    target = tmp_path / "knowledge"
    if prepare == "foreign_files":
        target.mkdir()
        (target / "notes.txt").write_text("mine")
    else:
        if os.name == "nt":
            pytest.skip("symlinks need a privilege on Windows")
        (tmp_path / "elsewhere").mkdir()
        target.symlink_to(tmp_path / "elsewhere")
    rc, out = init(target)
    assert rc == 2 and out["status"] in ("refused", "error"), out
    assert not (tmp_path / "elsewhere" / "scripts").exists()
    if prepare == "foreign_files":
        assert sorted(p.name for p in target.iterdir()) == ["notes.txt"]
