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


def test_a_failing_cli_names_its_own_reason(monkeypatch, tmp_path):
    """No log access (Windows service host): the CLI's stderr must reach the job error, secrets scrubbed."""
    import os, sys, textwrap
    exe = tmp_path / ("fake_claude.py")
    exe.write_text("#!%s\nimport sys\nsys.stderr.write('Not logged in sk-abcdef123456 - run claude login')\nsys.exit(1)\n" % sys.executable)
    os.chmod(exe, 0o755)
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(exe))
    with pytest.raises(RuntimeError) as ei:
        skill._call_storyboard_llm("p", backend="claude_cli", model="claude-sonnet-5-5")
    msg = str(ei.value)
    assert "exited 1" in msg and "Not logged in" in msg and "sk-abcdef" not in msg


def test_cli_runs_on_the_subscription_not_an_api_key(monkeypatch, tmp_path):
    import os, sys
    exe = tmp_path / "fake_claude.py"
    exe.write_text("#!%s\nimport os, json\nprint(json.dumps({'result': 'key=' + str('ANTHROPIC_API_KEY' in os.environ)}))\n" % sys.executable)
    os.chmod(exe, 0o755)
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(exe))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-should-not-reach-the-cli")
    assert skill._call_claude_cli("p", "claude-sonnet-5-5") == "key=False"
