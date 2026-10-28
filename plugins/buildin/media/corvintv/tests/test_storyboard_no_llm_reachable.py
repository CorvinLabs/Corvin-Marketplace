"""Offline / Claude Code not running (Windows host, 2026-10-27): there is no local fallback any more, and the
job must fail with an actionable message - not "HTTPConnectionPool ... localhost:11434 ... [WinError 10061]"."""
import pytest

from src import skill


def test_a_failing_claude_cli_says_what_is_needed(monkeypatch, tmp_path):
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(tmp_path / "no-such-claude"))  # real spawn failure
    with pytest.raises(RuntimeError, match="internet connection") as ei:
        skill._call_storyboard_llm("p", backend="claude_cli", model="claude-sonnet-5-5")
    assert "Claude Code" in str(ei.value) and "ANTHROPIC_API_KEY" in str(ei.value)
    assert "ollama" not in str(ei.value).lower()


def test_no_local_backend_exists():
    assert not hasattr(skill, "_OLLAMA_URL")
    with pytest.raises(ValueError, match="unknown storyboard backend"):
        skill._call_storyboard_llm("p", backend="ollama", model="m")
