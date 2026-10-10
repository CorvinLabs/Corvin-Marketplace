"""One language per video, and no silent video (review 2026-10-10, findings B1/B3)."""
import pytest

from src import skill

TEXT_DE = ["Willkommen bei Acme, hier sehen Sie unser eigenes Erscheinungsbild.",
           "Wir zeigen heute drei Schritte.", "Jeder Agent bekommt seinen eigenen Kontext."]


@pytest.mark.parametrize("text,lang", [*((t, "de") for t in TEXT_DE),
                                       ("Today we explain why the die is cast.", "en"),
                                       ("The audit chain links every record to the one before it.", "en")])
def test_short_sentences_are_classified_by_function_words(text, lang):
    assert skill._detect_lang(text) == lang


def test_every_scene_of_a_video_is_voiced_in_the_videos_language(run_orchestrate):
    # scene 2 alone ("Kontext und Agent.") carries no function word an older guess could use
    scenes = [{"id": f"s{i}", "kind": "example", "duration_ms": 8000, "narration_text": t, "visual_description": "d"}
              for i, t in enumerate([TEXT_DE[0], "Agent, Kontext, Pipeline: drei Begriffe.", TEXT_DE[2]], 1)]
    _, spies = run_orchestrate(scenes, spies_for=("_synthesize_narration_openai",))
    assert [a[2] for a, _ in spies["_synthesize_narration_openai"]] == ["de", "de", "de"]


def test_the_production_voice_chain_has_no_silent_tier():
    assert [name for name, _ in skill._TTS_CHAIN] == ["openai", "edge", "piper"]


def test_when_every_voice_declines_the_job_fails_instead_of_going_mute(monkeypatch, tmp_path):
    monkeypatch.setattr(skill, "_TTS_CHAIN", (("openai", lambda *a: False), ("edge", lambda *a: False)))
    with pytest.raises(skill.NoVoiceAvailable):
        skill._synthesize_narration_chain("Hallo Welt.", tmp_path / "a.mp3", "de")
