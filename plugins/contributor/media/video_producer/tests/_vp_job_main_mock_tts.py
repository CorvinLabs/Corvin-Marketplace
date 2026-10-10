"""Test entry for ProcessJobRunner: the real job_main with the TTS chain reduced to the offline mock tier
(no network, no spend). Production never uses this; the runner takes it through its ``entry`` argument."""
import importlib.util
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
_spec = importlib.util.spec_from_file_location("vp_job_main_under_test", _SRC / "job_main.py")
job_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(job_main)


def _offline(skill) -> None:
    skill._TTS_CHAIN = (("mock", skill._tts_tier_mock),)


if __name__ == "__main__":
    job_main._drop_script_dir_from_path()
    sys.exit(job_main.main(before_run=_offline))
