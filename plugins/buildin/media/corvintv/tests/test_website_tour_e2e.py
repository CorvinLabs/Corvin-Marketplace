"""Website tour through the JOB PIPELINE: the same entry the console's process runner starts (CONCEPT-0139 acceptance 3-6).

Real ``job_main`` in its own process, real local site server, headless Chromium drawing a real page with a CSS animation
and a reveal observer, real ffmpeg, real report.json. Only the voice (offline mock tier) and, in one test, the tour MODEL
(fixed answers) are replaced; every call of the narration chain is counted. The result is then opened in a real browser."""
import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from src.async_runner import ProcessJobRunner
from src.storage import get_storage, reset_storage
from src.website import page as pg
from tests.test_process_runner import mkjob, procs_for, wait_for

pytest.importorskip("playwright")
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs /proc (Linux)")]

HERE = Path(__file__).resolve().parent
ENTRY = [sys.executable, str(HERE / "_vp_job_main_website.py")]
FIXTURE = HERE / "fixtures" / "website_tour_site"
FPS = 24


def tour():
    s = lambda en, de, **kw: {"en": en, "de": de, **kw}  # noqa: E731
    return {
        "intro": {"en": ["Welcome to Orbit Notes.", "A short tour of this page."], "de": ["Willkommen bei Orbit Notes.", "Eine kurze Tour durch diese Seite."]},
        "outro": {"en": {"line": "Notes that keep their shape.", "sub": "Download it and write your first note."},
                  "de": {"line": "Notizen, die ihre Form behalten.", "sub": "Lade es herunter und schreibe deine erste Notiz."}, "url": "orbit.example"},
        "scenes": [
            {"id": "s1", "target": "k1", "view": "top", "sentences": [s("Orbit Notes keeps every note in shape.", "Orbit Notes hält jede Notiz in Form."),
                                                                       s("Let us look at how it works.", "Schauen wir uns an, wie es funktioniert.")]},
            {"id": "s2", "target": "k2", "view": "top", "sentences": [s("Every note holds exactly one idea.", "Jede Notiz enthält genau eine Idee."),
                                                                       s("You capture, link and revisit it.", "Du erfasst, verknüpfst und besuchst sie wieder.", focus="k2")]},
            {"id": "s3", "target": "k4", "view": "fit", "anchors": [{"key": "k4", "sentence": 0, "offset": 0}],
             "sentences": [s("The loop runs while you write.", "Die Schleife läuft, während du schreibst."),
                           s("A note grows with every pass.", "Eine Notiz wächst mit jedem Durchgang.")]},
            {"id": "s4", "target": "k6", "view": "top", "sentences": [s("Download it and write your first note.", "Lade es herunter und schreibe deine erste Notiz.")]},
        ]}


@pytest.fixture
def base(tmp_path):
    reset_storage()
    b = tmp_path / "tenant"
    (b / "websites").mkdir(parents=True)
    shutil.copytree(FIXTURE, b / "websites" / "orbit")
    yield str(b)
    reset_storage()


async def run_job(base, tmp_path, job_id, task="Tour of the orbit site", expect="complete", env=None, **extra):
    cfg = mkjob(base, job_id)
    cfg.update({"mode": "website", "website_site": "orbit", "website_fps": FPS})
    cfg.update(extra)
    log = tmp_path / "tts.log"
    runner = ProcessJobRunner(entry=ENTRY, env={**os.environ, "VP_TTS_LOG": str(log), **(env or {})})
    await runner.start_job(job_id, task, cfg)
    assert wait_for(lambda: get_storage(base).get_job(job_id).status in ("complete", "error"), 600, 0.2)
    job = get_storage(base).get_job(job_id)
    assert job.status == expect, job.error_message
    assert wait_for(lambda: procs_for(job_id) == [], 10)
    return job, Path(base) / "videos" / job_id, log


def probe(path, entries):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def n_sentences(t, langs):
    return sum(len(sc["sentences"]) for sc in t["scenes"]) * len(langs)


