# Configuration Guide — Video Producer Skill 2.0

Environment variables, API keys, and configuration options.

## Environment Variables

### Required

| Variable | Example | Description |
|---|---|---|
| `OPENAI_API_KEY` | `sk-...` | OpenAI API key for TTS (voice synthesis) |

**Set it:**
```bash
export OPENAI_API_KEY="sk-your-key-here"
```

### Optional

| Variable | Default | Description |
|---|---|---|
| `CORVIN_TENANT_ID` | `_default` | Tenant isolation (GDPR-compliant) |
| `CORVIN_HOME` | `~/.corvin` | Config directory |
| `VIDEO_PRODUCER_CACHE_DIR` | `$CORVIN_HOME/cache` | TTS cache location |
| `VIDEO_PRODUCER_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

**Set them:**
```bash
export CORVIN_TENANT_ID="tenant_123"
export VIDEO_PRODUCER_LOG_LEVEL="DEBUG"
```

## API Keys & Credentials

### OpenAI API Key (Required)

Get your key: https://platform.openai.com/account/api-keys

```bash
# Set in shell
export OPENAI_API_KEY="sk-..."

# Or save to ~/.bashrc for persistence
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.bashrc
source ~/.bashrc

# Verify
python3 -c "import os; print(f'Key set: {bool(os.environ[\"OPENAI_API_KEY\"])}')"
```

### YouTube Service Account (Optional)

For YouTube upload capability, create a Service Account:

1. Go to Google Cloud Console: https://console.cloud.google.com
2. Create a service account with YouTube Data v3 access
3. Download the JSON credentials file
4. Save to `~/.corvin/youtube-credentials.json`:

```bash
mkdir -p ~/.corvin
cp /path/to/downloaded-credentials.json ~/.corvin/youtube-credentials.json
chmod 600 ~/.corvin/youtube-credentials.json

# Verify
ls -la ~/.corvin/youtube-credentials.json
python3 -c "import json; json.load(open('~/.corvin/youtube-credentials.json'))"
```

## Runtime Configuration

### Project Directory

Each orchestration run uses a `project_dir` to store intermediate files:

```bash
python3 -m video_producer orchestrate \
  --project-dir "/path/to/project" \
  --assets "presentation.pptx"
```

**Files created:**
```
/path/to/project/
├── analysis.json           # Extracted facts + gates
├── storyboard.json         # Generated scenes + narration
├── cache/
│   ├── voice/
│   │   └── sha256_hash.mp3 # TTS cache (reused across runs)
│   └── ...
└── orchestration.log       # Execution log
```

### Cache Configuration

TTS results are cached by narration hash (SHA256):

```python
from video_producer import VideoProducerOrchestrator

orch = VideoProducerOrchestrator(project_dir="/tmp")
# Same narration → reused .mp3 file (no API call)
```

**Clear cache:**
```bash
rm -rf ~/.corvin/cache/video_producer/*
```

## Feature Flags (Optional)

None currently. Features are toggled via plugin enable/disable in CorvinOS settings.

## Logging Configuration

Set verbosity:

```bash
# Normal
export VIDEO_PRODUCER_LOG_LEVEL="INFO"
python3 -m video_producer orchestrate --assets "pres.pptx"

# Debug (shows all steps)
export VIDEO_PRODUCER_LOG_LEVEL="DEBUG"
python3 -m video_producer orchestrate --assets "pres.pptx"

# Quiet
export VIDEO_PRODUCER_LOG_LEVEL="WARNING"
```

## Performance Tuning

### TTS Quality vs. Speed

Default: `tts-1-hd` (highest quality, slightly slower)

**In code:**
```python
# Already using best quality by default
# See src/video_producer/voice_*.py
```

### H.264 Encoding Quality

Default: `CRF=18` (professional quality, slower encode)

**Options:**
- CRF 18–20: Professional (slower, recommended)
- CRF 23: Balanced
- CRF 28: Fast (lower quality)

**In code:**
```python
# See src/video_producer/video_ffmpeg.py
# Change: `-crf 18` to `-crf 23`
```

## Multi-Tenant Setup

CorvinOS supports multi-tenant isolation (GDPR-compliant):

```bash
# Tenant A
export CORVIN_TENANT_ID="tenant_a"
python3 -m video_producer orchestrate --assets "pres_a.pptx"
# Creates: ~/.corvin/tenants/tenant_a/...

# Tenant B
export CORVIN_TENANT_ID="tenant_b"
python3 -m video_producer orchestrate --assets "pres_b.pptx"
# Creates: ~/.corvin/tenants/tenant_b/...
```

Each tenant's data is isolated (separate cache, logs, analysis).

## Troubleshooting Config Issues

### ❌ "OPENAI_API_KEY not set"

```bash
# Check if set
echo $OPENAI_API_KEY

# Set it
export OPENAI_API_KEY="sk-..."

# Verify
python3 -c "import os; assert os.environ['OPENAI_API_KEY']; print('✅')"
```

### ❌ "YouTube credentials not found"

```bash
# Check path
ls -la ~/.corvin/youtube-credentials.json

# Create directory if needed
mkdir -p ~/.corvin

# Copy credentials
cp /path/to/credentials.json ~/.corvin/youtube-credentials.json

# Verify
python3 -c "
import json
with open('~/.corvin/youtube-credentials.json') as f:
    data = json.load(f)
    assert 'type' in data and data['type'] == 'service_account'
    print('✅ Valid Service Account JSON')
"
```

## Next Steps

- **Installation:** [INSTALLATION.md](./INSTALLATION.md)
- **Usage:** [USAGE.md](./USAGE.md)
- **Troubleshooting:** [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
