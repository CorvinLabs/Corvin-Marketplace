# How to Build Plugins for CorvinOS (Using Video Producer as Teaching Example)

**Status:** Complete guide  
**Level:** Intermediate (requires basic Python + async/await knowledge)  
**Time to Read:** 30 minutes

---

## What You're About to Learn

This document teaches you to build CorvinOS plugins by studying the **Video Producer Plugin** structure. Every concept has:
- **Why:** The design decision behind it
- **How:** Step-by-step code
- **Examples:** Working code you can extend

By the end, you'll understand:
1. ✅ Plugin lifecycle (bootstrap, execution, cleanup)
2. ✅ Worker isolation pattern (error handling, fallbacks)
3. ✅ Quality gates (deterministic scoring, hard enforcement)
4. ✅ Audit trail integration (logging every decision)
5. ✅ Learning loop wiring (ADR-0314)
6. ✅ How to add your own Worker to this plugin
7. ✅ How to create a new plugin from scratch

---

## Section 1: Plugin Anatomy

### 1.1 The Plugin Manifest (plugin.json)

Every plugin starts with a manifest — metadata that CorvinOS reads at boot:

```json
{
  "id": "video-producer-orchestrator",
  "name": "Video Producer",
  "version": "1.0.0",
  "description": "Generate professional demo videos from storyboards",
  "author": "CorvinOS Contributors",
  "entry_point": "src.plugin:VideoProducerPlugin",
  "dependencies": [
    "pillow>=9.0.0",
    "google-cloud-texttospeech>=2.0.0",
    "pydub>=0.25.0",
    "ffmpeg-python>=0.2.1"
  ],
  "boot_layer": "bundled",
  "capabilities": [
    "video:generate",
    "video:validate",
    "video:publish"
  ],
  "config_schema": {
    "google_tts_enabled": "bool",
    "piper_fallback_enabled": "bool",
    "quality_gate_threshold": "int",
    "design_system_path": "str"
  },
  "audit_events": [
    "video_generation_started",
    "slide_generated",
    "audio_generated",
    "video_assembled",
    "quality_validated",
    "quality_gate_decision"
  ]
}
```

**Key Concepts:**
- `id`: Unique identifier (plugin.py imports as `from <id> import Plugin`)
- `entry_point`: Points to the bootstrap class
- `boot_layer`: Control when it loads (`bundled`, `installed`, `community`)
- `audit_events`: Every event type you emit (not emitting an event = broken audit)

### 1.2 Plugin Bootstrap (src/plugin.py)

The entry point class that CorvinOS instantiates:

```python
# src/plugin.py
from typing import Any, Dict
from corvin_plugins.base import BasePlugin
from corvin_plugins.providers import audit_backend, skill_backend

class VideoProducerPlugin(BasePlugin):
    """Video generation orchestrator plugin."""
    
    async def bootstrap(self) -> None:
        """Initialize plugin (called once at boot)."""
        # Load design system
        self.design_system = self._load_design_system()
        
        # Initialize workers
        self.slide_generator = SlideGenerator(self.design_system)
        self.audio_generator = AudioGenerator(self.config)
        self.video_assembler = VideoAssembler()
        self.quality_validator = QualityValidator(self.design_system)
        
        # Register audit backend
        self.audit = audit_backend.get()
        
        # Register Skill (orchestrator)
        self.orchestrator = VideoOrchestrator(
            slide_gen=self.slide_generator,
            audio_gen=self.audio_generator,
            video_asm=self.video_assembler,
            quality_val=self.quality_validator,
            audit=self.audit
        )
        await skill_backend.register(self.orchestrator)
        
        # Log bootstrap
        await self.audit.write_event({
            "event_type": "plugin_bootstrap",
            "plugin_id": "video-producer-orchestrator",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "status": "success"
        })
    
    async def shutdown(self) -> None:
        """Cleanup (called at unload)."""
        # Cache cleanup, connection close, etc.
        pass
    
    def _load_design_system(self) -> DesignSystem:
        """Load design_system.json."""
        path = self.config.get("design_system_path", "design_system.json")
        with open(path) as f:
            spec = json.load(f)
        return DesignSystem.from_spec(spec)
```

