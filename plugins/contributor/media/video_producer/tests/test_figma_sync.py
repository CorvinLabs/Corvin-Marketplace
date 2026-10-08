"""Figma token sync through its real entry point: the CLI as a subprocess, against a
local HTTP server that answers like the Figma Variables REST API (PLAN-0940 P5).
A live check against api.figma.com needs a real token and plan: not run here."""

import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent
TOKEN = "figd_test_token_1234567890"
KEY = "AbCdEf1234567890"


def _var(vid, name, coll, rtype, values):
    return {"id": vid, "name": name, "variableCollectionId": coll, "resolvedType": rtype,
            "valuesByMode": values, "remote": False}


def payload(**overrides):
    variables = {
        "v1": _var("v1", "color/accent", "c1", "COLOR",
                   {"m-dark": {"r": 1, "g": 0.4, "b": 0.2, "a": 1}, "m-light": {"r": 0.6, "g": 0.2, "b": 0.1, "a": 1}}),
        "v2": _var("v2", "color/Glow", "c1", "COLOR",
                   {"m-dark": {"r": 1, "g": 0.4, "b": 0.2, "a": 0.25}, "m-light": {"type": "VARIABLE_ALIAS", "id": "p1"}}),
        "p1": _var("p1", "primitives/amber-200", "c2", "COLOR", {"m-prim": {"r": 0.95, "g": 0.78, "b": 0.48, "a": 0.3}}),
        "v3": _var("v3", "font/heading-family", "c3", "STRING", {"m-one": "Newsreader"}),
        "v4": _var("v4", "motion/rise-ms", "c3", "FLOAT", {"m-one": 700}),
        "v5": _var("v5", "spacing/gutter", "c3", "FLOAT", {"m-one": 24}),
    }
    collections = {
        "c1": {"id": "c1", "name": "Theme", "defaultModeId": "m-dark",
               "modes": [{"modeId": "m-dark", "name": "Dark"}, {"modeId": "m-light", "name": "Light"}]},
        "c2": {"id": "c2", "name": "Primitives", "defaultModeId": "m-prim", "modes": [{"modeId": "m-prim", "name": "Value"}]},
        "c3": {"id": "c3", "name": "Type", "defaultModeId": "m-one", "modes": [{"modeId": "m-one", "name": "Mode 1"}]},
    }
    variables.update(overrides.get("variables", {}))
    return {"status": 200, "error": False, "meta": {"variables": variables, "variableCollections": collections}}


