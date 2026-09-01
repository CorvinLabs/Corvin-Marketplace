# Wheel Content Inspector

## Overview

The Wheel Content Inspector analyzes Python wheel (.whl) distributions to extract metadata, validate integrity, detect security risks, and audit dependencies. It enables plugin vendors to verify package contents before distribution.

## Use Case

**Scenario:** A plugin maintainer uploads a new wheel to the marketplace. The inspector verifies: no hardcoded credentials, no suspicious symlinks, all dependencies declared, and signatures valid. Only then is the wheel indexed.

**Impact:** Prevents malicious wheel uploads; ensures supply-chain security (SLSA L2+).

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    Wheel Content Inspection Pipeline
  </text>
  
  <!-- Input Wheel -->
  <rect x="50" y="70" width="120" height="80" fill="#E3F2FD" stroke="#1976D2" stroke-width="2" rx="5"/>
  <text x="110" y="100" font-size="12" font-weight="bold" text-anchor="middle">Wheel File</text>
  <text x="110" y="120" font-size="10" text-anchor="middle">(.whl)</text>
  <text x="110" y="140" font-size="10" text-anchor="middle">Distribution</text>
  
  <!-- Extraction -->
  <rect x="210" y="70" width="120" height="80" fill="#F3E5F5" stroke="#7B1FA2" stroke-width="2" rx="5"/>
  <text x="270" y="100" font-size="12" font-weight="bold" text-anchor="middle">Extraction</text>
  <text x="270" y="120" font-size="10" text-anchor="middle">Unzip</text>
  <text x="270" y="140" font-size="10" text-anchor="middle">Parse</text>
  
  <!-- Analysis -->
  <rect x="370" y="70" width="120" height="80" fill="#FCE4EC" stroke="#C2185B" stroke-width="2" rx="5"/>
  <text x="430" y="100" font-size="12" font-weight="bold" text-anchor="middle">Analysis</text>
  <text x="430" y="120" font-size="10" text-anchor="middle">Scan</text>
  <text x="430" y="140" font-size="10" text-anchor="middle">Validate</text>
  
  <!-- Arrows -->
  <path d="M 170 110 L 210 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 330 110 L 370 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Inspection Checks -->
  <rect x="50" y="200" width="550" height="140" fill="#FFF9C4" stroke="#F57F17" stroke-width="2" rx="5" stroke-dasharray="5,5"/>
  <text x="325" y="225" font-size="14" font-weight="bold" text-anchor="middle">Inspection Checks</text>
  
  <!-- Checks list -->
  <text x="70" y="255" font-size="12" font-weight="bold">Metadata Extraction:</text>
  <text x="70" y="275" font-size="11">Name, version, author, dependencies from METADATA</text>
  
  <text x="350" y="255" font-size="12" font-weight="bold">Integrity Validation:</text>
  <text x="350" y="275" font-size="11">SHA256 checksums, file count, structure</text>
  
  <text x="70" y="305" font-size="12" font-weight="bold">Security Scanning:</text>
  <text x="70" y="325" font-size="11">No credentials, symlinks, unusual permissions</text>
  
  <text x="350" y="305" font-size="12" font-weight="bold">Dependency Audit:</text>
  <text x="350" y="325" font-size="11">Declared vs included, SBOM generation</text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## API Example

```python
from wheel_content_inspector import WheelContentInspector

inspector = WheelContentInspector()
await inspector.initialize(context)

wheel_path = "/tmp/my_plugin-1.0.0-py3-none-any.whl"

# Inspect wheel (NOT YET IMPLEMENTED)
report = await inspector.execute(
    wheel_path=wheel_path,
    extract_metadata=True,
    validate_integrity=True,
    security_scan=True,
    list_contents=True
)

# Expected output:
# {
#     "metadata": {
#         "name": "my_plugin",
#         "version": "1.0.0",
#         "author": "developer@example.com",
#         "dependencies": ["requests>=2.28.0"]
#     },
#     "integrity": {
#         "valid": True,
#         "checksum": "sha256:abc123...",
#         "file_count": 42
#     },
#     "security": {
#         "risk_level": "LOW",
#         "findings": [],
#         "credentials_detected": False,
#         "symlinks_detected": False
#     },
#     "contents": [
#         "my_plugin/__init__.py",
#         "my_plugin/plugin.py",
#         "my_plugin-1.0.0.dist-info/METADATA",
#         ...
#     ]
# }
```

## Configuration

No configuration required. Runs with security defaults.

## Status

**Implementation:** Stub (Phase 1 ready)
**Tests:** 5 unit tests (inspection, metadata, validation, error handling)
**Compliance:** SLSA L2+ | SBOM (SPDX) generation support

---
**Plugin ID:** `plugin:buildin-data_processing-wheel_content_inspector`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
