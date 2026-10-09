from src.skill import _degrade_to_web_slides, _apply_web_scene_contract
from src.web_templates import build_document


def test_invalid_scene_becomes_quote_slide_not_placeholder():
    scenes = [{"id": "s5", "kind": "example", "narration_text": "Die Kette reißt, sobald jemand einen Eintrag ändert. Das ist gewollt.",
               "template": None}]
    assert _degrade_to_web_slides(scenes) == 1
    assert scenes[0]["template"] == "quote"
    assert scenes[0]["data"]["locale"] == "de"
    assert not _apply_web_scene_contract([scenes[0]], strict=True)
    html = build_document(scenes[0]["template"], scenes[0]["data"], duration_s=6)
    assert "Die Kette" in html


def test_valid_and_capture_scenes_untouched():
    scenes = [{"id": "a", "template": "hero", "data": {"title": "x"}, "narration_text": "Hi there."},
              {"id": "b", "kind": "screenshot", "narration_text": "Look."}]
    assert _degrade_to_web_slides(scenes) == 0
    assert scenes[0]["template"] == "hero" and "template" not in scenes[1]


def test_logo_is_the_real_mark_with_gold_dot():
    html = build_document("hero", {"title": "T"}, duration_s=4)
    assert "#C9A227" in html and "M28 40 L56 60 L28 80" in html


def test_diagram_label_font_shrinks_for_long_word_in_six_nodes():
    nodes = [{"label": "Einwilligungsprüfung"}] + [{"label": f"N{i}"} for i in range(5)]
    html = build_document("diagram", {"title": "T", "nodes": nodes}, duration_s=8, lang="de")
    import re
    sizes = [int(m) for m in re.findall(r'class="l" style="font-size:(\d+)px">Einwilligungsprüfung', html)]
    assert sizes and sizes[0] < 40
