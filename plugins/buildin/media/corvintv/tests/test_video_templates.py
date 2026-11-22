"""Video templates (CONCEPT-0137): the shipped set loads, the schema is strict, the prompt and the checks follow
the chosen template, and the default template leaves the storyboard prompt exactly as it was."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from src import skill
from src import video_templates as vt

SHIPPED = {"standard", "short", "marketing", "code_debugging", "research", "didactic", "tutorial",
           "release_notes", "executive_brief", "postmortem", "faq", "website"}


def _raw(tid="probe", **over):
    """A minimal valid template dict (copied from the shipped didactic one so it stays in step with the schema)."""
    path = Path(vt.TEMPLATE_DIR) / "didactic.json"
    d = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
    d["id"] = tid
    d.update(over)
    return d


def _scene(i, kind, text, ms=8000, template=None):
    s = {"id": "s%d" % i, "kind": kind, "duration_ms": ms, "narration_text": text, "visual_description": "a picture"}
    if template:
        s["template"] = template
    return s


# -- the shipped set ---------------------------------------------------------------------------

def test_the_shipped_set_is_complete_and_valid():
    all_ = vt.load_all()
    assert set(all_) == SHIPPED
    for tid, t in all_.items():
        assert (Path(vt.TEMPLATE_DIR) / (tid + ".json")).is_file()
        assert t.name["de"] and t.name["en"] and t.summary["de"] and t.summary["en"]
        assert t.target_s <= t.max_s and t.scene_min <= t.scene_max


def test_the_default_template_is_first_and_the_order_is_stable():
    assert next(iter(vt.load_all())) == vt.DEFAULT_TEMPLATE_ID
    assert list(vt.load_all()) == [k for k, _ in sorted(vt.load_all().items(), key=lambda kv: (kv[1].sort, kv[0]))]


def test_short_is_listed_but_not_producible_until_the_vertical_renderer_exists():
    t = vt.get("short")
    assert t.aspect == "9:16" and t.available is False and t.unavailable_reason
    assert t.hook_max_words == 12 and "opens_with_question" in t.checks
    with pytest.raises(vt.TemplateError, match="not available"):
        vt.usable("short")


def test_every_other_template_is_16_9_and_producible():
    for tid in SHIPPED - {"short"}:
        assert vt.usable(tid).aspect == "16:9"


def test_only_the_website_template_has_another_mode_than_slides():
    # ADR-2336: a template with another mode picks another job pipeline; the others shape a slide storyboard
    assert {tid for tid, t in vt.load_all().items() if t.mode != "slides"} == {"website"}


def test_unknown_id_is_refused_and_none_means_default():
    assert vt.get(None).id == vt.get("").id == "standard"
    with pytest.raises(vt.TemplateError, match="unknown video template"):
        vt.get("nope")


# -- strict schema -------------------------------------------------------------------------------

@pytest.mark.parametrize("change, message", [
    ({"surprise": 1}, "unknown key"),
    ({"checks": ["no_such_check"]}, "unknown check"),
    ({"preferred_slides": ["no_such_slide"]}, "no such slide template"),
    ({"category": "other"}, "category"),
    ({"id": "Bad Id"}, "id must match"),
    ({"duration": {"target_s": 10, "min_s": 20, "max_s": 30}}, "min_s <= target_s"),
    ({"format": {"aspect": "16:9", "available": False}}, "must say why"),
    ({"format": {"aspect": "4:3", "available": True}}, "aspect"),
    ({"hook": {"kind": "question", "max_words": 12}}, "opens_with_question"),
    ({"recommended_model": "gpt"}, "recommended_model"),
    ({"schema": 2}, "schema"),
    ({"name": {"en": "only english"}}, "languages"),
])
def test_a_bad_template_is_refused_with_its_reason(change, message):
    with pytest.raises(vt.TemplateError, match=message):
        vt.parse_template(_raw(**change))


def test_a_file_whose_id_differs_from_its_name_fails_the_load(tmp_path):
    good = json.loads((Path(vt.TEMPLATE_DIR) / "standard.json").read_text(encoding="utf-8"))
    (tmp_path / "standard.json").write_text(json.dumps(good), encoding="utf-8")
    other = copy.deepcopy(good)
    other["id"] = "elsewhere"
    (tmp_path / "wrongname.json").write_text(json.dumps(other), encoding="utf-8")
    with pytest.raises(vt.TemplateError, match="must equal the file name"):
        vt.load_all(tmp_path)


def test_a_directory_without_the_default_fails_the_load(tmp_path):
    only = _raw("didactic")
    (tmp_path / "didactic.json").write_text(json.dumps(only), encoding="utf-8")
    with pytest.raises(vt.TemplateError, match="default template"):
        vt.load_all(tmp_path)


# -- prompt block --------------------------------------------------------------------------------

def test_the_default_template_adds_nothing_to_the_prompt():
    assert vt.prompt_block(vt.get("standard")) == ""


@pytest.mark.parametrize("tid", sorted(SHIPPED - {"standard"}))
def test_the_prompt_block_names_the_template_its_plan_and_its_rules(tid):
    t = vt.get(tid)
    block = vt.prompt_block(t)
    assert "VIDEO TEMPLATE: %s" % t.name["en"] in block
    assert all(r in block for r in t.rules)
    assert all(('kind "%s"' % s.kind) in block for s in t.structure)
    assert "Never use pressure, fear, shame or false urgency" in block


def test_the_short_prompt_demands_a_question_hook():
    block = vt.prompt_block(vt.get("short"))
    assert "HOOK:" in block and "at most 12 words" in block


def test_a_template_can_only_lower_the_tenant_ceiling():
    assert vt.effective_max_minutes(vt.get("marketing"), 60) == 2
    assert vt.effective_max_minutes(vt.get("marketing"), 1) == 1
    assert vt.effective_max_minutes(vt.get("standard"), 45) == 45


# -- checks --------------------------------------------------------------------------------------

def test_the_question_hook_check():
    t = vt.parse_template(_raw("hooked", hook={"kind": "question", "max_words": 6},
                               checks=["opens_with_question"]))

    def hook_codes(text):
        return [i.code for i in vt.check_storyboard(t, {"scenes": [_scene(1, "title", text)]})
                if i.code.startswith("hook_")]
    assert hook_codes("Why does an AI forget? It runs out of room.") == []
    assert hook_codes("An AI forgets. It runs out of room.") == ["hook_not_question"]
    assert hook_codes("Why does an artificial intelligence sometimes forget things?") == ["hook_too_long"]
    assert all(i.severity == "error" for i in vt.check_storyboard(t, {"scenes": [_scene(1, "title", "A statement.")]})
               if i.code.startswith("hook_"))


def test_length_and_scene_count_are_errors_only_above_the_maximum():
    t = vt.get("marketing")
    long_sb = {"scenes": [_scene(i, "solution", "x" * 150, ms=20000) for i in range(1, 8)]}  # 140 s > 120 s * 1.1
    codes = {i.code: i.severity for i in vt.check_storyboard(t, long_sb)}
    assert codes["too_long"] == "error"
    many = {"scenes": [_scene(i, "solution", "x" * 150, ms=6000) for i in range(1, 11)]}
    assert {i.code: i.severity for i in vt.check_storyboard(t, many)}["too_many_scenes"] == "error"
    short_sb = {"scenes": [_scene(1, "title", "x", ms=8000)]}
    assert {i.code: i.severity for i in vt.check_storyboard(t, short_sb)}["too_short"] == "warning"


def test_pressure_language_and_a_missing_code_scene_are_warnings():
    t = vt.get("code_debugging")
    sb = {"scenes": [_scene(1, "title", "Fix this now - last chance.", ms=9000)]}
    found = {i.code: i.severity for i in vt.check_storyboard(t, sb)}
    assert found["no_code_scene"] == "warning"
    t2 = vt.get("marketing")
    found2 = {i.code: i.severity for i in vt.check_storyboard(t2, sb)}
    assert found2["pressure_language"] == "warning"
    assert not vt.errors(vt.check_storyboard(t2, sb))


def test_the_default_template_has_no_extra_checks():
    assert vt.check_storyboard(vt.get("standard"), {"scenes": [_scene(1, "title", "x")]}) == []


# -- through the storyboard writer (the LLM call is the only thing replaced) --------------------------

def _good_marketing(n=6):
    kinds = ["title", "problem", "solution", "example", "example", "anchor"][:n]
    return {"id": "sb_t", "didactic_strategy": "minimal_visual",
            "scenes": [_scene(i + 1, k, "A concrete sentence about the product number %d." % i + " " * 0 + "x" * 120, ms=12000,
                              template="hero" if i == 0 else None) for i, k in enumerate(kinds)]}


def _run(monkeypatch, replies, template, **kw):
    prompts = []

    def fake(prompt, **_kw):
        prompts.append(prompt)
        return json.dumps(replies[min(len(prompts) - 1, len(replies) - 1)])
    monkeypatch.setattr(skill, "_call_storyboard_llm", fake)
    sb = asyncio.run(skill.generate_storyboard_with_llm("a task", backend="claude_cli", video_template=template, **kw))
    return sb, prompts


def test_a_template_changes_the_prompt_and_the_default_does_not(monkeypatch):
    _, with_tpl = _run(monkeypatch, [_good_marketing()], "marketing")
    assert "VIDEO TEMPLATE: Marketing" in with_tpl[0]
    assert "Each scene duration: 6000-16000 ms" in with_tpl[0]
    assert "Maximum 8 scenes" in with_tpl[0]
    _, plain = _run(monkeypatch, [_good_marketing()], None)
    assert "VIDEO TEMPLATE" not in plain[0]
    assert "Each scene duration: 8000-20000 ms (8-20 seconds)" in plain[0]


def test_a_template_error_gets_exactly_one_repair_call(monkeypatch):
    too_long = _good_marketing()
    for s in too_long["scenes"]:
        s["duration_ms"] = 30000  # 180 s > 132 s
    sb, prompts = _run(monkeypatch, [too_long, _good_marketing()], "marketing")
    assert len(prompts) == 2 and "breaks the video template" in prompts[1]
    assert sum(s.duration_ms for s in sb.scenes) <= 132000


def test_a_reply_that_stays_wrong_after_the_repair_fails_the_job(monkeypatch):
    too_long = _good_marketing()
    for s in too_long["scenes"]:
        s["duration_ms"] = 30000
    with pytest.raises(ValueError, match="breaks the 'marketing' video template"):
        _run(monkeypatch, [too_long, too_long], "marketing")


def test_an_unavailable_or_unknown_template_never_reaches_the_model(monkeypatch):
    calls = []
    monkeypatch.setattr(skill, "_call_storyboard_llm", lambda *a, **k: calls.append(1) or "{}")
    for tid in ("short", "nope"):
        with pytest.raises(vt.TemplateError):
            asyncio.run(skill.generate_storyboard_with_llm("a task", backend="claude_cli", video_template=tid))
    assert calls == []


def test_the_config_key_reaches_the_storyboard_writer(monkeypatch):
    """_orchestrate_from_config is the job process's entry: the template id in the config must arrive as the
    storyboard writer's video_template argument."""
    seen = {}

    async def fake_orchestrate(**kw):
        seen.update(kw)
        return {}
    monkeypatch.setattr(skill, "orchestrate_video", fake_orchestrate)
    asyncio.run(skill._orchestrate_from_config("job_x", "task", {"storage_base": "/tmp/x", "video_template": "research"}))
    assert seen["video_template"] == "research"


def test_no_text_the_panel_shows_carries_a_decision_or_concept_id():
    """The console is a production surface: names, summaries, audience, tone and the unavailable reason are drawn
    verbatim, and an internal id (ADR-nnnn, CONCEPT-nnnn) must stay in code comments and docs."""
    import re
    pat = re.compile(r"\b(ADR|CONCEPT|PLAN|REVIEW)-\d")
    for t in vt.load_all().values():
        shown = list(t.name.values()) + list(t.summary.values()) + [t.audience, t.tone, t.unavailable_reason]
        shown += [s.purpose for s in t.structure]
        assert not [x for x in shown if pat.search(x)], t.id
