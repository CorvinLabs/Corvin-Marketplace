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
cd plugins/contributor/media/video_producer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Installs exactly 4 packages: `anthropic`, `requests`, `gTTS`, `Pillow` (plus
their own transitive dependencies). Nothing else is imported by the live
code — verified by grepping every import line (including the ones inside
functions) across `src/models.py`, `storage.py`, `skill.py`,
`async_runner.py`, `__init__.py`.

Optionally, install the package itself (editable, for development):

```bash
pip install -e .
```

## Step 3: Verify (no API key, no network cost beyond gTTS)

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
import models, storage, skill, async_runner
print('all live modules import cleanly')
"
```

To verify the actual narration + encoding pipeline works (uses gTTS's free
public endpoint and your local ffmpeg — no account needed):

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path
import tempfile, skill
from PIL import Image

work = Path(tempfile.mkdtemp())
img, aud, out = work/'f.png', work/'a.mp3', work/'c.mp4'
Image.new('RGB', (1280, 720), 'navy').save(img)
skill._synthesize_narration('Installation verified.', aud, 'en')
skill._assemble_scene_clip(img, aud, out)
print('narration + assembly OK:', out.stat().st_size, 'bytes ->', out)
"
```

## Step 4: Anthropic API Key (optional)

The storyboard step prefers Anthropic when the HOST (the CorvinOS console,
not this plugin) decides the job's egress policy allows it; otherwise it
falls back to a local Ollama instance automatically. Setting
`ANTHROPIC_API_KEY` in the *console's* environment is a host-level decision,
not something this plugin configures on its own — see the main CorvinOS
docs for `tenant.corvin.yaml`'s egress policy.

## Not needed, despite earlier docs claiming otherwise

- **Node.js / Puppeteer** — the screenshot-capture code that used it was
  removed as dead (ADR-0953); not on the live path.
- **OpenAI API key** — narration uses gTTS, not OpenAI TTS.
- **YouTube / Google OAuth credentials** — upload is not built; the console
  route answers `501 Not Implemented`.
- **`python3 -m video_producer`** — there is no CLI. The only entry point is
  the host's HTTP API (`POST /v1/console/video/jobs`, see the main
  [README](../README.md)).

## Troubleshooting

**`ModuleNotFoundError` for anthropic/requests/gtts/PIL** — `pip install -r
requirements.txt` was skipped or ran in the wrong venv; re-run Step 2.

**`ffmpeg: command not found`** — Step 1 was skipped, or `ffmpeg` is not on
`PATH` in the process that runs the job (check the same shell/service
environment the console runs in, not just your interactive shell).

**gTTS step fails / times out** — it calls Google's public Translate TTS
endpoint; it needs outbound internet access and fails if that endpoint is
unreachable (corporate proxy, offline environment). There is currently no
offline TTS fallback on the live path.

## Uninstallation

Remove the plugin directory and, if you installed it editable,
`pip uninstall corvinos-video-producer`. No credentials or OAuth tokens are
written anywhere by the live path (gTTS needs none; Anthropic reads its key
from the host's own environment, this plugin never persists one).

## Next Steps

- **Usage / API shape:** [README.md](../README.md)
- **Why things are the way they are:**
  [ADR-0953](./ADR-0953-consolidation-dead-code-removal.md)
