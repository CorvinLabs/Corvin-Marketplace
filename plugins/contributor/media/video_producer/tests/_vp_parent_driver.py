"""A stand-in 'console': starts one real job through ProcessJobRunner, prints READY, then idles until killed."""
import json
import sys
import time
from pathlib import Path

MP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MP))
from src.async_runner import ProcessJobRunner  # noqa: E402
from src.models import VideoJob  # noqa: E402
from src.storage import get_storage  # noqa: E402
import asyncio  # noqa: E402

base, job_id, storyboard_file = sys.argv[1:4]
entry = sys.argv[4] if len(sys.argv) > 4 else "_vp_job_main_mock_tts.py"
get_storage(base).save_job(VideoJob(id=job_id, task="parent-death"))
runner = ProcessJobRunner(entry=[sys.executable, str(MP / "tests" / entry)])
asyncio.run(runner.start_job(job_id, "parent-death", {
    "storage_base": base, "tts_engine": "auto", "max_duration_minutes": 5,
    "storyboard": json.loads(Path(storyboard_file).read_text())}))
print("READY", flush=True)
while True:
    time.sleep(1)
