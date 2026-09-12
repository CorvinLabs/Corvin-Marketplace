# Setup Guide — Video Producer Plugin

## Prerequisites

- CorvinOS v1.0.0 or later
- Python 3.8+
- FFmpeg 6.0+ (for video assembly)
- 2GB free disk space (for temp files)

## Installation Steps

### Step 1: Install from Marketplace

```bash
# List available plugins
corvin plugin list --marketplace

# Install Video Producer
corvin plugin install video-producer

# Verify installation
corvin plugin status video-producer
# Expected output: "Status: active, Version: 1.0.0"
```

### Step 2: Verify Console Panel Registration

1. Open CorvinOS Console (http://localhost:8765/console/)
2. Navigate to "My Panels" (top-right user menu)
3. Scroll to "Media" section
4. Verify "Video Producer" panel is listed
5. Click to open the panel

### Step 3: Configure Plugin Settings (Optional)

Edit `~/.corvin/tenants/_default/plugins/video-producer.yaml`:

```yaml
video_producer:
  # TTS engine (azure, gcp, aws)
  tts_engine: "azure"
  
  # YouTube settings
  youtube_oauth_required: true
  
  # Production settings
  max_video_length_minutes: 60
  max_concurrent_jobs: 3
  
  # Learning optimizer
  enable_learning: true
```

### Step 4: Authenticate External Services (Optional)

#### YouTube Upload

```bash
corvin auth youtube --plugin video-producer
# Opens browser for OAuth consent
# Saves token to: ~/.config/corvin-voice/youtube-oauth.json
```

#### Azure Text-to-Speech

```bash
corvin auth azure-tts \
  --key YOUR_AZURE_KEY \
  --region YOUR_REGION
# Saves credentials to: ~/.config/corvin-voice/azure-tts.json
```

### Step 5: Run Health Check

```bash
curl -s http://localhost:8765/v1/console/video-producer/health
# Expected: {"status": "ok", "service": "video-producer"}
```

## Docker Installation

### Option 1: Using Pre-built Image

```bash
docker pull corvinlabs/corvinOS:latest-with-video-producer
docker run -v ~/.corvin:/root/.corvin \
  corvinlabs/corvinOS:latest-with-video-producer
```

### Option 2: Building Custom Image

```dockerfile
FROM corvinlabs/corvinOS:latest

RUN pip install git+https://github.com/CorvinLabs/Corvin-Marketplace.git#subdirectory=plugins/contributor/video_producer

EXPOSE 8765
CMD ["corvin-serve"]
```

Build and run:

```bash
docker build -t my-corvin-with-video .
docker run -v ~/.corvin:/root/.corvin my-corvin-with-video
```

## Troubleshooting Setup

### Plugin Not Appearing in Console

**Symptom:** Installed but not showing in "My Panels"

**Solution:**
1. Restart Console: `systemctl --user restart corvin-webui.service`
2. Hard-refresh browser (Ctrl+Shift+R)
3. Check plugin status: `corvin plugin status video-producer`
4. View logs: `tail -f ~/.corvin/logs/plugins.log`

### Console Panel Throws Error

**Symptom:** "Failed to load Video Producer" error in Console

**Solution:**
1. Check API health: `curl http://localhost:8765/v1/console/video-producer/health`
2. View error logs: `grep -A 5 "VideoProducer" ~/.corvin/logs/console.log`
3. Restart FastAPI backend: `systemctl --user restart corvin-console.service`

### Import Errors

**Symptom:** `ModuleNotFoundError: No module named 'video_producer'`

**Solution:**
```bash
# Reinstall in development mode
cd ~/.corvin/plugins/video-producer
pip install -e .

# Or reinstall from marketplace
corvin plugin uninstall video-producer
corvin plugin install video-producer
```

### FFmpeg Not Found

**Symptom:** "FFmpeg not found" error during video assembly

**Solution (Ubuntu/Debian):**
```bash
sudo apt-get install ffmpeg
```

**Solution (macOS):**
```bash
brew install ffmpeg
```

**Solution (Windows):**
Download from https://ffmpeg.org/download.html or use:
```powershell
choco install ffmpeg
```

### GDPR Compliance Issues

The plugin respects all CorvinOS GDPR controls:

1. **Audit Logging:** Enabled by default (cannot be disabled)
   - All video metadata logged to `~/.corvin/audit.jsonl`
   - Auditable via: `corvin audit query --filter plugin=video-producer`

2. **Consent Gates:** Plugin respects CorvinOS consent settings
   - If user hasn't consented, YouTube upload is blocked
   - Check: `corvin consent status`

3. **Data Retention:** Plugin follows CorvinOS retention policy
   - Temp files auto-deleted after 30 days
   - Configurable via: `~/.corvin/tenants/_default/spec.yaml`

## Uninstallation

```bash
# Remove plugin
corvin plugin uninstall video-producer

# Clean up config files (optional)
rm -rf ~/.corvin/tenants/_default/plugins/video-producer.yaml

# Clean up credentials (optional)
rm -f ~/.config/corvin-voice/youtube-oauth.json
rm -f ~/.config/corvin-voice/azure-tts.json
```

## Post-Installation Verification

Run the verification script:

```bash
cd ~/.corvin/plugins/video-producer
python -m pytest tests/test_plugin_registration.py::TestPluginStructure -v
```

Expected output: All tests PASSED

## Next Steps

1. **First Video:** Follow the [Quick Start](../README.md#quick-start) guide
2. **Learn APIs:** Read [API.md](API.md) for detailed endpoint documentation
3. **Feedback Loops:** Set up feedback collection for the learning optimizer
4. **Advanced Config:** Customize via [Configuration Guide](CONFIGURATION.md)
