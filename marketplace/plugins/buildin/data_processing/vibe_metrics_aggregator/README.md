# Vibe Metrics Aggregator

Aggregate Vibe session metrics across time windows and cohorts

## Features

- PII detection and masking
- Data classification engine
- Artifact extraction and processing
- Content inspection

## Installation

```bash
pip install corvin-plugin-data_processing_vibe_metrics_aggregator
```

## Usage

```python
from corvin_plugins import Data_ProcessingVibe_Metrics_Aggregator

plugin = Data_ProcessingVibe_Metrics_Aggregator()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-data_processing-vibe_metrics_aggregator
```

## Testing

```bash
pytest tests/plugins/test_data_processing_vibe_metrics_aggregator.py -v
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