**Key Concepts:**
- `bootstrap()`: Runs once at plugin load (setup workers, register Skills)
- `shutdown()`: Cleanup (optional)
- `audit`: All decisions logged (never skip)
- `config`: Plugin configuration (from plugin.json)

### 1.3 The Skill (Orchestrator)

The plugin's main entry point. Users call this, not the workers:

```python
# src/orchestrator.py
from corvin_skills.base import Skill
from corvin_skills.decorators import skill_method

class VideoOrchestrator(Skill):
    """Hero's Journey orchestrator (5-act narrative pipeline)."""
    
    skill_id = "video-producer-orchestrator"
    version = "1.0.0"
    
    def __init__(self, slide_gen, audio_gen, video_asm, quality_val, audit):
        super().__init__()
        self.slide_gen = slide_gen
        self.audio_gen = audio_gen
        self.video_asm = video_asm
        self.quality_val = quality_val
        self.audit = audit
    
    @skill_method
    async def generate(self, 
                      topic: str,
                      duration: str,  # "1m", "5m", "15m"
                      script: Optional[str] = None) -> VideoJob:
        """Generate video (DRAFT phase)."""
        
        # 1. Extract storyboard (Hero's Journey template)
        storyboard = await self._extract_storyboard(topic, duration, script)
        
        # 2. Generate slides (Worker 1)
        slides = await self.slide_gen.execute(storyboard)
        await self._audit_event("slide_generated", {
            "slide_count": len(slides),
            "storyboard_id": storyboard.id
        })
        
        # 3. Generate audio (Worker 2)
        audio = await self.audio_gen.execute(storyboard.narration)
        await self._audit_event("audio_generated", {
            "duration_ms": audio.duration_ms,
            "provider": audio.provider  # "google_tts" or "piper"
        })
        
        # 4. Assemble video (Worker 3, DRAFT only — no H.264 encoding yet)
        video_draft = await self.video_asm.execute_draft(slides, audio)
        
        # 5. Validate quality (Worker 4)
        quality = await self.quality_val.execute(video_draft, storyboard)
        await self._audit_event("quality_validated", {
            "score": quality.score,
            "breakdown": quality.breakdown
        })
        
        # 6. Enforce quality gate
        gate = self._gate_decision("DRAFT", quality.score)
        await self._audit_event("quality_gate_decision", {
            "gate": gate.name,
            "score": quality.score,
            "next_action": gate.next_action
        })
        
        return VideoJob(
            id=storyboard.id,
            topic=topic,
            duration=duration,
            state=gate.name,
            quality_score=quality.score,
            quality_breakdown=quality.breakdown,
            video_path=video_draft.path if gate.allow else None
        )
    
    @skill_method
    async def promote_to_production(self, job_id: str) -> VideoJob:
        """Promote DRAFT → PRODUCTION (full H.264 encoding)."""
        job = await self._load_job(job_id)
        
        # Full video assembly (H.264, 2.5 Mbps bitrate)
        video_prod = await self.video_asm.execute_production(job.video_path)
        
        # Re-validate on final output
        quality = await self.quality_val.execute_final(video_prod, job.storyboard)
        
        gate = self._gate_decision("PRODUCTION", quality.score)
        
        job.state = gate.name
        job.quality_score = quality.score
        await self._save_job(job)
        
        return job
    
    async def _audit_event(self, event_type: str, payload: Dict[str, Any]):
        """Emit audit event."""
        await self.audit.write_event({
            "event_type": event_type,
            "skill_id": self.skill_id,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        })
    
    def _gate_decision(self, gate_name: str, score: int) -> GateDecision:
        """Enforce quality gates."""
        if gate_name == "DRAFT":
            return GateDecision(name="DRAFT", allow=True, next_action="iterate")
        elif gate_name == "PRODUCTION":
            if score < 50:
                return GateDecision(name="DRAFT", allow=False, next_action="iterate_more")
            elif score >= 85:
                return GateDecision(name="BROADCAST", allow=True, next_action="manual_review")
            else:
                return GateDecision(name="PRODUCTION", allow=True, next_action="auto_queue")
        elif gate_name == "BROADCAST":
            if score >= 85:
                return GateDecision(name="BROADCAST", allow=True, next_action="upload")
            else:
                return GateDecision(name="PRODUCTION", allow=False, next_action="iterate_more")
```

