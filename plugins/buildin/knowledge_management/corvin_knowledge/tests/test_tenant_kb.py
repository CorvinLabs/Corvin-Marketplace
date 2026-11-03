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
        # the committed (LF) form: a Windows checkout (core.autocrlf=true) has CRLF on disk
        data = (SRC / "kb_engine" / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, name


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


# --- Windows regressions (2026-11-03): CRLF checkout, text-mode fds -----------------------------

def _crlf_plugin_copy(tmp_path: Path) -> Path:
    """A copy of src/ as Git for Windows (core.autocrlf=true) checks it out: every text file CRLF."""
    import shutil

    dst = tmp_path / "plugin_src"
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__", "web-next", "tests"))
    for f in list((dst / "kb_engine").glob("*.py")) + [f for f in (dst / "kb_template").rglob("*") if f.is_file()]:
        f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    return dst


def test_a_crlf_checkout_still_installs_the_pinned_lf_engine(tmp_path):
    src = _crlf_plugin_copy(tmp_path)
    assert b"\r\n" in (src / "kb_engine" / "kb.py").read_bytes()
    target = tmp_path / "knowledge"
    r = run(sys.executable, src / "kb_init.py", "--target", target)
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["status"] == "created", out      # was: "does not match ENGINE.json"
    m = json.loads((SRC / "kb_engine" / "ENGINE.json").read_text())
    for name, digest in m["files"].items():                             # byte-exact: the path-gate pin
        assert hashlib.sha256((target / "scripts" / name).read_bytes()).hexdigest() == digest, name
    for f in ("kb/_meta/sources.yaml", "kb/_meta/autonomy.yaml", "README.md", ".gitignore", ".gitattributes"):
        assert b"\r\n" not in (target / f).read_bytes(), f
    assert run("git", "-C", target, "status", "--porcelain").stdout == ""


def test_a_crlf_engine_in_a_tenant_kb_is_normalised_without_a_commit(tmp_path):
    repo = tmp_path / "knowledge"
    assert init(repo)[0] == 0
    p = repo / "scripts" / "kb.py"
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    log = run("git", "-C", repo, "log", "--oneline").stdout
    rc, out = init(repo)
    assert rc == 0 and out["status"] == "ok" and out.get("normalized"), out
    assert b"\r\n" not in p.read_bytes()
    assert run("git", "-C", repo, "log", "--oneline").stdout == log


def test_writes_leave_a_clean_index_and_no_lock(tmp_path):
    """On Windows os.open() is TEXT mode by default: the index kb swapped in got CRLF-mangled
    (`git ls-files -u` then listed a "\\r\\n.gitignore" entry and every later write was refused as
    "unmerged paths") and index.lock was never released. Two writes in a row prove both."""
    repo = tmp_path / "knowledge"
    assert init(repo)[0] == 0
    assert kb(repo, "new", "initiative", "--title", "One")[0] == 0
    rc, res = kb(repo, "new", "initiative", "--title", "Two")
    assert rc == 0 and res["id"] == "I-02", res
    assert not (repo / ".git" / "index.lock").exists()
    assert run("git", "-C", repo, "ls-files", "-u").stdout == ""
    assert run("git", "-C", repo, "status", "--porcelain").stdout == ""
    assert b"\r\n" not in (repo / "kb" / "audit.jsonl").read_bytes()


def test_non_ascii_titles_survive_export_and_index(tmp_path):
    repo = tmp_path / "knowledge"
    assert init(repo)[0] == 0
    assert kb(repo, "new", "initiative", "--title", "Übersicht – 認証")[0] == 0
    assert kb(repo, "index")[0] == 0
    rows = [json.loads(ln) for ln in (repo / "kb" / "graph" / "entities.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["title"] == "Übersicht – 認証" for r in rows)
