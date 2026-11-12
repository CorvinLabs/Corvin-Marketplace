"""environment.py: the host check names what is wrong, repairs only what it may, and never raises."""
import subprocess
import sys

import pytest

from src import environment as env


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    env._LAST.clear()
    monkeypatch.delenv(env.ALLOW_PILLOW_ENV, raising=False)
    monkeypatch.delenv(env.NO_REPAIR_ENV, raising=False)


def _cp(out="", code=0, err=""):
    return subprocess.CompletedProcess([], code, out, err)


def test_check_ok(monkeypatch):
    monkeypatch.setattr(env, "_run", lambda argv, t: _cp("OK 158.0.1\n"))
    r = env.check_chromium()
    assert r["ok"] and r["version"] == "158.0.1"


def test_check_names_build_mismatch_as_needing_install(monkeypatch):
    msg = "FAIL BrowserType.launch: Executable doesn't exist at /x/chromium_headless_shell-1254/a.exe"
    monkeypatch.setattr(env, "_run", lambda argv, t: _cp(msg + "\n", 4))
    r = env.check_chromium()
    assert not r["ok"] and r["needs_install"] and "playwright install chromium" in r["fix"]


def test_check_without_playwright_is_not_repairable_by_install(monkeypatch):
    monkeypatch.setattr(env, "_run", lambda argv, t: _cp("NOPW ModuleNotFoundError\n", 3))
    r = env.check_chromium()
    assert not r["ok"] and not r["needs_install"] and "pip install playwright" in r["fix"]


def test_probe_timeout_is_a_reason_not_an_exception(monkeypatch):
    monkeypatch.setattr(env, "_run", lambda argv, t: None)
    r = env.check_chromium(timeout=1)
    assert not r["ok"] and "did not finish" in r["reason"]


def test_ensure_repairs_once_then_reports_ok(monkeypatch):
    results = iter([{"ok": False, "reason": "Executable doesn't exist", "needs_install": True, "fix": "f"},
                    {"ok": True, "version": "1", "reason": None, "needs_install": False}])
    monkeypatch.setattr(env, "check_chromium", lambda *a, **k: next(results))
    calls = []
    monkeypatch.setattr(env, "repair_chromium", lambda *a, **k: calls.append(1) or {"ok": True})
    r = env.ensure_chromium()
    assert r["ok"] and r["repaired"] and len(calls) == 1


def test_no_auto_repair_switch_downloads_nothing(monkeypatch):
    monkeypatch.setenv(env.NO_REPAIR_ENV, "1")
    monkeypatch.setattr(env, "check_chromium",
                        lambda *a, **k: {"ok": False, "reason": "x", "needs_install": True, "fix": "f"})
    monkeypatch.setattr(env, "repair_chromium", lambda *a, **k: pytest.fail("must not download"))
    r = env.ensure_chromium()
    assert not r["ok"] and not r["repaired"]
    assert env.NO_REPAIR_ENV in env.describe(r)


def test_missing_playwright_is_never_installed_by_repair(monkeypatch):
    monkeypatch.setattr(env, "check_chromium",
                        lambda *a, **k: {"ok": False, "reason": "no pw", "needs_install": False, "fix": "pip"})
    monkeypatch.setattr(env, "repair_chromium", lambda *a, **k: pytest.fail("not repairable by browser install"))
    assert not env.ensure_chromium()["ok"]


def test_describe_names_reason_fix_and_the_pillow_opt_in():
    text = env.describe({"ok": False, "reason": "boom", "fix": "run X", "repaired": True})
    assert "boom" in text and "run X" in text and env.ALLOW_PILLOW_ENV in text and "repair was tried" in text


def test_pillow_opt_in(monkeypatch):
    assert not env.pillow_allowed()
    monkeypatch.setenv(env.ALLOW_PILLOW_ENV, "1")
    assert env.pillow_allowed()


def test_cached_success_skips_a_second_launch(monkeypatch):
    n = []
    monkeypatch.setattr(env, "check_chromium", lambda *a, **k: n.append(1) or {"ok": True, "needs_install": False})
    env.ensure_chromium_cached()
    env.ensure_chromium_cached()
    assert len(n) == 1


def test_ffmpeg_adopts_a_known_copy_onto_path(monkeypatch, tmp_path):
    exe = tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    exe.write_bytes(b"x")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(env, "_ffmpeg_candidates", lambda: [exe])
    r = env.ensure_ffmpeg()
    assert r["ok"] and r["source"] == "adopted"


def test_ffmpeg_missing_names_a_fix(monkeypatch):
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(env, "_ffmpeg_candidates", lambda: [])
    r = env.ensure_ffmpeg()
    assert not r["ok"] and "fix" in r and r["reason"]


# ---- the job-level preflight (skill.orchestrate_video) -------------------------------------------------

from src import skill  # noqa: E402
from src.models import VideoJob  # noqa: E402
from src.storage import get_storage, reset_storage  # noqa: E402

_BROKEN = {"ok": False, "reason": "Executable doesn't exist", "needs_install": True, "fix": "f", "repaired": True}


async def _run_job(tmp_path, monkeypatch, *, web_slides=True):
    reset_storage()
    base = str(tmp_path / "tenant")
    (tmp_path / "tenant").mkdir()
    get_storage(base).save_job(VideoJob(id="job_pf", task="t"))
    monkeypatch.setattr(skill.host_env, "ensure_ffmpeg", lambda: {"ok": True, "path": "x"})
    monkeypatch.setattr(skill.shutil, "which", lambda n: "ffmpeg")
    monkeypatch.setattr(skill.host_env, "ensure_chromium_cached", lambda *a, **k: dict(_BROKEN))

    async def _no_storyboard(*a, **k):
        raise AssertionError("the storyboard (an LLM call) must not start when the renderer cannot run")

    monkeypatch.setattr(skill, "generate_storyboard_with_llm", _no_storyboard)
    try:
        await skill.orchestrate_video("job_pf", "t", base, web_slides=web_slides, max_duration_minutes=5)
    except Exception:  # noqa: BLE001 - the job records its own error; a raise after that is fine too
        pass
    return get_storage(base).get_job("job_pf")


async def test_job_fails_loudly_before_the_llm_call_when_chromium_cannot_run(tmp_path, monkeypatch):
    job = await _run_job(tmp_path, monkeypatch)
    assert job.status == "error"
    assert "Chromium" in job.error_message and env.ALLOW_PILLOW_ENV in job.error_message


async def test_pillow_opt_in_lets_the_job_past_the_preflight(tmp_path, monkeypatch):
    monkeypatch.setenv(env.ALLOW_PILLOW_ENV, "1")
    with pytest.raises(AssertionError, match="storyboard"):   # reached the storyboard step = preflight passed
        reset_storage()
        base = str(tmp_path / "t2")
        (tmp_path / "t2").mkdir()
        get_storage(base).save_job(VideoJob(id="job_pf", task="t"))
        monkeypatch.setattr(skill.host_env, "ensure_ffmpeg", lambda: {"ok": True, "path": "x"})
        monkeypatch.setattr(skill.shutil, "which", lambda n: "ffmpeg")
        monkeypatch.setattr(skill.host_env, "ensure_chromium_cached", lambda *a, **k: dict(_BROKEN))

        async def _boom(*a, **k):
            raise AssertionError("storyboard reached")

        monkeypatch.setattr(skill, "generate_storyboard_with_llm", _boom)
        await skill.orchestrate_video("job_pf", "t", base, web_slides=True, max_duration_minutes=5)
