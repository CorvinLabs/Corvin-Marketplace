"""Test entry for ProcessJobRunner: the REAL job_main with two seams and nothing else replaced.

- the storyboard MODEL: ``_call_claude_cli`` answers from files in ``$VP_FAKE_LLM_DIR`` -
  ``<job_id>.storyboard.json`` for the storyboard prompt, ``<job_id>.repair.json`` for the one repair
  round (the prompt that carries "FAILED SCENES"). Everything after the model's answer - parsing,
  validation, the repair round, ``continue_from``, the renderer, the canvas probe, the degrade
  ladder, ffmpeg, the report and its signals - is production code;
- the TTS chain is reduced to the offline mock tier (no network, no spend).
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
    skill._TTS_CHAIN = (("mock", skill._tts_tier_mock),)
    folder = Path(os.environ["VP_FAKE_LLM_DIR"])
    job_id = os.environ["CORVIN_VIDEO_JOB_ID"]

    def fake_cli(prompt: str, model: str) -> str:
        which = "repair" if "FAILED SCENES" in prompt else "storyboard"
        return (folder / f"{job_id}.{which}.json").read_text(encoding="utf-8")

    skill._call_claude_cli = fake_cli


if __name__ == "__main__":
    job_main._drop_script_dir_from_path()
    sys.exit(job_main.main(before_run=_fake))
