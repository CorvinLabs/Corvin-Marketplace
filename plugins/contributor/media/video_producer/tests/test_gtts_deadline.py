"""gTTS has no kill switch: the client must carry a timeout and the call must be bound by a deadline
(T-0088 / ADR-2247 R1b). The hung call is a real blocked thread, not a mock of the deadline."""
import threading
import time

import pytest

from src import deadline as dl
from src import skill


def test_gtts_client_is_built_with_the_call_timeout(tmp_path, monkeypatch):
    import gtts

    seen = {}
    real_init = gtts.gTTS.__init__

    def spy_init(self, *a, **kw):
        real_init(self, *a, **kw)
        seen["timeout"] = self.timeout

    monkeypatch.setattr(gtts.gTTS, "__init__", spy_init)
    monkeypatch.setattr(gtts.gTTS, "save", lambda self, path: None)
    skill._synthesize_narration("hello", tmp_path / "a.mp3", "en")
    assert seen["timeout"] == skill._TTS_CALL_TIMEOUT_S


def test_a_hung_gtts_call_ends_at_the_deadline(tmp_path, monkeypatch):
    import gtts

    release = threading.Event()
    monkeypatch.setattr(gtts.gTTS, "save", lambda self, path: release.wait(30))
    monkeypatch.setattr(skill, "_TTS_CALL_TIMEOUT_S", 1)
    start = time.monotonic()
    try:
        with pytest.raises(dl.DeadlineExceeded):
            skill._synthesize_narration("hello", tmp_path / "a.mp3", "en")
        elapsed = time.monotonic() - start
    finally:
        release.set()
    assert elapsed <= 2 + 1, elapsed