**Key Concepts:**
- One Skill per orchestrator (not per worker)
- `@skill_method`: Makes methods callable from outside
- Workers are called sequentially (no parallelism yet — see PHASE 4)
- Every step logged to audit trail
- Gates are hard-enforced (no bypass)

---

## Section 2: Worker Pattern (Isolation + Fallback)

### 2.1 Worker Contract

Every worker implements the same interface:

```python
# src/workers/base.py
from typing import Protocol, AsyncContextManager
from dataclasses import dataclass

@dataclass
class WorkerError(Exception):
    """Worker failure with fallback info."""
    code: str  # "tts_api_down", "ffmpeg_missing", etc.
    message: str
    can_retry: bool  # Should orchestrator retry?
    fallback_worker: Optional[str]  # Name of fallback worker, if any

class Worker(Protocol):
    """Contract all workers must implement."""
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """Execute worker task.
        
        Raises WorkerError with fallback info.
        Never raises unhandled exceptions (error handling is mandatory).
        """
        ...
    
    @property
    def name(self) -> str:
        """Worker identifier (for logging, fallback routing)."""
        ...
```

### 2.2 Example Worker: SlideGenerator

```python
# src/workers/slide_generator.py
import asyncio
from PIL import Image, ImageDraw, ImageFont
from typing import List

class SlideGenerator:
    """Generate PNG slides from storyboard."""
    
    name = "slide_generator"
    
    def __init__(self, design_system: DesignSystem):
        self.design_system = design_system
        self.font = self._load_font()
    
    async def execute(self, scenes: List[Scene]) -> List[str]:
        """Generate PNG for each scene.
        
        Args:
            scenes: List of Scene(title, body_text, notes)
        
        Returns:
            List of PNG file paths
        
        Raises:
            WorkerError if Pillow unavailable or disk full
        """
        try:
            slide_paths = []
            for i, scene in enumerate(scenes):
                path = await self._render_slide(i, scene)
                slide_paths.append(path)
            return slide_paths
        
        except ImportError as e:
            raise WorkerError(
                code="pillow_missing",
                message=f"PIL not available: {e}",
                can_retry=False,
                fallback_worker="slide_generator_text_only"
            )
        except OSError as e:
            raise WorkerError(
                code="disk_full",
                message=f"Cannot write slides: {e}",
                can_retry=True,  # Retry after cleanup
                fallback_worker=None
            )
    
    async def _render_slide(self, index: int, scene: Scene) -> str:
        """Render single slide."""
        # Create blank image
        img = Image.new(
            'RGB',
            (self.design_system.slide_width, self.design_system.slide_height),
            color=self.design_system.colors['bg_light']
        )
        draw = ImageDraw.Draw(img)
        
        # Draw title
        draw.text(
            (self.design_system.margin, self.design_system.margin),
            scene.title,
            font=self.font['heading'],
            fill=self.design_system.colors['text_dark']
        )
        
        # Draw body
        draw.text(
            (self.design_system.margin, 300),
            scene.body_text,
            font=self.font['body'],
            fill=self.design_system.colors['text_dark']
        )
        
        # Verify contrast (WCAG AA)
        contrast = self._verify_contrast(
            self.design_system.colors['text_dark'],
            self.design_system.colors['bg_light']
        )
        if contrast < 4.5:
            raise WorkerError(
                code="contrast_fail",
                message=f"Text contrast {contrast} < 4.5 (WCAG AA)",
                can_retry=True,
                fallback_worker="slide_generator_high_contrast"
            )
        
        # Save
        path = f"/tmp/slide_{index:03d}.png"
        img.save(path)
        return path
```

**Key Concepts:**
- Workers are simple, testable, isolated
- Error handling is explicit (WorkerError with fallback info)
- One job per worker (generate all slides, then all audio, then assemble)
- No exceptions escape (error handling is mandatory)

### 2.3 Fallback Example: AudioGenerator with TTS Fallback

