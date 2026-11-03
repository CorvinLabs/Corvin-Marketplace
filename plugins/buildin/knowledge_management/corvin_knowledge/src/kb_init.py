#!/usr/bin/env python3
"""Create — or bring up to date — a tenant's own knowledge base.

    python3 kb_init.py --target <CORVIN_HOME>/tenants/<tenant>/knowledge

The CorvinOS host runs this (as a subprocess, stdlib only) once the Knowledge Graph plugin is
enabled for a tenant; the board projector then reads the result like any Corvin-Knowledge
checkout: `scripts/kb.py` + `kb/_meta/sources.yaml` in a git repository.

* **created** — `target` did not exist or was an empty directory: the template
  (`kb_template/`) and the engine (`kb_engine/`) are copied, `git init -b main`, one commit.
* **ok** — a knowledge base this plugin created (marker `kb/_meta/tenant_kb.json`) whose
  engine already matches `kb_engine/ENGINE.json`: nothing is written.
* **upgraded** — same, but the engine differs: the engine files (and only those) are
  replaced and committed. The operator's entities are never touched.
* **refused** — `target` holds something this plugin did not create: nothing is written.

Prints one JSON object; exit 0 for created/ok/upgraded, 2 for refused/error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "kb_engine"
TEMPLATE = HERE / "kb_template"
MARKER = Path("kb") / "_meta" / "tenant_kb.json"
_AUTHOR = ("-c", "user.name=kb-init", "-c", "user.email=kb@corvin.local",
           "-c", f"core.hooksPath={os.devnull}", "-c", "commit.gpgsign=false")


class InitError(Exception):
    pass


def _lf(data: bytes) -> bytes:
    """The committed (LF) form of an engine file. A Windows checkout with core.autocrlf=true
    (Git for Windows' default) has CRLF on disk; Python reads CRLF exactly as LF, so the
    CRLF->LF form IS the reviewed code. ENGINE.json and the CorvinOS path-gate pins are
    taken from the LF blob, and a tenant KB always receives the LF bytes."""
    return data.replace(b"\r\n", b"\n")


def _digest(path: Path) -> str:
    return hashlib.sha256(_lf(path.read_bytes())).hexdigest()


def engine_manifest() -> dict:
    m = json.loads((ENGINE / "ENGINE.json").read_text(encoding="utf-8"))
    for name, digest in m["files"].items():
        if _digest(ENGINE / name) != digest:
            raise InitError(f"kb_engine/{name} does not match ENGINE.json — refusing to install a modified engine")
    return m


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *_AUTHOR, *args], capture_output=True, text=True,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode != 0:
        raise InitError(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def _copy_engine(target: Path, files: dict) -> None:
    (target / "scripts").mkdir(parents=True, exist_ok=True)
    for name in files:
        dst = target / "scripts" / name
        if dst.is_symlink():
            raise InitError(f"scripts/{name} is a symlink — refusing to write through it")
        fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=f".{name}.")
        with os.fdopen(fd, "wb") as fh:
            fh.write(_lf((ENGINE / name).read_bytes()))   # LF: byte-identical to the pinned blob
        os.replace(tmp, dst)


def _engine_matches(target: Path, files: dict) -> bool:
    for name, digest in files.items():
        p = target / "scripts" / name
        # exact bytes, not the LF-normalised form: a CRLF engine in a tenant KB is rewritten
        # to LF, so the path gate's byte pin always matches what the KB runs
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            return False
    return True


def _create(target: Path, m: dict) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    for src in TEMPLATE.rglob("*"):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(TEMPLATE)
        name = rel.as_posix()
        dst = target / ("." + name if name in ("gitignore", "gitattributes") else rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(_lf(src.read_bytes()))   # LF: a Windows checkout of the template is CRLF
    _copy_engine(target, m["files"])
    (target / MARKER).write_text(json.dumps({
        "created_by": "corvin_knowledge plugin",
        "engine_commit": m["source_commit"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    # `git init -b` needs git >= 2.28; set the branch explicitly so older git works too
    _git(target, "init", "-q")
    _git(target, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "kb: initialise this tenant's knowledge base")
    return {"status": "created", "engine_commit": m["source_commit"]}


def ensure(target: Path) -> dict:
    target = Path(target)
    m = engine_manifest()
    if target.is_symlink():
        raise InitError("target is a symlink")
    if not target.exists() or (target.is_dir() and not any(target.iterdir())):
        return {**_create(target, m), "path": str(target)}
    if not (target / MARKER).is_file() or not (target / ".git").exists():
        return {"status": "refused", "path": str(target),
                "error": "the directory exists and was not created by the Knowledge Graph plugin"}
    if _engine_matches(target, m["files"]):
        return {"status": "ok", "path": str(target), "engine_commit": m["source_commit"]}
    _copy_engine(target, m["files"])
    marker = json.loads((target / MARKER).read_text(encoding="utf-8"))
    marker["engine_commit"] = m["source_commit"]
    (target / MARKER).write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                 newline="\n")
    paths = [f"scripts/{n}" for n in m["files"]] + [MARKER.as_posix()]
    _git(target, "add", "--", *paths)
    if not _git(target, "diff", "--cached", "--name-only", "--", *paths):
        # only the line endings differed (a CRLF engine rewritten to LF): same content, nothing to commit
        return {"status": "ok", "path": str(target), "engine_commit": m["source_commit"], "normalized": True}
    # pathspec commit: whatever else the operator has staged stays staged and out of this commit
    _git(target, "commit", "-q", "-m", f"kb: engine {m['source_commit'][:12]}", "--", *paths)
    return {"status": "upgraded", "path": str(target), "engine_commit": m["source_commit"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True)
    a = ap.parse_args()
    try:
        out = ensure(Path(a.target))
    except (InitError, OSError, ValueError, KeyError) as exc:
        out = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:400]}
    print(json.dumps(out))
    return 0 if out["status"] in ("created", "ok", "upgraded") else 2


if __name__ == "__main__":
    sys.exit(main())
