# Installation Guide — Video Producer

> **2026-10-04 rewrite (ADR-0953 Phase E):** this file previously documented
> installing Node.js/Puppeteer, a required `OPENAI_API_KEY`, and a
> `python3 -m video_producer` CLI — none of that is part of the live path.
> Everything below was verified on a genuinely fresh machine simulation: a
> brand-new venv, only `requirements.txt`, no access to any pre-existing
> CorvinOS environment.

## System Requirements

| Requirement | Version | Why |
|---|---|---|
| **Python** | ≥ 3.9 | Runtime |
| **FFmpeg** | any recent version | Video assembly (`subprocess`, not a Python wrapper) |

That's it. No Node.js, no API key is *required* (see below).

## Step 1: System Dependency (FFmpeg)

```bash
# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y ffmpeg

# macOS
brew install ffmpeg

# Verify
ffmpeg -version
```

## Step 2: Python Dependencies

```bash
cd plugins/buildin/media/corvintv
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Installs `requests`, `Pillow`, `numpy` and `playwright` (plus their own transitive
dependencies). Since 1.8.0 there is **no LLM SDK and no TTS package** in this list:
the storyboard is written by the host's native Claude Code engine (the signed-in
`claude` CLI) and the narration by the CorvinOS voice chain
(`corvin_console.native_tts` → `say.py`: OpenAI → edge-tts → Piper), whose packages
CorvinOS installs itself. CorvinTV therefore runs inside a CorvinOS installation; a
fresh one installs and enables it at first boot without any step.

Optionally, install the package itself (editable, for development):

```bash
pip install -e .
```

## Step 3: Verify the imports

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
import models, storage, skill, async_runner
print('all live modules import cleanly')
"
```

To verify narration + encoding end to end, run the CorvinOS live test with
the console's own interpreter (it boots a console on a fresh temp home, makes a
real short video with the real `claude` CLI and the real voice chain, and
checks it with ffprobe):

```bash
cd <CorvinOS checkout>
CLAUDE_LIVE_E2E=1 pytest core/console/tests/test_corvintv_native_live_e2e.py -m live -s
```

## Step 4: Claude Code (required)

Every storyboard is one tool-less `claude -p` call of the host's Claude Code
CLI. Install Claude Code on the CorvinOS host and sign in once (`claude` in a
terminal). The CLI runs on that Claude Code subscription: it is started
without `ANTHROPIC_API_KEY`, and its own error message reaches the job error.
The console resolves the binary like its own chat does
(`CORVIN_CLAUDE_BIN`, PATH, the known install locations, a Windows `claude.cmd`
shim through the cmd.exe-safe launcher) and hands the job exactly that binary.
There is no API-key path and no local model: without the CLI a job is refused
before it starts, and a CLI failure ends the job with `ClaudeEngineUnavailable`
and the reason. Whether the task may go to api.anthropic.com at all is still
the host's decision (L35 egress / L34 classification, `tenant.corvin.yaml`).

## Not needed, despite earlier docs claiming otherwise

- **Node.js / Puppeteer** — the screenshot-capture code that used it was
  removed as dead (ADR-0953); not on the live path.
- **An OpenAI API key for CorvinTV** — narration is the CorvinOS voice chain; a key
  configured for chat TTS is used here too, and without one edge-tts or Piper speaks.
- **`ANTHROPIC_API_KEY`** — never used; the storyboard comes from the `claude` CLI.
- **YouTube / Google OAuth credentials** — upload is not built; the console
  route answers `501 Not Implemented`.
- **`python3 -m video_producer`** — there is no CLI. The only entry point is
  the host's HTTP API (`POST /v1/console/video/jobs`, see the main
  [README](../README.md)).

## Troubleshooting

**`ModuleNotFoundError` for requests/PIL** — `pip install -r
requirements.txt` was skipped or ran in the wrong venv; re-run Step 2.

**`ffmpeg: command not found`** — Step 1 was skipped, or `ffmpeg` is not on
`PATH` in the process that runs the job (check the same shell/service
environment the console runs in, not just your interactive shell).

**"No narration voice is available"** — no tier of the CorvinOS voice chain
could speak; the message lists each tier's reason (`say.py: ...`). Fix chat TTS
and CorvinTV follows: an OpenAI TTS key, network access for edge-tts
(speech.platform.bing.com), or a Piper voice model for offline narration.

**"... native Claude Code engine ... no `claude` CLI"** — install Claude Code on
the host and sign in; see Step 4.

## Uninstallation

Remove the plugin directory and, if you installed it editable,
`pip uninstall corvinos-video-producer`. No credentials or OAuth tokens are
written anywhere by the live path (the `claude` CLI keeps its own login; the
voice chain's keys belong to CorvinOS; this plugin never persists one).

## Next Steps

- **Usage / API shape:** [README.md](../README.md)
- **Why things are the way they are:**
  [ADR-0953](./ADR-0953-consolidation-dead-code-removal.md)
