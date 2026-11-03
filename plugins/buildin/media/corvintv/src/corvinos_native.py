"""The two CorvinOS-native engines CorvinTV uses — and nothing else (1.8.0).

* **LLM: the native Claude Code engine.** Every LLM step (storyboard, web-slide repair,
  grounded-claims repair) is one tool-less ``claude -p`` call of the host's own, signed-in
  Claude Code CLI. There is no other backend and no fallback: a host without a usable CLI
  fails the job with :class:`ClaudeEngineUnavailable` instead of quietly switching engines.
  The binary is the one the console resolves (``CORVIN_CLAUDE_BIN``, which the console's
  ``_job_env`` pins to its own ``helper_model.resolve_claude_bin()``), else PATH, else the
  host's resolver; a Windows ``claude.cmd`` shim is spawned through the host's cmd.exe-safe
  ``_win_shim`` (the prompt always travels over stdin).

* **Narration: the CorvinOS TTS chain.** ``corvin_console.native_tts`` — the chat TTS
  chain (say.py: openai -> edge -> piper, ``CORVIN_TTS_PROVIDER``, the tenant profile,
  ``CORVIN_TTS_LOCAL_ONLY``, length-scaled deadlines). CorvinTV has no TTS of its own.
  On a host whose console predates that module, the same helpers are taken from the chat
  route itself (``corvin_console.routes.voice``) - still the native chain, never a copy.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union


# --------------------------------------------------------------------------------------------
# Claude Code CLI
# --------------------------------------------------------------------------------------------

class ClaudeEngineUnavailable(RuntimeError):
    """The native Claude Code engine cannot be used for this job (CLI missing, not signed in,
    failed or answered with an error). The job fails with this message; nothing else is tried."""


def _host_module(name: str):
    """A module of the host's ``corvin_operator/bridges/shared`` tree (on sys.path once
    ``corvin_console``/``corvin_core`` is imported), or None outside CorvinOS."""
    try:
        return __import__(name)
    except Exception:  # noqa: BLE001
        pass
    try:
        import corvin_console  # noqa: F401,PLC0415 - its bootstrap puts bridges/shared on sys.path
        return __import__(name)
    except Exception:  # noqa: BLE001
        return None


def _known_claude_locations() -> List[str]:
    """Off-PATH install locations of the Claude Code CLI (a service / job process often runs with a
    stripped PATH). The host's own resolver is preferred - it is what the console chat spawns - and this
    short list is the standalone fallback, Windows npm / native-installer dirs included."""
    home = os.path.expanduser("~")
    out = [os.path.join(home, ".local", "bin", "claude"), "/usr/local/bin/claude", "/opt/homebrew/bin/claude",
           os.path.join(home, ".claude", "local", "claude")]
    for var, rel in (("APPDATA", ("npm", "claude.cmd")), ("APPDATA", ("npm", "claude.exe")),
                     ("USERPROFILE", (".local", "bin", "claude.exe"))):
        base = os.environ.get(var)
        if base:
            out.append(os.path.join(base, *rel))
    return out


def claude_cli_path() -> Optional[str]:
    """The Claude Code CLI the host runs: the canonical pin ``CORVIN_CLAUDE_BIN`` (exact, never
    second-guessed), else PATH, else the host's own resolver (known install dirs, nvm, Windows
    shims), else the standalone list of known install locations. None when there is none."""
    pinned = (os.environ.get("CORVIN_CLAUDE_BIN") or "").strip()
    if pinned:
        return pinned if os.path.isfile(pinned) and os.access(pinned, os.X_OK) else None
    found = shutil.which("claude")
    if found:
        return found
    hm = _host_module("helper_model")
    if hm is not None:
        try:
            cand = hm.resolve_claude_bin()
            if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
        except Exception:  # noqa: BLE001
            pass
    for cand in _known_claude_locations():
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def is_cmd_shim(exe: str) -> bool:
    return os.name == "nt" and exe.lower().endswith((".cmd", ".bat"))


def _win_shim_module():
    """CorvinOS's cmd.exe-safe shim launcher (``bridges/shared/agents/_win_shim.py``), None outside CorvinOS."""
    try:
        from agents import _win_shim as shim  # type: ignore[import-not-found]  # noqa: PLC0415 - bridges/shared
        return shim
    except Exception:  # noqa: BLE001
        mod = _host_module("agents._win_shim")
        return getattr(mod, "_win_shim", None) if mod is not None else None