@pytest.fixture
def figma_server():
    state = {"payload": payload(), "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            state["requests"].append((self.path, self.headers.get("X-Figma-Token")))
            if self.headers.get("X-Figma-Token") != TOKEN:
                self._send(403, {"status": 403, "err": "Invalid token"})
            elif self.path != f"/v1/files/{KEY}/variables/local":
                self._send(404, {"status": 404, "err": "Not found"})
            else:
                self._send(200, state["payload"])

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["base"] = f"http://127.0.0.1:{srv.server_address[1]}"
    yield state
    srv.shutdown()


@pytest.fixture
def tokens_file(tmp_path):
    p = tmp_path / "design_tokens.json"
    shutil.copy(PLUGIN / "src" / "web" / "design_tokens.json", p)
    return p


def run_cli(*args, token=TOKEN):
    return subprocess.run(
        [sys.executable, "-m", "src.figma_sync", *args, "--token-stdin"],
        input=(token + "\n") if token is not None else "", capture_output=True, text=True, cwd=PLUGIN, timeout=60,
    )


def test_sync_maps_modes_aliases_and_types_then_writes_valid_tokens(figma_server, tokens_file):
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", figma_server["base"])
    assert r.returncode == 0, r.stderr
    t = json.loads(tokens_file.read_text())
    assert t["dark"]["accent"] == "#ff6633" and t["light"]["accent"] == "#99331a"
    assert t["dark"]["glow"] == "rgba(255, 102, 51, 0.25)"
    assert t["light"]["glow"] == "rgba(242, 199, 122, 0.3)"  # resolved through the alias
    assert t["animation"]["rise_ms"] == 700
    assert "dark.accent: #e8a83a -> #ff6633" in r.stdout
    assert "spacing/gutter" in r.stdout  # unmapped variables are reported, not dropped silently
    assert TOKEN not in r.stdout + r.stderr
    from src.web_templates import validate_tokens
    validate_tokens(t)


def test_dry_run_writes_nothing(figma_server, tokens_file):
    before = tokens_file.read_bytes()
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", figma_server["base"], "--dry-run")
    assert r.returncode == 0 and "dry run" in r.stdout
    assert tokens_file.read_bytes() == before


def test_rejected_token_exits_3_and_never_echoes_it(figma_server, tokens_file):
    before = tokens_file.read_bytes()
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", figma_server["base"], token="figd_wrong_token_000000")
    assert r.returncode == 3 and "403" in r.stderr and "plan" in r.stderr
    assert "figd_wrong" not in r.stdout + r.stderr
    assert tokens_file.read_bytes() == before


def test_unknown_file_exits_4(figma_server, tokens_file):
    r = run_cli("--file-key", "Zz" + KEY[2:], "--out", str(tokens_file), "--api-base", figma_server["base"])
    assert r.returncode == 4


@pytest.mark.parametrize("bad", [
    {"variables": {"v3": _var("v3", "font/heading-family", "c3", "STRING", {"m-one": "x'; } * { color: red"})}},
    {"variables": {"v3": _var("v3", "font/heading-family", "c3", "STRING", {"m-one": "Inter"})}},
    {"variables": {"v4": _var("v4", "motion/rise-ms", "c3", "FLOAT", {"m-one": 99999})}},
])
def test_values_that_fail_the_token_schema_are_refused(figma_server, tokens_file, bad):
    figma_server["payload"] = payload(**bad)
    before = tokens_file.read_bytes()
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", figma_server["base"])
    assert r.returncode == 6 and "refusing to write" in r.stderr
    assert tokens_file.read_bytes() == before


def test_nothing_matched_exits_7(figma_server, tokens_file):
    figma_server["payload"] = {"meta": {"variables": {"x": _var("x", "foo/bar", "c3", "FLOAT", {"m-one": 1})},
                                        "variableCollections": payload()["meta"]["variableCollections"]}}
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", figma_server["base"])
    assert r.returncode == 7


@pytest.mark.parametrize("args,msg", [
    (["--file-key", "../../etc/passwd"], "file key"),
    (["--file-key", KEY, "--api-base", "http://169.254.169.254"], "api base"),
    (["--file-key", KEY, "--api-base", "https://evil.example"], "api base"),
])
def test_input_validation_blocks_traversal_and_ssrf(figma_server, tokens_file, args, msg):
    r = run_cli(*args, "--out", str(tokens_file))
    assert r.returncode == 2 and msg in r.stderr
    assert figma_server["requests"] == []


def test_token_only_from_stdin(tokens_file):
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), token=None)
    assert r.returncode == 2 and "no valid token" in r.stderr


# ── review round 1 regressions ──

def test_a_redirect_is_refused_and_the_token_never_reaches_the_target(tokens_file):
    received = []

    class Target(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            received.append(self.headers.get("X-Figma-Token"))
            self.send_response(200)
            self.end_headers()

    target = HTTPServer(("127.0.0.1", 0), Target)
    threading.Thread(target=target.serve_forever, daemon=True).start()

    class Redirector(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}/steal")
            self.end_headers()

    redirector = HTTPServer(("127.0.0.1", 0), Redirector)
    threading.Thread(target=redirector.serve_forever, daemon=True).start()
    try:
        r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", f"http://127.0.0.1:{redirector.server_address[1]}")
    finally:
        redirector.shutdown()
        target.shutdown()
    assert r.returncode == 5 and "redirect" in r.stderr
    assert received == []


def test_infinite_values_are_reported_not_a_crash(figma_server, tokens_file):
    figma_server["payload"] = payload(variables={"v4": _var("v4", "motion/rise-ms", "c3", "FLOAT", {"m-one": 1e309})})
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", figma_server["base"])
    assert "Traceback" not in r.stderr
    assert r.returncode == 0 and "skipped 'motion/rise-ms'" in r.stdout


def test_file_mode_is_preserved(figma_server, tokens_file):
    import os
    os.chmod(tokens_file, 0o644)
    r = run_cli("--file-key", KEY, "--out", str(tokens_file), "--api-base", figma_server["base"])
    assert r.returncode == 0
    assert os.stat(tokens_file).st_mode & 0o777 == 0o644


def test_file_key_with_trailing_newline_is_rejected(figma_server, tokens_file):
    r = run_cli("--file-key", KEY + "\n", "--out", str(tokens_file), "--api-base", figma_server["base"])
    assert r.returncode == 2
