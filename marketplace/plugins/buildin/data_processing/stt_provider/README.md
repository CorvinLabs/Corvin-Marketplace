# Speech-to-Text Provider

Speech transcription with metadata-only audit. GDPR Art. 5 compliance.

## Features

- PII detection and masking
- Data classification engine
- Artifact extraction and processing
- Content inspection

## Installation

```bash
pip install corvin-plugin-data_processing_stt_provider
```

## Usage

```python
from corvin_plugins import Data_ProcessingStt_Provider

plugin = Data_ProcessingStt_Provider()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-data_processing-stt_provider
```

## Testing

```bash
pytest tests/plugins/test_data_processing_stt_provider.py -v
```

## Compliance

- L34/L36 data classification, PII detection, anonymization
- GDPR Art. 32 (data security)
- No PII in audit logs (scrubbed via `_assert_safe`)

## Related Plugins

See other plugins in the `data_processing` category:

```bash
corvin plugin list --category data_processing
```

## Support

Report issues or contribute: https://github.com/CorvinLabs/CorvinOS

## License

Apache-2.0 with CLA v3.1