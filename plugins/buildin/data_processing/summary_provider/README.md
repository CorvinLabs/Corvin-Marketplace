# Summary Provider

## Overview

The Summary Provider plugin manages text summarization providers (default: Claude CLI wrapper). It allows custom summarization backends to register while maintaining a thread-safe registry and graceful fallback to truncation if summarization fails.

## Use Case

**Scenario:** A long conversation needs to be summarized for the session audit trail. The Summary Provider delegates to Claude CLI, which generates a 200-token executive summary. If that fails, it falls back to smart truncation.

**Impact:** Reduces audit trail verbosity; enables custom summarization strategies.

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    Summary Provider Architecture (L11 Compliance)
  </text>
  
  <!-- Input Text -->
  <rect x="50" y="70" width="120" height="80" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="110" y="100" font-size="12" font-weight="bold" text-anchor="middle">Long Text</text>
  <text x="110" y="120" font-size="10" text-anchor="middle">Session</text>
  <text x="110" y="135" font-size="10" text-anchor="middle">History</text>
  
  <!-- Registry -->
  <rect x="220" y="70" width="160" height="80" fill="#F3E5F5" stroke="#7B1FA2" stroke-width="2" rx="5"/>
  <text x="300" y="100" font-size="12" font-weight="bold" text-anchor="middle">Provider</text>
  <text x="300" y="120" font-size="10" text-anchor="middle">Registry &</text>
  <text x="300" y="135" font-size="10" text-anchor="middle">Selection</text>
  
  <!-- Output Summary -->
  <rect x="430" y="70" width="120" height="80" fill="#E8F5E9" stroke="#388E3C" stroke-width="2" rx="5"/>
  <text x="490" y="100" font-size="12" font-weight="bold" text-anchor="middle">Summary</text>
  <text x="490" y="120" font-size="10" text-anchor="middle">Concise</text>
  <text x="490" y="135" font-size="10" text-anchor="middle">Audit-ready</text>
  
  <!-- Arrows -->
  <path d="M 170 110 L 220 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 380 110 L 430 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Fallback Chain -->
  <rect x="50" y="200" width="550" height="140" fill="#FFF9C4" stroke="#F57F17" stroke-width="2" rx="5" stroke-dasharray="5,5"/>
  <text x="325" y="225" font-size="14" font-weight="bold" text-anchor="middle">Provider Selection & Fallback Chain</text>
  
  <!-- Chain steps -->
  <text x="70" y="255" font-size="12" font-weight="bold">1. Try Custom Provider</text>
  <text x="70" y="275" font-size="11">Plugin-registered implementation</text>
  
  <text x="350" y="255" font-size="12" font-weight="bold">2. Try Default (Claude CLI)</text>
  <text x="350" y="275" font-size="11">operator/voice/scripts/summarize.py</text>
  
  <text x="70" y="305" font-size="12" font-weight="bold">3. Fallback: Smart Truncation</text>
  <text x="70" y="325" font-size="11">Keep first N tokens, preserve structure</text>
  
  <!-- Compliance note -->
  <text x="325" y="360" font-size="11" text-anchor="middle" fill="#D32F2F">
    L11 Compliance (Delegation) | ADR-0033 (Provider Abstractions)
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
from summary_provider import SummaryProviderRegistry, ClaudeCliSummaryProvider

registry = SummaryProviderRegistry()

# Option 1: Use default provider
default_provider = ClaudeCliSummaryProvider()
registry.set_active("plugin_audit", default_provider)

# Option 2: Register custom provider
class MyCustomSummarizer:
    async def summarize(self, text, max_length=200):
        # Custom summarization logic
        return "Custom summary"

custom = MyCustomSummarizer()
registry.set_active("plugin_audit", custom)

# Get active and summarize
active = registry.get_active("plugin_audit")
summary = await active.summarize(long_text, max_length=200)

# Output:
# "Custom summary"
#
# Or falls back to truncation if provider fails
```

## Configuration

No configuration required. Default provider included.

## Status

**Implementation:** Complete (Production-ready)
**Tests:** 6 unit tests (registration, summarization, fallback, error handling)
**Compliance:** L11 (Delegation) | ADR-0033 (Provider Abstractions)

---
**Plugin ID:** `plugin:buildin-data_processing-summary_provider`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
