# Recall Backend Plugin

## Purpose

The **Recall Backend** plugin provides a registry for managing conversation recall implementations with thread-safe provider swapping. It includes a default SQLite-based implementation for indexing and retrieving past conversations (ADR-0033, L28).

## Usage Example

```python
from corvin_plugins.providers.recall_backend import get_active, set_active

# Install custom recall backend
class PostgresRecallBackend:
    def index_turn(self, channel, chat_key, *, user_text, assistant_text, tenant_id="_default", **kwargs):
        # Store in Postgres instead of SQLite
        self.db.execute("INSERT INTO conversations ...")
        return {"ok": True, "indexed": True}

    def recall(self, query, *, channel=None, limit=20, tenant_id="_default", **kwargs):
        # Search conversation history
        rows = self.db.execute("SELECT * FROM conversations WHERE ...")
        return rows

    def forget(self, *, channel=None, chat_key=None, before_ts=None, tenant_id="_default"):
        # GDPR Art. 17 erasure
        count = self.db.execute("DELETE FROM conversations WHERE ...")
        return count

# Install during plugin load
ctx.recall_registry.set_active(PostgresRecallBackend())

# Caller retrieves and uses
backend = get_active()
backend.index_turn("web-chat", "user-123", user_text="hello", assistant_text="hi")
recalled = backend.recall("what did I ask last time", channel="web-chat")
```

## Integration Points

**Provides:**
- `set_active(provider)` — Install custom recall backend
- `get_active()` — Retrieve active backend
- `clear()` — Restore default SqliteRecallBackend
- `release_owned_by(plugin_id)` — Release by plugin identity
- `clear_if_active(provider)` — Restore only if instance matches

**Requires:**
- `corvin_plugins.loading.current()` — Plugin ownership tracking
- `operator/bridges/shared/conversation_recall.py` — Default SQLite implementation (lazy-loaded)

**Default Implementation:**
- **SqliteRecallBackend** — Indexes turns into SQLite; searches and forgets with graceful degradation

**Integrates with:**
- **L28 Conversation Recall**: Multi-turn context and persona history
- **GDPR Art. 17**: `forget()` method for user data erasure
- **GDPR Art. 32**: Audit trail for all recall operations
- **Audit Trail**: index_turn/recall/forget logged to audit chain

## Conversation Flow

```svg
<svg width="620" height="340" xmlns="http://www.w3.org/2000/svg">
  <text x="10" y="25" font-size="16" font-weight="bold">Recall Backend Architecture</text>
  
  <!-- Conversation turns -->
  <rect x="20" y="60" width="100" height="50" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="30" y="85" font-size="11" font-weight="bold">Chat Turn</text>
  <text x="30" y="100" font-size="9">user_text +</text>
  <text x="30" y="110" font-size="9">assistant_text</text>
  
  <!-- Index -->
  <path d="M 120 85 L 170 120" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="135" y="105" font-size="9">index_turn()</text>
  
  <!-- Registry -->
  <rect x="170" y="80" width="160" height="70" fill="#fff8dc" stroke="#333" stroke-width="2"/>
  <text x="180" y="100" font-size="11" font-weight="bold">RecallBackendRegistry</text>
  <text x="180" y="115" font-size="9">_active: SqliteRecallBackend</text>
  <text x="180" y="128" font-size="9">_owner_plugin_id: plugin-id</text>
  
  <!-- Backend -->
  <path d="M 330 115 L 390 115" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  
  <rect x="390" y="60" width="110" height="110" fill="#e8f8e8" stroke="#333" stroke-width="2"/>
  <text x="400" y="80" font-size="10" font-weight="bold">SqliteRecallBackend</text>
  <text x="400" y="95" font-size="9">index_turn()</text>
  <text x="400" y="107" font-size="9">recall()</text>
  <text x="400" y="119" font-size="9">forget() [GDPR]</text>
  <text x="400" y="131" font-size="9">Default: lazy-load</text>
  
  <!-- Search -->
  <rect x="20" y="150" width="100" height="40" fill="#f0e8f4" stroke="#333" stroke-width="2"/>
  <text x="30" y="175" font-size="11" font-weight="bold">Search Query</text>
  
  <path d="M 120 170 L 170 145" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="135" y="157" font-size="9">recall()</text>
  
  <!-- Results -->
  <path d="M 330 85 L 360 130" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  
  <rect x="360" y="180" width="140" height="60" fill="#fff8e8" stroke="#333" stroke-width="2"/>
  <text x="370" y="205" font-size="10" font-weight="bold">Recalled Turns</text>
  <text x="370" y="220" font-size="9">[{user_text, asst_text},...]</text>
  <text x="370" y="232" font-size="9">Limited by: limit, time range</text>
  
  <!-- Audit trail -->
  <rect x="170" y="280" width="300" height="50" fill="#ffe8e8" stroke="#333" stroke-width="2" stroke-dasharray="5,5"/>
  <text x="180" y="305" font-size="10" font-weight="bold">Audit Trail (GDPR Art. 30)</text>
  <text x="180" y="320" font-size="9">index_turn, recall, forget (erasure) logged</text>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## Compliance Notes

- **ADR-0033**: Provider registry pattern — thread-safe, ownership-based release
- **L28 Conversation Recall**: Multi-turn context and persona-aware recall
- **GDPR Art. 17**: `forget()` method implements user data erasure
- **GDPR Art. 30**: All recall operations logged to audit trail
- **GDPR Art. 32**: Encryption of conversation history (planning)
- **Thread-safety**: All registry operations protected by `threading.Lock()`
- **Graceful degradation**: Returns empty/zero when SQLite module unavailable

## References

- **Plugin**: `plugin:buildin-memory-recall_backend` (buildin tier)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/memory/recall_backend/src/recall_backend.py`
- **Tests**: `tests/test_recall_backend.py` (10 test cases covering registry, SQLite impl, GDPR methods)
