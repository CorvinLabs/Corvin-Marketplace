# PII Detector

## Overview

The PII Detector identifies personally identifiable information (email, phone, SSN, addresses, credit cards) in text using pattern matching and ML-based models. It's fail-closed: any PII-shaped pattern is reported, never suppressed.

## Use Case

**Scenario:** An operator sharing a chat log with a colleague accidentally includes a customer's email and phone number. The PII Detector flags both before sending, suggesting redaction masks.

**Impact:** Prevents accidental PII leakage; ensures GDPR Art. 6, 7 (consent) and Art. 32 (security) compliance.

## Architecture

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg">
  <text x="300" y="30" font-size="24" font-weight="bold" text-anchor="middle">
    PII Detection Framework (ADR-0297)
  </text>
  
  <!-- Input Text -->
  <rect x="50" y="70" width="130" height="80" fill="#FFEBEE" stroke="#D32F2F" stroke-width="2" rx="5"/>
  <text x="115" y="100" font-size="13" font-weight="bold" text-anchor="middle">Input Text</text>
  <text x="115" y="120" font-size="11" text-anchor="middle">User content</text>
  <text x="115" y="140" font-size="11" text-anchor="middle">Logs, messages</text>
  
  <!-- Pattern Scanner -->
  <rect x="230" y="70" width="130" height="80" fill="#F3E5F5" stroke="#7B1FA2" stroke-width="2" rx="5"/>
  <text x="295" y="100" font-size="13" font-weight="bold" text-anchor="middle">Scanner</text>
  <text x="295" y="120" font-size="11" text-anchor="middle">Regex patterns</text>
  <text x="295" y="140" font-size="11" text-anchor="middle">ML models</text>
  
  <!-- Output Findings -->
  <rect x="410" y="70" width="130" height="80" fill="#E8F5E9" stroke="#388E3C" stroke-width="2" rx="5"/>
  <text x="475" y="100" font-size="13" font-weight="bold" text-anchor="middle">Findings</text>
  <text x="475" y="120" font-size="11" text-anchor="middle">PII locations</text>
  <text x="475" y="140" font-size="11" text-anchor="middle">Risk score</text>
  
  <!-- Arrows -->
  <path d="M 180 110 L 230 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  <path d="M 360 110 L 410 110" stroke="#333" stroke-width="2" fill="none" marker-end="url(#arrowhead)"/>
  
  <!-- Detectable PII Types -->
  <rect x="50" y="200" width="550" height="140" fill="#FCE4EC" stroke="#C2185B" stroke-width="2" rx="5" stroke-dasharray="5,5"/>
  <text x="325" y="225" font-size="14" font-weight="bold" text-anchor="middle">Detectable PII Types (Fail-Closed)</text>
  
  <!-- Types -->
  <text x="70" y="255" font-size="12" font-weight="bold">Emails:</text>
  <text x="70" y="275" font-size="11">user@domain.com, name@company.org</text>
  
  <text x="350" y="255" font-size="12" font-weight="bold">Phones:</text>
  <text x="350" y="275" font-size="11">+1-800-555-0123, (555) 0123</text>
  
  <text x="70" y="305" font-size="12" font-weight="bold">IDs:</text>
  <text x="70" y="325" font-size="11">SSN (***-**-6789), Credit cards</text>
  
  <text x="350" y="305" font-size="12" font-weight="bold">Addresses:</text>
  <text x="350" y="325" font-size="11">Street address, ZIP codes (partial)</text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## API Example

```python
from pii_detector import PIIDetector

detector = PIIDetector()
await detector.initialize(context)

text = """
Contact John Doe at john.doe@example.com or +1-800-555-0123.
My SSN is 123-45-6789. Address: 456 Oak Ave, Springfield, IL 62701.
"""

# Scan for PII (NOT YET IMPLEMENTED)
findings = await detector.execute(
    text=text,
    pii_type="all"  # all, email, phone, ssn, address
)

# Expected output:
# {
#     "findings": [
#         {
#             "type": "email",
#             "value": "john.doe@example.com",
#             "position": (28, 48),
#             "confidence": 0.99,
#             "risk_score": 0.95
#         },
#         {
#             "type": "phone",
#             "value": "+1-800-555-0123",
#             "position": (52, 67),
#             "confidence": 0.98,
#             "risk_score": 0.90
#         },
#         {
#             "type": "ssn",
#             "value": "123-45-6789",
#             "position": (85, 96),
#             "confidence": 0.99,
#             "risk_score": 0.99
#         }
#     ],
#     "overall_risk": 0.95,
#     "recommendation": "BLOCK_TRANSMISSION"
# }
```

## Configuration

No configuration required. Uses ADR-0297 defaults (fail-closed).

## Status

**Implementation:** Stub (Phase 1 ready)
**Tests:** 6 unit tests (email, phone, SSN, address, batch, error handling)
**Compliance:** GDPR Art. 6, 7, 32 | ADR-0297 (PII Detection Framework)

---
**Plugin ID:** `plugin:buildin-data_processing-pii_detector`  
**Version:** 1.0.0 | **Boot Layer:** bundled  
**Maintainer:** plugins@anthropic.com
