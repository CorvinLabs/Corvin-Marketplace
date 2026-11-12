from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
FAKE = HERE / "fake_claude.py"
CORVIN_ROOT = Path(os.environ.get("CORVIN_ROOT", "/home/shumway/projects/CorvinOS"))
PY = CORVIN_ROOT / ".venv" / "bin" / "python"

LIVE_PATHS = [CORVIN_ROOT / ".corvin", Path.home() / ".corvin"]


def snapshot_live() -> dict[str, tuple[int, int]]:
    snap = {}
    for root in LIVE_PATHS:
        if root.exists():
            for p in root.rglob("audit*.jsonl"):
                try:
                    st = p.stat()
                    snap[str(p)] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    pass
    return snap


class Run:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.wd = tmp / "wd"
        self.out = tmp / "out"
        self.dump = tmp / "dump"
        self.wd.mkdir()

    def result(self) -> dict:
        return json.loads((self.out / "result.json").read_text())

    def dumps(self, kind: str) -> list[dict]:
        out = []
        for f in sorted(self.dump.glob("*.json")):
            d = json.loads(f.read_text())
            if d["kind"] == kind:
                out.append(d)
        return out


@pytest.fixture
def run(tmp_path):
    return Run(tmp_path)


def invoke(run: Run, *, instruction: str = "Create the file.", stdin: bool = False, extra_env=None,
           extra_args=(), timeout=180, model="zai-org/GLM-5.3-Flash"):
    if not PY.exists():
        pytest.skip(f"no CorvinOS interpreter at {PY}")
    env = {
        "PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "PYTHONPATH": str(SRC),
        "CORVIN_CLAUDE_BIN": str(FAKE), "FAKE_CLAUDE_DUMP": str(run.dump),
        "CORVIN_HARNESS_KEEP_HOME": "1",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "hlb-sandbox-SECRET-run42",
    }
    env.update(extra_env or {})
    cmd = [str(PY), "-m", "corvin_harness_runner", "--workdir", str(run.wd), "--out-dir", str(run.out),
           "--model", model, "--corvin-root", str(CORVIN_ROOT), *extra_args]
    if stdin:
        cmd += ["--instruction-file", "-"]
        proc = subprocess.run(cmd, input=instruction.encode(), env=env, capture_output=True, timeout=timeout)
    else:
        f = run.tmp / "instruction.txt"
        f.write_text(instruction)
        cmd += ["--instruction-file", str(f)]
        proc = subprocess.run(cmd, env=env, capture_output=True, timeout=timeout)
    run.cmd = cmd
    return proc
