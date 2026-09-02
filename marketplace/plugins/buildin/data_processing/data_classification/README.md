# Data Classification

L34 data classification engine

## Features

- PII detection and masking
- Data classification engine
- Artifact extraction and processing
- Content inspection

## Installation

```bash
pip install corvin-plugin-data_processing_data_classification
```

## Usage

```python
from corvin_plugins import Data_ProcessingData_Classification

plugin = Data_ProcessingData_Classification()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-data_processing-data_classification
```

## Testing

```bash
pytest tests/plugins/test_data_processing_data_classification.py -v
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