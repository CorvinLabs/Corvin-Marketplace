# Setup Guide — Video Producer Plugin (CorvinOS-side)

> **2026-10-04 rewrite (ADR-0953 Phase E):** removed the Azure-TTS /
> YouTube-OAuth setup steps, the fantasy Docker image reference, and the
> Puppeteer/Node.js prerequisite — none of that is part of the live path.
> For the plugin's own Python dependency installation (verified against a
> genuinely fresh machine), see [INSTALLATION.md](./INSTALLATION.md); this
> file covers only the CorvinOS-side plugin lifecycle.

## Prerequisites

- A running CorvinOS console
- FFmpeg on the host (see [INSTALLATION.md](./INSTALLATION.md))
- This plugin's Python dependencies installed in the console's own
  environment (`pip install -r requirements.txt` from this checkout — there
  is no automatic installer; see INSTALLATION.md Step 2)

## Step 1: Install via the Marketplace CLI

```bash
corvin plugin list --marketplace
corvin plugin install video_producer
corvin plugin status video_producer
```

## Step 2: Verify Console Panel Registration

1. Open the CorvinOS Console
2. Find "Video Producer" under the Media section of the sidebar
3. Open the panel — it lists jobs, lets you submit a task, and shows
   playback + quality metrics for completed videos

The panel's existence is declared in [`../plugin.yaml`](../plugin.yaml)
(`console_panel.component: VideoProducerPage`) and enabled/disabled through
the normal plugin enable/disable lifecycle (`corvin plugin enable/disable
video_producer`) — there is no separate plugin-specific config file.

## Step 3: Settings (via the Console UI, not a YAML file)

Settings live per-tenant in the console itself (`GET`/`PUT
/v1/console/video/settings`), not in a file you edit by hand. The only
setting that affects behaviour is `max_duration_minutes` (1–60); the TTS
engine is fixed to gTTS (see [`../plugin.yaml`](../plugin.yaml)'s
`settings_schema` for the exact shape).

## Step 4: Health Check

```bash
curl -s http://localhost:8765/v1/console/video/overview
```

A 200 response with a `jobs_total` field means the route loaded the plugin
successfully.

## Troubleshooting

**Panel missing from the sidebar** — hard-refresh the console tab
(`Ctrl+Shift+R`); the panel manifest is served from the build the browser
already cached. If still missing, confirm the plugin is enabled:
`corvin plugin status video_producer`.

**`503 Video Producer plugin not available`** — the console could not
import `src/__init__.py` from this checkout. Confirm the four
`requirements.txt` packages are installed in the *console's* Python
environment (not just a separate venv), and check the console's own logs
for the specific import error.

**Everything else** (FFmpeg, Python package install, gTTS reachability) —
see [INSTALLATION.md](./INSTALLATION.md).

## Uninstallation

```bash
corvin plugin uninstall video_producer
```

No credentials or OAuth tokens are written by the live path, so there is
nothing further to clean up.
