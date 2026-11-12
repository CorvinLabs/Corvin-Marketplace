"""CorvinTV's own host check and self-repair: a fresh instance must produce web-quality video, not Pillow slides.

Why this exists (2026-11-12): the host's Playwright wanted Chromium build 1254 while only 1248 was installed.
Every web slide failed to launch, every scene silently fell back to the Pillow slide, and the operator saw
"bad looking videos" with nothing naming the cause. Nothing in the plugin checked or repaired its own
prerequisites; they lived only in ``requirements.txt``.

What is handled here, all in user space (no admin rights, no system package manager):

* **chromium** - the only thing that makes the web slides. ``check`` proves it by really launching it (a file
  check cannot see a Playwright/browser build mismatch); ``repair`` runs ``playwright install chromium`` with the
  interpreter that runs the job, into the user's own Playwright cache.
* **ffmpeg** - found on PATH, else in ``~/.corvin/bin`` or the ``imageio-ffmpeg`` wheel, and then put on this
  process's PATH so every later ``ffmpeg`` call of a job finds it. It is NOT downloaded here: an unpinned binary
  from the network is a supply-chain step this plugin does not take; the report names the fix instead.

Everything is bounded by a deadline, single-flight (two jobs starting together repair once), and reports a reason
for each component; nothing here raises for a missing component.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CHECK_TIMEOUT_S = 60.0
REPAIR_TIMEOUT_S = 900.0   # ~330 MiB of browser downloads on a slow line
ALLOW_PILLOW_ENV = "CORVINTV_ALLOW_PILLOW"
NO_REPAIR_ENV = "CORVINTV_NO_AUTO_REPAIR"   # offline / locked-down hosts: check and report, never download

# A launch probe in a clean interpreter: imports nothing of this plugin, prints one line.
_PROBE = (
    "import sys\n"
    "try:\n"
    "    from playwright.sync_api import sync_playwright\n"
    "except Exception as e:\n"
    "    print('NOPW ' + type(e).__name__); sys.exit(3)\n"
    "try:\n"
    "    with sync_playwright() as p:\n"
    "        b = p.chromium.launch(headless=True)\n"
    "        v = b.version\n"
    "        b.close()\n"
    "    print('OK ' + v)\n"
    "except Exception as e:\n"
    "    print('FAIL ' + (str(e).splitlines() or [type(e).__name__])[0][:300]); sys.exit(4)\n"
)

_LOCK = threading.Lock()
_LAST: Dict[str, Any] = {}


def pillow_allowed() -> bool:
    """The operator's explicit opt-in to Pillow slides when Chromium cannot run (the pre-1.8.1 behaviour)."""
    return os.environ.get(ALLOW_PILLOW_ENV, "").strip().lower() in ("1", "true", "yes")


def auto_repair_allowed() -> bool:
    return os.environ.get(NO_REPAIR_ENV, "").strip().lower() not in ("1", "true", "yes")


def _run(argv: List[str], timeout: float) -> "subprocess.CompletedProcess[str] | None":
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------- ffmpeg

