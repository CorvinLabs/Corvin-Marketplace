"""Narration-synced cues (ADR-2245): timeline maths, real-audio pause detection,
and the renderer/assembler contract that puts a late cue on screen."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from src import skill
from src.grounded_storyboard import repair_grounded_scenes
from src.web_templates import build_document, scene_item_subs, scene_items, validate_scene_data
from src.web_timeline import (
    FOCUS_MIN_GAP_S, MIN_VISIBLE_S, REVEAL_LEAD_S, AudioPauses, Timeline, build_timeline, detect_pauses,
    fallback_chip, find_mentions, sentence_starts, split_sentences, validate_beats,
)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _sentences(text):
    return [text[a:b].strip() for a, b in split_sentences(text)]


# ── text ───────────────────────────────────────────────────────────────────

def test_abbreviations_and_decimals_do_not_end_a_sentence():
    text = "Das gilt z. B. für ca. 30 Fälle mit 3.5 Sekunden. Danach folgt Nr. 2! Ende?"
    assert _sentences(text) == ["Das gilt z. B. für ca. 30 Fälle mit 3.5 Sekunden.", "Danach folgt Nr. 2!", "Ende?"]


def test_a_label_is_found_through_a_compound_part_and_through_its_sub_line():
    narration = "Ein Emitter legt sie in eine Queue. Das Nutzerfeedback zählt mit."
    found = find_mentions(narration, ["EventEmitter", "Queue + Worker-Pool", "Lernsignal"],
                          ["", "", "Feedback, Outcome, Score"])
    assert narration[found[0][0]:].startswith("Emitter")
    assert narration[found[1][0]:].startswith("Queue")
    assert "feedback" in narration[found[2][0]:found[2][0] + 20].lower()


def test_a_token_two_items_share_does_not_decide():
    # "audit" is in both labels: only the unique parts may place them
    found = find_mentions("Erst die Kette, dann das Protokoll.", ["Audit-Kette", "Audit-Protokoll"])
    assert found[0] and found[1] and found[0][0] < found[1][0]


def test_fallback_chip_takes_a_noun_from_inside_the_sentence():
    assert fallback_chip("Jede Entscheidung landet als Architekturentscheidung im Wissensgraph.", "de") == \
        "Architekturentscheidung"
    assert fallback_chip("Kurz.", "de") is None


# ── audio ──────────────────────────────────────────────────────────────────

def test_sentence_starts_snap_to_pauses_in_order_and_use_each_pause_once():
    text = "Eins zwei drei vier. Fünf sechs sieben acht. Neun zehn elf zwölf."
    spans = split_sentences(text)
    # char share puts sentences 2 and 3 at ~3.3 s and ~6.6 s; real pauses end at 4.0 s and 6.1 s
    p = AudioPauses(duration=10.0, pause_ends=[4.0, 6.1], speech_start=0.0, speech_end=10.0, silent_ratio=0.1)
    starts = sentence_starts(spans, p)
    assert starts[0] == 0.0 and starts[1] == 4.0 and starts[2] == 6.1
    # two estimates competing for one pause: the second keeps its estimate
    # one pause both estimates (3.2 s, 6.6 s) could reach: the first takes it, the second keeps its estimate
    p2 = AudioPauses(duration=10.0, pause_ends=[4.2], speech_start=0.0, speech_end=10.0, silent_ratio=0.1)
    s2 = sentence_starts(spans, p2)
    assert s2[1] == 4.2 and s2[2] > s2[1] and s2[2] != 4.2


def test_silent_audio_is_not_snapped():
    spans = split_sentences("Eins zwei. Drei vier.")
    p = AudioPauses(duration=8.0, pause_ends=[1.0], speech_start=0.0, speech_end=8.0, silent_ratio=0.95)
    assert sentence_starts(spans, p)[1] != 1.0


@needs_ffmpeg
def test_detect_pauses_finds_the_gaps_in_real_audio(tmp_path):
    wav = tmp_path / "a.wav"
    # tone 1.0 s, pause 0.6 s, tone 2.0 s, pause 0.6 s, tone 1.0 s
    graph = ("sine=f=300:d=1[a];anullsrc=r=44100:cl=mono,atrim=0:0.6[s1];sine=f=300:d=2[b];"
             "anullsrc=r=44100:cl=mono,atrim=0:0.6[s2];sine=f=300:d=1[c];[a][s1][b][s2][c]concat=n=5:v=0:a=1")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-filter_complex", graph, "-ar", "44100", str(wav)], check=True)
    p = detect_pauses(wav, 5.2)
    assert len(p.pause_ends) == 2
    assert abs(p.pause_ends[0] - 1.6) < 0.08 and abs(p.pause_ends[1] - 4.2) < 0.08
    assert p.silent_ratio < 0.4


# ── cues ───────────────────────────────────────────────────────────────────

NARRATION = "Alles beginnt mit einem Fehler. Daraus wird ein Loss-Signal. Das ADR-Gate prüft es. Am Ende steht der Test."
NODES = {"title": "Kette", "nodes": [{"label": "Fehler"}, {"label": "Loss-Signal"}, {"label": "ADR-Gate"},
                                     {"label": "E2E-Test"}]}
PAUSES = AudioPauses(duration=12.0, pause_ends=[3.0, 6.0, 9.0], speech_start=0.0, speech_end=12.0, silent_ratio=0.1)


def _items(template, data):
    d = validate_scene_data(template, data)
    return scene_items(template, d), scene_item_subs(template, d)


def test_llm_beats_reveal_each_item_as_its_sentence_starts():
    items, subs = _items("diagram", NODES)
    tl = build_timeline("diagram", items, NARRATION, PAUSES, beats=[0, 1, 2, 3], subs=subs)
    assert tl.source == "llm"
    assert tl.step_times[3] == pytest.approx(3.0 - REVEAL_LEAD_S)
    assert tl.step_times[5] == pytest.approx(9.0 - REVEAL_LEAD_S)
    assert [s for _, s in tl.focus] == [3, 4, 5], "focus walks with the narration once two items are visible"
    assert all(b[0] - a[0] >= FOCUS_MIN_GAP_S for a, b in zip(tl.focus, tl.focus[1:]))


def test_without_beats_items_follow_where_the_narration_names_them():
    items, subs = _items("diagram", NODES)
    tl = build_timeline("diagram", items, NARRATION, PAUSES, subs=subs)
    assert tl.source == "fallback"
    times = [tl.step_times[s] for s in (2, 3, 4, 5)]
    assert times == sorted(times) and times[-1] > 8.0, "the last item is shown when the last sentence names it"


def test_beats_that_do_not_fit_the_narration_are_ignored_and_reported():
    items, subs = _items("diagram", NODES)
    tl = build_timeline("diagram", items, NARRATION, PAUSES, beats=[0, 1], subs=subs)
    assert tl.source == "fallback" and "beats length" in tl.notes[0]
    assert validate_beats([0, True, None, 1], 4, 4, _sentences(NARRATION), False)[0] is None
    assert validate_beats([0, 9, None, 1], 4, 4, _sentences(NARRATION), False)[0] is None
    # a chip on a non-sparse template is silently a null beat; a chip not in its sentence is invalid
    assert validate_beats(["Fehler", None, None, None], 4, 4, _sentences(NARRATION), False)[0][0] is None
    assert validate_beats(["Erfunden", None, None, None], 4, 4, _sentences(NARRATION), True)[0] is None


def test_an_item_named_in_the_last_words_is_still_on_screen_long_enough():
    items, subs = _items("diagram", NODES)
    late = AudioPauses(duration=12.0, pause_ends=[3.0, 6.0, 11.6], speech_start=0.0, speech_end=12.0, silent_ratio=0.1)
    tl = build_timeline("diagram", items, NARRATION, late, beats=[0, 1, 2, 3], subs=subs)
    assert max(tl.step_times.values()) <= 12.0 - MIN_VISIBLE_S + 1e-6


def test_chips_only_on_sparse_slides_and_never_when_claims_are_unverified():
    quote = {"quote": "Messen statt raten."}
    text = "Jede Entscheidung braucht ein Messsignal. Ohne Messsignal bleibt jede Architekturentscheidung geraten."
    p = AudioPauses(duration=10.0, pause_ends=[4.5], speech_start=0.0, speech_end=10.0, silent_ratio=0.1)
    tl = build_timeline("quote", [], text, p, lang="de", beats=["Messsignal", "Architekturentscheidung"])
    assert [c for _, c in tl.chips] == ["Messsignal", "Architekturentscheidung"]
    assert not build_timeline("quote", [], text, p, lang="de", chips_allowed=False,
                              beats=["Messsignal", "Architekturentscheidung"]).chips
    items, subs = _items("diagram", NODES)
    assert not build_timeline("diagram", items, NARRATION, PAUSES, lang="de", subs=subs).chips
    assert "Messen statt raten" in build_document("quote", quote, duration_s=10, timeline=tl)


def test_a_grounded_repair_drops_the_stale_beats():
    sb = {"scenes": [{"id": "s1", "kind": "solution", "duration_ms": 9000, "narration_text": "Alt. Alt.",
                      "beats": [0, 1], "template": "diagram", "data": NODES}]}
    fix = {"scenes": [{"id": "s1", "narration_text": "Neu und belegt."}]}
    n = repair_grounded_scenes(sb, {"s1": [("number", "42")]}, "pack", {}, call_llm=lambda p: json.dumps(fix),
                               validate_storyboard=lambda s: True, validate_scene=lambda s: True)
    assert n == 1, "the repair must be accepted for this test to mean anything"
    assert "beats" not in sb["scenes"][0] and sb["scenes"][0]["narration_text"] == "Neu und belegt."


def test_collision_fallback_to_bullets_keeps_every_node():
    data = {"title": "Kette", "nodes": [{"label": "Fehler", "sub": "rot"}, {"label": "Signal"}, {"label": "Gate"}]}
    trial = skill._content_trial("diagram", data, "x")
    assert trial["data"]["bullets"] == ["Fehler — rot", "Signal", "Gate"]
    assert skill._content_trial("chart", {"title": "t", "bars": [{"label": "a", "value": 1},
                                                                 {"label": "b", "value": 2}]}, "x") is None


# ── renderer + assembler through the real browser ──────────────────────────

@pytest.fixture
async def renderer():
    from src.web_renderer import WebRenderError, WebSlideRenderer
    try:
        async with WebSlideRenderer() as r:
            yield r
    except WebRenderError as e:
        pytest.skip(f"chromium unavailable: {e}")


def _frame(video: Path, t: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                    str(out)], check=True)
    return Image.open(out).convert("RGB")


@needs_ffmpeg
async def test_a_cue_late_in_a_long_scene_reaches_the_clip(renderer, tmp_path):
    """45 s scene, last bullet at 38 s: past the old 900-frame cap, and after a long
    stretch in which nothing animates (frames are skipped there). The clip must show it."""
    data = validate_scene_data("content", {"title": "Kette", "bullets": ["Fehler", "Loss-Signal", "ADR-Gate",
                                                                         "E2E-Test beweist die Entscheidung"]})
    tl = Timeline(duration=45.0, sentences=[], starts=[], step_times={2: 1.0, 3: 3.0, 4: 5.0, 5: 38.0},
                  item_steps=[2, 3, 4, 5], focus=[], chips=[], source="llm")
    frames = await renderer.render("content", data, 45.0, tmp_path / "f", timeline=tl)
    assert frames.schedule is not None and len(frames.schedule) >= 45 * 30
    assert len(frames) < len(frames.schedule) / 4, "quiet stretches must not be captured again"
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                    "-t", "45", str(wav)], check=True)
    clip = tmp_path / "c.mp4"
    skill._assemble_frames_clip(frames[0].parent, len(frames), wav, 45.0, clip, 30, schedule=frames.schedule)
    before, mid, after = (_frame(clip, t, tmp_path / f"{t}.png") for t in (20.0, 36.0, 42.0))
    # positive control: nothing changes in the quiet stretch (only codec noise)...
    assert ImageStat.Stat(ImageChops.difference(before, mid).convert("L")).mean[0] < 0.5
    # ...and the late bullet appears afterwards, below the others
    changed = ImageChops.difference(mid, after).convert("L").point(lambda x: 255 if x > 40 else 0).getbbox()
    assert changed is not None and changed[1] > 540, f"late bullet missing from the clip (changed box {changed})"


async def test_focus_brightens_the_named_item_and_dims_the_rest(renderer, tmp_path):
    data = validate_scene_data("diagram", NODES)
    tl = Timeline(duration=8.0, sentences=[], starts=[], step_times={2: 1.0, 3: 1.4, 4: 1.8, 5: 2.2},
                  item_steps=[2, 3, 4, 5], focus=[(5.0, 3)], chips=[], source="llm")
    frames = await renderer.render("diagram", data, 8.0, tmp_path / "f", timeline=tl)
    early = Image.open(frames[frames.schedule[int(4.5 * 30)]]).convert("L")
    late = Image.open(frames[frames.schedule[int(7.0 * 30)]]).convert("L")
    # node 0 (left) dims, node 1 (focused) keeps its brightness
    left, focused = (170, 450, 470, 750), (560, 450, 860, 750)
    assert ImageStat.Stat(late.crop(left)).mean[0] < ImageStat.Stat(early.crop(left)).mean[0] - 2
    assert ImageStat.Stat(late.crop(focused)).mean[0] >= ImageStat.Stat(early.crop(focused)).mean[0] - 1


@needs_ffmpeg
def test_silent_mock_audio_spreads_the_cues_over_the_whole_clip(tmp_path):
    """The offline mock voice is pure silence: its 'speech' must not collapse to the end."""
    wav = tmp_path / "s.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                    "-t", "10", str(wav)], check=True)
    p = detect_pauses(wav, 10.0)
    assert p.speech_start == 0.0 and p.speech_end == 10.0 and p.pause_ends == []
    items, subs = _items("diagram", NODES)
    tl = build_timeline("diagram", items, NARRATION, p, beats=[0, 1, 2, 3], subs=subs)
    times = sorted(tl.step_times.values())
    assert times[0] < 2.0 and 5.0 < times[-1] < 9.0
