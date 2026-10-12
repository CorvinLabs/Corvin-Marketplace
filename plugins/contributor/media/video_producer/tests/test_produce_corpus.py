"""scripts/produce_corpus.py (ADR-2247, T-0097): the corpus producer, run as a subprocess against a stub console.

The stub (stdlib ``http.server``) speaks the console's contract: local-login sets the session cookie, whoami
hands out the CSRF token, every POST must carry ``x-csrf-token``, a job is pending for a few polls and then
reaches its end state with ``report.json`` in the job store, ``/measure`` merges ``cue_alignment`` into it.
No network beyond loopback, no live install touched. Asserted: the manifest, the byte-identical copies,
a failed job recorded as failed (not retried), and the single whole-run repeat after a TTS fallback.
"""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "produce_corpus.py"
CSRF = "tok-123"
SID = "sid-abc"


class Stub:
    def __init__(self, videos: Path, outcome):
        self.videos = videos
        self.outcome = outcome          # (task, attempt) -> ("complete"|"error", [degradation kinds])
        self.jobs = {}
        self.polls = {}
        self.posts = []
        self.attempts = {}
        self.measured = []
        self.lock = threading.Lock()

    def finish(self, job_id):
        j = self.jobs[job_id]
        d = self.videos / job_id
        d.mkdir(parents=True)
        rep = {"schema": 1, "job_id": job_id, "status": j["status"],
               "scenes": [{"index": 1, "audio_s": 5.0, "tts_tier": "openai"},
                          {"index": 2, "audio_s": 6.0, "tts_tier": "openai"}],
               "degradations": [{"kind": k, "scene": 1} for k in j["kinds"]],
               "signals": [{"id": "mux_integrity", "verdict": "pass"}],
               "llm_usage": {"calls": 1, "input_tokens": 3, "output_tokens": 100}}
        (d / "report.json").write_text(json.dumps(rep), encoding="utf-8")
        (d / "metadata.json").write_text("{}", encoding="utf-8")
        (d / "output.mp4").write_bytes(b"not copied")


def make_handler(stub: Stub):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=None, headers=()):
            raw = json.dumps(body).encode() if body is not None else b""
            self.send_response(code)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _authed(self):
            return f"corvin_console_sid={SID}" in (self.headers.get("Cookie") or "")

        def do_GET(self):
            p = self.path
            if p == "/v1/console/auth/local-login":
                return self._send(302, None, [("Location", "/console/"),
                                              ("Set-Cookie", f"corvin_console_sid={SID}; Path=/; HttpOnly")])
            if not self._authed():
                return self._send(401, {"detail": "no session"})
            if p == "/v1/console/auth/whoami":
                return self._send(200, {"csrf_token": CSRF, "tenant_id": "_default"})
            if p == "/v1/console/video/settings":
                return self._send(200, {"tts_engine": "openai", "max_duration_minutes": 60,
                                        "output_folder": str(stub.videos)})
            if p.startswith("/v1/console/video/jobs/"):
                jid = p.rsplit("/", 1)[1]
                with stub.lock:
                    j = stub.jobs.get(jid)
                    if not j:
                        return self._send(404, {"detail": "Job not found"})
                    stub.polls[jid] = stub.polls.get(jid, 0) + 1
                    if stub.polls[jid] >= 3 and j["shown"] == "pending":
                        j["shown"] = j["status"]
                        stub.finish(jid)
                    return self._send(200, {"id": jid, "status": j["shown"],
                                            "error_message": "boom" if j["shown"] == "error" else None})
            return self._send(404, {"detail": "nope"})

        def do_POST(self):
            if not self._authed():
                return self._send(401, {"detail": "no session"})
            if self.headers.get("x-csrf-token") != CSRF:
                return self._send(403, {"detail": "missing CSRF token"})
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/v1/console/video/jobs":
                with stub.lock:
                    stub.posts.append(body)
                    task = body["task"]
                    stub.attempts[task] = stub.attempts.get(task, 0) + 1
                    status, kinds = stub.outcome(task, stub.attempts[task])
                    jid = f"job_{len(stub.jobs):08x}"
                    stub.jobs[jid] = {"status": status, "kinds": kinds, "shown": "pending"}
                return self._send(200, {"job_id": jid, "status": "pending"})
            if self.path.endswith("/measure"):
                jid = self.path.split("/")[-2]
                f = stub.videos / jid / "report.json"
                rep = json.loads(f.read_text())
                rep["signals"].append({"id": "cue_alignment", "verdict": "pass", "value": 0.5,
                                       "basis": {"n": 2, "of": 2}, "detail": {"p90_s": 0.9}})
                f.write_text(json.dumps(rep))
                stub.measured.append(jid)
                return self._send(200, {"job_id": jid, "measured": True, "stored": True})
            return self._send(404, {"detail": "nope"})

    return H


