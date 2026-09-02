# Brain Learning Tracker

Track Brain subsystem learning and preference evolution over time

## Features

- Session recall and storage
- Learning event persistence
- User modeling and preferences
- Conversation history

## Installation

```bash
pip install corvin-plugin-memory_brain_learning_tracker
```

## Usage

```python
from corvin_plugins import MemoryBrain_Learning_Tracker

plugin = MemoryBrain_Learning_Tracker()
result = plugin.execute(...)
```

## Configuration

See plugin configuration or use:

```bash
corvin plugin config plugin:buildin-memory-brain_learning_tracker
```

## Testing

```bash
pytest tests/plugins/test_memory_brain_learning_tracker.py -v
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