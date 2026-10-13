#!/usr/bin/env python3
"""Optional Penpot stack (Strang B) for the Video Producer: detect | up | down | status | health.

Standard library only. The stack is never required: ``detect`` exits non-zero
when no container runtime with a compose provider exists, and callers must then
not offer the design strand.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_COMPOSE = HERE / "compose.yaml"
DEFAULT_PORT = 9001
DEFAULT_PROJECT = "penpot"
EXIT_NO_RUNTIME = 3
PROBE_TIMEOUT_S = 20


def _run(argv, timeout=PROBE_TIMEOUT_S):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p


def _ok(argv):
    p = _run(argv)
    return p is not None and p.returncode == 0


def detect() -> dict:
    """Pick docker first, then podman. Returns runtime, compose argv and a reason when unusable."""
    reasons = []
    for rt in ("docker", "podman"):
        exe = shutil.which(rt)
        if not exe:
            reasons.append(f"{rt}: not found on PATH")
            continue
        if not _ok([exe, "--version"]):
            reasons.append(f"{rt}: `{rt} --version` failed")
            continue
        if not _ok([exe, "info"]):
            reasons.append(f"{rt}: installed but `{rt} info` failed (daemon not running or no permission)")
            continue
        candidates = [[exe, "compose"], ]
        if rt == "docker":
            dc = shutil.which("docker-compose")
            if dc:
                candidates.append([dc])
        else:
            pc = shutil.which("podman-compose")
            if pc:
                candidates.insert(0, [pc])
        for cmd in candidates:
            if _ok(cmd + ["version"] if cmd[-1] == "compose" else cmd + ["--version"]):
                p = _run([exe, "--version"])
                return {"runtime": rt, "runtime_path": exe, "compose": cmd,
                        "version": (p.stdout.strip() if p else ""), "reason": None}
        reasons.append(f"{rt}: present but no compose provider "
                       f"({'docker compose plugin' if rt == 'docker' else 'podman-compose'}) works")
    return {"runtime": None, "runtime_path": None, "compose": None, "version": "",
            "reason": "; ".join(reasons)}


def _state_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("CORVIN_PENPOT_STACK_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "corvin" / "penpot-stack"
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "corvin" / "penpot-stack"


def secrets_path(state_dir: Path, project: str) -> Path:
    return state_dir / f"{project}.secrets.json"


def ensure_secrets(state_dir: Path, project: str) -> dict:
    """Create random secrets once; the file is created 0600 from the start (no readable window)."""
    path = secrets_path(state_dir, project)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("PENPOT_SECRET_KEY") and data.get("PENPOT_DB_PASSWORD"):
            return data
    state_dir.mkdir(parents=True, exist_ok=True)
    data = {"PENPOT_SECRET_KEY": secrets.token_urlsafe(64),
            "PENPOT_DB_PASSWORD": secrets.token_urlsafe(24)}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return data


def _env(args, with_secrets: bool) -> dict:
    env = dict(os.environ)
    env["PENPOT_PORT"] = str(args.port)
    if with_secrets:
        env.update(ensure_secrets(_state_dir(args.state_dir), args.project))
    else:
        sp = secrets_path(_state_dir(args.state_dir), args.project)
        if sp.exists():
            env.update(json.loads(sp.read_text(encoding="utf-8")))
        else:
            env.setdefault("PENPOT_SECRET_KEY", "unused")
            env.setdefault("PENPOT_DB_PASSWORD", "unused")
    return env


def redact(text: str, env: dict) -> str:
    """podman-compose echoes every container's -e KEY=VALUE pairs; never let the secrets reach a terminal or log."""
    for k in ("PENPOT_SECRET_KEY", "PENPOT_DB_PASSWORD"):
        v = env.get(k)
        if v and v != "unused":
            text = text.replace(v, "***")
    return text


def _run_redacted(argv, env, stdin=None, stdout=None):
    """Run argv; its stderr (and stdout unless redirected) is streamed through redact()."""
    merge = stdout is None
    proc = subprocess.Popen(argv, env=env, stdin=stdin, stdout=subprocess.PIPE if merge else stdout,
                            stderr=subprocess.STDOUT if merge else subprocess.PIPE,
                            text=True, errors="replace")
    stream = proc.stdout if merge else proc.stderr
    out = sys.stdout if merge else sys.stderr
    for line in stream:
        out.write(redact(line, env))
    return subprocess.CompletedProcess(argv, proc.wait())


def _compose(args, extra, with_secrets=False):
    d = detect()
    if not d["runtime"]:
        _no_runtime(d)
        return None
    argv = d["compose"] + ["-p", args.project, "-f", str(Path(args.compose_file))] + extra
    return _run_redacted(argv, _env(args, with_secrets))


def _no_runtime(d):
    print("penpot-stack: no usable container runtime (docker or podman with compose). "
          "The Penpot design strand is not available on this host. "
          f"Details: {d['reason']}", file=sys.stderr)


