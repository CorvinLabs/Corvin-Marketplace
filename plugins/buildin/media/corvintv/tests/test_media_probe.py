"""media_probe: durations and stream kinds without ffprobe (2026-10-19).

The console's bundled ffmpeg (imageio-ffmpeg) has no ffprobe; every job on such a host died at its first scene
with "[WinError 2] The system cannot find the file specified". Real ffmpeg, real media files."""
import shutil
import subprocess
from pathlib import Path

import pytest

from src import media_probe, signals as sg, skill

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    mp4, mp3 = d / "clip ä'x.mp4", d / "voice.mp3"
    # video 3.0 s, audio 2.0 s: the per-stream durations differ on purpose
    _ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=160x90:r=25:d=3", "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(mp4))
    _ffmpeg("-f", "lavfi", "-i", "sine=f=330:d=1.5", "-c:a", "libmp3lame", str(mp3))
    return mp4, mp3


@pytest.fixture
def no_ffprobe(monkeypatch):
    real = shutil.which
    monkeypatch.setattr(media_probe.shutil, "which", lambda n, *a, **k: None if n == "ffprobe" else real(n, *a, **k))


def _stream(info, kind):
    return next(float(s["duration"]) for s in info["streams"] if s["codec_type"] == kind)


def test_without_ffprobe_the_facts_come_from_ffmpeg(media, no_ffprobe):
    mp4, mp3 = media
    info = media_probe.probe(mp4, deadline_s=30)
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}
    assert _stream(info, "video") == pytest.approx(3.0, abs=0.1)
    assert _stream(info, "audio") == pytest.approx(2.0, abs=0.1)
    assert float(info["format"]["duration"]) == pytest.approx(3.0, abs=0.1)
    assert media_probe.duration_s(mp3, deadline_s=30) == pytest.approx(1.5, abs=0.1)
    # the callers the job uses
    assert skill._ffprobe_duration(mp3) == pytest.approx(1.5, abs=0.1)
    assert sg._stream_s(sg._probe(mp4), "audio") == pytest.approx(2.0, abs=0.1)


def test_without_ffprobe_a_missing_or_broken_file_raises(media, no_ffprobe, tmp_path):
    with pytest.raises(FileNotFoundError):
        media_probe.duration_s(tmp_path / "gone.mp3", deadline_s=30)
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not media at all")
    with pytest.raises(RuntimeError):
        media_probe.duration_s(junk, deadline_s=30)


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed: nothing to compare against")
def test_both_paths_agree(media, monkeypatch):
    mp4, _ = media
    with_probe = media_probe.probe(mp4, deadline_s=30)
    real = shutil.which
    monkeypatch.setattr(media_probe.shutil, "which", lambda n, *a, **k: None if n == "ffprobe" else real(n, *a, **k))
    without = media_probe.probe(mp4, deadline_s=30)
    for kind in ("video", "audio"):
        assert _stream(without, kind) == pytest.approx(_stream(with_probe, kind), abs=0.05)
    assert float(without["format"]["duration"]) == pytest.approx(float(with_probe["format"]["duration"]), abs=0.05)