@pytest.fixture
def console(tmp_path):
    holder = {}

    def start(outcome):
        stub = Stub(tmp_path / "videos", outcome)
        (tmp_path / "videos").mkdir()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(stub))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        holder["srv"] = srv
        return stub, f"http://127.0.0.1:{srv.server_address[1]}"

    yield start
    if "srv" in holder:
        holder["srv"].shutdown()


def baseline(tmp_path, n=3):
    entries = [{"id": f"vid_{i}", "language": "de", "task": f"task number {i}", "measured": {}} for i in range(n)]
    f = tmp_path / "baseline.json"
    f.write_text(json.dumps({"schema": 1, "entries": entries}), encoding="utf-8")
    return f, entries


def run(url, bl, out, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), "--base-url", url, "--baseline", str(bl), "--out", str(out),
                           "--poll", "0.05", "--job-timeout", "30", *extra],
                          capture_output=True, text=True, timeout=120)


def test_manifest_copies_and_failed_job_recorded_not_retried(console, tmp_path):
    stub, url = console(lambda task, attempt: ("error", []) if task.endswith("1") else ("complete", []))
    bl, entries = baseline(tmp_path)
    out = tmp_path / "corpus"
    p = run(url, bl, out, "--with-alignment", "--concurrency", "2")
    assert p.returncode == 1, p.stdout + p.stderr       # one job failed -> non-zero, but the run is recorded
    man = json.loads((out / "manifest.json").read_text())
    assert set(man["jobs"]) == {"vid_0", "vid_1", "vid_2"}
    assert man["jobs"]["vid_1"]["status"] == "error"
    assert man["jobs"]["vid_0"]["status"] == man["jobs"]["vid_2"]["status"] == "complete"
    assert len(stub.posts) == 3                           # the failed job was NOT resubmitted
    assert all(set(b) == {"task"} for b in stub.posts)    # no model / TTS / style override
    assert len(man["runs"]) == 1 and man["runs"][0]["invalid_tts_fallback"] is False
    for e in entries:
        jid = man["jobs"][e["id"]]["job_id"]
        assert man["jobs"][e["id"]]["wall_s"] >= 0
        # byte-identical to the job store (after measure), the video itself is not copied
        assert (out / e["id"] / "report.json").read_bytes() == (stub.videos / jid / "report.json").read_bytes()
        assert not (out / e["id"] / "output.mp4").exists()
    # alignment ran only for completed jobs, before the copy
    assert sorted(stub.measured) == sorted(man["jobs"][k]["job_id"] for k in ("vid_0", "vid_2"))
    assert json.loads((out / "vid_0" / "report.json").read_text())["signals"][-1]["id"] == "cue_alignment"
    assert man["jobs"]["vid_0"]["cue_alignment"]["p90_s"] == 0.9
    assert man["jobs"]["vid_0"]["scenes"] == 2


def test_tts_fallback_repeats_whole_run_once_and_keeps_the_invalid_run(console, tmp_path):
    # every attempt falls back: run 1 AND run 2 are invalid -> exactly two runs, never a third
    stub, url = console(lambda task, attempt: ("complete", ["tts_tier_below"] if task.endswith("0") else []))
    bl, _ = baseline(tmp_path)
    out = tmp_path / "corpus"
    p = run(url, bl, out)
    assert p.returncode == 0, p.stdout + p.stderr
    man = json.loads((out / "manifest.json").read_text())
    assert [r["run"] for r in man["runs"]] == [1, 2]
    assert man["runs"][0]["invalid_tts_fallback"] and man["runs"][1]["invalid_tts_fallback"]
    kept = tmp_path / "corpus.run1-invalid"
    assert (kept / "vid_0" / "report.json").is_file() and (kept / "manifest.json").is_file()
    assert len(stub.posts) == 6                           # 3 jobs x 2 runs
    assert man["jobs"]["vid_0"]["degradations"] == ["tts_tier_below"]


def test_refuses_non_empty_output_and_unreachable_console(console, tmp_path):
    _, url = console(lambda task, attempt: ("complete", []))
    bl, _ = baseline(tmp_path, 1)
    out = tmp_path / "corpus"
    out.mkdir()
    (out / "stale").mkdir()
    assert run(url, bl, out).returncode == 2
    assert run("http://127.0.0.1:9", bl, tmp_path / "other").returncode == 2
