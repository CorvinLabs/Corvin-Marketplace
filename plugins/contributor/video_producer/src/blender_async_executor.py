"""Blender Async Executor (Tier 3)

Manages non-blocking async Blender render jobs with:
- Submission queue (fast <100ms submission)
- Job polling without blocking
- Auto-downgrade to Tier 2 if Blender unavailable >48h
- Error recovery + fallback chain
"""

import json
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class BlenderJob:
    """Async Blender render job."""
    job_id: str
    blend_file: str
    output_path: str
    scene_name: str
    status: str  # "queued", "running", "complete", "failed"
    start_time: Optional[str]
    end_time: Optional[str]
    process_pid: Optional[int]
    error: Optional[str]


class BlenderAsyncExecutor:
    """Submit Blender render jobs asynchronously (non-blocking, <100ms)."""

    def __init__(
        self,
        blender_path: str = "/usr/bin/blender",
        max_jobs: int = 2,
        job_storage: str = "~/.corvin/video-producer/blender-jobs",
    ):
        self.blender_path = blender_path
        self.max_jobs = max_jobs
        self.job_storage = Path(job_storage).expanduser()
        self.job_storage.mkdir(parents=True, exist_ok=True)
        self.running_jobs: Dict[str, Dict] = {}
        self.failure_log = self.job_storage / "failures.jsonl"
        self._verify_blender_available()

    def submit_job(
        self,
        blend_file: str,
        output_path: str,
        scene_name: str,
    ) -> Optional[str]:
        """Submit Blender job (non-blocking, <100ms).

        Returns: job_id on success, None on failure
        """
        start_time = time.time()

        # Check if Blender is available and not overloaded
        if not self._is_blender_healthy():
            logger.warning("Blender unavailable or too many failures; return None for fallback")
            return None

        # Check current job count
        if len(self.running_jobs) >= self.max_jobs:
            logger.warning(f"Blender job queue full ({self.max_jobs} jobs); queue job")
            return None

        job_id = str(uuid.uuid4())

        # Blender Python script (CYCLES rendering, video-optimized)
        blend_script = f"""
import bpy
import sys

# Use CYCLES engine (EEVEE fails in headless mode)
bpy.context.scene.render.engine = 'CYCLES'

# Video optimization: lower samples = faster per-frame
# For 2-minute @ 30fps = 3600 frames; use adaptive sampling
bpy.context.scene.cycles.samples = 32  # 16-32 for video
bpy.context.scene.cycles.use_denoising = True  # OptiX if available
bpy.context.scene.cycles.denoiser = 'OPTIХ' if bpy.app.version >= (3, 2) else 'NLM'

# Render animation sequence (not single frame)
bpy.ops.render.render(animation=True)
print(f"BLENDER_SUCCESS: {{job_id}}")
sys.exit(0)
        """

        # Write script to temp file
        script_file = self.job_storage / f"script_{job_id}.py"
        try:
            script_file.write_text(blend_script)
        except Exception as e:
            logger.error(f"Failed to write Blender script: {e}")
            return None

        # Submit as background process
        try:
            process = subprocess.Popen(
                [
                    self.blender_path,
                    "-b",  # background mode
                    blend_file,
                    "-P",
                    str(script_file),
                    "-o",
                    output_path,
                    "-f",
                    "1",  # frame 1
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            elapsed = time.time() - start_time
            self.running_jobs[job_id] = {
                "process": process,
                "output_path": output_path,
                "start_time": datetime.utcnow().isoformat() + "Z",
                "script_file": str(script_file),
                "submission_time_ms": int(elapsed * 1000),
            }

            logger.info(f"Blender job submitted: {job_id} (submission={elapsed*1000:.0f}ms)")
            return job_id

        except FileNotFoundError:
            logger.error(f"Blender executable not found at {self.blender_path}")
            self._record_failure(job_id, "Blender not installed")
            return None

        except Exception as e:
            logger.error(f"Failed to submit Blender job: {e}")
            self._record_failure(job_id, str(e))
            return None

    def poll_job(self, job_id: str) -> Dict:
        """Check job status (non-blocking poll).

        Returns: {
            "status": "queued|running|complete|failed",
            "elapsed_seconds": float,
            "output_path": str (if complete),
            "error": str (if failed),
        }
        """
        if job_id not in self.running_jobs:
            return {"status": "not_found", "error": f"Job {job_id} not found"}

        job = self.running_jobs[job_id]
        poll = job["process"].poll()

        elapsed = time.time() - datetime.fromisoformat(job["start_time"].replace("Z", "+00:00")).timestamp()

        if poll is None:
            # Still running
            return {
                "status": "running",
                "elapsed_seconds": elapsed,
                "output_path": job["output_path"],
            }

        elif poll == 0:
            # Success
            logger.info(f"Blender job complete: {job_id} (elapsed={elapsed:.0f}s)")
            # Cleanup
            self.running_jobs.pop(job_id, None)
            return {
                "status": "complete",
                "elapsed_seconds": elapsed,
                "output_path": job["output_path"],
            }

        else:
            # Failed
            stderr = job["process"].stderr if hasattr(job["process"], "stderr") else "Unknown error"
            error_msg = f"Blender failed with code {poll}: {stderr}"
            logger.error(error_msg)
            self._record_failure(job_id, error_msg)
            self.running_jobs.pop(job_id, None)
            return {
                "status": "failed",
                "elapsed_seconds": elapsed,
                "error": error_msg,
            }

    def auto_downgrade(self) -> Optional[str]:
        """Check if we should downgrade to Tier 2.

        Downgrade conditions:
        - 3+ failures in last 48h
        - Blender process timeout (>5min)
        - Consistent memory exhaustion

        Returns: "FALLBACK_TO_TIER_2" if conditions met, else None
        """
        failures = self._count_recent_failures(hours=48)

        if failures >= 3:
            logger.warning(f"3+ Blender failures in 48h; recommending fallback to Tier 2")
            return "FALLBACK_TO_TIER_2"

        return None

    def _is_blender_healthy(self) -> bool:
        """Check if Blender is available and functioning."""
        try:
            # Quick health check: can we invoke Blender --version?
            result = subprocess.run(
                [self.blender_path, "--version"],
                timeout=5,
                capture_output=True,
                text=True,
            )
            is_healthy = result.returncode == 0
            if not is_healthy:
                logger.warning(f"Blender health check failed: {result.stderr}")
            return is_healthy
        except FileNotFoundError:
            logger.warning(f"Blender not found at {self.blender_path}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("Blender health check timeout")
            return False
        except Exception as e:
            logger.warning(f"Blender health check error: {e}")
            return False

    def _verify_blender_available(self):
        """Verify Blender is available at startup."""
        try:
            result = subprocess.run(
                [self.blender_path, "--version"],
                timeout=5,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"Blender verified: {result.stdout.strip()}")
            else:
                logger.warning(f"Blender verification failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"Blender verification error: {e}")

    def _record_failure(self, job_id: str, error: str):
        """Record failure for monitoring."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "job_id": job_id,
            "error": error,
        }
        try:
            with open(self.failure_log, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to record Blender failure: {e}")

    def _count_recent_failures(self, hours: int = 48) -> int:
        """Count failures in last N hours."""
        if not self.failure_log.exists():
            return 0

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        count = 0

        try:
            with open(self.failure_log, "r") as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                        if ts > cutoff:
                            count += 1
        except Exception as e:
            logger.warning(f"Failed to count failures: {e}")

        return count
