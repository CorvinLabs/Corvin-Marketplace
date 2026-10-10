"""Test entry for ProcessJobRunner: the real job_main whose first narration call blocks for a minute, so a
test can act on a job that is provably still running (no race against a fast render)."""
import importlib.util
import sys
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
_spec = importlib.util.spec_from_file_location("vp_job_main_under_test", _SRC / "job_main.py")
job_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(job_main)


def _stall(skill) -> None:
    def tier(text, out_path, lang):
        time.sleep(60)
        return skill._tts_tier_mock(text, out_path, lang)
    skill._TTS_CHAIN = (("mock", tier),)


if __name__ == "__main__":
    job_main._drop_script_dir_from_path()
    sys.exit(job_main.main(before_run=_stall))
