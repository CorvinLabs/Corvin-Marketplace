# Data Classification

## Overview

The Data Classification plugin assigns sensitivity levels (public, internal, confidential, restricted) to data based on content analysis. It integrates with L34 (Data Classification Layer) to enforce access controls and audit requirements.

## Use Case

**Scenario:** A financial analyst shares a quarterly earnings report. The plugin auto-classifies it as "confidential," triggering: audit logging, restricted distribution, watermarking, and automatic TTL (delete after 90 days).

**Impact:** Ensures data governance without manual tagging; enforces GDPR Art. 32 security requirements.

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    Data Classification Pipeline
  </text>
  
  <!-- Input -->
  <rect x="50" y="70" width="130" height="80" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="115" y="100" font-size="13" font-weight="bold" text-anchor="middle">Input Data</text>
  <text x="115" y="120" font-size="11" text-anchor="middle">Content</text>
  <text x="115" y="140" font-size="11" text-anchor="middle">Metadata</text>
  
  <!-- Analyzer -->
  <rect x="230" y="70" width="130" height="80" fill="#F3E5F5" stroke="#7B1FA2" stroke-width="2" rx="5"/>
  <text x="295" y="100" font-size="13" font-weight="bold" text-anchor="middle">Classifier</text>
  <text x="295" y="120" font-size="11" text-anchor="middle">Keywords</text>
  <text x="295" y="140" font-size="11" text-anchor="middle">Patterns</text>
  
  <!-- Output -->
  <rect x="410" y="70" width="130" height="80" fill="#E8F5E9" stroke="#388E3C" stroke-width="2" rx="5"/>
  <text x="475" y="100" font-size="13" font-weight="bold" text-anchor="middle">Classification</text>
  <text x="475" y="120" font-size="11" text-anchor="middle">Level</text>
  <text x="475" y="140" font-size="11" text-anchor="middle">Controls</text>
  
  <!-- Arrows -->
  <path d="M 180 110 L 230 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 360 110 L 410 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Sensitivity Levels -->
  <rect x="50" y="200" width="550" height="140" fill="#FFF9C4" stroke="#F57F17" stroke-width="2" rx="5" stroke-dasharray="5,5"/>
  <text x="325" y="225" font-size="14" font-weight="bold" text-anchor="middle">Sensitivity Levels (ADR-0329)</text>
  
  <!-- Levels -->
  <text x="70" y="255" font-size="12" font-weight="bold">PUBLIC</text>
  <text x="70" y="275" font-size="11">Open to all users, no restrictions</text>
  
  <text x="350" y="255" font-size="12" font-weight="bold">INTERNAL</text>
  <text x="350" y="275" font-size="11">Company only, audit logged</text>
  
  <text x="70" y="305" font-size="12" font-weight="bold">CONFIDENTIAL</text>
  <text x="70" y="325" font-size="11">Need-to-know, watermarked, TTL 90d</text>
  
  <text x="350" y="305" font-size="12" font-weight="bold">RESTRICTED</text>
  <text x="350" y="325" font-size="11">C-suite only, encrypted, audit trail</text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## API Example

```python
from data_classification import DataClassification

classifier = DataClassification()
await classifier.initialize(context)

data = {
    "content": "Q3 2026 earnings: $2.3B revenue, 18% YoY growth. Confidential until press release.",
    "type": "financial_report"
}

# Classify data (NOT YET IMPLEMENTED)
classification = await classifier.execute(
    data=data,
    classify_sensitivity=True
)

# Expected output:
# {
#     "sensitivity_level": "CONFIDENTIAL",
#     "score": 0.95,
#     "keywords_detected": ["earnings", "revenue", "confidential"],
#     "recommended_controls": [
#         "restrict_distribution",
#         "watermark",
#         "audit_log",
#         "ttl_90_days"
#     ],
#     "category": "financial_data"
# }
```

## Configuration

No configuration required. Uses L34 default rules (ADR-0335).

## Status

**Implementation:** Stub (Phase 1 ready)
**Tests:** 5 unit tests (classification, validation, batch processing)
**Compliance:** GDPR Art. 32 | EU AI Act Art. 12, 13, 14 (ADR-0329, ADR-0335)

---
**Plugin ID:** `plugin:buildin-data_processing-data_classification`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
