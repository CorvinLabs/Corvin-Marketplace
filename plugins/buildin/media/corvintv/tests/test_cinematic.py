"""Cinematic mode, unit level: screenplay prompt and validator, page safety, timeline, frame plan, Penpot designs.

The job pipeline end to end (real job_main, Chromium, ffmpeg) is in ``test_cinematic_job_e2e.py``."""
import copy
import json
import re
import wave
from pathlib import Path

import pytest

from src.cinematic import direction as dr
from src.cinematic import produce, stage

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOOD = {"title": {"en": "T"}, "acts": [
    {"id": "01", "beats": [{"en": "word " * 12}, {"en": "word " * 12}, {"en": "word " * 12}],
     "actors": [{"id": "sky", "type": "sky", "par": 0.1}, {"id": "cap", "type": "caption", "text": {"en": "Hello"}},
                {"id": "d", "type": "art", "src": "board", "w": 800, "h": 450, "p": 0}],
     "tweens": [{"a": "d", "p": "p", "to": 1, "at": "b1", "d": 1.2, "e": "out"},
                {"a": "cam", "p": "zoom", "to": 1.1, "at": "b0", "d": 4}]},
    {"id": "02", "beats": [{"en": "word " * 12}, {"en": "word " * 12}, {"en": "word " * 12}, {"en": "word " * 12}],
     "actors": [{"id": "g", "type": "grade", "v": 0.6, "z": 100}], "tweens": []}]}


def ok(doc=None, minutes=1, langs=("en",), art=("board",)):
    return dr.check(doc if doc is not None else GOOD, minutes, langs, art)


def test_a_valid_screenplay_has_no_findings():
    assert ok() == []


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d["acts"][0]["actors"].append({"id": "x", "type": "dragon"}), "unknown actor type"),
    (lambda d: d["acts"][0]["actors"][0].update(bogus=1), "unknown property"),
    (lambda d: d["acts"][0]["actors"][2].update(src="ghost"), "unknown design"),
    (lambda d: d["acts"][0]["tweens"].append({"a": "nobody", "p": "x", "to": 1, "at": 0}), "unknown actor"),
    (lambda d: d["acts"][0]["tweens"].append({"a": "sky", "p": "tone", "to": 1, "at": "b9"}), "refers to beat 9"),
    (lambda d: d["acts"][0]["tweens"].append({"a": "sky", "p": "tone", "to": 1, "at": "soon"}), "bad 'at'"),
    (lambda d: d["acts"][0]["tweens"].append({"a": "sky", "p": "tone", "to": 1, "at": 0, "e": "wobble"}), "unknown easing"),
    (lambda d: d["acts"][0]["beats"][0].pop("en"), "lacks en"),
    (lambda d: d["acts"][0]["actors"][1].update(text={"de": "x"}), "caption"),
    (lambda d: d["acts"][1].update(id="01"), "duplicate act id"),
])
def test_the_validator_names_every_defect(mutate, needle):
    doc = copy.deepcopy(GOOD)
    mutate(doc)
    assert any(needle in f for f in ok(doc)), ok(doc)


def test_the_validator_reports_all_findings_at_once_for_one_repair_round():
    doc = copy.deepcopy(GOOD)
    doc["acts"][0]["actors"].append({"id": "x", "type": "dragon"})
    doc["acts"][0]["actors"][2]["src"] = "ghost"
    assert len(ok(doc)) >= 2


def test_a_second_language_is_required_on_every_beat_and_caption():
    errs = ok(GOOD, langs=("en", "de"))
    assert any("lacks de" in e for e in errs) and any("caption" in e for e in errs)


def test_narration_far_from_the_target_length_is_flagged():
    doc = copy.deepcopy(GOOD)
    for a in doc["acts"]:
        for b in a["beats"]:
            b["en"] = "word " * 80
    assert any("narration has" in e for e in ok(doc))


def test_extract_handles_fences_and_rejects_garbage():
    assert dr.extract("```json\n" + json.dumps(GOOD) + "\n```")["acts"]
    with pytest.raises(dr.DirectionError):
        dr.extract("no json here")
    with pytest.raises(dr.DirectionError):
        dr.extract("{bad json}")


def test_the_prompt_carries_the_manual_the_designs_and_the_brief_exactly_once():
    brief = "Explain {LIBRARY} and {ART_NAMES} please"  # tokens inside the brief must not be re-expanded
    p = dr.build_prompt(brief, 3, ["de", "en"], ["board", "logo"])
    assert "board, logo" in p and "ACTORS" not in p and "`art`" in p
    assert p.count(brief) == 1
    assert '{"de": "...", "en": "..."}' in p
    assert "{TASK}" not in p and "{MINUTES}" not in p
    assert "none are supplied" in dr.build_prompt("x", 3, ["en"], [])


