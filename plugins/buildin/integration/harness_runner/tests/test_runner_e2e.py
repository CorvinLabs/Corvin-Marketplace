"""E2E: real `python -m corvin_harness_runner` subprocess, real adapter, fake `claude` BINARY.

L44's Tier-1 classifier is a `claude -p` call; the fake binary answers it, so the real house-rules
code (rule block, parsing, confidence, audit) runs. No product-code test switch exists.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import CORVIN_ROOT, PY, invoke, snapshot_live


def _verify_chain(home: Path) -> tuple[bool, str]:
    """Verify the throwaway home's chain with CorvinOS's own verifier, in a fresh interpreter."""
    chain = home / "tenants" / "_default" / "global" / "forge" / "audit.jsonl"
    code = ("import sys;sys.path[:0]=[%r,%r];from pathlib import Path;import security_events as s;"
            "r=s.verify_chain(Path(%r));print(repr(r));sys.exit(0 if (r[0] if isinstance(r,tuple) else r) else 1)"
            % (str(CORVIN_ROOT / "corvin_operator" / "forge" / "forge"),
               str(CORVIN_ROOT / "corvin_operator" / "forge"), str(chain)))
    env = {**os.environ, "CORVIN_HOME": str(home), "CORVIN_AUDIT_ANCHOR_KEY": str(home.parent / "audit_anchor.key"),
           "XDG_CONFIG_HOME": str(home.parent / "xdg_config")}
    p = subprocess.run([str(PY), "-c", code], env=env, capture_output=True, text=True)
    return p.returncode == 0, p.stdout + p.stderr[-500:]


def test_completed_turn_end_to_end(run):
    proc = invoke(run)
    assert proc.returncode == 0, proc.stderr.decode()[-2000:]
    res = run.result()
    assert res["status"] == "completed" and res["answer"] == "done: fake answer"
    assert res["usage"] == {"input": 11, "output": 7, "cache_read": 3, "cache_write": 2}
    assert res["cost_usd"] is None  # redirected endpoint: the CLI's price table is not a cost
    assert {"L34", "L35", "L44"} <= set(res["gates_ran"])
    assert (run.wd / "fake_output.txt").read_text() == "written by fake claude\n"
    assert (run.out / "events.jsonl").stat().st_size > 0
    # the worker's session files land under out-dir/sessions
    assert list((run.out / "sessions").rglob("*.jsonl"))
    # the Corvin audit chain of the throwaway home exists, is chained and copied out
    chain = Path(res["sandbox_home"]) / "tenants" / "_default" / "global" / "forge" / "audit.jsonl"
    lines = [l for l in chain.read_text().splitlines() if l.strip()]
    assert lines and (run.out / "audit.jsonl").read_text() == chain.read_text()
    ok, why = _verify_chain(Path(res["sandbox_home"]))
    assert ok, why
    import json
    recs = [json.loads(l) for l in lines]
    assert all("hash" in r or "prev_hash" in r or "chain_hash" in r for r in recs), recs[0].keys()
    events = {r.get("event_type") or r.get("event") for r in recs}
    assert any(e and ("data_flow" in e or "house_rules" in e or "egress" in e) for e in events), events


def test_instruction_from_stdin_reaches_the_worker(run):
    task = "Fix the bug in @pytest.fixture usage.\nSecond line; $VAR `tick` \"quote\""
    proc = invoke(run, instruction=task, stdin=True)
    assert proc.returncode == 0, proc.stderr.decode()[-2000:]
    got = (run.dump / next(p.name for p in run.dump.glob("*.prompt.txt"))).read_text()
    # Disclosed deviations: sentinel line in front, zero-width joiner before '@'.
    assert got.startswith("User input:\n")
    assert task.replace("@", "@") in got.replace("‍", "").replace("⁠", "")


def test_gate_refusal_exits_2(run):
    proc = invoke(run, instruction="please do VIOLATEME now", extra_env={"FAKE_CLAUDE_VIOLATE": "VIOLATEME"})
    assert proc.returncode == 2, proc.stderr.decode()[-2000:]
    res = run.result()
    assert res["status"] == "refused"
    assert res["refusals"] and res["refusals"][0]["gate"] == "L44"
    assert "L44" in res["gates_ran"]
    assert not (run.wd / "fake_output.txt").exists()      # the worker never ran
    assert not run.dumps("worker")


def test_timeout_exits_4(run):
    proc = invoke(run, extra_env={"FAKE_CLAUDE_MODE": "hang"}, extra_args=("--timeout-s", "6"))
    assert proc.returncode == 4, proc.stderr.decode()[-2000:]
    assert run.result()["status"] == "timeout"


def test_usage_error_exits_64(run):
    proc = subprocess.run([sys.executable, "-m", "corvin_harness_runner", "--model", "x"],
                          env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
                          capture_output=True)
    assert proc.returncode == 64


def test_version_line():
    proc = subprocess.run([str(PY), "-m", "corvin_harness_runner", "--version", "--corvin-root", str(CORVIN_ROOT)],
                          env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stdout.strip().startswith("corvin-harness-runner 0.1.0 corvinos ")
    assert " commit " in proc.stdout


def test_live_installation_untouched(run):
    before = snapshot_live()
    assert invoke(run).returncode == 0
    assert snapshot_live() == before


def test_telemetry_optouts_reach_the_worker(run):
    assert invoke(run, extra_args=("--effort", "high")).returncode == 0
    for d in run.dumps("worker") + run.dumps("classifier"):
        env = d["env"]
        assert env["CORVIN_TELEMETRY_OPTIN"] == "false"
        assert env["CORVIN_GEO_OPT_OUT"] == "1"
        assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
        assert env["DISABLE_TELEMETRY"] == "1"
    assert run.dumps("worker")[0]["env"]["CLAUDE_CODE_EFFORT_LEVEL"] == "high"


def test_limits_pass_through_unchanged(run):
    proc = invoke(run, extra_env={"CLAUDE_CODE_MAX_CONTEXT_TOKENS": "131072",
                                  "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "8192"})
    assert proc.returncode == 0
    env = run.dumps("worker")[0]["env"]
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "131072"
    assert env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "8192"


def test_endpoint_and_key_never_in_argv(run):
    assert invoke(run).returncode == 0
    secret, url = "hlb-sandbox-SECRET-run42", "8787"
    assert not any(secret in a or url in a for a in run.cmd)
    for d in run.dumps("worker") + run.dumps("classifier"):
        assert not any(secret in a or url in a for a in d["cmdline"]), d["cmdline"]
    # but the worker does reach the endpoint, through its env
    assert run.dumps("worker")[0]["env"]["ANTHROPIC_BASE_URL"].endswith("/anthropic")
    assert run.dumps("worker")[0]["env"]["ANTHROPIC_AUTH_TOKEN"] == "hlb-sandbox-SECRET-run42"


@pytest.mark.parametrize("model", ["zai-org/GLM-5.3-Flash:zai-org", "zai-org/GLM-5.3-Flash",
                                   "moonshotai/Kimi-K2.6:novita", "claude-haiku-4-5", "opus"])
def test_board_model_id_arrives_byte_for_byte(run, model):
    """The board's model is a PIN: no prefix strip, no lineage swap, no Haiku/Sonnet/Opus auto-route."""
    assert invoke(run, model=model).returncode == 0
    for kind in ("worker", "classifier"):
        d = run.dumps(kind)[0]
        assert d["argv"][d["argv"].index("--model") + 1] == model, (kind, d["argv"])
    assert run.result()["model_sent"] == model


