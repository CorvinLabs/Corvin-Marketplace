"""1.6.0 Fresh-Install E2E: clone, install, render Canvas, check MP4."""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs Linux")]


def test_fresh_install_canvas_render():
    """Clone from GitHub, pip install, run Canvas storyboard, verify MP4."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Clone Corvin-Marketplace
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/CorvinLabs/Corvin-Marketplace.git", str(tmppath / "repo")],
            check=True, capture_output=True, timeout=60
        )
        repo = tmppath / "repo"
        
        # pip install -e plugin
        subprocess.run(
            ["pip", "install", "-e", str(repo / "plugins/contributor/media/video_producer")],
            check=True, capture_output=True, timeout=120
        )
        
        # Run storyboard → Canvas render → MP4
        storyboard_json = """{
            "scenes": [
                {
                    "id": "s1",
                    "template": "canvas",
                    "duration_ms": 3000,
                    "narration_text": "Canvas with a box and underline.",
                    "data": {
                        "title": "Canvas Test",
                        "elements": [
                            {"id": "box1", "type": "box", "x": 50, "y": 50, "w": 200, "h": 100, "text": "Hello Canvas"}
                        ]
                    }
                }
            ],
            "audio": {
                "url": "file:///dev/null",
                "sample_rate": 44100
            }
        }"""
        
        storyboard_file = tmppath / "storyboard.json"
        storyboard_file.write_text(storyboard_json)
        
        # Render via skill
        from video_producer import skill
        result = skill.run_video_producer(
            task_id="test-1-6-0",
            storyboard_path=str(storyboard_file),
            output_dir=str(tmppath / "output"),
        )
        
        # Check MP4 exists and is not empty
        mp4_path = tmppath / "output" / f"{result['job_id']}.mp4"
        assert mp4_path.exists(), f"MP4 not found at {mp4_path}"
        assert mp4_path.stat().st_size > 1000, f"MP4 too small: {mp4_path.stat().st_size} bytes"


if __name__ == "__main__":
    test_fresh_install_canvas_render()
    print("✅ 1.6.0 Fresh-Install E2E passed")
