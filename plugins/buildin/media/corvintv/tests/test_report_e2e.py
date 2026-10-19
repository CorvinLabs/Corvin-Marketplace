"""E2E: a real job in its own process writes report.json with the runtime signals (T-0089).

Same entry the process-runner tests use: the REAL job_main in a child (real Chromium, ffmpeg, MP4),
the TTS chain reduced to the offline mock tier. That reduction is itself a degradation the report must
record (``tts_tier_below`` on every scene) - which makes this run the live positive control of the
ADR-2247 rule that a failing ``degradation_rate`` invalidates the other signals."""
import json
import os
import time
from pathlib import Path

import pytest

from src import report as rp
from src.async_runner import ProcessJobRunner
from src.storage import get_storage, reset_storage
from tests.test_process_runner import REAL, mkjob, procs_for, wait_for
from tests.test_style_e2e import STORYBOARD

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")]


@pytest.fixture
def base(tmp_path):
    reset_storage()
    b = tmp_path / "tenant"
    b.mkdir()
    yield str(b)
    reset_storage()


async def test_real_job_writes_a_report_with_signals_and_no_text(base):
    task = "Geheimer Auftrag: erklaere die Quartalszahlen der Firma ACME fuer den Vorstand im Detail."
    cfg = mkjob(base, "job_rep")
    cfg["storyboard"] = STORYBOARD
    r = ProcessJobRunner(entry=REAL)
    t0 = time.monotonic()
    await r.start_job("job_rep", task, cfg)
    assert wait_for(lambda: get_storage(base).get_job("job_rep").status in ("complete", "error"), 300, 0.2)
    job = get_storage(base).get_job("job_rep")
    assert job.status == "complete", job.error_message
    assert wait_for(lambda: procs_for("job_rep") == [], 10)

    job_dir = Path(base) / "videos" / "job_rep"
    path = job_dir / rp.REPORT_NAME
    assert path.is_file() and path.stat().st_size <= rp.MAX_REPORT_BYTES
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    rp.validate(data)  # schema 1 holds on what was actually written
    assert data["status"] == "complete" and data["job_id"] == "job_rep" and data["failed_stage"] is None
    assert [s["name"] for s in data["stages"]] == ["setup", "storyboard", "scenes", "assemble", "signals"]
    n = len(STORYBOARD["scenes"])
    assert [s["index"] for s in data["scenes"]] == list(range(1, n + 1))
    assert all(s["tts_tier"] == "mock" and s["audio_s"] > 0 for s in data["scenes"])
    assert data["llm_usage"]["calls"] == 0  # an operator storyboard: no model call, nothing invented
    # no task text and no narration in the report
    for text in [task] + [s["narration_text"] for s in STORYBOARD["scenes"]]:
        assert text[:30] not in raw
    # the offline TTS tier is recorded per scene, where it happened
    tts = [d for d in data["degradations"] if d["kind"] == "tts_tier_below"]
    assert sorted(d["scene"] for d in tts) == list(range(1, n + 1)) and {d["tier"] for d in tts} == {"mock"}

    sig = {s["id"]: s for s in data["signals"]}
    assert set(sig) >= {"degradation_rate", "layout_clean", "fact_support", "mux_integrity",
                        "plan_estimate_error", "beats_provenance", "style_fidelity"}
    for s in sig.values():
        assert set(s) >= {"id", "value", "unit", "threshold", "verdict", "basis", "valid"}
        assert s["verdict"] in ("pass", "warn", "fail", "skip", "info")
    assert sig["mux_integrity"]["verdict"] == "pass", sig["mux_integrity"]
    assert sig["mux_integrity"]["basis"] == {"n": n, "of": n}
    assert sig["fact_support"]["verdict"] == "skip"   # not a grounded task
    assert sig["style_fidelity"]["verdict"] == "skip"  # no custom style
    # mock TTS on every scene: degradation_rate fails and invalidates the gated signals
    assert sig["degradation_rate"]["verdict"] == "fail" and sig["degradation_rate"]["basis"] == {"n": n, "of": n}
    assert sig["layout_clean"]["valid"] is False and sig["layout_clean"]["invalidated_by"] == "degradation_rate"
    assert sig["mux_integrity"]["valid"] is True  # mux guards the encoder, it is not gated
    # the stored video metadata points at the report
    assert get_storage(base).get_video_output("job_rep").metadata["report"] == rp.REPORT_NAME
    print(f"\nMEASURE report e2e: {time.monotonic() - t0:.1f}s, {path.stat().st_size} bytes, "
          f"signals={ {k: v['verdict'] for k, v in sig.items()} }")
