# Router Backend Plugin

## Purpose

The **Router Backend** plugin provides a registry for managing persona routing implementations with graceful degradation (ADR-0033, L5). It includes a default chain-based router that delegates to the existing `operator/bridges/shared/router.py` and enables plugins to install custom routing strategies without breaking the existing routing pipeline.

## Usage Example

```python
from corvin_plugins.providers.router_backend import get_active, set_active

class EmbeddingRouterBackend:
    def route(self, text, personas, *, model="", mode="embeddings", tenant_id="_default", **kwargs):
        # Custom embedding-based routing logic
        embeddings = embed_text(text)
        persona_embeddings = [embed_persona(p) for p in personas]
        scores = cosine_similarity(embeddings, persona_embeddings)
        best_idx = argmax(scores)
        return {"selected_persona": personas[best_idx], "confidence": scores[best_idx]}

# Install during plugin load
ctx.router_registry.set_active(EmbeddingRouterBackend())

# Caller retrieves active router
router = get_active()
result = router.route("hello world", [p1, p2, p3], model="claude-3-sonnet")
```

## Integration Points

**Provides:**
- `set_active(provider)` — Install custom router backend
- `get_active()` — Retrieve active router (default: ChainRouterBackend)
- `clear()` — Restore default ChainRouterBackend
- `release_owned_by(plugin_id)` — Release by plugin identity
- `clear_if_active(provider)` — Restore only if instance matches

**Requires:**
- `corvin_plugins.loading.current()` — Plugin ownership tracking
- `operator/bridges/shared/router.py` — Default chain implementation (lazy-loaded)

**Default Implementation:**
- **ChainRouterBackend** — Delegates to existing router chain with parameter pass-through; returns None on any exception (ADR-0033 must-NOT-raise contract)

**Integrates with:**
- **L5 Auto-routing**: Keyword-based persona selection; custom routers override this layer
- **ADR-0033**: Provider registry pattern — must-NOT-raise contract ensures degradation
- **Delegation routing** (ADR-0255): Router result influences delegation decisions

## Data Flow Diagram

```svg
<svg width="640" height="380" xmlns="http://www.w3.org/2000/svg">
  <text x="10" y="25" font-size="18" font-weight="bold">Router Backend Architecture</text>
  
  <!-- User input -->
  <rect x="20" y="60" width="100" height="40" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="35" y="85" font-size="11" font-weight="bold">User Input</text>
  
  <!-- Route call -->
  <path d="M 120 80 L 180 100" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="130" y="90" font-size="9">route()</text>
  
  <!-- Registry -->
  <rect x="180" y="70" width="160" height="60" fill="#fff8dc" stroke="#333" stroke-width="2"/>
  <text x="190" y="90" font-size="11" font-weight="bold">RouterBackendRegistry</text>
  <text x="190" y="105" font-size="9">_active: ChainRouterBackend | Custom</text>
  
  <!-- Default chain path -->
  <path d="M 340 80 L 380 100" stroke="#0c0" stroke-width="2.5" marker-end="url(#arrowgreen)"/>
  <text x="350" y="95" font-size="9" fill="#060">default path</text>
  
  <rect x="380" y="60" width="120" height="60" fill="#e8f8e8" stroke="#0c0" stroke-width="2"/>
  <text x="390" y="80" font-size="10" font-weight="bold">ChainRouterBackend</text>
  <text x="390" y="95" font-size="8">Load router.py</text>
  <text x="390" y="105" font-size="8">Pass through params</text>
  
  <!-- Custom path -->
  <path d="M 340 140 L 380 140" stroke="#c00" stroke-width="2.5" marker-end="url(#arrowred)"/>
  <text x="350" y="135" font-size="9" fill="#c00">custom path</text>
  
  <rect x="380" y="120" width="120" height="40" fill="#f0e8f4" stroke="#c00" stroke-width="2"/>
  <text x="390" y="145" font-size="10" font-weight="bold">Custom Impl</text>
  
  <!-- Personas -->
  <rect x="20" y="160" width="100" height="50" fill="#e8f4f8" stroke="#333" stroke-width="2"/>
  <text x="35" y="180" font-size="11" font-weight="bold">Persona List</text>
  <text x="35" y="195" font-size="9">[p1, p2, p3, ...]</text>
  
  <path d="M 120 190 L 180 130" stroke="#333" stroke-width="1.5" marker-end="url(#arrowhead)"/>
  
  <!-- Result -->
  <rect x="380" y="190" width="120" height="50" fill="#fff8e8" stroke="#333" stroke-width="2"/>
  <text x="390" y="210" font-size="10" font-weight="bold">Route Result</text>
  <text x="390" y="225" font-size="9">{ selected: P, confidence: N }</text>
  
  <path d="M 500 140 L 500 190" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="510" y="165" font-size="9">return</text>
  
  <!-- Delegation -->
  <rect x="180" y="280" width="240" height="70" fill="#ffe8e8" stroke="#333" stroke-width="2" stroke-dasharray="5,5"/>
  <text x="190" y="305" font-size="11" font-weight="bold">L5 Auto-routing + Delegation Influence</text>
  <text x="190" y="320" font-size="9">Router score → delegation decision (ADR-0255)</text>
  <text x="190" y="335" font-size="9">Must-NOT-raise: None on error (graceful degrade)</text>
  
  <path d="M 440 240 L 440 280" stroke="#999" stroke-width="1" stroke-dasharray="3,3"/>
  
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#333"/>
    </marker>
    <marker id="arrowgreen" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#0c0"/>
    </marker>
    <marker id="arrowred" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <polygon points="0 0, 10 3, 0 6" fill="#c00"/>
    </marker>
  </defs>
</svg>
```

## Compliance Notes

- **ADR-0033**: Provider registry pattern — must-NOT-raise contract ensures safe degradation
- **ADR-0255**: Delegation routing — router confidence influences delegation decisions
- **L5 Auto-routing**: Keyword-based persona selection; custom routers are optional replacements
- **Graceful degradation**: Returns None (not exception) when router module unavailable or crashes
- **Parameter pass-through**: All router parameters (model, timeout, min_confidence, mode) preserved
- **Thread-safety**: All registry operations protected by `threading.Lock()`

## References

- **Plugin**: `plugin:buildin-integration-router_backend` (buildin tier, bundled boot layer)
- **Source**: `/home/shumway/projects/Corvin-Marketplace/plugins/buildin/integration/router_backend/src/router_backend.py`
- **Tests**: `tests/test_router_backend.py` (10 test cases covering registry, chain router, error handling, thread-safety)