```python
# src/workers/audio_generator.py
from google.cloud import texttospeech
from piper import PiperTTS

class AudioGenerator:
    """Generate audio from narration script."""
    
    name = "audio_generator"
    
    def __init__(self, config):
        self.config = config
        self.google_tts = texttospeech.TextToSpeechClient() if config.google_tts_enabled else None
        self.piper_tts = PiperTTS() if config.piper_fallback_enabled else None
    
    async def execute(self, text: str) -> Audio:
        """Generate audio from text.
        
        Strategy: Try Google TTS (high quality). If fails, fallback to Piper (offline).
        If both fail, return silence.
        """
        
        # Try primary: Google Cloud TTS
        if self.google_tts:
            try:
                audio = await self._google_tts_synthesize(text)
                return Audio(
                    path=audio.path,
                    duration_ms=audio.duration_ms,
                    provider="google_tts"
                )
            except Exception as e:
                print(f"Google TTS failed: {e}. Trying Piper...")
        
        # Fallback 1: Piper (local, offline)
        if self.piper_tts:
            try:
                audio = await self._piper_synthesize(text)
                return Audio(
                    path=audio.path,
                    duration_ms=audio.duration_ms,
                    provider="piper"
                )
            except Exception as e:
                print(f"Piper failed: {e}. Using silence...")
        
        # Fallback 2: Silence (always works)
        audio = await self._silence_fallback(estimated_duration_ms=len(text) * 80)
        return Audio(
            path=audio.path,
            duration_ms=audio.duration_ms,
            provider="silence"
        )
    
    async def _google_tts_synthesize(self, text: str) -> Audio:
        """Synthesize with Google Cloud TTS."""
        request = texttospeech.SynthesizeSpeechRequest(
            input={"text": text},
            voice={"language_code": "en-US", "name": "en-US-Neural2-A"},
            audio_config={"audio_encoding": "LINEAR16", "sample_rate": 16000}
        )
        response = await asyncio.to_thread(
            self.google_tts.synthesize_speech, request
        )
        path = "/tmp/audio_google.wav"
        with open(path, "wb") as f:
            f.write(response.audio_content)
        return Audio(path=path, duration_ms=len(response.audio_content) // 32)  # 16kHz, 16-bit
    
    async def _piper_synthesize(self, text: str) -> Audio:
        """Synthesize with Piper (offline)."""
        path = "/tmp/audio_piper.wav"
        await asyncio.to_thread(
            self.piper_tts.synthesize, text, output_path=path
        )
        duration_ms = self._get_wav_duration(path) * 1000
        return Audio(path=path, duration_ms=int(duration_ms))
    
    async def _silence_fallback(self, estimated_duration_ms: int) -> Audio:
        """Generate silence (always works)."""
        import soundfile as sf
        duration_sec = estimated_duration_ms / 1000.0
        samples = np.zeros(int(16000 * duration_sec))
        path = "/tmp/audio_silence.wav"
        sf.write(path, samples, 16000)
        return Audio(path=path, duration_ms=estimated_duration_ms)
```

**Key Concepts:**
- Fallback chain: Primary → Secondary → Always-Works
- Every step is logged (which provider was used)
- No hard failures (silence is always available)
- Testable (mock Google TTS API, verify Piper fallback works)

---

## Section 3: Quality Gating (Deterministic Scoring + Hard Enforcement)

### 3.1 Quality Scorer (5 Components)

