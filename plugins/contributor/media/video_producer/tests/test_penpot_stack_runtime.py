"""Runtime override and pull fallback for scripts/penpot_stack (plugin setting ``penpot_runtime``)."""
import importlib.util
import json
import subprocess
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
    monkeypatch.delenv(ps.ENV_RUNTIME, raising=False)
    return d


def _rt(name):
    return {"runtime": name, "runtime_path": f"/fake/{name}", "compose": [f"/fake/{name}", "compose"],
            "version": "", "reason": None}


@posix_only
def test_forced_podman_is_used_even_when_docker_is_usable(bindir):
    _fake(bindir, "docker")
    _fake(bindir, "podman")
    assert ps.detect("podman")["runtime"] == "podman"
    assert ps.detect("docker")["runtime"] == "docker"
    usable, _ = ps.probe("podman")
    assert [d["runtime"] for d in usable] == ["podman"]


@posix_only
def test_forced_docker_without_daemon_is_not_replaced_by_podman(bindir):
    _fake(bindir, "docker", fail_on="info")
    _fake(bindir, "podman")
    d = ps.detect("docker")
    assert d["runtime"] is None and "daemon" in d["reason"]
    assert "podman" not in d["reason"]


@posix_only
def test_cli_flag_beats_env_and_forced_runtime_never_falls_back(bindir, monkeypatch, capsys):
    _fake(bindir, "podman")
    monkeypatch.setenv(ps.ENV_RUNTIME, "podman")
    rc = ps.main(["--runtime", "docker", "detect"])
    out = capsys.readouterr()
    assert rc == ps.EXIT_NO_RUNTIME
    assert json.loads(out.out)["runtime"] is None
    assert "Traceback" not in out.err


def test_unknown_runtime_name_is_rejected(monkeypatch, capsys):
    monkeypatch.setenv(ps.ENV_RUNTIME, "kubernetes")
    rc = ps.main(["detect"])
    assert rc == 2
    assert "must be one of auto, docker, podman" in capsys.readouterr().err


def test_choose_for_up_falls_back_when_docker_pull_fails(tmp_path, monkeypatch):
    calls = []

    def fake_compose(args, d, extra, with_secrets=False):
        calls.append((d["runtime"], extra))
        return subprocess.CompletedProcess([], 1 if d["runtime"] == "docker" else 0)

    monkeypatch.setattr(ps, "_has_image", lambda d, image: False)
    monkeypatch.setattr(ps, "_compose_on", fake_compose)
    args = ps.build_parser().parse_args(["--state-dir", str(tmp_path), "up"])
    chosen, failures = ps._choose_for_up(args, [_rt("docker"), _rt("podman")])
    assert chosen["runtime"] == "podman"
    assert calls == [("docker", ["pull"]), ("podman", ["pull"])]
    assert failures == ["docker: `compose pull` exited 1"]


def test_choose_for_up_uses_a_runtime_that_already_holds_the_images(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ps, "_has_image", lambda d, image: d["runtime"] == "podman")
    monkeypatch.setattr(ps, "_compose_on",
                        lambda args, d, extra, with_secrets=False: calls.append(extra) or subprocess.CompletedProcess([], 0))
    args = ps.build_parser().parse_args(["--state-dir", str(tmp_path), "up"])
    chosen, failures = ps._choose_for_up(args, [_rt("docker"), _rt("podman")])
    assert chosen["runtime"] == "podman" and failures == []
    assert calls == []  # no pull at all: the pinned images are local


def test_every_pull_failing_returns_no_runtime_and_all_reasons(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_has_image", lambda d, image: False)
    monkeypatch.setattr(ps, "_compose_on",
                        lambda args, d, extra, with_secrets=False: subprocess.CompletedProcess([], 1))
    args = ps.build_parser().parse_args(["--state-dir", str(tmp_path), "up"])
    chosen, failures = ps._choose_for_up(args, [_rt("docker"), _rt("podman")])
    assert chosen is None
    assert len(failures) == 2


def test_a_forced_runtime_whose_pull_fails_is_final(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_has_image", lambda d, image: False)
    monkeypatch.setattr(ps, "_compose_on",
                        lambda args, d, extra, with_secrets=False: subprocess.CompletedProcess([], 1))
    args = ps.build_parser().parse_args(["--state-dir", str(tmp_path), "--runtime", "docker", "up"])
    chosen, failures = ps._choose_for_up(args, [_rt("docker")])
    assert chosen is None and failures == ["docker: `compose pull` exited 1"]


def test_ordered_puts_the_runtime_that_holds_the_stack_first(monkeypatch):
    def fake_run(argv, timeout=ps.PROBE_TIMEOUT_S):
        names = "penpotx_penpot-frontend_1\n" if "/fake/podman" in argv[0] else "unrelated\n"
        return subprocess.CompletedProcess(argv, 0, stdout=names, stderr="")

    monkeypatch.setattr(ps, "_run", fake_run)
    ordered = ps._ordered([_rt("docker"), _rt("podman")], "penpotx")
    assert [d["runtime"] for d in ordered] == ["podman", "docker"]


def _restore_args(tmp_path, monkeypatch, table_count):
    calls = []

    def fake_exec(args, pg_argv, stdin=None, stdout=None):
        calls.append(pg_argv[0])
        if pg_argv[0] == "psql":
            stdout.write(f"{table_count}\n")
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(ps, "_exec_pg", fake_exec)
    monkeypatch.setattr(ps, "_compose", lambda args, extra, with_secrets=False: subprocess.CompletedProcess([], 0))
    dump = tmp_path / "penpot.dump"
    dump.write_bytes(b"x")
    args = ps.build_parser().parse_args(["--state-dir", str(tmp_path), "restore", "--in", str(dump)])
    return args, calls


def test_restore_refuses_a_populated_database_before_stopping_anything(tmp_path, monkeypatch, capsys):
    args, calls = _restore_args(tmp_path, monkeypatch, table_count=61)
    rc = ps.cmd_restore(args)
    assert rc == 2
    assert "pg_restore" not in calls
    assert "already has 61 tables" in capsys.readouterr().err


def test_restore_proceeds_on_an_empty_database(tmp_path, monkeypatch):
    args, calls = _restore_args(tmp_path, monkeypatch, table_count=0)
    monkeypatch.setattr(ps, "cmd_up", lambda a: 0)
    assert ps.cmd_restore(args) == 0
    assert "pg_restore" in calls
