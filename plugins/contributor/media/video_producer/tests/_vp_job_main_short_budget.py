"""Test entry for ProcessJobRunner: like _vp_job_main_mock_tts (offline mock TTS) but with the job's
wall-clock budget cut to VP_TEST_BUDGET_S seconds, so the budget path can be driven in seconds, not 3 minutes."""
import importlib.util
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
_spec = importlib.util.spec_from_file_location("vp_job_main_under_test", _SRC / "job_main.py")
job_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(job_main)


def _offline(skill) -> None:
    skill._TTS_CHAIN = (("mock", skill._tts_tier_mock),)
    secs = float(os.environ["VP_TEST_BUDGET_S"])
    skill.dl.job_budget_seconds = lambda minutes: secs


if __name__ == "__main__":
    job_main._drop_script_dir_from_path()
    sys.exit(job_main.main(before_run=_offline))