```python
# src/quality_scorer.py
from dataclasses import dataclass

@dataclass
class QualityBreakdown:
    visual_clarity: int  # 0-20
    audio_quality: int  # 0-20
    narrative_flow: int  # 0-20
    accessibility: int  # 0-20
    technical_specs: int  # 0-20
    
    @property
    def total(self) -> int:
        return (self.visual_clarity + self.audio_quality +
                self.narrative_flow + self.accessibility +
                self.technical_specs)

class QualityValidator:
    """Deterministic 5-component quality scorer."""
    
    name = "quality_validator"
    
    def __init__(self, design_system: DesignSystem):
        self.design_system = design_system
    
    async def execute(self, video_path: str, storyboard: Storyboard) -> QualityBreakdown:
        """Score video on 5 components."""
        
        # 1. Visual clarity (text readability + contrast)
        visual = await self._score_visual(video_path)
        
        # 2. Audio quality (volume normalization, clipping detection)
        audio = await self._score_audio(video_path)
        
        # 3. Narrative flow (pacing matches visuals)
        narrative = await self._score_narrative(video_path, storyboard)
        
        # 4. Accessibility (captions present, audio descriptions)
        accessibility = await self._score_accessibility(video_path)
        
        # 5. Technical specs (codec, bitrate, frame rate)
        technical = await self._score_technical(video_path)
        
        return QualityBreakdown(
            visual_clarity=visual,
            audio_quality=audio,
            narrative_flow=narrative,
            accessibility=accessibility,
            technical_specs=technical
        )
    
    async def _score_visual(self, video_path: str) -> int:
        """Check: text contrast ≥ 4.5:1 (WCAG AA)."""
        score = 20  # Start at max
        
        # Sample frames, extract text, check contrast
        frames = await self._sample_frames(video_path, n_samples=5)
        for frame in frames:
            contrast = self._measure_contrast(frame)
            if contrast < 4.5:
                score = max(0, score - 4)  # Penalize per low-contrast frame
        
        return score
    
    async def _score_audio(self, video_path: str) -> int:
        """Check: no clipping, loudness -23 LUFS (YouTube standard)."""
        score = 20
        
        # Extract audio, measure loudness
        audio_path = await self._extract_audio(video_path)
        loudness = self._measure_loudness(audio_path)  # LUFS
        
        # YouTube standard: -23 ± 3 LUFS
        if loudness < -26 or loudness > -20:
            score = max(0, score - 5)
        
        # Check for clipping (peak level)
        if self._has_clipping(audio_path):
            score = max(0, score - 10)
        
        return score
    
    async def _score_narrative(self, video_path: str, storyboard: Storyboard) -> int:
        """Check: pacing matches (transition timing ± 10%)."""
        score = 20
        
        # For each transition in storyboard, verify timing is ±10% of target
        for i, scene in enumerate(storyboard.scenes[:-1]):
            actual_duration = await self._measure_scene_duration(video_path, i)
            expected_duration = scene.expected_duration_ms
            
            if abs(actual_duration - expected_duration) / expected_duration > 0.1:
                score = max(0, score - 2)  # Penalize per scene drift
        
        return score
    
    async def _score_accessibility(self, video_path: str) -> int:
        """Check: captions present, audio descriptions (if needed)."""
        score = 20
        
        # Check for subtitle track
        has_captions = await self._has_captions(video_path)
        if not has_captions:
            score -= 10
        
        # Check for audio description track (optional, but bonus)
        has_audio_desc = await self._has_audio_description(video_path)
        if has_audio_desc:
            score = min(20, score + 2)
        
        return score
    
    async def _score_technical(self, video_path: str) -> int:
        """Check: H.264 codec, 2-6 Mbps bitrate, 30 fps."""
        score = 20
        
        metadata = await self._get_video_metadata(video_path)
        
        # Codec
        if metadata['codec'] != 'h264':
            score -= 10
        
        # Bitrate (YouTube recommends 2-6 Mbps for 1080p)
        bitrate_mbps = metadata['bitrate'] / 1_000_000
        if not (2 <= bitrate_mbps <= 6):
            score -= 5
        
        # Frame rate
        if metadata['fps'] < 24:
            score -= 5
        
        return score
```

**Key Concepts:**
- 5 independent components (each 0-20 points = 0-100 total)
- Each component is deterministic (no LLM, no subjective judgement)
- Every check is logged (why score was 85, not 87)
- Score never fails (always returns 0-100)

### 3.2 Quality Gates (Hard Enforcement)

```python
# src/quality_gates.py
from enum import Enum

class QualityGate(Enum):
    DRAFT = "draft"  # 0-50 points
    PRODUCTION = "production"  # 50-85 points
    BROADCAST = "broadcast"  # 85-100 points

class QualityGateEnforcer:
    """Hard enforcement of quality gates (no bypass)."""
    
    @staticmethod
    def enforce(score: int) -> QualityGate:
        """Determine gate from score.
        
        HARD RULES:
        - score < 50  → DRAFT (must iterate)
        - 50 ≤ score < 85 → PRODUCTION (auto-queue or manual edit)
        - score ≥ 85 → BROADCAST (requires human approval)
        
        No env var override. No skip flag.
        """
        if score < 50:
            return QualityGate.DRAFT
        elif score < 85:
            return QualityGate.PRODUCTION
        else:
            return QualityGate.BROADCAST
```