def test_every_actor_the_manual_lists_exists_in_the_engine_and_the_validator():
    manual = dr.library_text()
    engine = "".join((stage.ENGINE / f).read_text(encoding="utf-8") for f in stage.FILES)
    defined = set(re.findall(r"ACTORS\.(\w+) =", engine))
    assert defined == set(dr.PROPS), defined ^ set(dr.PROPS)
    for name in defined:
        assert f"`{name}`" in manual, f"{name} is not documented in LIBRARY.md"


def test_the_page_cannot_be_broken_out_of_by_screenplay_text():
    hostile = "</script><img src=x onerror=alert(1)><!-- \u2028"
    acts = [{"id": "a", "dur": 4.0, "beats": [1.0], "tweens": [],
             "actors": [{"id": "c", "type": "caption", "text": {"en": hostile}}]}]
    page = stage.build_page(acts, {})
    assert "</script><img" not in page and "<!--" not in page.split("const ACTS", 1)[1].split("const ASSETS", 1)[0]
    assert page.count("</script>") == 1
    assert "\\u003c/script\\u003e" in page


def test_the_page_embeds_the_bundled_fonts_so_a_video_looks_the_same_everywhere():
    page = stage.build_page([], {})
    assert page.count("@font-face") == 3 and "Newsreader" in page and "Instrument Sans" in page


def test_a_penpot_design_becomes_a_sanitised_data_image():
    out = stage.prepare_art({"board": (FIXTURES / "penpot_board.svg").read_bytes()})
    url = out["board"]
    assert url.startswith("data:image/svg+xml;base64,")
    import base64
    svg = base64.b64decode(url.split(",", 1)[1]).decode("utf-8")
    assert svg.lstrip().startswith("<svg") and "<script" not in svg and "localhost:9001" not in svg


def test_hostile_or_malformed_designs_are_refused_by_name():
    with pytest.raises(stage.CinematicError, match="board"):
        stage.prepare_art({"board": b"<svg><![CDATA[x]]></svg"})
    with pytest.raises(stage.CinematicError, match="name"):
        stage.prepare_art({"../x": b"<svg/>"})
    with pytest.raises(stage.CinematicError, match="at most"):
        stage.prepare_art({f"d{i}": b"<svg/>" for i in range(stage.MAX_ART + 1)})


def test_timeline_slots_follow_the_longer_language_and_sit_on_the_frame_grid():
    acts = [{"id": "a", "beats": [{}, {}]}, {"id": "b", "beats": [{}]}]
    d = {(0, 0, "de"): 2.0, (0, 0, "en"): 3.0, (0, 1, "de"): 1.0, (0, 1, "en"): 1.0, (1, 0, "de"): 4.0, (1, 0, "en"): 2.0}
    tl = produce.build_timeline(acts, d, ["de", "en"], 24)
    a0, a1 = tl["acts"]
    assert a0["slots"] == [3.0 + produce.GAP_S, 1.0 + produce.GAP_S]
    assert a0["beats"][0] == produce.LEAD_S and a0["beats"][1] == pytest.approx(produce.LEAD_S + a0["slots"][0], abs=1e-3)
    assert a1["start"] == pytest.approx(a0["dur"], abs=1e-3)
    for a in tl["acts"]:
        assert round(a["dur"] * 24) == pytest.approx(a["dur"] * 24, abs=1e-6)  # whole frames
    assert tl["total_s"] == pytest.approx(a0["dur"] + a1["dur"], abs=1e-3)


def test_frame_plan_draws_text_acts_once_per_language_and_shared_acts_once(tmp_path):
    acts = [{"actors": [{"type": "caption"}]}, {"actors": [{"type": "sky"}]}]
    tl = {"fps": 24, "acts": [{"act": 0, "dur": 1.0}, {"act": 1, "dur": 1.0}]}
    plan, seq = produce.frame_plan(acts, tl, ["de", "en"], tmp_path, "jpg")
    assert len(plan) == 24 * 2 + 24 and len(seq["de"]) == len(seq["en"]) == 48
    assert seq["de"][:24] != seq["en"][:24] and seq["de"][24:] == seq["en"][24:]
    plan1, seq1 = produce.frame_plan(acts, tl, ["en"], tmp_path, "jpg")
    assert len(plan1) == 48 == len(seq1["en"])  # a single language never doubles a captioned act


def test_audio_lands_on_the_timeline_grid(tmp_path):
    def mk(name, secs):
        p = tmp_path / name
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
            w.writeframes(b"\x01\x00" * int(24000 * secs))
        return p
    wavs = {(0, 0): mk("a.wav", 1.0), (0, 1): mk("b.wav", 0.5)}
    durs = {(0, 0): 1.0, (0, 1): 0.5}
    tl = produce.build_timeline([{"id": "a", "beats": [{}, {}]}], {(0, 0, "en"): 1.0, (0, 1, "en"): 0.5}, ["en"], 24)
    out = tmp_path / "o.wav"
    produce.write_audio(out, tl, wavs, durs)
    with wave.open(str(out)) as w:
        assert w.getnframes() / w.getframerate() == pytest.approx(tl["total_s"], abs=0.05)
