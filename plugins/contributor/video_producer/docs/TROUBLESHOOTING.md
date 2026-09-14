# Troubleshooting Guide — Video Producer Skill 2.0

Common issues, diagnostic steps, and solutions.

## Installation & Setup Issues

### ❌ "No module named video_producer"

**Symptom:**
```
/usr/bin/python3: No module named video_producer
```

**Causes:**
1. Plugin not installed
2. Python path not configured
3. Wrong Python version

**Solutions:**

```bash
# Option 1: Install from source
cd /path/to/video_producer
pip install -e .
python3 -m video_producer health

# Option 2: Check Python path
python3 -c "import sys; print('\\n'.join(sys.path))"
# Should include: /path/to/video_producer/src

# Option 3: Set PYTHONPATH explicitly
export PYTHONPATH="/path/to/video_producer/src:$PYTHONPATH"
python3 -m video_producer health

# Option 4: Check Python version
python3 --version  # Must be ≥3.9
```

---

### ❌ "ffmpeg: command not found"

**Symptom:**
```
ffmpeg: command not found
```

**Causes:**
1. FFmpeg not installed
2. FFmpeg not in PATH

**Solutions:**

```bash
# Check if installed
which ffmpeg
ffmpeg -version

# Install:
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Verify
ffmpeg -version | head -3
```

---

### ❌ "OPENAI_API_KEY not set"

**Symptom:**
```
ValueError: OPENAI_API_KEY not set
```

**Solutions:**

```bash
# Set it
export OPENAI_API_KEY="sk-..."

# Make persistent (add to ~/.bashrc or ~/.zshrc)
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.bashrc
source ~/.bashrc

# Verify
python3 -c "import os; print('Set' if os.getenv('OPENAI_API_KEY') else 'Not set')"
```

---

## Runtime Issues

### ⚠️ "Analysis gates not met"

**Symptom:**
```
AnalysisGateFailedError: Analysis gates not met:
- Facts extracted: 0 (need ≥3)
- Asset roles mapped: 0 (need ≥1)
- Blockers:
  • (list of blockers)
```

**Causes:**
1. Input file too minimal (e.g., empty, single line)
2. PPT has insufficient content
3. Analysis failed to extract facts

**Solutions:**

```bash
# 1. Check input file exists and is non-empty
ls -lh presentation.pptx
file presentation.pptx

# 2. Use a real PowerPoint (≥3 slides with content)
# Not: empty.pptx, single_line.txt

# 3. Try verbose mode to see what's happening
export VIDEO_PRODUCER_LOG_LEVEL="DEBUG"
python3 -m video_producer orchestrate --assets "presentation.pptx"
# Look for "Facts extracted:" count

# 4. If all else fails, check the analysis.json directly
cat output/analysis.json | python3 -m json.tool | grep -A5 "blockers"
```

---

### ⚠️ "Learning optimizer unavailable"

**Symptom:**
```
⚠️  Learning optimizer unavailable: No module named 'core'
```

**Causes:**
1. CorvinOS core not installed (expected for standalone installation)
2. Optional dependency missing

**Solutions:**

```bash
# This is OPTIONAL — core orchestrator works fine without it
# Only needed if you want learning loop integration:

pip install corvin-core  # When available
# OR just ignore the warning — it's not critical
```

---

### ❌ "YouTube credentials not found"

**Symptom:**
```
ValueError: YouTube credentials not found: ~/.corvin/youtube-credentials.json
```

**Causes:**
1. Service Account JSON not created
2. Wrong path

**Solutions:**

```bash
# 1. Check if file exists
ls -la ~/.corvin/youtube-credentials.json

# 2. Create directory if missing
mkdir -p ~/.corvin

# 3. Download Service Account JSON from Google Cloud
# https://console.cloud.google.com → Service Accounts → Download JSON

# 4. Copy to correct location
cp /path/to/downloaded.json ~/.corvin/youtube-credentials.json

# 5. Verify
python3 -c "
import json
with open('~/.corvin/youtube-credentials.json') as f:
    data = json.load(f)
    assert 'type' in data and data['type'] == 'service_account'
    print(f'✅ Valid: {data.get(\"project_id\")}')"
```

---

### ❌ "TTS voice not available"

**Symptom:**
```
openai.error.InvalidRequestError: The model 'tts-1-hd' does not exist
```

**Causes:**
1. OpenAI API key invalid or expired
2. API key doesn't have TTS permissions
3. Account quota exceeded

**Solutions:**