**Key Concepts:**
- No configuration, no flags
- Gate threshold is hardcoded in code (not in config file)
- To change gates, update code + add ADR + review

---

## Section 4: Adding Your Own Worker

### How to Add a New Worker (Example: TranscriptGenerator)

**Goal:** Add a new worker that generates SRT subtitles from video + audio.

**Step 1: Define Worker Input/Output**

```python
# src/workers/transcript_generator.py
from dataclasses import dataclass
from typing import List

@dataclass
class Subtitle:
    start_ms: int
    end_ms: int
    text: str

class TranscriptGeneratorWorker:
    """Generate SRT subtitles from audio."""
    
    name = "transcript_generator"
```

**Step 2: Implement Worker Contract**

```python
async def execute(self, audio_path: str, video_path: str) -> List[Subtitle]:
    """Generate subtitles from audio.
    
    Args:
        audio_path: Path to WAV file
        video_path: Path to MP4 (for timing reference)
    
    Returns:
        List of Subtitle(start_ms, end_ms, text)
    
    Raises:
        WorkerError if audio transcription fails
    """
    try:
        # Use Google Cloud Speech-to-Text (or open-source alternative)
        subtitles = await self._transcribe(audio_path)
        
        # Verify subtitles don't exceed safe character rates (60 cpm)
        for sub in subtitles:
            cpm = len(sub.text) / ((sub.end_ms - sub.start_ms) / 1000 / 60)
            if cpm > 60:
                sub.text = await self._shorten(sub.text)
        
        return subtitles
    
    except ImportError as e:
        raise WorkerError(
            code="transcription_unavailable",
            message=f"Speech-to-Text unavailable: {e}",
            can_retry=False,
            fallback_worker="transcript_generator_manual"  # User provides SRT
        )
```

**Step 3: Register in Plugin**

```python
# src/plugin.py (in bootstrap method)
self.transcript_generator = TranscriptGeneratorWorker()

# Add to orchestrator
self.orchestrator.add_worker(self.transcript_generator)
```

**Step 4: Add to Orchestrator**

```python
# src/orchestrator.py
@skill_method
async def generate_with_subtitles(self, ...):
    """Generate video + subtitles."""
    
    # ... existing steps (slides, audio, video assembly)
    
    # 5. Generate subtitles (new worker!)
    subtitles = await self.transcript_generator.execute(
        audio_path=audio.path,
        video_path=video_draft.path
    )
    await self._audit_event("subtitles_generated", {
        "subtitle_count": len(subtitles)
    })
    
    # 6. Embed subtitles into video
    video_with_subs = await self.video_asm.embed_subtitles(video_draft, subtitles)
    
    # 7. Re-validate quality (subtitles affect accessibility score)
    quality = await self.quality_val.execute(video_with_subs, storyboard)
    
    # ... gates, etc.
```

**Step 5: Test**

```python
# tests/test_transcript_generator.py
import pytest

@pytest.mark.asyncio
async def test_transcribe_simple_audio():
    """Test basic transcription."""
    worker = TranscriptGeneratorWorker()
    
    subtitles = await worker.execute(
        "tests/fixtures/simple_narration.wav",
        "tests/fixtures/video.mp4"
    )
    
    assert len(subtitles) > 0
    assert subtitles[0].start_ms == 0
    assert "CorvinOS" in subtitles[0].text

@pytest.mark.asyncio
async def test_fallback_to_manual():
    """Test fallback if transcription fails."""
    worker = TranscriptGeneratorWorker()
    
    # Mock: transcription API unavailable
    with pytest.raises(WorkerError) as exc_info:
        await worker.execute(
            "tests/fixtures/audio.wav",
            "tests/fixtures/video.mp4"
        )
    
    assert exc_info.value.fallback_worker == "transcript_generator_manual"
```

