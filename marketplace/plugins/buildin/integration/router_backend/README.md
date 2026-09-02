# Router Backend

Message routing and delegation. ADR-0255 worker engine integration.

## Features

- Event routing and delegation
- Multi-persona orchestration
- Notification and pub/sub messaging
- Webhook dispatch

## Installation

```bash
pip install corvin-plugin-integration_router_backend
```

## Usage

```python
from corvin_plugins import IntegrationRouter_Backend

plugin = IntegrationRouter_Backend()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-integration-router_backend
```

## Testing

```bash
pytest tests/plugins/test_integration_router_backend.py -v
```

## Compliance

- L4/L38 integration bridges
- GDPR Art. 5 (purpose limitation, data minimization)
- ADR-0255 worker engine integration

## Related Plugins

See other plugins in the `integration` category:

```bash
corvin plugin list --category integration
```

## Support

Report issues or contribute: https://github.com/CorvinLabs/CorvinOS

## License

Apache-2.0 with CLA v3.1