def _ffmpeg_candidates() -> List[Path]:
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    out = [Path.home() / ".corvin" / "bin" / exe]
    try:
        import imageio_ffmpeg  # type: ignore

        out.append(Path(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:  # noqa: BLE001 - the wheel is optional
        pass
    return out


def ensure_ffmpeg() -> Dict[str, Any]:
    """ffmpeg on this process's PATH, adopting a known user-space copy when PATH has none."""
    found = shutil.which("ffmpeg")
    if found:
        return {"ok": True, "path": found, "source": "path", "reason": None}
    for cand in _ffmpeg_candidates():
        if cand.is_file():
            # the dir holds the binary under its real name; imageio's copy is named ffmpeg-win64-vX.exe, so
            # link it under the plain name in a private dir rather than putting a whole directory on PATH
            bindir = cand.parent
            if cand.name.lower() not in ("ffmpeg", "ffmpeg.exe"):
                bindir = Path.home() / ".corvin" / "bin"
                try:
                    bindir.mkdir(parents=True, exist_ok=True)
                    target = bindir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
                    if not target.exists():
                        shutil.copy2(cand, target)
                except OSError:
                    continue
            os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
            if shutil.which("ffmpeg"):
                return {"ok": True, "path": shutil.which("ffmpeg"), "source": "adopted", "reason": None}
    return {"ok": False, "path": None, "source": None,
            "reason": "ffmpeg not found on PATH, in ~/.corvin/bin or in the imageio-ffmpeg wheel",
            "fix": ("winget install Gyan.FFmpeg  |  brew install ffmpeg  |  apt-get install ffmpeg  |  "
                    "pip install imageio-ffmpeg")}


# ---------------------------------------------------------------- chromium

def check_chromium(timeout: float = CHECK_TIMEOUT_S) -> Dict[str, Any]:
    """Launch Chromium for real in a child interpreter. ``ok`` only when the browser answered."""
    p = _run([sys.executable, "-I", "-c", _PROBE], timeout)
    if p is None:
        return {"ok": False, "reason": f"browser probe did not finish within {timeout:.0f}s", "needs_install": False}
    line = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
    if p.returncode == 0 and line.startswith("OK "):
        return {"ok": True, "version": line[3:], "reason": None, "needs_install": False}
    if line.startswith("NOPW"):
        return {"ok": False, "reason": "the playwright package is not installed in this Python",
                "needs_install": False, "fix": f"{sys.executable} -m pip install playwright"}
    reason = line[5:] if line.startswith("FAIL ") else (p.stderr or "launch failed").strip()[:300]
    missing = "doesn't exist" in reason or "playwright install" in reason.lower() or "Executable" in reason
    return {"ok": False, "reason": reason, "needs_install": missing,
            "fix": f"{sys.executable} -m playwright install chromium"}


def repair_chromium(timeout: float = REPAIR_TIMEOUT_S) -> Dict[str, Any]:
    """``playwright install chromium`` with the interpreter that runs the jobs (user cache, no admin)."""
    started = time.monotonic()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True,
                           text=True, timeout=timeout, encoding="utf-8", errors="replace", env=env,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"ok": False, "seconds": round(time.monotonic() - started, 1),
                "reason": f"browser download did not finish within {timeout:.0f}s"}
    except OSError as e:
        return {"ok": False, "seconds": 0.0, "reason": f"could not start the installer: {type(e).__name__}"}
    tail = " ".join(((p.stderr or "") + " " + (p.stdout or "")).split())[-300:]
    return {"ok": p.returncode == 0, "seconds": round(time.monotonic() - started, 1),
            "reason": None if p.returncode == 0 else f"installer exit {p.returncode}: {tail}"}


def ensure_chromium(repair: bool = True) -> Dict[str, Any]:
    """check -> (repair -> check). Single-flight: a second caller waits for the first and shares its answer."""
    with _LOCK:
        res = check_chromium()
        res["repaired"] = False
        if res["ok"] or not repair or not auto_repair_allowed() or not res.get("needs_install"):
            _LAST["chromium"] = res
            return res
        rep = repair_chromium()
        again = check_chromium()
        again["repaired"] = True
        again["repair"] = rep
        _LAST["chromium"] = again
        return again


# ---------------------------------------------------------------- whole host

def ensure(repair: bool = True) -> Dict[str, Any]:
    """Status of everything CorvinTV needs for web-quality video; repairs what it can in user space."""
    chromium = ensure_chromium(repair=repair)
    ffmpeg = ensure_ffmpeg()
    return {"ok": bool(chromium["ok"] and ffmpeg["ok"]), "web_quality": bool(chromium["ok"]),
            "chromium": chromium, "ffmpeg": ffmpeg, "python": sys.executable}


CACHE_TTL_S = 600.0


def ensure_chromium_cached(ttl: float = CACHE_TTL_S) -> Dict[str, Any]:
    """``ensure_chromium``, but a recent success is reused: a job must not pay a browser launch every time."""
    with _LOCK:
        hit = _LAST.get("chromium")
        if hit and hit.get("ok") and time.monotonic() - _LAST.get("at", 0.0) < ttl:
            return dict(hit)
    res = ensure_chromium()
    with _LOCK:
        _LAST["at"] = time.monotonic()
    return res


def last_known() -> Dict[str, Any]:
    """The cached answer of the last ``ensure_chromium`` in this process (cheap; for health checks)."""
    return dict(_LAST.get("chromium") or {})


def describe(res: Dict[str, Any]) -> str:
    """One operator-readable sentence for a failed chromium result."""
    parts = [f"Chromium (the web slide renderer) cannot start: {res.get('reason') or 'unknown reason'}"]
    if res.get("repaired"):
        parts.append("an automatic repair was tried and did not help")
    elif not auto_repair_allowed():
        parts.append(f"automatic repair is off ({NO_REPAIR_ENV})")
    if res.get("fix"):
        parts.append(f"fix: {res['fix']}")
    parts.append(f"to accept plain Pillow slides instead set {ALLOW_PILLOW_ENV}=1")
    return "; ".join(parts)