---

## Section 5: Learning Loop Integration (ADR-0314)

### How to Wire Your Plugin into the Learning Loop

Every worker's output should feed into the learning loop:

```python
# src/orchestrator.py
@skill_method
async def generate(self, topic: str, duration: str, script: Optional[str] = None) -> VideoJob:
    """Generate video with learning loop integration."""
    
    job = VideoJob(topic=topic, duration=duration)
    
    # ... existing generation steps ...
    
    # Emit learning event
    await self._emit_learning_event(
        event_type="outcome_feedback",
        payload={
            "video_id": job.id,
            "quality_score": job.quality_score,
            "quality_breakdown": {
                "visual": job.quality_breakdown.visual_clarity,
                "audio": job.quality_breakdown.audio_quality,
                "narrative": job.quality_breakdown.narrative_flow,
                "accessibility": job.quality_breakdown.accessibility,
                "technical": job.quality_breakdown.technical_specs
            },
            "generation_time_ms": job.generation_time_ms,
            "worker_latencies": {
                "slide_generator": job.latencies['slide_gen'],
                "audio_generator": job.latencies['audio_gen'],
                "video_assembler": job.latencies['video_asm'],
                "quality_validator": job.latencies['quality_val']
            }
        }
    )
    
    return job

async def _emit_learning_event(self, event_type: str, payload: Dict):
    """Emit to learning infrastructure."""
    from corvin_learning import event_store
    
    await event_store.write_event(
        event_type=event_type,
        skill_id=self.skill_id,
        payload=payload,
        tenant_id=self.tenant_id
    )
```

**Then, users provide feedback:**

```python
# User rates video (via console API)
# POST /api/video/{video_id}/rate
# {"rating": 5, "feedback": "Great tutorial!"}

# This triggers:
await event_store.write_event(
    event_type="user_feedback",
    payload={
        "video_id": video_id,
        "rating": 5,
        "feedback_text": "Great tutorial!"
    }
)

# Learning daemon (daily) reads both events:
# - Original: quality_score = 87
# - Feedback: rating = 5 stars
# Conclusion: videos with score ≥87 are well-received
# Next: Lower gate threshold from 85 → 82 (confidence 0.85)

# This becomes an audit event:
await audit.write_event({
    "event_type": "quality_gate_adjusted",
    "plugin_id": "video-producer",
    "adjustment": "threshold 85 → 82",
    "reason": "user_feedback_correlation (87 → 5 stars)",
    "confidence": 0.85
})
```

---

## Section 6: Best Practices for Plugin Development

### 1. Error Handling is Mandatory
- Every worker raises `WorkerError` (never unhandled exceptions)
- Every error includes fallback info
- Test both happy path + error paths

### 2. Audit Trail is Non-Negotiable
- Emit audit event for every decision
- Include: what was decided, why, when, by whom
- Audit trail is immutable (append-only)

### 3. Design System is Code
- Never hardcode colors, fonts, dimensions
- Load from design_system.json at startup
- Version design_system.json with the plugin

### 4. Quality Gates are Hard
- No env vars, no flags, no overrides
- Gate logic is hardcoded in code
- To change gates: update code → PR review → ADR → merge

### 5. Testing is Required
- Unit tests for each worker (mock dependencies)
- Integration tests for orchestrator (real workers, mock APIs)
- E2E tests for full pipeline (end-to-end, verify output)
- Target: ≥85% code coverage

### 6. Learning Loop Feedback
- Every major decision gets a learning event
- Include: input, output, latency, quality score
- User feedback loops back to optimizer

---

## Next Steps

1. ✅ Read `/docs/1_IDEA_DIALECTICAL.md` (master plan)
2. ✅ Read `/docs/3_ADRS_0851_0859.md` (9 design decisions)
3. ✅ Study `src/orchestrator.py` (main Skill logic)
4. ✅ Study `src/workers/` (4 worker examples)
5. ✅ Run `pytest tests/ -v` (see tests pass)
6. ✅ Add your own worker (follow "Section 4" above)
7. ✅ Submit PR with new worker + tests + audit events

---

**Status: READY FOR YOUR FIRST PLUGIN EXTENSION**