def health(port: int, timeout: float = 5.0) -> dict:
    """Frontend serves the SPA; an anonymous get-profile call proves nginx -> backend -> postgres."""
    base = f"http://127.0.0.1:{port}"
    out = {}
    for name, path in (("frontend", "/"), ("backend", "/api/rpc/command/get-profile")):
        try:
            req = urllib.request.Request(base + path, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out[name] = r.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            out[name] = False
    out["healthy"] = all(out.values())
    return out


def cmd_detect(args):
    d = detect()
    print(json.dumps(d))
    if not d["runtime"] or not d["compose"]:
        _no_runtime(d)
        return EXIT_NO_RUNTIME
    return 0


def cmd_up(args):
    t0 = time.monotonic()
    p = _compose(args, ["up", "-d"], with_secrets=True)
    if p is None:
        return EXIT_NO_RUNTIME
    if p.returncode != 0:
        print("penpot-stack: compose up failed", file=sys.stderr)
        return p.returncode
    t_up = time.monotonic() - t0
    deadline = time.monotonic() + args.wait
    h = health(args.port)
    while not h["healthy"] and time.monotonic() < deadline:
        time.sleep(2)
        h = health(args.port)
    t_total = time.monotonic() - t0
    print(json.dumps({"up_seconds": round(t_up, 1), "healthy_after_seconds": round(t_total, 1), **h}))
    return 0 if h["healthy"] else 1


def cmd_down(args):
    extra = ["down"] + (["-v"] if args.volumes else [])
    p = _compose(args, extra)
    if p is None:
        return EXIT_NO_RUNTIME
    d = detect()
    if d["runtime"] == "podman":
        # podman-compose 1.0.6 leaves the project network behind (measured)
        subprocess.run([d["runtime_path"], "network", "rm", f"{args.project}_penpot"],
                       capture_output=True, timeout=PROBE_TIMEOUT_S)
    return p.returncode


def _exec_pg(args, pg_argv, stdin=None, stdout=None):
    d = detect()
    if not d["runtime"]:
        _no_runtime(d)
        return None
    argv = d["compose"] + ["-p", args.project, "-f", str(Path(args.compose_file)),
                           "exec", "-T", "penpot-postgres"] + pg_argv
    return _run_redacted(argv, _env(args, False), stdin=stdin, stdout=stdout or None)


def cmd_backup(args):
    """pg_dump (custom format) of the Penpot database. Uploaded media in the assets volume is NOT included."""
    out = Path(args.out)
    tmp = out.with_name(out.name + ".part")
    with open(tmp, "wb") as fh:
        p = _exec_pg(args, ["pg_dump", "-U", "penpot", "-Fc", "penpot"], stdout=fh)
    if p is None:
        return EXIT_NO_RUNTIME
    if p.returncode != 0 or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        print("penpot-stack: pg_dump failed", file=sys.stderr)
        return p.returncode or 1
    os.replace(tmp, out)
    print(json.dumps({"backup": str(out), "bytes": out.stat().st_size}))
    return 0


def cmd_restore(args):
    """Restore a backup into a stopped-application stack: only postgres runs while pg_restore executes."""
    src = Path(args.src)
    if not src.is_file():
        print(f"penpot-stack: backup file not found: {src}", file=sys.stderr)
        return 2
    p = _compose(args, ["stop", "penpot-frontend", "penpot-backend", "penpot-exporter", "penpot-admin-console"])
    if p is None:
        return EXIT_NO_RUNTIME
    p = _compose(args, ["up", "-d", "penpot-postgres"], with_secrets=True)
    if p.returncode != 0:
        return p.returncode
    deadline = time.monotonic() + 60
    while _exec_pg(args, ["pg_isready", "-U", "penpot"], stdout=subprocess.DEVNULL).returncode != 0:
        if time.monotonic() > deadline:
            print("penpot-stack: postgres did not become ready", file=sys.stderr)
            return 1
        time.sleep(2)
    with open(src, "rb") as fh:
        p = _exec_pg(args, ["pg_restore", "-U", "penpot", "-d", "penpot", "--clean", "--if-exists",
                            "--no-owner"], stdin=fh)
    if p.returncode != 0:
        print("penpot-stack: pg_restore reported errors (see output above)", file=sys.stderr)
        return p.returncode
    return cmd_up(args)


def cmd_status(args):
    p = _compose(args, ["ps"])
    if p is None:
        return EXIT_NO_RUNTIME
    return p.returncode


def cmd_health(args):
    h = health(args.port)
    print(json.dumps(h))
    return 0 if h["healthy"] else 1


def build_parser():
    ap = argparse.ArgumentParser(prog="penpot_stack", description=__doc__)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--project", default=DEFAULT_PROJECT, help="compose project name")
    ap.add_argument("--compose-file", default=str(DEFAULT_COMPOSE))
    ap.add_argument("--state-dir", default=None, help="where the 0600 secrets file lives")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect").set_defaults(fn=cmd_detect)
    up = sub.add_parser("up")
    up.add_argument("--wait", type=int, default=300, help="seconds to wait for health")
    up.set_defaults(fn=cmd_up)
    dn = sub.add_parser("down")
    dn.add_argument("--volumes", action="store_true", help="also delete the named volumes (data loss)")
    dn.set_defaults(fn=cmd_down)
    bk = sub.add_parser("backup")
    bk.add_argument("--out", required=True)
    bk.set_defaults(fn=cmd_backup)
    rs = sub.add_parser("restore")
    rs.add_argument("--in", dest="src", required=True)
    rs.add_argument("--wait", type=int, default=300)
    rs.set_defaults(fn=cmd_restore)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("health").set_defaults(fn=cmd_health)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except subprocess.TimeoutExpired:
        print("penpot-stack: command timed out", file=sys.stderr)
        return 124
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
