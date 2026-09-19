"""Voice Synthesizer — Text-to-Speech with Caching

Converts narration text to MP3 audio with SHA256-based caching.
Uses OpenAI TTS API (tts-1-hd, voice=nova) by default.

ADR-0742: Didactic Storyboard System (Voice Synthesis)
"""

import hashlib
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SynthesisRequest:
    """Request to synthesize narration"""
    text: str                   # Narration text to synthesize
    voice: str = "nova"         # OpenAI voice option
    model: str = "tts-1-hd"     # Model option
    format: str = "mp3"         # Output format


@dataclass
class SynthesisResult:
    """Result of text-to-speech synthesis"""
    text_hash: str              # SHA256 of input text
    audio_path: Optional[Path] = None
    duration_sec: float = 0.0
    synthesis_time_ms: int = 0
    success: bool = False
    error: Optional[str] = None


class VoiceSynthesizer:
    """Text-to-speech synthesizer with caching

    Uses OpenAI TTS API by default. Caches results by SHA256 hash
    of input text to avoid re-synthesizing identical narration.
    """

    def __init__(self, api_key: Optional[str] = None, cache_enabled: bool = True):
        """Initialize VoiceSynthesizer

        Args:
            api_key: OpenAI API key (optional, uses OPENAI_API_KEY env var if not provided)
            cache_enabled: Enable caching by text hash
        """
        self.name = "voice_synthesizer"
        self.version = "5.1.0"
        self.api_key = api_key
        self.cache_enabled = cache_enabled

        # Setup directories (relative to plugin)
        plugin_root = Path(__file__).parent
        self.cache_dir = plugin_root / "outputs" / "voice_cache"
        self.output_dir = plugin_root / "outputs" / "audio"

        for d in [self.cache_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesize narration audio

        Args:
            request: SynthesisRequest with text and options

        Returns:
            SynthesisResult with audio path and metadata
        """
        import time
        start_time = time.time()

        try:
            # Step 1: Compute text hash
            text_hash = hashlib.sha256(request.text.encode()).hexdigest()

            # Step 2: Check cache
            if self.cache_enabled:
                cached = self._get_cached(text_hash)
                if cached:
                    synthesis_time_ms = int((time.time() - start_time) * 1000)
                    return SynthesisResult(
                        text_hash=text_hash,
                        audio_path=Path(cached["audio_path"]),
                        duration_sec=cached["duration_sec"],
                        synthesis_time_ms=synthesis_time_ms,
                        success=True
                    )

            # Step 3: Synthesize via API
            audio_path = self._synthesize_via_api(
                text=request.text,
                voice=request.voice,
                model=request.model,
                text_hash=text_hash
            )

            if not audio_path:
                synthesis_time_ms = int((time.time() - start_time) * 1000)
                return SynthesisResult(
                    text_hash=text_hash,
                    success=False,
                    error="API synthesis failed",
                    synthesis_time_ms=synthesis_time_ms
                )

            # Step 4: Get duration
            duration = self._get_duration(audio_path)
            synthesis_time_ms = int((time.time() - start_time) * 1000)

            # Cache result
            if self.cache_enabled:
                self._cache_result(text_hash, str(audio_path), duration)

            return SynthesisResult(
                text_hash=text_hash,
                audio_path=audio_path,
                duration_sec=duration,
                synthesis_time_ms=synthesis_time_ms,
                success=True
            )

        except Exception as e:
            synthesis_time_ms = int((time.time() - start_time) * 1000)
            return SynthesisResult(
                text_hash="",
                success=False,
                error=f"Exception: {str(e)}",
                synthesis_time_ms=synthesis_time_ms
            )

    def _synthesize_via_api(self, text: str, voice: str, model: str, text_hash: str) -> Optional[Path]:
        """Synthesize audio via OpenAI TTS API

        Args:
            text: Narration text
            voice: Voice option (nova, onyx, alloy, echo, fable, shimmer)
            model: Model (tts-1 or tts-1-hd)
            text_hash: SHA256 hash of text

        Returns:
            Path to MP3 file or None on failure
        """
        try:
            # Try importing openai
            import openai
            import os

            # Set API key
            api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("[VOICE_SYNTHESIZER] No OpenAI API key available")
                return None

            openai.api_key = api_key

            # Call TTS API
            response = openai.Audio.create(
                model=model,
                input=text,
                voice=voice
            )

            # Save to file
            output_path = self.output_dir / f"{text_hash[:16]}.mp3"
            with open(output_path, "wb") as f:
                f.write(response.content)

            return output_path

        except ImportError:
            print("[VOICE_SYNTHESIZER] openai module not installed. Install with: pip install openai")
            return None
        except Exception as e:
            print(f"[VOICE_SYNTHESIZER] API error: {e}")
            return None

    def _get_duration(self, audio_path: Path) -> float:
        """Get audio duration via ffprobe

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds (0.0 if cannot determine)
        """
        try:
            import subprocess
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path)
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            print(f"[VOICE_SYNTHESIZER] ffprobe error: {e}")

        return 0.0

    def _get_cached(self, text_hash: str) -> Optional[dict]:
        """Get cached synthesis result

        Args:
            text_hash: SHA256 hash of text

        Returns:
            Cached metadata or None
        """
        cache_file = self.cache_dir / f"{text_hash}_meta.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except:
                pass
        return None

    def _cache_result(self, text_hash: str, audio_path: str, duration_sec: float):
        """Cache synthesis result

        Args:
            text_hash: SHA256 hash of text
            audio_path: Path to audio file
            duration_sec: Audio duration
        """
        cache_file = self.cache_dir / f"{text_hash}_meta.json"
        cache_data = {
            "text_hash": text_hash,
            "audio_path": audio_path,
            "duration_sec": duration_sec,
            "cached_at": datetime.now().isoformat()
        }
        try:
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            print(f"[VOICE_SYNTHESIZER] Cache write error: {e}")