```bash
# 1. Check API key
python3 -c "
import os
from openai import OpenAI
key = os.getenv('OPENAI_API_KEY')
try:
    client = OpenAI(api_key=key)
    models = client.models.list()
    print(f'✅ API key works. Found {len(models.data)} models')
except Exception as e:
    print(f'❌ API key issue: {e}')"

# 2. Verify TTS model availability
python3 -c "
import os
from openai import OpenAI
try:
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    response = client.audio.speech.create(
        model='tts-1-hd',
        voice='nova',
        input='test'
    )
    print('✅ TTS works')
except Exception as e:
    print(f'❌ TTS issue: {e}')"

# 3. Check quota/rate limits
# Visit: https://platform.openai.com/account/billing/overview
```

---

## Performance Issues

### 🐢 "Orchestration is very slow"

**Symptom:**
```
Takes 2+ minutes to complete
```

**Causes:**
1. Large PPT (many slides)
2. Network latency (API calls)
3. Encoding speed (FFmpeg CRF 18 is slow)

**Solutions:**

```bash
# 1. Check what's slow
export VIDEO_PRODUCER_LOG_LEVEL="DEBUG"
python3 -m video_producer orchestrate --assets "presentation.pptx"
# Look for timing markers

# 2. Reduce PPT size
# Use fewer slides or lower resolution images

# 3. Lower FFmpeg quality (if acceptable)
# Edit src/video_producer/video_ffmpeg.py:
# Change: -crf 18 → -crf 23 (faster, slightly lower quality)

# 4. Use smaller input assets
python3 -m video_producer orchestrate \
  --assets "small_presentation.pptx" \
  --project-dir "/tmp"
```

---

### 💾 "Disk space issues"

**Symptom:**
```
OSError: No space left on device
```

**Causes:**
1. Cache growing large
2. Temporary files not cleaned up

**Solutions:**

```bash
# 1. Check disk space
df -h ~/.corvin

# 2. Clear old cache
rm -rf ~/.corvin/cache/video_producer/*

# 3. Clean project directories
rm -rf /tmp/video_project_*

# 4. Check for large files
du -sh ~/.corvin/*
```

---

## Debugging Steps

### Enable Debug Logging

```bash
export VIDEO_PRODUCER_LOG_LEVEL="DEBUG"
python3 -m video_producer orchestrate --assets "presentation.pptx" 2>&1 | tee debug.log
```

**Look for:**
- Analysis progress
- Gate check results
- Storyboard generation details
- Any error stack traces

### Check Intermediate Files

```bash
# After an orchestration run:
ls -la project_dir/

# View generated analysis
cat project_dir/analysis.json | python3 -m json.tool

# View storyboard
cat project_dir/storyboard.json | python3 -m json.tool
```

### Test Individual Components

```bash
# Test just the orchestrator
python3 -c "
from video_producer import VideoProducerOrchestrator
import asyncio

async def test():
    orch = VideoProducerOrchestrator('/tmp/test')
    print('✅ Orchestrator works')

asyncio.run(test())
"

# Test OpenAI API
python3 -c "
import os
from openai import OpenAI
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
response = client.audio.speech.create(
    model='tts-1-hd',
    voice='nova',
    input='Hello world'
)
print(f'✅ TTS works: {len(response.content)} bytes')
"

# Test FFmpeg
ffmpeg -version | head -3
ffmpeg -f lavfi -i "color=red:s=320x240:d=1" -f lavfi -i "sine=f=440:d=1" \
  -c:v libx264 -crf 18 -c:a aac /tmp/test.mp4 -y 2>&1 | grep -E "ERROR|error" || echo "✅ FFmpeg works"
```

---

## Getting Help

If you've tried all above steps:

1. **Check logs:**
   ```bash
   export VIDEO_PRODUCER_LOG_LEVEL="DEBUG"
   python3 -m video_producer orchestrate --assets "pres.pptx" 2>&1 | head -100
   ```

2. **Create minimal reproduction:**
   ```bash
   # Create a tiny test file
   echo "# Simple Slide\n\nContent here" > /tmp/minimal.txt
   python3 -m video_producer orchestrate --assets "/tmp/minimal.txt" --project-dir "/tmp/debug"
   ```

3. **Report the issue** with:
   - Error message (exact text)
   - Your OS & Python version (`python3 --version`)
   - Steps to reproduce
   - Debug log output
   - System dependencies (`ffmpeg -version`, `node --version`)

---

## Next Steps

- **Installation:** [INSTALLATION.md](./INSTALLATION.md)
- **Usage:** [USAGE.md](./USAGE.md)
- **Configuration:** [CONFIGURATION.md](./CONFIGURATION.md)
