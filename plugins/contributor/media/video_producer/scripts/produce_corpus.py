#!/usr/bin/env python3
"""Produce the REAL quality corpus for the ready gate (ADR-2247, T-0097) from live console jobs.

Every task text of ``tests/corpus/baseline.json`` is submitted as a real job to a running console, exactly
the way the panel does it (console local-login cookie + ``x-csrf-token``; the operator's own settings - no
model, TTS or style override; grounding is decided by the host, not by the request). Each finished job's
own ``report.json`` (and ``metadata.json``) is copied byte-for-byte to ``<out>/<baseline_id>/`` and
``<out>/manifest.json`` records baseline id -> console job id, status, wall time. ``ready_gate.py
--corpus-dir <out>`` then reads it.

Rules (these are the point of the script, not conveniences):
  * A report is never written or edited here - only copied from the job store.
  * A failed / cancelled / timed-out job is recorded as such in the manifest, never retried silently.
  * At most ONE repeat of the WHOLE run, and only when the run was invalidated by a TTS fallback
    (a ``tts_tier_below`` degradation - ready_gate's ``run_validity``). The invalid run is kept beside
    the output as ``<out>.run1-invalid`` and both runs are named in the manifest.
  * ``--with-alignment`` calls ``POST /jobs/{id}/measure`` (whisper-1, costs money) on every completed job
    BEFORE the copy, so the copied report carries ``cue_alignment``.

Usage: produce_corpus.py --out DIR [--base-url URL] [--with-alignment] [--concurrency N]
                         [--job-timeout S] [--poll S] [--only ID ...] [--no-retry]
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PLUGIN = Path(__file__).resolve().parents[1]
BASELINE = PLUGIN / "tests" / "corpus" / "baseline.json"
API = "/v1/console/video"
TERMINAL = frozenset({"complete", "error", "cancelled"})
HOST_CAP = 2                      # _MAX_ACTIVE_JOBS_PER_TENANT in the console route
COPIED = ("report.json", "metadata.json")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Console:
    """A browser-shaped client: local-login cookie, CSRF token from whoami on every mutation."""

    def __init__(self, base: str, timeout: float = 120.0):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):  # the login 302 only sets the cookie
                return None

        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), _NoRedirect)
        self.csrf: Optional[str] = None
        self.lock = threading.Lock()

    def _req(self, method: str, path: str, body: Optional[dict] = None) -> tuple:
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            r.add_header("Content-Type", "application/json")
        if method != "GET" and self.csrf:
            r.add_header("x-csrf-token", self.csrf)
        try:
            with self.opener.open(r, timeout=self.timeout) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else None
            except ValueError:
                return e.code, {"detail": raw[:300].decode("utf-8", "replace")}

    def login(self) -> None:
        code, _ = self._req("GET", "/v1/console/auth/local-login")
        if code not in (200, 302, 303, 307):
            raise RuntimeError(f"local-login answered {code}")
        code, who = self._req("GET", "/v1/console/auth/whoami")
        if code != 200 or not (who or {}).get("csrf_token"):
            raise RuntimeError(f"whoami answered {code}: no session / CSRF token")
        self.csrf = who["csrf_token"]

    def call(self, method: str, path: str, body: Optional[dict] = None) -> tuple:
        with self.lock:
            code, data = self._req(method, path, body)
            if code == 401:  # session expired during a long run: log in again, once
                self.login()
                code, data = self._req(method, path, body)
            return code, data


def load_baseline(path: Path, only: Optional[List[str]]) -> List[Dict[str, str]]:
    entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    out = [{"id": e["id"], "task": e["task"], "language": e.get("language")} for e in entries]
    if only:
        out = [e for e in out if e["id"] in only]
    return out


def summarize_report(rep: Optional[dict]) -> Dict[str, Any]:
    if not rep:
        return {}
    sig = {s.get("id"): s for s in rep.get("signals") or [] if isinstance(s, dict)}
    ca = sig.get("cue_alignment") or {}
    return {"report_status": rep.get("status"), "scenes": len(rep.get("scenes") or []),
            "duration_s": (rep.get("media") or {}).get("duration_s"),
            "audio_s": round(sum(float(s.get("audio_s") or 0) for s in rep.get("scenes") or []), 2),
            "tts_tiers": sorted({s.get("tts_tier") for s in rep.get("scenes") or [] if s.get("tts_tier")}),
            "degradations": [d.get("kind") for d in rep.get("degradations") or []],
            "llm_usage": rep.get("llm_usage"),
            "fact_support": (sig.get("fact_support") or {}).get("verdict"),
            "still_time": (sig.get("still_time") or {}).get("verdict"),
            "cue_alignment": {"verdict": ca.get("verdict"), "value": ca.get("value"),
                              "p90_s": (ca.get("detail") or {}).get("p90_s")} if ca else None}


def run_one(con: Console, entry: Dict[str, str], out: Path, videos_dir: Path, args, sem: threading.Semaphore,
            log) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"baseline_id": entry["id"], "language": entry["language"]}
    with sem:
        t0 = time.monotonic()
        deadline_submit = t0 + args.submit_wait
        while True:
            code, data = con.call("POST", f"{API}/jobs", {"task": entry["task"]})
            if code == 429 and time.monotonic() < deadline_submit:  # host cap busy (another job) - wait, not a retry
                time.sleep(args.poll)
                continue
            break
        if code != 200 or not (data or {}).get("job_id"):
            rec.update(status="submit_failed", http=code, detail=(data or {}).get("detail"), wall_s=0)
            log(f"{entry['id']}: submit failed {code} {rec['detail']}")
            return rec
        job_id = data["job_id"]
        rec.update(job_id=job_id, submitted_at=now())
        t0 = time.monotonic()
        log(f"{entry['id']}: submitted as {job_id}")
        status, job = "pending", {}
        while True:
            code, job = con.call("GET", f"{API}/jobs/{job_id}")
            status = (job or {}).get("status", f"http_{code}")
            if status in TERMINAL:
                break
            if time.monotonic() - t0 > args.job_timeout:
                con.call("POST", f"{API}/jobs/{job_id}/cancel")
                status = "timeout"
                break
            time.sleep(args.poll)
        rec.update(status=status, wall_s=round(time.monotonic() - t0, 1), finished_at=now(),
                   error_message=(job or {}).get("error_message"))
    log(f"{entry['id']}: {job_id} -> {status} in {rec['wall_s']} s")
    if status == "complete" and args.with_alignment:
        code, m = con.call("POST", f"{API}/jobs/{job_id}/measure")
        rec["measure"] = {"http": code, "measured": (m or {}).get("measured"), "stored": (m or {}).get("stored"),
                          "refusal": (m or {}).get("refusal"), "detail": (m or {}).get("detail")}
        log(f"{entry['id']}: measure {code} measured={rec['measure']['measured']}")
    src = videos_dir / job_id
    dst = out / entry["id"]
    copied = []
    for name in COPIED:
        f = src / name
        if f.is_file() and not f.is_symlink():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst / name)
            copied.append(name)
    rec["copied"] = copied
    rep = None
    if "report.json" in copied:
        try:
            rep = json.loads((dst / "report.json").read_text(encoding="utf-8"))
        except ValueError:
            rec["report_unreadable"] = True
    rec.update(summarize_report(rep))
    return rec


def run_corpus(con: Console, entries, out: Path, videos_dir: Path, args, log) -> List[Dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    sem = threading.Semaphore(max(1, min(args.concurrency, HOST_CAP)))
    with ThreadPoolExecutor(max_workers=max(1, min(args.concurrency, HOST_CAP))) as ex:
        futs = [ex.submit(run_one, con, e, out, videos_dir, args, sem, log) for e in entries]
        return [f.result() for f in futs]


def tts_fallback(records: List[Dict[str, Any]]) -> bool:
    return any("tts_tier_below" in (r.get("degradations") or []) for r in records)


def totals(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    t = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "llm_calls": 0}
    for r in records:
        u = r.get("llm_usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            t[k] += int(u.get(k) or 0)
        t["llm_calls"] += int(u.get("calls") or 0)
    t["audio_s"] = round(sum(float(r.get("audio_s") or 0) for r in records), 1)
    t["measured"] = sum(1 for r in records if (r.get("measure") or {}).get("measured"))
    t["by_status"] = {s: sum(1 for r in records if r.get("status") == s) for s in {r.get("status") for r in records}}
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--with-alignment", action="store_true")
    ap.add_argument("--concurrency", type=int, default=1, help=f"parallel jobs (capped at the host's {HOST_CAP})")
    ap.add_argument("--job-timeout", type=float, default=2400.0, help="seconds per job before it is cancelled")
    ap.add_argument("--submit-wait", type=float, default=3600.0, help="how long to wait on a busy host (429)")
    ap.add_argument("--poll", type=float, default=10.0)
    ap.add_argument("--videos-dir", type=Path, help="job store videos dir (default: the console's settings)")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-retry", action="store_true", help="never repeat a TTS-fallback-invalidated run")
    args = ap.parse_args(argv)

    def log(msg: str) -> None:
        print(f"[{now()}] {msg}", flush=True)

    entries = load_baseline(args.baseline, args.only)
    if not entries:
        print("produce_corpus: no baseline entries", file=sys.stderr)
        return 2
    con = Console(args.base_url)
    try:
        con.login()
        code, settings = con.call("GET", f"{API}/settings")
    except (RuntimeError, OSError) as e:
        print(f"produce_corpus: console not usable: {e}", file=sys.stderr)
        return 2
    if code != 200:
        print(f"produce_corpus: GET {API}/settings answered {code}: {settings}", file=sys.stderr)
        return 2
    videos_dir = args.videos_dir or Path(settings["output_folder"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        print(f"produce_corpus: {out} is not empty; refusing to mix runs", file=sys.stderr)
        return 2
    manifest: Dict[str, Any] = {"schema": 1, "started_at": now(), "base_url": args.base_url,
                                "with_alignment": args.with_alignment, "settings": {
                                    k: settings.get(k) for k in ("tts_engine", "max_duration_minutes")},
                                "baseline": str(args.baseline), "runs": []}
    log(f"{len(entries)} jobs, videos at {videos_dir}, concurrency {min(args.concurrency, HOST_CAP)}")
    records = run_corpus(con, entries, out, videos_dir, args, log)
    manifest["runs"].append({"run": 1, "out": str(out), "invalid_tts_fallback": tts_fallback(records)})
    if tts_fallback(records) and not args.no_retry:
        kept = out.with_name(out.name + ".run1-invalid")
        out.rename(kept)
        (kept / "manifest.json").write_text(json.dumps({**manifest, "jobs": {r["baseline_id"]: r for r in records},
                                                        "totals": totals(records)}, indent=2) + "\n")
        manifest["runs"][0]["out"] = str(kept)
        log(f"run 1 invalidated by a TTS fallback; kept at {kept}; repeating the whole run once")
        records = run_corpus(con, entries, out, videos_dir, args, log)
        manifest["runs"].append({"run": 2, "out": str(out), "invalid_tts_fallback": tts_fallback(records)})
    manifest.update(finished_at=now(), jobs={r["baseline_id"]: r for r in records}, totals=totals(records))
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"manifest: {out / 'manifest.json'} {manifest['totals']['by_status']}")
    return 0 if all(r.get("status") == "complete" for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
