# Vibe Decision Audit

Audit trail for Vibe session decisions, routing, and state changes

## Features

- Hash-chained audit logging
- Consent enforcement
- Data flow guard
- Filesystem write protection

## Installation

```bash
pip install corvin-plugin-security_compliance_vibe_decision_audit
```

## Usage

```python
from corvin_plugins import Security_ComplianceVibe_Decision_Audit

plugin = Security_ComplianceVibe_Decision_Audit()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-security_compliance-vibe_decision_audit
```

## Testing

```bash
pytest tests/plugins/test_security_compliance_vibe_decision_audit.py -v
```

## Compliance

- L10/L16 security hardening
- GDPR Art. 30, 32 (audit trail, data integrity)
- Hash-chained immutable audit logging

## Related Plugins

See other plugins in the `security_compliance` category:

```bash
corvin plugin list --category security_compliance
```

## Support

Report issues or contribute: https://github.com/CorvinLabs/CorvinOS

## License

Apache-2.0 with CLA v3.1