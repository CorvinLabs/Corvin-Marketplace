"""Tests for scripts/penpot_stack (optional Penpot design strand)."""
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path

import pytest

STACK_DIR = Path(__file__).resolve().parent.parent / "scripts" / "penpot_stack"

spec = importlib.util.spec_from_file_location("penpot_stack", STACK_DIR / "penpot_stack.py")
ps = importlib.util.module_from_spec(spec)
sys.modules["penpot_stack"] = ps
spec.loader.exec_module(ps)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="fake executables are POSIX scripts")


def _fake(bindir: Path, name: str, fail_on: str = ""):
    path = bindir / name
    path.write_text(
        f"#!{sys.executable}\nimport sys\n"
        f"fail_on = {fail_on!r}\n"
        "if fail_on and fail_on in sys.argv[1:]:\n    sys.exit(1)\n"
        f"print('{name} fake 1.0')\n"
    )
    path.chmod(0o755)


@pytest.fixture
def bindir(tmp_path, monkeypatch):
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setenv("PATH", str(d))
    return d


@posix_only
def test_no_runtime(bindir, capsys):
    d = ps.detect()
    assert d["runtime"] is None and d["compose"] is None
    assert "docker: not found" in d["reason"] and "podman: not found" in d["reason"]
    rc = ps.main(["detect"])
    cap = capsys.readouterr()
    assert rc == ps.EXIT_NO_RUNTIME
    assert json.loads(cap.out)["runtime"] is None
    assert "not available" in cap.err and "Traceback" not in cap.err


@posix_only
def test_podman_only_with_podman_compose(bindir):
    _fake(bindir, "podman")
    _fake(bindir, "podman-compose")
    d = ps.detect()
    assert d["runtime"] == "podman"
    assert Path(d["compose"][0]).name == "podman-compose"


@posix_only
def test_podman_only_via_compose_subcommand(bindir):
    _fake(bindir, "podman")
    d = ps.detect()
    assert d["runtime"] == "podman"
    assert Path(d["compose"][0]).name == "podman" and d["compose"][1] == "compose"


@posix_only
def test_docker_with_compose_plugin_wins_over_podman(bindir, capsys):
    _fake(bindir, "docker")
    _fake(bindir, "podman")
    d = ps.detect()
    assert d["runtime"] == "docker" and d["compose"][1] == "compose"
    assert ps.main(["detect"]) == 0
    assert json.loads(capsys.readouterr().out)["runtime"] == "docker"


@posix_only
def test_docker_without_compose_falls_back_to_podman(bindir):
    _fake(bindir, "docker", fail_on="compose")
    _fake(bindir, "podman")
    assert ps.detect()["runtime"] == "podman"


@posix_only
def test_docker_with_unreachable_daemon_falls_back_to_podman(bindir):
    _fake(bindir, "docker", fail_on="info")
    _fake(bindir, "podman")
    d = ps.detect()
    assert d["runtime"] == "podman"


@posix_only
def test_only_unreachable_docker_reports_reason(bindir):
    _fake(bindir, "docker", fail_on="info")
    d = ps.detect()
    assert d["runtime"] is None and "daemon" in d["reason"]


@posix_only
def test_runtime_without_compose_is_unusable(bindir, capsys):
    _fake(bindir, "docker", fail_on="compose")
    d = ps.detect()
    assert d["runtime"] is None and "no compose provider" in d["reason"]
    assert ps.main(["up"]) == ps.EXIT_NO_RUNTIME
    assert "Traceback" not in capsys.readouterr().err


def test_secrets_file_is_0600_random_and_stable(tmp_path):
    a = ps.ensure_secrets(tmp_path / "state", "t1")
    p = ps.secrets_path(tmp_path / "state", "t1")
    if sys.platform != "win32":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert len(a["PENPOT_SECRET_KEY"]) >= 64 and a["PENPOT_DB_PASSWORD"] != "penpot"
    assert ps.ensure_secrets(tmp_path / "state", "t1") == a
    b = ps.ensure_secrets(tmp_path / "state", "t2")
    assert b["PENPOT_SECRET_KEY"] != a["PENPOT_SECRET_KEY"]


def test_compose_images_are_pinned_and_secrets_not_committed():
    text = (STACK_DIR / "compose.yaml").read_text()
    images = re.findall(r"^\s*image:\s*\"?([^\"\s]+)\"?", text, re.M)
    assert len(images) == 8
    for img in images:
        assert ":" in img.rsplit("/", 1)[-1], img
        assert not img.endswith(":latest"), img
    assert all(i.endswith(":2.18.3") for i in images if "penpotapp" in i)
    assert "change-this-insecure-key" not in text
    assert "PENPOT_PASSWORD: penpot" not in text and "POSTGRES_PASSWORD=penpot" not in text
    assert "${PENPOT_SECRET_KEY:?" in text and "${PENPOT_DB_PASSWORD:?" in text


def test_frontend_binds_loopback_only():
    assert '"127.0.0.1:${PENPOT_PORT:-9001}:8080"' in (STACK_DIR / "compose.yaml").read_text()


def test_health_false_when_nothing_listens():
    h = ps.health(1, timeout=0.5)
    assert h["healthy"] is False


def test_cli_exposes_all_commands():
    names = ps.build_parser()._subparsers._group_actions[0].choices
    assert {"detect", "up", "down", "status", "health", "backup", "restore"} <= set(names)
    assert ps.build_parser().parse_args(["--port", "9101", "up"]).port == 9101
