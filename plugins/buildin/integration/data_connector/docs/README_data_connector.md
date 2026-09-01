# Data Connector Plugin

## Purpose

The **Data Connector** plugin provides a registry interface for managing external data source integrations with CorvinOS artifact processing pipelines. It abstracts data source access through a thread-safe registry, enabling plugins to install custom data connectors while maintaining compliance with Layer 24 (L24) metadata-only audit constraints (GDPR Art. 5).

## Usage Example

```python
from corvin_plugins.providers.data_connector import get_active, set_active

# Install a custom data connector
class MyDataConnector:
    def fetch_data(self, source_id):
        # Never include raw row contents in audit logs
        return {"rows": [...], "schema": [...]}

# During plugin load
ctx.data_connector_registry.set_active(MyDataConnector())

# Later, caller retrieves active connector
connector = get_active()
data = connector.fetch_data("source-1")
```

## Integration Points

**Provides:**
- `set_active(provider)` — Install a custom data connector
- `get_active()` — Retrieve the active connector
- `is_installed()` — Check if a connector is available
- `clear()` — Restore default (no connector)
- `release_owned_by(plugin_id)` — Release slot by plugin identity

**Requires:**
- `corvin_plugins.loading.current()` — Tracks plugin ownership for lifecycle safety

**Integrates with:**
- **L24 Snapshot Layer** — Data connector audit records METADATA ONLY (schema, row count, source ID; never raw row contents)
- **GDPR Art. 5** — Purpose limitation: audit logs never contain personal data from data sources
- **Plugin Lifecycle** — Ownership tracking prevents double-registration and unload deadlocks

## Data Flow Diagram

```svg
<svg width="600" height="400" xmlns="http://www.w3.org/2000/svg">
  <!-- Title -->
  <text x="10" y="25" font-size="18" font-weight="bold">Data Connector Registry</text>
  
  <!-- Caller -->
  <rect x="20" y="60" width="100" height="50" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="30" y="90" font-size="12" font-weight="bold">Caller</text>
  
  <!-- get_active() -->
  <path d="M 120 85 L 180 85" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="135" y="78" font-size="10">get_active()</text>
  
  <!-- Registry -->
  <rect x="180" y="60" width="150" height="50" fill="#fff8dc" stroke="#333" stroke-width="2"/>
  <text x="190" y="85" font-size="12" font-weight="bold">DataConnectorRegistry</text>
  <text x="190" y="100" font-size="10">_lock, _owner_plugin_id, _active</text>
  
  <!-- Plugin install path -->
  <rect x="20" y="150" width="100" height="50" fill="#f0e8f4" stroke="#333" stroke-width="2"/>
  <text x="30" y="175" font-size="12" font-weight="bold">Plugin</text>
  <text x="30" y="190" font-size="10">on_load()</text>
  
  <!-- set_active() -->
  <path d="M 120 175 L 180 115" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="130" y="150" font-size="10">set_active()</text>
  
  <!-- Loading context -->
  <path d="M 140 150 L 160 120" stroke="#999" stroke-width="1" stroke-dasharray="5,5"/>
  <text x="120" y="135" font-size="9" fill="#666">loading.current()</text>
  
  <!-- Data access -->
  <rect x="380" y="60" width="140" height="50" fill="#e8f8e8" stroke="#333" stroke-width="2"/>
  <text x="390" y="85" font-size="12" font-weight="bold">Data Source</text>
  <text x="390" y="100" font-size="10">(DB, API, etc)</text>
  
  <path d="M 330 85 L 380 85" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="340" y="78" font-size="10">fetch_data()</text>
  
  <!-- Audit layer -->
  <rect x="180" y="280" width="240" height="60" fill="#ffe8e8" stroke="#333" stroke-width="2" stroke-dasharray="5,5"/>
  <text x="190" y="305" font-size="12" font-weight="bold">L24 Audit (Metadata Only)</text>
  <text x="190" y="320" font-size="10">Schema, row_count, source_id</text>
  <text x="190" y="335" font-size="10" fill="#c00">Never: raw row contents or query payloads</text>
  
  <!-- Compliance notes -->
  <path d="M 300 110 L 300 280" stroke="#999" stroke-width="1" stroke-dasharray="3,3"/>
  
  <!-- Arrow marker -->
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
  </defs>
</svg>
```

## Compliance Notes

- **ADR-0030**: Plugin system architecture — defines plugin types including `data_connector`
- **ADR-0033**: Provider registry pattern — unified contract for all provider registries
- **Layer 24 (L24)**: Data snapshot layer — audit records METADATA ONLY; row contents strictly forbidden
- **GDPR Art. 5**: Purpose limitation and data minimization — audit trails must not contain personal data from data sources
- **Thread-safety**: `threading.Lock()` protects concurrent access to `_active` and `_owner_plugin_id`

## References

- **Plugin**: `plugin:buildin-integration-data_connector` (buildin tier, bundled boot layer)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/integration/data_connector/src/data_connector.py`
- **Tests**: `tests/test_data_connector.py` (10 test cases covering registry, ownership, thread-safety)
