"""Stand-in job process for runner-level tests: argv = <job_id> <config.json>. Behaviour from STUB_MODE:
quick | sleep | ignore_term | die7 | silent | complete_exit3 | done_then_hang. Keeps a grandchild in the job's process group (like Chromium)."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

job_id, cfg = sys.argv[1], Path(sys.argv[2])
payload = json.loads(cfg.read_text())
base = Path(payload["config"]["storage_base"])
mode = os.environ.get("STUB_MODE", "quick")
marks = Path(os.environ["STUB_MARKS"])
marks.mkdir(exist_ok=True)
(marks / f"{job_id}.start").write_text(str(time.time()))


def set_status(status):
    f = base / "jobs" / f"{job_id}.json"
    d = json.loads(f.read_text())
    d["status"] = status
    f.write_text(json.dumps(d))


if mode in ("complete_exit3", "done_then_hang"):
    set_status("complete")
    if mode == "complete_exit3":
        sys.exit(3)
    time.sleep(600)
if mode == "die7":
    sys.exit(7)
if mode in ("sleep", "ignore_term"):
    if mode == "ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        subprocess.Popen(["sh", "-c", 'trap "" TERM; sleep 600'])
    else:
        subprocess.Popen(["sleep", "600"])
    set_status("skills_running")
    time.sleep(float(os.environ.get("STUB_SECS", "600")))
if mode != "silent":
    set_status("complete")
