"""The Penpot stack CLI through its real process boundary (ADR-2257 strand B, T-0191).

``test_penpot_stack.py`` calls the module's functions; these tests run ``penpot_stack.py`` as a
subprocess, the way an operator does. The no-runtime case always runs. The real-stack case needs a
container runtime, about 3 GB of RAM and several minutes, so it is opt-in:
``CORVIN_PENPOT_STACK_E2E=1 pytest tests/test_penpot_stack_cli_e2e.py``.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parent.parent / "scripts" / "penpot_stack" / "penpot_stack.py"
pytestmark = pytest.mark.e2e


def cli(*args, path=None, timeout=900):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run([sys.executable, "-I", str(CLI), *args], capture_output=True, text=True, env=env, timeout=timeout)


def test_without_a_container_runtime_the_cli_refuses_cleanly():
    empty = tempfile.mkdtemp()
    r = cli("detect", path=empty)
    assert r.returncode != 0
    assert json.loads(r.stdout.splitlines()[0])["runtime"] is None
    assert "Traceback" not in r.stderr and r.stderr.strip(), r.stderr
    for cmd in (["up", "--wait", "1"], ["status"], ["down"]):
        r = cli(*cmd, path=empty)
        assert r.returncode != 0 and "Traceback" not in r.stderr, (cmd, r.stderr)


def _runtime():
    d = subprocess.run([sys.executable, "-I", str(CLI), "detect"], capture_output=True, text=True)
    return json.loads(d.stdout.splitlines()[0]) if d.returncode == 0 else None


@pytest.mark.skipif(os.environ.get("CORVIN_PENPOT_STACK_E2E") != "1", reason="opt-in: starts the real Penpot stack")
def test_real_stack_up_health_backup_down():
    rt = _runtime()
    if rt is None:
        pytest.skip("no usable container runtime on this host")
    state = tempfile.mkdtemp(prefix="vp-stack-state-")
    work = tempfile.mkdtemp(prefix="vp-stack-work-")
    common = ["--port", "9102", "--project", "penpotvpe2e", "--state-dir", state]
    try:
        up = cli(*common, "up", "--wait", "420")
        assert up.returncode == 0, up.stdout[-800:] + up.stderr[-800:]
        info = json.loads(up.stdout.strip().splitlines()[-1])
        assert info["healthy"] is True
        h = cli(*common, "health")
        assert h.returncode == 0 and json.loads(h.stdout)["healthy"] is True
        sec = Path(state) / "penpotvpe2e.secrets.json"
        assert sec.is_file() and (sec.stat().st_mode & 0o777) == 0o600
        values = list(json.loads(sec.read_text()).values())
        assert len(values) == 2 and all(len(v) >= 24 for v in values)  # positive control: there ARE secrets to leak
        seen = up.stdout + up.stderr + h.stdout + h.stderr
        assert not any(v in seen for v in values), "a secret reached the CLI output"
        out = Path(work) / "penpot.dump"
        bk = cli(*common, "backup", "--out", str(out))
        assert bk.returncode == 0 and out.stat().st_size > 1000, bk.stderr[-400:]
    finally:
        down = cli(*common, "down", "--volumes")
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)
    assert down.returncode == 0, down.stderr[-400:]
    left = subprocess.run([rt["runtime_path"], "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True).stdout
    assert "penpotvpe2e" not in left
