"""No scene can make the host fetch a page (review 2026-10-09 #1, reproduced 2026-10-10).

A model-written ``screenshot_url`` used to be opened by a browser on the console's loopback, where
``local-login`` hands any loopback peer an owner session of tenant ``_default``. The capture path is
removed; a ``screenshot`` scene - from the model, an operator storyboard or an old stored record -
renders as an ordinary slide, through the real ``orchestrate_video``.
"""
import importlib.util
import socket

from src import skill
from src.models import Scene, Storyboard

URL = "http://127.0.0.1:8765/v1/console/auth/local-login?next=/console/app/video-producer"
TEXT = "Ein kurzer Satz fuer den Test, der lang genug ist um sauber zu validieren."


def test_a_screenshot_scene_loses_its_url_and_becomes_a_slide():
    sc = Scene.from_dict({"id": "s", "kind": "screenshot", "duration_ms": 8000, "narration_text": TEXT,
                          "screenshot_url": URL, "highlight_selector": "#x"})
    assert sc.kind == "example"
    assert "screenshot_url" not in sc.to_dict() and "highlight_selector" not in sc.to_dict()


def test_a_stored_record_with_a_screencast_scene_still_loads():
    sb = Storyboard.from_dict({"id": "sb", "task": "t", "generated_at": "2026-10-10T00:00:00",
                               "scenes": [{"id": "s", "kind": "screencast", "duration_ms": 8000,
                                           "screenshot_url": URL}]})
    assert [s.kind for s in sb.scenes] == ["example"]


def test_the_capture_modules_are_gone():
    for mod in ("src.screenshot_capturer", "src.screenshot_annotator"):
        assert importlib.util.find_spec(mod) is None, mod
    assert not hasattr(skill, "_render_screenshot_scene")


def test_orchestrate_renders_it_without_any_outbound_connection(run_orchestrate, monkeypatch):
    attempts = []

    def guarded(self, addr):  # ffmpeg/ffprobe are subprocesses; this process must not dial anything
        attempts.append(addr)
        raise AssertionError(f"outbound connection to {addr!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded)
    scenes = [
        {"id": "s1", "kind": "problem", "duration_ms": 8000, "narration_text": TEXT, "visual_description": "d"},
        {"id": "s2", "kind": "screenshot", "duration_ms": 8000, "narration_text": TEXT, "visual_description": "d",
         "screenshot_url": URL, "highlight_selector": "#app"},
    ]
    result, spies = run_orchestrate(scenes, spies_for=("_render_slide_image",))
    assert attempts == []
    assert "screenshot" not in result["metadata"]["renderers"]
    assert [a[0].kind for a, _ in spies["_render_slide_image"]] == ["problem", "example"]