async def test_a_tour_of_a_real_page_becomes_two_videos_and_a_page_to_put_online(base, tmp_path):
    t = tour()
    job, out, log = await run_job(base, tmp_path, "job_w1", website_langs=["en", "de"], tour=t)
    meta = get_storage(base).get_video_output("job_w1").metadata

    # 1) the videos: 1920x1080 H.264 + AAC, as long as the timeline says, both languages the same length
    tl = json.loads((out / "website" / "timeline.json").read_text(encoding="utf-8"))
    for name in ("output.mp4", "output.de.mp4"):
        info = probe(out / name, "stream=codec_name,width,height:format=duration")
        kinds = {s["codec_name"] for s in info["streams"]}
        assert {"h264", "aac"} <= kinds and any(s.get("width") == 1920 and s.get("height") == 1080 for s in info["streams"])
        assert abs(float(info["format"]["duration"]) - tl["total_s"]) < 0.25, name
    assert meta["language_sync_diff_ms"] < 150 and meta["languages"] == ["en", "de"] and meta["mode"] == "website"

    # 1b) the intro card is READABLE: its text is clearly brighter or darker than the card's own background (a card whose text
    # colour equals its background was shipped once: body had the default black on a dark page)
    from PIL import Image
    for name in ("output.mp4", "output.de.mp4"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2.0", "-i", str(out / name), "-frames:v", "1", str(tmp_path / "intro.png")], check=True)
        im = Image.open(tmp_path / "intro.png").convert("L")
        w, h = im.size
        corner = im.getpixel((10, 10))
        band = [im.getpixel((x, y)) for x in range(w // 4, 3 * w // 4, 6) for y in range(h // 3, 2 * h // 3, 6)]
        assert max(abs(v - corner) for v in band) > 80, f"{name}: the intro text is not readable on its background"

    # 2) ONE voice path: every sentence in every language went through the CorvinOS chain function, nothing else spoke
    assert len(log.read_text().split()) == n_sentences(t, ["en", "de"])
    assert meta["tts_chain"] == "corvinos" and meta["tts_provider_used"] == "mock"

    # 3) the page asked for something outside the site (the fixture has a tracker script): it was aborted and counted
    assert meta["source"]["kind"] == "site" and meta["source"]["blocked_requests"] >= 1

    # 4) the report carries the measured camera and the effects
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    cam = rep["media"]["camera"]
    assert cam["max_step_px"] > 0 and cam["max_accel_px"] < 6 and cam["peak_speed_px_s"] <= 900 * 1.02 and cam["late_moves"] == 0
    assert rep["media"]["effects"] == {"spot": True, "reveal": True, "zoom": True, "vignette": True}

    # 5) the bundle
    site = out / "site"
    for f in ("index.html", "poster.jpg", "README.txt", "video.en.mp4", "video.de.mp4", "chapters.en.vtt", "captions.de.vtt"):
        assert (site / f).is_file(), f
    names = set(zipfile.ZipFile(out / "website-bundle.zip").namelist())
    assert {"index.html", "video.en.mp4", "poster.jpg", "chapters.de.vtt"} <= names

    # 6) the page opens in a real browser: no request to any other site, the video plays, a chapter jumps, the language switch keeps the place
    from playwright.async_api import async_playwright
    server = pg.LocalSite(site)
    url = server.start()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page()
            problems, origins = [], set()
            page.on("console", lambda m: problems.append(m.text) if m.type in ("error", "warning") else None)
            page.on("request", lambda r: origins.add(re.match(r"^\w+://[^/]+", r.url).group(0)))
            await page.goto(url)
            await page.wait_for_function("document.getElementById('v').readyState >= 1")
            info = await page.evaluate("""async () => { const v = document.getElementById('v'); const b = document.querySelectorAll('[data-t]');
              b[2].click(); await new Promise(r => setTimeout(r, 600)); const jumped = v.currentTime; v.pause();
              document.querySelector('[data-lang=de]').click(); await new Promise(r => setTimeout(r, 900));
              return {duration: v.duration, chapters: b.length, jumped, after: v.currentTime, src: v.getAttribute('src'),
                      tracks: [...v.querySelectorAll('track')].map(t => t.kind + ':' + t.srclang)}; }""")
            await browser.close()
    finally:
        server.stop()
    assert origins == {url.rsplit("/", 1)[0].replace("/index.html", "")} or all(o.startswith("http://127.0.0.1") for o in origins), origins
    assert problems == [], problems
    assert abs(info["duration"] - tl["total_s"]) < 0.3 and info["chapters"] == 4
    assert abs(info["jumped"] - tl["scenes"][2]["start"]) < 1.0, "a chapter button jumps to its scene"
    assert info["src"] == "video.de.mp4" and abs(info["after"] - info["jumped"]) < 1.0 and "captions:de" in info["tracks"]
    html = (site / "index.html").read_text(encoding="utf-8")
    inline = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    assert "sha256-" + base64.b64encode(hashlib.sha256(inline.encode("utf-8")).digest()).decode() in html


async def test_the_camera_in_the_finished_video_moves_smoothly(base, tmp_path):
    np = pytest.importorskip("numpy")
    from PIL import Image
    t = tour()
    job, out, _ = await run_job(base, tmp_path, "job_w2", website_langs=["en"], tour=t)
    frames = tmp_path / "fr"
    frames.mkdir()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out / "output.mp4"), "-vf", "scale=480:-2,format=gray", str(frames / "%05d.png")], check=True)
    prof = [np.asarray(Image.open(f), dtype=np.float32)[:, 60:420].mean(axis=1) for f in sorted(frames.glob("*.png"))]

    def shift(p, q):
        best, sc = None, []
        lags = list(range(-30, 31))
        for lag in lags:
            a, b = p[max(0, lag):len(p) + min(0, lag)], q[max(0, -lag):len(q) - max(0, lag)]
            a, b = a - a.mean(), b - b.mean()
            sc.append(float((a * b).sum() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)))
        i = int(np.argmax(sc))
        off = 0.5 * (sc[i - 1] - sc[i + 1]) / (sc[i - 1] - 2 * sc[i] + sc[i + 1]) if 0 < i < len(sc) - 1 and (sc[i - 1] - 2 * sc[i] + sc[i + 1]) else 0.0
        return (lags[i] + off) * 4.0, sc[i]   # back to full-size device pixels

    steps = [shift(prof[i], prof[i + 1]) for i in range(len(prof) - 1)]
    good = [s for s, c in steps if c > 0.9]
    assert len([1 for s, c in steps if c > 0.9 and abs(s) > 0.5]) > 20, "the camera really moved"
    biggest = max(abs(s) for s in good)
    changes = [abs(steps[i + 1][0] - steps[i][0]) for i in range(len(steps) - 1) if steps[i][1] > 0.9 and steps[i + 1][1] > 0.9]
    # a Hermite move peaks at 1.5 x distance / time; the cap is 900 css px/s = 1215 device px/s
    assert biggest <= 900 * 1.35 / FPS * 1.2 + 2, biggest
    assert max(changes) <= 8.0, f"speed changed by {max(changes):.1f} device px from one frame to the next"


