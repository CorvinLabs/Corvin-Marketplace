# Installation Guide — Video Producer Skill 2.0

Complete step-by-step installation for developers and operators.

## System Requirements

| Requirement | Version | Why |
|---|---|---|
| **Python** | ≥ 3.9 | Core runtime |
| **FFmpeg** | ≥ 4.2 | Video encoding (H.264, AAC) |
| **Node.js** | ≥ 14 | Puppeteer for screenshots |
| **OpenAI API Key** | (account) | Text-to-speech (voice narration) |
| **YouTube Credentials** | (Service Account) | Optional: YouTube upload |

## Step 1: System Dependencies

### macOS
```bash
brew install ffmpeg node
```

### Ubuntu / Debian
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg nodejs npm
```

### Verify Installation
```bash
ffmpeg -version | head -3
node --version
npm --version
```

## Step 2: Python Package Installation

### Option A: From Source (Development)
```bash
cd /path/to/video_producer
pip install -e .
```

### Option B: From PyPI (When Published)
```bash
pip install video-producer-orchestrator>=2.0.0
```

### Verify Installation
```bash
python3 -m video_producer health --verbose
# Expected output: "Status: healthy" (or "Status: degraded" if optional deps missing)
```

## Step 3: Configure Environment Variables

### Required: OpenAI API Key
```bash
export OPENAI_API_KEY="sk-..."
# Or save to ~/.bashrc or ~/.zshrc for persistence
```

### Optional: YouTube Upload
```bash
# Save Service Account credentials to:
mkdir -p ~/.corvin
cp /path/to/youtube-credentials.json ~/.corvin/youtube-credentials.json

# Verify:
ls -la ~/.corvin/youtube-credentials.json
```

## Step 4: Verify Everything Works

### Test 1: CLI Health Check
```bash
python3 -m video_producer health --verbose
```

Expected output:
```
📹 Video Producer — Health Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Orchestrator: ✅
  Optimizer: ✅ (or ⚠️ if optional deps missing)
  Console Panel: ✅ (or ⚠️ if pydantic not installed)

Status: healthy
```

### Test 2: Full Orchestration Pipeline
```bash
# Create a test PPT (or use existing)
cat > /tmp/test_presentation.txt << 'EOF'
# Test Presentation

## Slide 1: Introduction
Content here

## Slide 2: Main Topic
More content
EOF

# Run orchestration
python3 -m video_producer orchestrate \
  --assets "/tmp/test_presentation.txt" \
  --project-dir "/tmp/video_test" \
  --output "/tmp/result.json"

# Check result
cat /tmp/result.json | python3 -m json.tool
```

Expected output:
```json
{
  "status": "success" | "blocked",
  "analysis": { ... },
  "storyboard": { ... }
}
```

## Step 5: Optional — Install Development Tools

For contributing to the plugin:

```bash
# Testing
pip install pytest pytest-cov

# Code formatting
pip install black ruff

# Install dev dependencies
pip install -e ".[dev]"
```

## Troubleshooting

### ❌ "No module named video_producer"
**Solution:** Make sure you're in the right directory or did `pip install -e .`:
```bash
cd /path/to/video_producer
pip install -e .
python3 -m video_producer health
```

### ❌ "ffmpeg: command not found"
**Solution:** FFmpeg not installed. Run Step 1 above (brew install / apt-get install).

### ❌ "OPENAI_API_KEY not set"
**Solution:** Set the environment variable:
```bash
export OPENAI_API_KEY="sk-..."
# Or add to ~/.bashrc:
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.bashrc
source ~/.bashrc
```

### ⚠️ "Learning optimizer unavailable" / "Console panel unavailable"
**Solution:** These are optional components. The core orchestrator still works. To enable them:
```bash
pip install pydantic google-api-python-client
```

### ❌ "Analysis gates not met"
**Solution:** Your input assets (PPT, images) are too minimal. The analysis requires:
- At least 3 factual claims extracted
- At least 1 asset role identified
- No contradictions

Try with a real PowerPoint file (3+ slides) instead of a text file.

## Uninstallation

```bash
pip uninstall video-producer-orchestrator

# Optional: clean up configs
rm -rf ~/.corvin/youtube-credentials.json
```

## Next Steps

- **Usage:** See [USAGE.md](./USAGE.md)
- **Configuration:** See [CONFIGURATION.md](./CONFIGURATION.md)
- **Troubleshooting:** See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
- **Architecture:** See [ARCHITECTURE.md](./ARCHITECTURE.md)
