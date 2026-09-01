# STT Provider

## Overview

The STT Provider plugin manages speech-to-text provider registration and lifecycle. It allows custom STT engines (Whisper, Google Cloud Speech, etc.) to register as the active provider while maintaining thread-safe access and GDPR Art. 5 compliance (metadata-only audit).

## Use Case

**Scenario:** A user switches from Whisper (running locally) to Google Cloud STT for better accuracy. The STT Provider safely swaps providers mid-session without dropping active transcription.

**Impact:** Enables STT engine swapping; maintains provider isolation and audit compliance.

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    STT Provider Registry (L23 Compliance)
  </text>
  
  <!-- Provider A -->
  <rect x="50" y="70" width="120" height="80" fill="#E0F2F1" stroke="#00897B" stroke-width="2" rx="5"/>
  <text x="110" y="95" font-size="12" font-weight="bold" text-anchor="middle">Provider A</text>
  <text x="110" y="115" font-size="10" text-anchor="middle">(e.g. Whisper)</text>
  <text x="110" y="130" font-size="10" text-anchor="middle">Registered</text>
  
  <!-- Registry Hub -->
  <rect x="220" y="70" width="160" height="80" fill="#FCE4EC" stroke="#C2185B" stroke-width="2" rx="5"/>
  <text x="300" y="95" font-size="13" font-weight="bold" text-anchor="middle">STT Registry</text>
  <text x="300" y="115" font-size="10" text-anchor="middle">Thread-safe</text>
  <text x="300" y="130" font-size="10" text-anchor="middle">Active tracking</text>
  
  <!-- Provider B -->
  <rect x="430" y="70" width="120" height="80" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="490" y="95" font-size="12" font-weight="bold" text-anchor="middle">Provider B</text>
  <text x="490" y="115" font-size="10" text-anchor="middle">(e.g. Google)</text>
  <text x="490" y="130" font-size="10" text-anchor="middle">Registered</text>
  
  <!-- Arrows to registry -->
  <path d="M 170 110 L 220 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 380 110 L 430 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Registry Operations -->
  <rect x="50" y="200" width="550" height="140" fill="#FFF3E0" stroke="#E65100" stroke-width="2" rx="5" stroke-dasharray="5,5"/>
  <text x="325" y="225" font-size="14" font-weight="bold" text-anchor="middle">Thread-Safe Operations</text>
  
  <!-- Operations -->
  <text x="70" y="255" font-size="12" font-weight="bold">set_active(plugin_id, provider)</text>
  <text x="70" y="275" font-size="11">Register or switch active provider</text>
  
  <text x="350" y="255" font-size="12" font-weight="bold">get_active(plugin_id)</text>
  <text x="350" y="275" font-size="11">Retrieve current active provider</text>
  
  <text x="70" y="305" font-size="12" font-weight="bold">release_owned_by(plugin_id)</text>
  <text x="70" y="325" font-size="11">Release provider on plugin shutdown</text>
  
  <!-- Compliance note -->
  <text x="325" y="360" font-size="11" text-anchor="middle" fill="#D32F2F">
    GDPR Art. 5 (Data Minimization) | L23: Metadata-only audit (never transcript text)
  </text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## API Example

```python
from stt_provider import STTProviderRegistry, STTProvider

class MyCustomSTTProvider(STTProvider):
    def __init__(self):
        self.id = "custom_stt_1"
    
    async def transcribe(self, audio_bytes):
        # Actual transcription logic
        return "transcribed text"

# Use the registry
registry = STTProviderRegistry()

# Register custom provider
provider = MyCustomSTTProvider()
registry.set_active("plugin_voice", provider)

# Retrieve active provider
active = registry.get_active("plugin_voice")
transcription = await active.transcribe(audio_bytes)

# Release on shutdown
registry.release_owned_by("plugin_voice")
```

## Configuration

No configuration required. Thread-safe by design.

## Status

**Implementation:** Complete (Production-ready)
**Tests:** 7 unit tests (registration, thread-safety, ownership tracking)
**Compliance:** GDPR Art. 5 | L23 (STT Layer) | ADR-0033

---
**Plugin ID:** `plugin:buildin-data_processing-stt_provider`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
