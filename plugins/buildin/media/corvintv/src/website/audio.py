"""The narration track of one language: every spoken sentence placed at its time on a silent track (24 kHz mono WAV).

The sentence clips are the CorvinOS TTS chain's output (converted to WAV by ffmpeg before they get here); this module
only places them. Python's ``wave`` module, no numpy.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Dict, Sequence, Tuple

RATE = 24000
WIDTH = 2


def mix(path: Path, total_s: float, placements: Sequence[Tuple[float, Path]]) -> float:
    """Write ``path`` (``total_s`` long) with each clip at its time; returns the end of the last clip (seconds)."""
    n = int(round(total_s * RATE))
    track = bytearray(n * WIDTH)
    end = 0.0
    for at, clip in placements:
        with wave.open(str(clip), "rb") as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (RATE, 1, WIDTH):
                raise ValueError("a narration clip is not 24 kHz mono 16-bit")
            data = w.readframes(w.getnframes())
        off = int(round(at * RATE)) * WIDTH
        if off < 0 or off >= len(track):
            continue
        chunk = data[: len(track) - off]
        track[off:off + len(chunk)] = chunk
        end = max(end, at + len(chunk) / (RATE * WIDTH))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(WIDTH)
        out.setframerate(RATE)
        out.writeframes(bytes(track))
    return end