def test_cwd_repository_is_not_written(run, tmp_path):
    """A caller whose CWD sits in a git checkout must not get a `.corvin` there."""
    from conftest import FAKE, SRC
    repo = tmp_path / "callerrepo"
    (repo / ".git").mkdir(parents=True)
    before = sorted(p.name for p in repo.iterdir())
    f = run.tmp / "i.txt"
    f.write_text("x")
    proc = subprocess.run([str(PY), "-m", "corvin_harness_runner", "--instruction-file", str(f),
                           "--workdir", str(run.wd), "--out-dir", str(run.out), "--model", "m",
                           "--corvin-root", str(CORVIN_ROOT)], cwd=repo, capture_output=True,
                          env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "PYTHONPATH": str(SRC),
                               "CORVIN_CLAUDE_BIN": str(FAKE), "FAKE_CLAUDE_DUMP": str(run.dump)})
    assert proc.returncode == 0, proc.stderr.decode()[-1500:]
    assert sorted(p.name for p in repo.iterdir()) == before


def test_worker_starts_in_the_task_directory_not_the_session_directory(run):
    """Board tasks use relative paths from the directory they start in. The worker's cwd must be the
    task's workdir (realpath), and the task's own files must be where the worker can reach them."""
    (run.wd / "task_input.txt").write_text("from the task dir\n")
    proc = invoke(run)
    assert proc.returncode == 0, proc.stderr[-800:] if hasattr(proc, "stderr") else proc
    cwd = run.dumps("worker")[0]["cwd"]
    assert Path(cwd).resolve() == run.wd.resolve(), cwd
    assert (Path(cwd) / "task_input.txt").read_text() == "from the task dir\n"
