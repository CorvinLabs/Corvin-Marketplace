"""E2E tests for TTS fallback chain (ADR-2211, graceful degradation).

Verifies that when OpenAI fails (API error, timeout, auth failure, quota limit),
the system automatically falls back to Edge TTS, and finally fails
only when both are exhausted (Piper is not part of the chain). This test suite runs against real/mock TTS
providers and exercises the complete fallback logic.
"""

import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skill import (
    _tts_tier_openai,
    _tts_tier_edge,
    _tts_tier_mock,
    _synthesize_narration_chain,
    NoVoiceAvailable,
    _openai_api_key,
    _TTS_CALL_TIMEOUT_S,
)


def _absent(name: str):
    """sys.modules entry that makes ``import <name>`` raise ImportError, as on a host without the package."""
    return patch.dict(sys.modules, {name: None})


def _fake_edge_tts():
    """A stand-in for the edge_tts package that records the voice it is asked for and writes a file."""
    mod = types.ModuleType("edge_tts")
    mod.voices = []

    class Communicate:
        def __init__(self, text, voice):
            mod.voices.append(voice)

        async def save(self, path):
            Path(path).write_bytes(b"fake mp3")

    mod.Communicate = Communicate
    return mod


class TestOpenAIFallback:
    """OpenAI tier: test all failure modes that trigger fallback."""

    def test_openai_no_api_key(self):
        """No API key → decline gracefully, don't raise."""
        with patch.dict(os.environ, clear=True):
            # OPENAI_API_KEY and CORVIN_TTS_OPENAI_KEY not set
            result = _tts_tier_openai("hello", Path("/tmp/test.mp3"), "en")
            assert result is False, "Should decline (not raise) when no API key"

    def test_openai_package_not_installed(self):
        """OpenAI package ImportError → decline gracefully."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            with patch("skill._openai_speech", side_effect=ImportError("No module named 'openai'")):
                result = _tts_tier_openai("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on ImportError"

    def test_openai_auth_failure(self):
        """API returns 401 Unauthorized → decline and log auth failure."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-invalid-key"}):
            auth_error = Exception("401 Unauthorized: Invalid API key")
            with patch("skill._openai_speech", side_effect=auth_error):
                result = _tts_tier_openai("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on auth failure"

    def test_openai_rate_limit(self):
        """API returns 429 Too Many Requests → decline and log rate limit."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            rate_limit_error = Exception("429 Too Many Requests: Rate limit exceeded")
            with patch("skill._openai_speech", side_effect=rate_limit_error):
                result = _tts_tier_openai("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on rate limit"

    def test_openai_quota_exceeded(self):
        """API returns quota exceeded → decline and log quota failure."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            quota_error = Exception("Error: Your quota has been exceeded")
            with patch("skill._openai_speech", side_effect=quota_error):
                result = _tts_tier_openai("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on quota exceeded"

    def test_openai_timeout(self):
        """Request times out → decline and log timeout."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            timeout_error = Exception("deadline exceeded in openai tts")
            with patch("skill._openai_speech", side_effect=timeout_error):
                result = _tts_tier_openai("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on timeout"

    def test_openai_network_error(self):
        """Network error (connection refused, DNS lookup failure) → decline."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            network_error = Exception("Connection refused: Unable to connect to api.openai.com")
            with patch("skill._openai_speech", side_effect=network_error):
                result = _tts_tier_openai("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on network error"

    def test_openai_success(self):
        """OpenAI succeeds → return True."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                out_path = Path(f.name)
                out_path.write_bytes(b"fake mp3 data")
                try:
                    with patch("skill._openai_speech") as mock_speech:
                        result = _tts_tier_openai("hello", out_path, "en")
                        assert result is True, "Should succeed when OpenAI works"
                        mock_speech.assert_called_once()
                finally:
                    out_path.unlink()


class TestEdgeTTSFallback:
    """Edge TTS tier: test network failures and missing package."""

    def test_edge_package_not_installed(self):
        """edge_tts package ImportError → decline gracefully."""
        with _absent("edge_tts"):
            result = _tts_tier_edge("hello", Path("/tmp/test.mp3"), "en")
            assert result is False, "Should decline on ImportError"

    def test_edge_network_timeout(self):
        """Network timeout from edge-tts → decline and log timeout."""
        import asyncio

        with patch.dict(sys.modules, {"edge_tts": _fake_edge_tts()}):
            timeout_error = asyncio.TimeoutError("Microsoft TTS service timeout")
            with patch("skill._run_coroutine_blocking", side_effect=timeout_error):
                result = _tts_tier_edge("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on timeout"

    def test_edge_network_error(self):
        """Network connection failure → decline and log error."""
        with patch.dict(sys.modules, {"edge_tts": _fake_edge_tts()}):
            network_error = Exception("Connection failed: Unable to reach tts.bing.com")
            with patch("skill._run_coroutine_blocking", side_effect=network_error):
                result = _tts_tier_edge("hello", Path("/tmp/test.mp3"), "en")
                assert result is False, "Should decline on network error"


class TestFallbackChain:
    """Full fallback chain: verify tier priority and complete fallback path.

    ``_TTS_CHAIN`` holds the tier functions themselves, so the tests replace the chain, not the module names.
    """

    @staticmethod
    def _chain(openai=False, edge=False):
        fns = {"openai": MagicMock(return_value=openai), "edge": MagicMock(return_value=edge)}
        return fns, tuple((name, fn) for name, fn in fns.items())

    def test_chain_openai_succeeds(self):
        """OpenAI succeeds -> use OpenAI, don't try others."""
        fns, chain = self._chain(openai=True)
        with patch("skill._TTS_CHAIN", chain):
            assert _synthesize_narration_chain("hello", Path("/tmp/test.mp3"), "en") == "openai"
        fns["openai"].assert_called_once()
        fns["edge"].assert_not_called()

    def test_chain_openai_fails_edge_succeeds(self):
        """OpenAI fails -> try Edge TTS -> Edge succeeds."""
        fns, chain = self._chain(edge=True)
        with patch("skill._TTS_CHAIN", chain):
            assert _synthesize_narration_chain("hello", Path("/tmp/test.mp3"), "en") == "edge"
        fns["openai"].assert_called_once()
        fns["edge"].assert_called_once()

    def test_chain_all_fail(self):
        """All tiers decline -> raise NoVoiceAvailable with a helpful message."""
        fns, chain = self._chain()
        with patch("skill._TTS_CHAIN", chain):
            with pytest.raises(NoVoiceAvailable) as exc_info:
                _synthesize_narration_chain("hello", Path("/tmp/test.mp3"), "en")
        error_msg = str(exc_info.value)
        assert "OpenAI" in error_msg, "Error should mention OpenAI"
        assert "Edge" in error_msg, "Error should mention Edge TTS"
        assert "Piper" not in error_msg, "Piper is not a tier"
        assert "OpenAI TTS key" in error_msg or "OPENAI_API_KEY" in error_msg
        for fn in fns.values():
            fn.assert_called_once()

    def test_the_production_chain_is_openai_then_edge_only_and_has_no_mock(self):
        """Pins the real order: a silent mock tier in production would ship mute videos (review 2026-10-10)."""
        import skill
        assert [name for name, _ in skill._TTS_CHAIN] == ["openai", "edge"]
        assert [fn for _, fn in skill._TTS_CHAIN] == [_tts_tier_openai, _tts_tier_edge]


class TestLanguageVariants:
    """Verify correct voice selection for German and English (the voice edge-tts is really asked for)."""

    @staticmethod
    def _run(text, lang):
        fake = _fake_edge_tts()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"edge_tts": fake}):
            out_path = Path(tmp) / "out.mp3"
            result = _tts_tier_edge(text, out_path, lang)
            return result, fake.voices, out_path.exists()

    def test_german_voice_selection(self):
        """German -> de-DE-KatjaNeural for edge-tts."""
        result, voices, wrote = self._run("Guten Tag", "de")
        assert (result, voices, wrote) == (True, ["de-DE-KatjaNeural"], True)

    def test_english_voice_selection(self):
        """English -> en-US-AvaMultilingualNeural for edge-tts."""
        result, voices, wrote = self._run("Good day", "en")
        assert (result, voices, wrote) == (True, ["en-US-AvaMultilingualNeural"], True)

    def test_an_empty_file_is_a_decline_not_a_success(self):
        fake = _fake_edge_tts()

        async def save_nothing(self, path):
            Path(path).write_bytes(b"")

        fake.Communicate.save = save_nothing
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"edge_tts": fake}):
            assert _tts_tier_edge("hello", Path(tmp) / "out.mp3", "en") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
