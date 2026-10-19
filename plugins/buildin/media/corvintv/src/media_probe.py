"""Media durations and stream kinds - with ffprobe when the host has it, with ffmpeg alone when not.

The console provisions ffmpeg from the ``imageio-ffmpeg`` wheel when the system has none (Windows, a fresh
install), and that wheel ships ffmpeg ONLY. Every job on such a host died at its first scene with
"[WinError 2] The system cannot find the file specified" - the bare ``ffprobe`` call (2026-10-19).

``probe`` answers in ffprobe's JSON shape (``streams[].codec_type/duration``, ``format.duration``) either way,
so callers do not care which tool measured. Without ffprobe: the container duration and the stream kinds come
from ffmpeg's input header, each stream's own duration from a stream-copy pass to the null muxer (no decode;
the last ``time=`` it reports is the stream's end).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from . import deadline as dl
except ImportError:  # pragma: no cover - script use
    import deadline as dl

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_STREAM_RE = re.compile(r"Stream #0:\d+[^:]*:\s*(Video|Audio|Subtitle|Data):")
_TIME_RE = re.compile(r"time=\s*(-?)(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


def _hms(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def _ffmpeg_text(args: List[str], deadline_s: float, what: str) -> str:
    # ffmpeg writes everything worth reading to stderr; without an output it exits 1 by design
    r = dl.run_process(["ffmpeg", "-hide_banner", "-nostdin", *args], text=True, check=False,
                       deadline_s=deadline_s, what=what)
    return r.stderr or ""


def _stream_end(path: Path, kind: str, deadline_s: float, what: str) -> Optional[float]:
    text = _ffmpeg_text(["-i", str(path), "-map", f"0:{kind}:0", "-c", "copy", "-f", "null", "-"], deadline_s, what)
    times = [_hms(*m.groups()[1:]) for m in _TIME_RE.finditer(text) if not m.group(1)]
    return times[-1] if times else None


def _probe_with_ffmpeg(path: Path, deadline_s: float, what: str, stream_durations: bool) -> Dict[str, Any]:
    if not Path(path).is_file():
        raise FileNotFoundError(str(path))
    head = _ffmpeg_text(["-i", str(path)], deadline_s, what)
    d = _DURATION_RE.search(head)
    if d is None:
        raise RuntimeError(f"{what}: ffmpeg could not read the media header")
    streams: List[Dict[str, Any]] = []
    for kind in dict.fromkeys(m.group(1).lower() for m in _STREAM_RE.finditer(head)):
        s: Dict[str, Any] = {"codec_type": kind}
        if stream_durations and kind in ("video", "audio"):
            end = _stream_end(path, kind[0], deadline_s, what)
            if end is not None:
                s["duration"] = f"{end:.6f}"
        streams.append(s)
    return {"streams": streams, "format": {"duration": f"{_hms(*d.groups()):.6f}"}}


def probe(path: Path, *, deadline_s: float, what: str = "probe", stream_durations: bool = True) -> Dict[str, Any]:
    """ffprobe-shaped facts of ``path``: ``{"streams": [{"codec_type", "duration"?}], "format": {"duration"}}``."""
    if shutil.which("ffprobe"):
        import json

        r = dl.run_process(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration:format=duration",
                            "-of", "json", str(path)], text=True, check=True, deadline_s=deadline_s, what=what)
        return json.loads(r.stdout or "{}")
    return _probe_with_ffmpeg(Path(path), deadline_s, what, stream_durations)


def duration_s(path: Path, *, deadline_s: float, what: str = "probe") -> float:
    """The container duration of ``path`` in seconds."""
    d = (probe(path, deadline_s=deadline_s, what=what, stream_durations=False).get("format") or {}).get("duration")
    if d in (None, "N/A"):
        raise RuntimeError(f"{what}: no duration for the media file")
    return float(d)
