"""Week 11: Real FFmpeg H.264/AAC Assembly

FFmpeg command-line integration for professional video assembly.
"""

import subprocess
from pathlib import Path
from typing import Dict

def execute(input_data: Dict, state_dir: Path) -> Dict:
    """Assemble video using real FFmpeg (H.264 + AAC)."""
    storyboard = input_data.get("storyboard", {})
    audio_file = input_data.get("audio_file")
    screenshots_dir = input_data.get("screenshots_dir")
    output_dir = Path(input_data.get("output_dir", state_dir))
    
    output_dir.mkdir(parents=True, exist_ok=True)
    output_mp4 = output_dir / "output.mp4"
    
    # Week 11: Real FFmpeg command
    duration = storyboard.get("duration_seconds", 120)
    
    cmd = [
        "ffmpeg", "-y",
        "-framerate", "30",
        "-pattern_type", "glob",
        "-i", f"{screenshots_dir}/scene_*.png",
        "-i", audio_file,
        "-c:v", "libx264",
        "-crf", "18",  # Quality (18-28 typical)
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(duration),
        str(output_mp4),
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        
        return {
            "output_path": str(output_mp4),
            "duration_sec": duration,
            "codec": "h264",
            "audio": "aac",
        }
    
    except FileNotFoundError:
        raise ImportError("ffmpeg not installed")
    except Exception as e:
        raise RuntimeError(f"Video assembly failed: {e}")
