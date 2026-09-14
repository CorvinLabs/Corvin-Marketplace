"""WAVE 6 Phase 1: OpenAI TTS Integration Tests

Real API integration for voice synthesis.
Load-bearing: SHA256 caching, duration estimation, API error handling.
"""

import os
import json
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Import the real voice_openai module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from voice_openai import execute, estimate_duration


class TestDurationEstimation:
    """Duration estimation: 150 words/min = 2.5 words/sec."""

    def test_estimate_duration_empty_text(self):
        """Empty text → 0 seconds."""
        assert estimate_duration("") == 0.0

    def test_estimate_duration_single_word(self):
        """Single word: 1 word / 2.5 = 0.4 sec."""
        assert estimate_duration("hello") == pytest.approx(0.4)

    def test_estimate_duration_ten_words(self):
        """10 words: 10 / 2.5 = 4 seconds."""
        assert estimate_duration("one two three four five six seven eight nine ten") == pytest.approx(4.0)

    def test_estimate_duration_realistic(self):
        """100-word text (~40 seconds, realistic for 2-minute video)."""
        text = " ".join(["word"] * 100)
        duration = estimate_duration(text)
        assert duration == pytest.approx(40.0)


class TestSHA256Caching:
    """SHA256-based narration caching (stable, deterministic)."""

    def test_narration_hash_deterministic(self):
        """Same narration → same hash."""
        narration = "Hello world this is a test"
        hash1 = hashlib.sha256(narration.encode()).hexdigest()[:16]
        hash2 = hashlib.sha256(narration.encode()).hexdigest()[:16]
        assert hash1 == hash2

    def test_narration_hash_different_for_different_text(self):
        """Different narration → different hash."""
        hash1 = hashlib.sha256("Hello".encode()).hexdigest()[:16]
        hash2 = hashlib.sha256("World".encode()).hexdigest()[:16]
        assert hash1 != hash2

    def test_cache_file_path_construction(self):
        """Cache file path: {hash[:16]}.mp3."""
        narration = "test narration"
        narration_hash = hashlib.sha256(narration.encode()).hexdigest()
        cache_filename = f"{narration_hash[:16]}.mp3"
        assert cache_filename.endswith(".mp3")
        assert len(cache_filename) == 20  # 16 hex chars + ".mp3"


