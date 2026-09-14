"""Week 8–9: Real OpenAI TTS Integration

Replace voice_worker_real stub with actual OpenAI API calls.
"""

import os
import hashlib
from pathlib import Path
from typing import Dict

def execute(input_data: Dict, state_dir: Path) -> Dict:
    """Synthesize voice using OpenAI TTS API (tts-1-hd, voice=nova)."""
    storyboard = input_data.get("storyboard", {})
    scenes = storyboard.get("scenes", [])

    if not scenes:
        raise ValueError("Storyboard has no scenes")

    # Aggregate narration from all scenes
    narration = " ".join(s.get("narration", "") for s in scenes)
    narration_hash = hashlib.sha256(narration.encode()).hexdigest()

    # Check cache
    cache_file = state_dir / f"{narration_hash[:16]}.mp3"
    if cache_file.exists():
        return {
            "audio_path": str(cache_file),
            "duration_sec": estimate_duration(narration),
            "narration_hash": narration_hash,
            "cached": True,
        }

    # Week 8: Call real OpenAI API (requires OPENAI_API_KEY)
    try:
        import openai

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        client = openai.OpenAI(api_key=api_key)

        # Real TTS call
        response = client.audio.speech.create(
            model="tts-1-hd",
            voice="nova",
            input=narration,
        )

        # Save to file
        with open(cache_file, "wb") as f:
            f.write(response.content)

        duration = estimate_duration(narration)

        return {
            "audio_path": str(cache_file),
            "duration_sec": duration,
            "narration_hash": narration_hash,
            "cached": False,
        }

    except ImportError:
        raise ImportError("openai library not installed: pip install openai")
    except Exception as e:
        raise RuntimeError(f"OpenAI TTS failed: {e}")


def estimate_duration(text: str) -> float:
    """Estimate audio duration from word count (150 words/min)."""
    words = len(text.split())
    return words / 2.5
