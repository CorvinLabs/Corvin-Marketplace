# User Model Learner

L28 user modeling and learning

## Features

- Session recall and storage
- Learning event persistence
- User modeling and preferences
- Conversation history

## Installation

```bash
pip install corvin-plugin-memory_user_model_learner
```

## Usage

```python
from corvin_plugins import MemoryUser_Model_Learner

plugin = MemoryUser_Model_Learner()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-memory-user_model_learner
```

## Testing

```bash
pytest tests/plugins/test_memory_user_model_learner.py -v
```

## Compliance

- L28 session recall and learning infrastructure
- GDPR Art. 5, 6, 7 (data storage, consent)
- ADR-0314 learning event schema (immutable, tenant-scoped)

## Related Plugins

See other plugins in the `memory` category:

```bash
corvin plugin list --category memory
```

## Support

Report issues or contribute: https://github.com/CorvinLabs/CorvinOS

## License

Apache-2.0 with CLA v3.1