class TestOpenAITTSIntegration:
    """Real OpenAI TTS API integration (with mock for testing)."""

    def test_execute_with_missing_api_key(self):
        """Missing OPENAI_API_KEY → ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as tmpdir:
                input_data = {
                    "storyboard": {
                        "scenes": [
                            {"narration": "Hello world"}
                        ]
                    }
                }
                state_dir = Path(tmpdir)
                
                with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
                    execute(input_data, state_dir)

    def test_execute_with_empty_scenes(self):
        """Empty scenes → ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_data = {"storyboard": {"scenes": []}}
            state_dir = Path(tmpdir)
            
            with pytest.raises(ValueError, match="Storyboard has no scenes"):
                execute(input_data, state_dir)

    @patch("voice_openai.openai.OpenAI")
    def test_execute_with_mock_api_success(self, mock_openai_class):
        """Successful TTS call (mocked OpenAI API)."""
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.content = b"fake audio data"
        mock_client.audio.speech.create.return_value = mock_response
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                input_data = {
                    "storyboard": {
                        "scenes": [
                            {"narration": "Hello world"}
                        ]
                    }
                }
                state_dir = Path(tmpdir)
                
                result = execute(input_data, state_dir)
                
                # Verify result
                assert "audio_path" in result
                assert "duration_sec" in result
                assert "narration_hash" in result
                assert result["cached"] is False
                
                # Verify API was called correctly
                mock_client.audio.speech.create.assert_called_once()
                call_kwargs = mock_client.audio.speech.create.call_args.kwargs
                assert call_kwargs["model"] == "tts-1-hd"
                assert call_kwargs["voice"] == "nova"
                assert call_kwargs["input"] == "Hello world"

    @patch("voice_openai.openai.OpenAI")
    def test_execute_with_cache_hit(self, mock_openai_class):
        """Cache hit: return cached audio without API call."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                state_dir = Path(tmpdir)
                
                # Pre-populate cache
                narration = "Hello world"
                narration_hash = hashlib.sha256(narration.encode()).hexdigest()
                cache_file = state_dir / f"{narration_hash[:16]}.mp3"
                cache_file.write_bytes(b"cached audio")
                
                input_data = {
                    "storyboard": {
                        "scenes": [
                            {"narration": narration}
                        ]
                    }
                }
                
                result = execute(input_data, state_dir)
                
                # Verify cache was used
                assert result["cached"] is True
                assert result["audio_path"] == str(cache_file)
                
                # Verify API was NOT called
                mock_openai_class.assert_not_called()

    @patch("voice_openai.openai.OpenAI")
    def test_execute_with_multiple_scenes(self, mock_openai_class):
        """Multiple scenes: aggregate narration."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.content = b"audio"
        mock_client.audio.speech.create.return_value = mock_response
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                input_data = {
                    "storyboard": {
                        "scenes": [
                            {"narration": "Scene 1"},
                            {"narration": "Scene 2"},
                            {"narration": "Scene 3"}
                        ]
                    }
                }
                state_dir = Path(tmpdir)
                
                result = execute(input_data, state_dir)
                
                # Verify aggregated narration was sent to API
                call_kwargs = mock_client.audio.speech.create.call_args.kwargs
                assert call_kwargs["input"] == "Scene 1 Scene 2 Scene 3"

    @patch("voice_openai.openai.OpenAI")
    def test_execute_api_error_handling(self, mock_openai_class):
        """API error: RuntimeError with descriptive message."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.audio.speech.create.side_effect = Exception("Rate limited")
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                input_data = {
                    "storyboard": {
                        "scenes": [
                            {"narration": "Hello"}
                        ]
                    }
                }
                state_dir = Path(tmpdir)
                
                with pytest.raises(RuntimeError, match="OpenAI TTS failed"):
                    execute(input_data, state_dir)

    def test_execute_missing_openai_library(self):
        """Missing openai library: ImportError."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("voice_openai.openai", side_effect=ImportError("No module")):
                with tempfile.TemporaryDirectory() as tmpdir:
                    input_data = {
                        "storyboard": {
                            "scenes": [
                                {"narration": "Hello"}
                            ]
                        }
                    }
                    state_dir = Path(tmpdir)
                    
                    with pytest.raises(ImportError, match="openai library not installed"):
                        execute(input_data, state_dir)


class TestAudioFileGeneration:
    """Audio file generation and storage."""

    @patch("voice_openai.openai.OpenAI")
    def test_audio_file_written_to_cache(self, mock_openai_class):
        """Generated audio: written to cache file."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        audio_data = b"real audio data here"
        mock_response = MagicMock()
        mock_response.content = audio_data
        mock_client.audio.speech.create.return_value = mock_response
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                input_data = {
                    "storyboard": {
                        "scenes": [
                            {"narration": "Hello"}
                        ]
                    }
                }
                state_dir = Path(tmpdir)
                
                result = execute(input_data, state_dir)
                
                # Verify file was written
                audio_file = Path(result["audio_path"])
                assert audio_file.exists()
                assert audio_file.read_bytes() == audio_data

    @patch("voice_openai.openai.OpenAI")
    def test_audio_duration_returned_in_result(self, mock_openai_class):
        """Duration: calculated and returned."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.content = b"audio"
        mock_client.audio.speech.create.return_value = mock_response
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                # 100 words = ~40 seconds
                narration = " ".join(["word"] * 100)
                input_data = {
                    "storyboard": {
                        "scenes": [
                            {"narration": narration}
                        ]
                    }
                }
                state_dir = Path(tmpdir)
                
                result = execute(input_data, state_dir)
                
                assert result["duration_sec"] == pytest.approx(40.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
