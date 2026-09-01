# Context Snapshot Analyzer

## Overview

The Context Snapshot Analyzer monitors CorvinOS context depth, token usage, and memory allocation in real-time. It provides diagnostics to prevent context exhaustion and optimize performance across sessions.

## Use Case

**Scenario:** An operator running a long data-analysis session sees context growing dangerously close to the 128k-token limit. The analyzer alerts them proactively with diagnostics showing the top 3 context consumers (prior turns, artifact history, variable scope).

**Impact:** Prevents silent context drops; enables mid-session context optimization.

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    Context Snapshot Analysis
  </text>
  
  <!-- Monitoring -->
  <rect x="50" y="70" width="140" height="80" fill="#E0F2F1" stroke="#00897B" stroke-width="2" rx="5"/>
  <text x="120" y="100" font-size="13" font-weight="bold" text-anchor="middle">Monitoring</text>
  <text x="120" y="120" font-size="11" text-anchor="middle">Depth tracking</text>
  <text x="120" y="140" font-size="11" text-anchor="middle">Token count</text>
  
  <!-- Analysis -->
  <rect x="230" y="70" width="140" height="80" fill="#FCE4EC" stroke="#C2185B" stroke-width="2" rx="5"/>
  <text x="300" y="100" font-size="13" font-weight="bold" text-anchor="middle">Analysis</text>
  <text x="300" y="120" font-size="11" text-anchor="middle">Breakdown</text>
  <text x="300" y="140" font-size="11" text-anchor="middle">Metrics calc</text>
  
  <!-- Alerting -->
  <rect x="410" y="70" width="140" height="80" fill="#FFF3E0" stroke="#E65100" stroke-width="2" rx="5"/>
  <text x="480" y="100" font-size="13" font-weight="bold" text-anchor="middle">Diagnostics</text>
  <text x="480" y="120" font-size="11" text-anchor="middle">Alert</text>
  <text x="480" y="140" font-size="11" text-anchor="middle">Recommendations</text>
  
  <!-- Arrows -->
  <path d="M 190 110 L 230 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 370 110 L 410 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Metrics shown -->
  <rect x="50" y="200" width="550" height="140" fill="#F1F8E9" stroke="#558B2F" stroke-width="2" rx="5"/>
  <text x="325" y="225" font-size="14" font-weight="bold" text-anchor="middle">Tracked Metrics</text>
  
  <text x="70" y="255" font-size="12" font-weight="bold">Context Depth:</text>
  <text x="70" y="275" font-size="11">Current turns, max depth, % utilization</text>
  
  <text x="350" y="255" font-size="12" font-weight="bold">Token Usage:</text>
  <text x="350" y="275" font-size="11">Input tokens, output tokens, total used</text>
  
  <text x="70" y="305" font-size="12" font-weight="bold">Memory Pressure:</text>
  <text x="70" y="325" font-size="11">Artifact cache size, variable scope</text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## API Example

```python
from context_snapshot_analyzer import ContextSnapshotAnalyzer

analyzer = ContextSnapshotAnalyzer()
await analyzer.initialize(context)

snapshot = {
    "timestamp": "2026-09-01T12:00:00Z",
    "task_id": "task_123",
    "context_depth": 95,
    "max_depth": 128,
    "tokens_used": 45000,
    "tokens_available": 128000
}

# Analyze snapshot (NOT YET IMPLEMENTED)
diagnostics = await analyzer.execute(
    snapshot=snapshot,
    validate=True
)

# Expected output:
# {
#     "context_utilization": 74.2,
#     "token_utilization": 35.2,
#     "status": "healthy",
#     "warnings": [],
#     "recommendations": ["Consider archiving old turns"],
#     "top_consumers": [
#         {"name": "artifact_cache", "size": 12000},
#         {"name": "turn_history", "size": 8000}
#     ]
# }
```

## Configuration

No configuration required. Runs with adaptive thresholds.

## Status

**Implementation:** Partial (event handlers present)
**Tests:** 5 unit tests (analysis, validation, lifecycle)
**Compliance:** GDPR Art. 5 (data integrity), 32 (logging)

---
**Plugin ID:** `plugin:buildin-data_processing-context_snapshot_analyzer`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