def spawnable(argv: Sequence[str]) -> Union[List[str], str]:
    """``argv`` ready for ``Popen``. A Windows ``.cmd``/``.bat`` shim cannot be started by
    CreateProcess and must not go through ``list2cmdline`` + cmd.exe (metachar breakout), so it
    becomes the host's cmd.exe-safe command line; everything else stays a list, byte-identical."""
    argv = list(argv)
    if not argv or not is_cmd_shim(argv[0]):
        return argv
    shim = _win_shim_module()
    if shim is None:
        raise ClaudeEngineUnavailable(
            f"the Claude Code CLI is a Windows shim ({os.path.basename(argv[0])}) and CorvinOS's safe shim "
            "launcher (agents/_win_shim.py) is not importable; set CORVIN_CLAUDE_BIN to claude.exe")
    return shim.resolve_cli_argv(argv)


# --------------------------------------------------------------------------------------------
# CorvinOS TTS chain
# --------------------------------------------------------------------------------------------

class NativeTTSMissing(RuntimeError):
    """The CorvinOS TTS chain is not importable in this process (CorvinTV runs inside CorvinOS)."""


@dataclass
class TTSPlan:
    """One synthesis, prepared by the host: run ``argv`` with ``env`` within ``timeout_s``."""
    argv: List[str]
    env: Dict[str, str]
    timeout_s: float
    out_path: Path
    api: Any = field(repr=False, default=None)


class _RouteShim:
    """``native_tts`` for a console that predates it: the same chat-route helpers, wrapped."""

    API_VERSION = 0
    AUTO_CHAIN = ("openai", "edge", "piper")

    def __init__(self, voice):
        self._v = voice

    def expected_provider(self) -> str:
        return self._v._resolve_tts_provider() or self.AUTO_CHAIN[0]

    def prepare(self, text: str, out_path: Path, lang: str):
        sp = self._v._VOICE_SCRIPTS / "say.py"
        if not sp.is_file():
            raise NativeTTSMissing(f"say.py missing at {sp}")
        return TTSPlan(argv=list(self._v._say_cmd(Path(out_path), text, lang)), env=self._v._say_env(),
                       timeout_s=float(self._v._tts_timeout_for(text)), out_path=Path(out_path))

    def provider_from_stderr(self, stderr: str) -> str:
        m = self._v._say_provider(stderr or "")
        return m.split(":", 1)[1] if ":" in m else ""

    @staticmethod
    def reasons_from_stderr(stderr: str, limit: int = 8) -> List[str]:
        lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip().startswith("say.py:")]
        return [ln[:200] for ln in lines if "provider=" not in ln][-limit:]


_TTS_API: Any = None


def tts_api():
    """The host's native TTS API (cached per process). Raises :class:`NativeTTSMissing`."""
    global _TTS_API
    if _TTS_API is not None:
        return _TTS_API
    try:
        from corvin_console import native_tts as api  # noqa: PLC0415
        _TTS_API = api
        return api
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        raise NativeTTSMissing(f"the CorvinOS TTS chain failed to load ({type(e).__name__}: {e})") from None
    try:
        from corvin_console.routes import voice  # noqa: PLC0415
        _TTS_API = _RouteShim(voice)
        return _TTS_API
    except Exception as e:  # noqa: BLE001
        raise NativeTTSMissing(
            "the CorvinOS TTS chain (corvin_console.native_tts / say.py) is not available in this process "
            f"({type(e).__name__}); CorvinTV narrates only through CorvinOS") from None


def plan_tts(text: str, out_path: Path, lang: str) -> TTSPlan:
    api = tts_api()
    p = api.prepare(text, Path(out_path), lang)
    return TTSPlan(argv=list(p.argv), env=dict(p.env), timeout_s=float(p.timeout_s), out_path=Path(p.out_path),
                   api=api)


def reset_for_tests() -> None:
    global _TTS_API
    _TTS_API = None

