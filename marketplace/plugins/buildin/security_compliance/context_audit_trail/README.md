# Context Audit Trail

Detailed audit trail for context engineering (preservation, truncation, re-injection)

## Features

- Hash-chained audit logging
- Consent enforcement
- Data flow guard
- Filesystem write protection

## Installation

```bash
pip install corvin-plugin-security_compliance_context_audit_trail
```

## Usage

```python
from corvin_plugins import Security_ComplianceContext_Audit_Trail

plugin = Security_ComplianceContext_Audit_Trail()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-security_compliance-context_audit_trail
```

## Testing

```bash
pytest tests/plugins/test_security_compliance_context_audit_trail.py -v
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