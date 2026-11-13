"""Headless single-turn runner: one ``call_claude_streaming`` turn in a throwaway CorvinOS home.

Contract (fixed, called by the Harbor agent):

    python -m corvin_harness_runner --instruction-file PATH|- --workdir DIR --out-dir DIR
        --model ID [--effort low|medium|high|max] [--timeout-s N] [--max-output-tokens N]
        [--context-window N] [--corvin-root PATH] [--version]

The endpoint and key come ONLY from the environment (ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN),
never from argv. No gate (L34/L35/L44) and no audit write is switched off here: the runner only
OBSERVES them (wrappers that record and return the unchanged result).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from . import (EXIT_COMPLETED, EXIT_ENGINE_ERROR, EXIT_REFUSED, EXIT_TIMEOUT, EXIT_USAGE,
               __version__)

PROVIDER_ID = "harness_meter"
CREDENTIAL_ENV = "HLB_PROVIDER_KEY"
CHANNEL = "harness"
CHAT_KEY = "single-turn"

# Opt-outs set for the whole process (and therefore inherited by the claude worker).
OPT_OUT_ENV = {
    "CORVIN_TELEMETRY_OPTIN": "false",
    "CORVIN_GEO_OPT_OUT": "1",
    "CORVIN_CONSOLE_NO_AUTOBUILD": "1",
    "CORVIN_A2A_INGRESS": "off",
    "CORVIN_TELEMETRY_URL": "",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_AUTOUPDATER": "1",
}
# Left over from a parent shell, any of these would change what the turn is.
SCRUB_ENV = ("ADAPTER_FAKE_CLAUDE", "CORVIN_ATO_M5_ENABLED", "CORVIN_ATO_M7_ENABLED",
             "CORVIN_CHANNEL_ID", "CORVIN_CC_PROVIDER", "CORVIN_CC_LOCAL_MODE", "FORGE_ROOT",
             "CORVIN_TENANT_ID", "ANTHROPIC_API_KEY", "ANTHROPIC_API_BASE")

TENANT_ID = "_default"


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # exit 64, never argparse's 2 (2 means "refused")
        raise _Usage(message)


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="corvin_harness_runner", add_help=True)
    p.add_argument("--instruction-file", help="path to the task text, or '-' for stdin")
    p.add_argument("--workdir")
    p.add_argument("--out-dir")
    p.add_argument("--model")
    p.add_argument("--effort", choices=["low", "medium", "high", "max"])
    p.add_argument("--timeout-s", type=float, default=0)
    p.add_argument("--max-output-tokens", type=int)
    p.add_argument("--context-window", type=int)
    p.add_argument("--corvin-root")
    p.add_argument("--version", action="store_true")
    return p


# ---------------------------------------------------------------- install location

def _source_root(explicit: str | None) -> Path | None:
    cand = explicit or os.environ.get("CORVIN_ROOT")
    if not cand:
        return None
    root = Path(cand).resolve()
    return root if (root / "corvin_operator" / "bridges" / "shared" / "adapter.py").is_file() else None


def _corvinos_version(root: Path | None) -> str:
    try:
        from importlib.metadata import version
        return version("corvinos")
    except Exception:  # noqa: BLE001
        pass
    if root is not None:
        try:
            for line in (root / "pyproject.toml").read_text("utf-8").splitlines():
                if line.startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    return "unknown"


def _corvin_commit(root: Path | None) -> str:
    env = os.environ.get("CORVIN_COMMIT", "").strip()
    if env:
        return env
    if root is not None and (root / ".git").exists():
        try:
            out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                                 text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except Exception:  # noqa: BLE001
            pass
    return "unknown"


def _version_line(root: Path | None) -> str:
    return (f"corvin-harness-runner {__version__} corvinos {_corvinos_version(root)} "
            f"commit {_corvin_commit(root)}")


def _import_adapter(root: Path | None):
    """Source tree: put the three roots on sys.path. Wheel: the vendored tree via the bootstrap."""
    if root is not None:
        for sub in ("corvin_operator/bridges/shared", "corvin_operator/forge", "core/console", ""):
            p = str(root / sub) if sub else str(root)
            if p not in sys.path:
                sys.path.insert(0, p)
    else:
        from corvin_core._operator_bootstrap import ensure_operator_on_path
        if not ensure_operator_on_path():
            raise ImportError("no CorvinOS source tree (--corvin-root) and no vendored operator tree")
        # A wheel ships the operator tree as corvin_core/_vendor/corvin_operator, but adapter.py's
        # chat-turn quota gate imports `corvin_operator.forge.forge.paths`. Without that package the
        # gate cannot import and refuses EVERY turn (fail-closed). Alias the vendored directory so the
        # gate runs (it is enabled here, not bypassed).
        if "corvin_operator" not in sys.modules:
            import types
            from corvin_core._operator_bootstrap import vendor_operator_root
            vroot = vendor_operator_root()
            if vroot is not None:
                alias = types.ModuleType("corvin_operator")
                alias.__path__ = [str(vroot)]  # type: ignore[attr-defined]
                sys.modules["corvin_operator"] = alias
    import adapter  # type: ignore
    return adapter


# ---------------------------------------------------------------- sandbox

def _write_secret(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def _yaml_dump(obj: Any) -> str:
    import yaml
    return yaml.safe_dump(obj, sort_keys=False)


def _build_sandbox(base: Path, *, out_dir: Path, model: str, base_url: str, adapter_registry: Path | None
                   ) -> dict[str, Path]:
    home = base / "corvin_home"
    xdg = base / "xdg_config"
    anchor = base / "audit_anchor.key"
    for d in (home, xdg, base / "xdg_data", base / "xdg_cache", base / "helper_claude"):
        d.mkdir(parents=True, exist_ok=True)
    if not anchor.exists():  # never re-key: records written before this point carry its MAC
        _write_secret(anchor, os.urandom(32).hex())

    spec: dict[str, Any] = {
        "telemetry": {"ping_enabled": False, "healing_traces": False, "error_traces": False},
        "engine_models": {"claude_code": {"os_model": model}},
    }
    if base_url:
        spec["engine_models"]["claude_code"]["provider"] = PROVIDER_ID
        if adapter_registry is not None:
            import yaml
            reg = yaml.safe_load(adapter_registry.read_text("utf-8")) or {}
            reg.setdefault("providers", {})[PROVIDER_ID] = {
                "label": "Harness meter", "base_url": base_url, "proxy_base_url": base_url,
                "model_source": "static", "credential_env": CREDENTIAL_ENV, "kind": "cloud",
            }
            _write_secret(base / "engine_model_registry.yaml", _yaml_dump(reg))
    tdir = home / "tenants" / TENANT_ID / "global"
    tdir.mkdir(parents=True, exist_ok=True)
    _write_secret(tdir / "tenant.corvin.yaml", _yaml_dump({"spec": spec}))  # 0600: read fail-closed
    return {"home": home, "xdg": xdg, "anchor": anchor, "base": base,
            "registry": base / "engine_model_registry.yaml"}


def _seed_login(config_dir: Path) -> None:
    """Login mode (no endpoint): copy the operator's Claude Code login into a THROWAWAY config dir,
    mode 0600. The login never goes to out-dir; only the session files are copied out, afterwards."""
    src = Path(os.path.expanduser("~")) / ".claude" / ".credentials.json"
    if not src.is_file():
        raise RuntimeError(f"no Claude Code login at {src}; run `claude /login` or pass an endpoint")
    config_dir.mkdir(parents=True, exist_ok=True)
    dst = config_dir / ".credentials.json"
    shutil.copyfile(src, dst)
    os.chmod(dst, 0o600)


def _apply_env(sb: dict[str, Path], out_dir: Path, args, base_url: str, token: str,
               helper_model: str) -> None:
    for k in SCRUB_ENV:
        os.environ.pop(k, None)
    os.environ.update({
        "CORVIN_HOME": str(sb["home"]), "XDG_CONFIG_HOME": str(sb["xdg"]),
        "XDG_DATA_HOME": str(sb["base"] / "xdg_data"), "XDG_CACHE_HOME": str(sb["base"] / "xdg_cache"),
        "CORVIN_AUDIT_ANCHOR_KEY": str(sb["anchor"]),
        "CLAUDE_CONFIG_DIR": str(out_dir / "sessions"),
        # L44's classifier is a separate `claude -p`; it must use the same model/endpoint.
        "CORVIN_HELPER_MODEL": helper_model,
        "CORVIN_HELPER_MODEL_HOUSE_RULES_ADJUDICATOR": helper_model,
        **OPT_OUT_ENV,
    })
    if args.effort:
        os.environ["CLAUDE_CODE_EFFORT_LEVEL"] = args.effort
    if args.max_output_tokens:
        os.environ["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(args.max_output_tokens)
    if args.context_window:
        os.environ["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(args.context_window)
    if base_url:
        # Kept in os.environ for the L44 helper (`claude -p` inherits it); the worker gets its own
        # copy from the provider route. The key goes through the declared credential variable.
        os.environ["ANTHROPIC_BASE_URL"] = base_url
        os.environ["ANTHROPIC_AUTH_TOKEN"] = token
        os.environ[CREDENTIAL_ENV] = token


# ---------------------------------------------------------------- observers

class _Obs:
    def __init__(self, events_path: Path):
        self.lock = threading.Lock()
        self.gates: list[str] = []
        self.refusals: list[dict[str, str]] = []
        self.engines: list[Any] = []
        self.usage: dict[str, int] = {}
        self.model_reported = ""
        self.cost: float | None = None
        self.completed = False
        self.error_events: list[str] = []
        self.fh = open(events_path, "w", encoding="utf-8")

    def gate(self, name: str) -> None:
        with self.lock:
            if name not in self.gates:
                self.gates.append(name)

    def event(self, ev: Any) -> None:
        rec = {"t": round(time.time(), 3), "type": getattr(ev, "type", "?"),
               "text": getattr(ev, "text", "") or "", "usage": getattr(ev, "usage", None),
               "error": getattr(ev, "error", None), "raw": getattr(ev, "raw", None)}
        with self.lock:
            self.fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self.fh.flush()
            if rec["type"] == "turn_completed":
                self.completed = True
                if rec["usage"]:
                    self.usage = dict(rec["usage"])
                raw = rec["raw"] or {}
                if isinstance(raw, dict) and isinstance(raw.get("total_cost_usd"), (int, float)):
                    self.cost = float(raw["total_cost_usd"])
            if rec["type"] == "session_started" and isinstance(rec["raw"], dict):
                self.model_reported = str(rec["raw"].get("model") or self.model_reported)
            if rec["type"] == "error" or rec["error"]:
                self.error_events.append(str(rec["error"] or rec["text"])[:200])


def _install_observers(adapter, obs: _Obs, helper_dir: Path) -> None:
    import spawn_gates  # type: ignore

    def wrap_gate(mod, attr: str, label: str):
        orig = getattr(mod, attr)

        def wrapped(*a, **kw):
            obs.gate(label)
            return orig(*a, **kw)
        wrapped.__name__ = attr
        setattr(mod, attr, wrapped)

    wrap_gate(spawn_gates, "check_l34", "L34")
    wrap_gate(spawn_gates, "check_l35", "L35")

    orig_hr = adapter._check_house_rules_or_fail

    def hr(*a, **kw):
        obs.gate("L44")
        # The L44 classifier is its own `claude -p`; keep ITS session files out of out-dir/sessions
        # (the Harbor converter must only see the worker's session).
        prev = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(helper_dir)
        try:
            return orig_hr(*a, **kw)
        finally:
            if prev is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = prev
    adapter._check_house_rules_or_fail = hr

    orig_ref = adapter._turn_refused

    def refused(reason, retry_count=None, *, cancelled=False):
        if not cancelled and reason not in adapter._ENGINE_FAILURE_REASONS:
            with obs.lock:
                obs.refusals.append({"gate": _gate_of(str(reason)), "reason": str(reason)})
        return orig_ref(reason, retry_count, cancelled=cancelled)
    adapter._turn_refused = refused

    base_cls = adapter._ClaudeCodeEngine

    class _TeeEngine(base_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            obs.engines.append(self)

        def spawn(self, *a, **kw):
            for ev in super().spawn(*a, **kw):
                obs.event(ev)
                yield ev
    adapter._ClaudeCodeEngine = _TeeEngine


def _gate_of(reason: str) -> str:
    return {"house_rules": "L44", "l34_compliance": "L34", "l34_block": "L34", "egress": "L35",
            "l34_route_unavailable": "L34"}.get(reason, reason)


def _kill_descendants() -> None:
    me = os.getpid()
    kids: dict[int, list[int]] = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            ppid = int((d / "stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        kids.setdefault(ppid, []).append(int(d.name))
    stack, found = [me], []
    while stack:
        for c in kids.get(stack.pop(), []):
            found.append(c)
            stack.append(c)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in found:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        time.sleep(0.3)


# ---------------------------------------------------------------- main

def _norm_usage(u: dict[str, Any]) -> dict[str, int]:
    def g(*names: str) -> int:
        for n in names:
            if isinstance(u.get(n), (int, float)):
                return int(u[n])
        return 0
    return {"input": g("input", "input_tokens"), "output": g("output", "output_tokens"),
            "cache_read": g("cache_read", "cache_read_input_tokens"),
            "cache_write": g("cache_write", "cache_creation_input_tokens")}


def _read_instruction(spec: str) -> str:
    if spec == "-":
        return sys.stdin.buffer.read().decode("utf-8")
    return Path(spec).read_text("utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _parser().parse_args(argv)
        root = _source_root(args.corvin_root)
        if args.version:
            print(_version_line(root))
            return EXIT_COMPLETED
        for need in ("instruction_file", "workdir", "out_dir", "model"):
            if not getattr(args, need):
                raise _Usage(f"missing --{need.replace('_', '-')}")
    except _Usage as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except SystemExit as exc:  # --help
        return int(exc.code or 0)

    out_dir = Path(args.out_dir).resolve()
    workdir = Path(args.workdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sessions").mkdir(exist_ok=True)
    try:
        instruction = _read_instruction(args.instruction_file)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"usage error: cannot read instruction: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not workdir.is_dir() or not instruction.strip():
        print("usage error: workdir missing or instruction empty", file=sys.stderr)
        return EXIT_USAGE

    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    started = time.monotonic()
    result: dict[str, Any] = {
        "status": "engine_error", "answer": "", "refusals": [],
        "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, "cost_usd": None,
        "model": args.model, "effort": args.effort, "corvin_version": _corvinos_version(root),
        "corvin_commit": _corvin_commit(root), "gates_ran": [], "duration_s": 0.0,
    }
    keep_home = os.environ.get("CORVIN_HARNESS_KEEP_HOME") == "1"
    base = Path(tempfile.mkdtemp(prefix="hlb-corvin-"))
    # Some Corvin stores (skill-forge) resolve `<repo root of the CWD>/.corvin`; never let that be a
    # task repository or the caller's checkout. All paths used later are absolute.
    os.chdir(base)
    code = EXIT_ENGINE_ERROR
    obs = _Obs(out_dir / "events.jsonl")
    try:
        # the engine/registry live in the adapter tree: locate it first (needed for the registry copy)
        scratch_home = base / "corvin_home"
        os.environ["CORVIN_HOME"] = str(scratch_home)  # import-time side effects stay in the sandbox
        os.environ["XDG_CONFIG_HOME"] = str(base / "xdg_config")
        os.environ["CORVIN_AUDIT_ANCHOR_KEY"] = str(base / "audit_anchor.key")
        (base / "xdg_config").mkdir(parents=True, exist_ok=True)
        scratch_home.mkdir(parents=True, exist_ok=True)
        _write_secret(base / "audit_anchor.key", os.urandom(32).hex())
        for k, v in OPT_OUT_ENV.items():
            os.environ[k] = v
        for k in SCRUB_ENV:
            if k not in ("ANTHROPIC_API_KEY",):
                os.environ.pop(k, None)
        adapter = _import_adapter(root)
        import engine_models  # type: ignore
        reg_src = Path(engine_models._REGISTRY_FILE)
        sb = _build_sandbox(base, out_dir=out_dir, model=args.model, base_url=base_url,
                            adapter_registry=reg_src if base_url else None)
        # The model is the board's PIN and must reach the worker (and the L44 helper) byte for byte:
        # the meter routes on the full "org/model:provider" id. model_selector.normalise_pin cuts a
        # "provider/" prefix (right for the Anthropic API, wrong for this route), so for THIS one id
        # the runner answers the pin question itself. Runner-local; CorvinOS files are untouched.
        import model_selector  # type: ignore
        _orig_pin = model_selector.normalise_pin

        def _pin(model, engine_id, _o=_orig_pin, _m=args.model):
            return _m if isinstance(model, str) and model.strip() == _m else _o(model, engine_id)
        model_selector.normalise_pin = _pin
        helper_model = args.model
        result["model_sent"] = helper_model
        _apply_env(sb, out_dir, args, base_url, token, helper_model)
        login_dir = base / "cc_login"
        if not base_url:
            # login mode: worker and L44 classifier run on the operator's own Claude Code login
            _seed_login(login_dir)
            _seed_login(base / "helper_claude")
            os.environ["CLAUDE_CONFIG_DIR"] = str(login_dir)
        if base_url:
            engine_models._REGISTRY_FILE = sb["registry"]
            engine_models._registry_cache = None
            engine_models._providers_cache = None
        _install_observers(adapter, obs, base / "helper_claude")
        # The worker starts in the chat's session directory, never in the task directory, so a task's
        # relative paths resolve in the wrong place. Runner-local fix: that session directory becomes a
        # link to the task's workdir inside this run's throwaway home; the adapter's own paths are unchanged.
        session = Path(adapter._session_dir(CHANNEL, CHAT_KEY))
        if session.is_symlink() or session.is_dir():
            session.unlink() if session.is_symlink() else shutil.rmtree(session)
        session.parent.mkdir(parents=True, exist_ok=True)
        session.symlink_to(workdir, target_is_directory=True)

        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["answer"] = adapter.call_claude_streaming(
                    instruction, channel=CHANNEL, chat_key=CHAT_KEY, mode="unrestricted",
                    add_dir=str(workdir), on_status=None, status_mode="compact", profile=None,
                    msg_id="harness-1", sender="harness")
                out = getattr(adapter._TURN_OUTCOME, "failed", None)
                box["failed"] = str(out) if out else ""
            except BaseException as exc:  # noqa: BLE001
                box["exc"] = f"{type(exc).__name__}: {exc}"[:300]

        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        th = threading.Thread(target=work, daemon=True, name="harness-turn")
        th.start()
        deadline = time.monotonic() + args.timeout_s if args.timeout_s else None
        timed_out = False
        while th.is_alive():
            th.join(0.25)
            if stop.is_set() or (deadline and time.monotonic() > deadline):
                timed_out = True
                for eng in list(obs.engines):
                    try:
                        eng.cancel()
                    except Exception:  # noqa: BLE001
                        pass
                _kill_descendants()
                break
        result["answer"] = str(box.get("answer") or "")
        if timed_out:
            code, result["status"] = EXIT_TIMEOUT, "timeout"
        elif obs.refusals:
            code, result["status"] = EXIT_REFUSED, "refused"
            result["refusals"] = [dict(r, reason=(result["answer"] or r["reason"])[:500])
                                  for r in obs.refusals]
        elif "exc" in box or box.get("failed") or not obs.completed:
            code, result["status"] = EXIT_ENGINE_ERROR, "engine_error"
            result["error"] = box.get("exc") or box.get("failed") or "; ".join(obs.error_events) \
                or "the worker produced no completed turn"
        else:
            code, result["status"] = EXIT_COMPLETED, "completed"
        result["usage"] = _norm_usage(obs.usage)
        # The CLI prices with ITS table; for a redirected (non-Anthropic) model that number is not a cost.
        result["cost_usd"] = obs.cost if (obs.cost is not None and not base_url) else None
        if obs.model_reported:
            result["model_reported"] = obs.model_reported
        chain = sb["home"] / "tenants" / TENANT_ID / "global" / "forge" / "audit.jsonl"
        if chain.is_file():
            (out_dir / "audit.jsonl").write_bytes(chain.read_bytes())
        if keep_home:
            result["sandbox_home"] = str(sb["home"])
    except BaseException as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"[:400]
        code, result["status"] = EXIT_ENGINE_ERROR, "engine_error"
    finally:
        result["gates_ran"] = list(obs.gates)
        result["duration_s"] = round(time.monotonic() - started, 3)
        (out_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), "utf-8")
        try:
            obs.fh.close()
        except Exception:  # noqa: BLE001
            pass
        login_sessions = base / "cc_login" / "projects"
        if login_sessions.is_dir():
            shutil.copytree(login_sessions, out_dir / "sessions" / "projects", dirs_exist_ok=True)
        if not keep_home or (base / "cc_login").exists():
            shutil.rmtree(base, ignore_errors=True)  # a kept home would keep the login copy: never kept in login mode
    return code
