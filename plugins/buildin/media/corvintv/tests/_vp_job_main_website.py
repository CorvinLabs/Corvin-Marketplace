"""Test entry for ProcessJobRunner (website tour): the REAL job_main with two seams and nothing else replaced.

- the TTS chain is reduced to the offline mock tier, and every call of ``_synthesize_narration_chain`` is appended to
  ``$VP_TTS_LOG`` (one line per call) so a test can prove the tour speaks through that one function and no other;
- the tour MODEL: ``_call_claude_cli`` answers from ``$VP_FAKE_LLM_DIR/<job>.tour.json`` (first call) and
  ``<job>.repair.json`` (the repair prompt, which carries "Your previous answer had these problems").
Production never uses this; the runner takes it through its ``entry`` argument."""
import importlib.util
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
_spec = importlib.util.spec_from_file_location("vp_job_main_under_test", _SRC / "job_main.py")
job_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(job_main)


def _fake(skill) -> None:
    def probe_tier(text, out_path, lang):
        # what the production tier does with the job's voice override: rewrite the voice slot of say.py's argv (logged, then mocked)
        log = os.environ.get("VP_TTS_VOICE_LOG")
        if log:
            argv, env = skill._apply_tts_override(["py", "/x/say.py", "out", "t", lang, "nova"], {})
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"{argv[-1]}|{env.get('CORVIN_TTS_OPENAI_MODEL', '-')}\n")
        return skill._tts_tier_mock(text, out_path, lang)

    skill._TTS_CHAIN = (("mock", probe_tier),)
    real = skill._synthesize_narration_chain

    def counted(text, out_path, lang):
        with open(os.environ["VP_TTS_LOG"], "a", encoding="utf-8") as fh:
            fh.write(f"{lang}\n")
        return real(text, out_path, lang)

    skill._synthesize_narration_chain = counted
    folder = os.environ.get("VP_FAKE_LLM_DIR")
    if folder:
        job_id = os.environ["CORVIN_VIDEO_JOB_ID"]

        def fake_cli(prompt: str, model: str, timeout_s=None) -> str:
            which = "repair" if "Your previous answer had these problems" in prompt else "tour"
            return (Path(folder) / f"{job_id}.{which}.json").read_text(encoding="utf-8")

        skill._call_claude_cli = fake_cli


if __name__ == "__main__":
    job_main._drop_script_dir_from_path()
    sys.exit(job_main.main(before_run=_fake))
