"""Voice Worker (Real OpenAI TTS, WAVE 2 k=6–k=8)"""

import hashlib
import json
from pathlib import Path
from typing import Dict

def execute(input_data: Dict, state_dir: Path) -> Dict:
    """Synthesize voice from storyboard (OpenAI TTS stub for now)."""
    storyboard = input_data.get("storyboard", {})
    scenes = storyboard.get("scenes", [])
    
    narration = " ".join(s.get("narration", "") for s in scenes)
    text_hash = hashlib.sha256(narration.encode()).hexdigest()
    
    # Stub: create dummy audio (in k=7 will call OpenAI API)
    audio_file = state_dir / "narration.mp3"
    audio_file.write_bytes(b"AUDIO_STUB")
    
    # Estimate duration (150 words/min = 2.5 words/sec)
    duration_sec = len(narration.split()) / 2.5
    
    return {
        "audio_path": str(audio_file),
        "duration_sec": duration_sec,
        "narration_hash": text_hash,
        "cached": False,
    }
