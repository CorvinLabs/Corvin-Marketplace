"""Offline / Claude Code not running (Windows host, 2026-10-27): there is no local fallback and (1.8.0) no
API-key path - the job must fail with a typed, actionable ClaudeEngineUnavailable naming the cause, not
"HTTPConnectionPool ... localhost:11434 ... [WinError 10061]"."""
import sys

import pytest

from src import skill
from tests.conftest import install_fake_claude_bin


def _fake(tmp_path, monkeypatch, body: str):
    script = tmp_path / "fake_claude.py"
    script.write_text("#!%s\n%s" % (sys.executable, body))
    script.chmod(0o755)
    install_fake_claude_bin(script, monkeypatch)


def test_a_missing_claude_cli_says_what_is_needed(monkeypatch, tmp_path):
    monkeypatch.setenv("CORVIN_CLAUDE_BIN", str(tmp_path / "no-such-claude"))
    with pytest.raises(skill.ClaudeEngineUnavailable) as ei:
        skill._call_storyboard_llm("p", backend="claude_cli", model="claude-sonnet-5-5")
    msg = str(ei.value)
    assert "Claude Code" in msg and "sign in" in msg
    assert "ollama" not in msg.lower() and "ANTHROPIC_API_KEY" not in msg


def test_no_other_backend_exists():
    assert not hasattr(skill, "_OLLAMA_URL") and not hasattr(skill, "anthropic")
    for other in ("ollama", "anthropic"):
        with pytest.raises(ValueError, match="unknown storyboard backend"):
            skill._call_storyboard_llm("p", backend=other, model="m")


def test_a_failing_cli_names_its_own_reason(monkeypatch, tmp_path):
    """No log access (Windows service host): the CLI's stderr must reach the job error, secrets scrubbed."""
    _fake(tmp_path, monkeypatch,
          "import sys\nsys.stderr.write('Not logged in sk-abcdef123456 - run claude login')\nsys.exit(1)\n")
    with pytest.raises(skill.ClaudeEngineUnavailable) as ei:
        skill._call_storyboard_llm("p", backend="claude_cli", model="claude-sonnet-5-5")
    msg = str(ei.value)
    assert "exited 1" in msg and "Not logged in" in msg and "sk-abcdef" not in msg


def test_cli_runs_on_the_subscription_not_an_api_key(monkeypatch, tmp_path):
    _fake(tmp_path, monkeypatch,
          "import os, json\nprint(json.dumps({'result': 'key=' + str('ANTHROPIC_API_KEY' in os.environ)}))\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-should-not-reach-the-cli")
    assert skill._call_claude_cli("p", "claude-sonnet-5-5") == "key=False"
