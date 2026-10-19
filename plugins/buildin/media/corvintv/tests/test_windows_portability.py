"""Host portability of the job path (adversarial review 2026-10-19, CorvinTV on Windows 11).

* the classic slide loaded /usr/share/fonts/.../DejaVuSans.ttf only: every fallback slide on Windows died
  "OSError: cannot open resource";
* a queued job that could not start was closed with reason "start_failed", which the store did not know: the
  write was refused and the job stayed "pending" for good;
* on Windows os.replace fails while a reader holds the record open: the record write must retry, not fail.
"""
import os
from pathlib import Path

import pytest
from PIL import ImageFont

from src import skill, storage
from src.models import VideoJob
from src.storage import get_storage, reset_storage


def test_the_classic_slide_font_never_needs_a_linux_path(monkeypatch):
    monkeypatch.setattr(skill, "_FONT_CANDIDATES", {False: ("/nope/a.ttf",), True: ("/nope/b.ttf",)})
    for bold in (False, True):
        f = skill._slide_font(30, bold=bold)
        assert f.getbbox("Grüße")[2] > 0


def test_the_classic_slide_font_uses_a_real_font_on_this_host():
    f = skill._slide_font(40, bold=True)
    assert isinstance(f, ImageFont.FreeTypeFont)
    assert f.size == 40


def test_a_classic_slide_renders_on_this_host(tmp_path):
    from src.models import Scene

    scene = Scene(id="s1", kind="title", duration_ms=3000, narration_text="Grüße aus Köln – ein Test.")
    out = tmp_path / "s1.png"
    skill._render_slide_image(scene, out, strategy="rich_visual", scene_index=0, total_scenes=1)
    assert out.is_file() and out.stat().st_size > 1000


@pytest.fixture
def base(tmp_path):
    reset_storage()
    yield str(tmp_path / "t")
    reset_storage()


def test_start_failed_is_a_reason_the_store_accepts(base):
    st = get_storage(base)
    st.save_job(VideoJob(id="job_00000sf1", task="t"))

    def _end(j):
        j.status = "error"
        j.error_message = "The job could not be started."

    job, applied = st.advance_job("job_00000sf1", _end, reason="start_failed")
    assert applied and st.get_job("job_00000sf1").status == "error"


def test_the_record_write_retries_a_replace_blocked_by_a_reader(base, monkeypatch):
    calls = []
    real = os.replace

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)

    monkeypatch.setattr(storage.os, "name", "nt")
    monkeypatch.setattr(storage.os, "replace", flaky)
    monkeypatch.setattr(storage.time, "sleep", lambda s: None)
    st = get_storage(base)
    st.save_job(VideoJob(id="job_00000rp1", task="t"))
    assert len(calls) >= 3
    monkeypatch.setattr(storage.os, "replace", real)
    assert st.get_job("job_00000rp1") is not None