async def test_a_tour_written_by_the_model_is_repaired_once_and_validated(base, tmp_path):
    first = tour()
    first["scenes"][1]["target"] = "k99"                     # not an outline key
    first["scenes"][2]["sentences"][0]["en"] = "It costs 49 euros."   # not on the page
    llm = tmp_path / "llm"
    llm.mkdir()
    (llm / "job_w3.tour.json").write_text(json.dumps(first), encoding="utf-8")
    (llm / "job_w3.repair.json").write_text(json.dumps({**tour(), "scenes": tour()["scenes"][:2]}), encoding="utf-8")
    job, out, log = await run_job(base, tmp_path, "job_w3", task="Explain what Orbit Notes does", website_langs=["en"],
                                  storyboard_backend="claude_cli", storyboard_model="fake-model", env={"VP_FAKE_LLM_DIR": str(llm)})
    meta = get_storage(base).get_video_output("job_w3").metadata
    assert meta["tour_source"] == "model" and meta["tour_repaired"] >= 2 and meta["scenes"] == 2
    tour_saved = json.loads((out / "website" / "tour.json").read_text(encoding="utf-8"))
    assert [s["target"] for s in tour_saved["scenes"]] == ["k1", "k2"]


async def test_a_model_that_keeps_breaking_the_rules_fails_the_job_with_the_reasons(base, tmp_path):
    bad = tour()
    bad["scenes"][0]["target"] = "body > a"
    llm = tmp_path / "llm"
    llm.mkdir()
    (llm / "job_w4.tour.json").write_text(json.dumps(bad), encoding="utf-8")
    (llm / "job_w4.repair.json").write_text(json.dumps(bad), encoding="utf-8")
    job, out, _ = await run_job(base, tmp_path, "job_w4", task="Explain it", website_langs=["en"], expect="error",
                                storyboard_backend="claude_cli", storyboard_model="fake-model", env={"VP_FAKE_LLM_DIR": str(llm)})
    assert "after one repair round" in job.error_message and "target" in job.error_message


async def test_a_loopback_url_or_a_site_with_a_symlink_ends_the_job_without_drawing_anything(base, tmp_path):
    job, out, _ = await run_job(base, tmp_path, "job_w5", expect="error", website_site=None, website_url="http://127.0.0.1:9/", website_langs=["en"], tour=tour())
    assert "cannot be used" in job.error_message
    (Path(base) / "websites" / "orbit" / "evil").symlink_to("/etc/passwd")
    job, out, _ = await run_job(base, tmp_path, "job_w6", expect="error", website_langs=["en"], tour=tour())
    assert "symbolic link" in job.error_message
    assert not (out / "output.mp4").exists()
