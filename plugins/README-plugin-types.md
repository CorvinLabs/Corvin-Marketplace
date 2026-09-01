# Plugin Types: Deterministic vs. LLM-Driven

## Overview

CorvinOS supports two plugin types, co-existing in the same marketplace:

| Aspect | Deterministic | LLM-Driven |
|--------|---------------|-----------|
| **Execution** | Pure Python | LLM-based reasoning |
| **Latency** | <1ms | 100-500ms |
| **Determinism** | 100% | ~80-95% |
| **Learning** | Manual updates | Skill 2.0 grading |
| **Criticality** | Can be critical | Non-critical only |
| **Use Case** | Real-time monitoring, security, audit | Intelligent decisions, adaptation |

---

## Declaring Plugin Type in plugin.json

```json
{
  "id": "plugin:buildin-observability-vibe_health_monitor",
  "type": "plugin",
  "name": "Vibe Health Monitor",
  "version": "1.0.0",
  
  "plugin_type": "deterministic",
  "plugin_tier": "high",
  "plugin_capabilities": {
    "max_latency_ms": 1,
    "requires_llm": false,
    "can_call_other_plugins": false,
    "learnable": false
  },
  
  "category": "observability",
  "description": "Fast health monitoring for Vibe sessions"
}
```

## LLM-Driven Plugin Example

```json
{
  "id": "plugin:buildin-integration-intelligent_error_healer",
  "type": "plugin",
  "name": "Intelligent Error Healer",
  "version": "1.0.0",
  
  "plugin_type": "llm_driven",
  "plugin_tier": "high",
  "plugin_capabilities": {
    "max_latency_ms": 500,
    "requires_llm": true,
    "can_call_other_plugins": true,
    "learnable": true,
    "llm_backend": "claude-opus-5",
    "skill_id": "intelligent_error_healer_v1"
  },
  
  "category": "integration",
  "description": "LLM-based intelligent error analysis and healing"
}
```

---

## Plugin Orchestration by Type

### Deterministic Plugins

```
Registry.on_event(event):
  for plugin in deterministic_plugins:
    try:
      result = await plugin.handle(event)  # <1ms timeout
    except Timeout:
      circuit_breaker.trip()  # Fail fast
      raise
```

### LLM-Driven Plugins

```
Registry.on_event(event):
  tasks = []
  for plugin in llm_plugins:
    tasks.append(
      plugin.handle_async(event)  # Fire & forget
    )
  
  # Don't wait for LLM plugins
  # Handle results asynchronously
  asyncio.create_task(
    gather_llm_results(tasks)
  )
```

---

## Creating a Deterministic Plugin

```python
# plugins/buildin/observability/my_monitor/src/my_monitor.py

from corvin_plugins.plugin_base import DeterministicPlugin, PluginTier

class MyFastMonitor(DeterministicPlugin):
    """Fast, <1ms plugin."""

    def get_tier(self) -> PluginTier:
        return PluginTier.HIGH

    def get_max_latency_ms(self) -> int:
        return 1  # Sub-millisecond

    async def on_brain_metric(self, metric):
        # Pure Python only
        # Must complete in <1ms
        if metric.value > self.threshold:
            self.counter += 1
```

---

## Creating an LLM-Driven Plugin

```python
# plugins/buildin/integration/intelligent_healer/src/intelligent_healer.py

from corvin_plugins.plugin_base import LLMDrivenPlugin, PluginTier

class IntelligentErrorHealer(LLMDrivenPlugin):
    """Smart, adaptive plugin with LLM reasoning."""

    def get_tier(self) -> PluginTier:
        return PluginTier.HIGH

    def get_max_latency_ms(self) -> int:
        return 300  # Allow 300ms for LLM round-trip

    async def on_error(self, error):
        # Use LLM to reason
        decision = await self.reason(
            f"""
            Error occurred: {error.message}
            Context: {error.context}
            
            What healing strategy should we use?
            Available: retry, fallback, escalate, ignore
            """
        )

        # Execute decision
        healing_result = await self.execute_healing(decision)

        # Learn from outcome
        outcome = await self.monitor_healing(healing_result)
        await self.learn_from_outcome(
            decision_id=decision.id,
            outcome_score=outcome.success_rate,
            feedback=outcome.explanation
        )
```

---

## Marketplace Filtering

### List only Deterministic Plugins (for critical systems)

```bash
curl http://localhost:8765/api/v1/marketplace/plugins \
  ?plugin_type=deterministic
```

### List only LLM-Driven Plugins (for smart deployments)

```bash
curl http://localhost:8765/api/v1/marketplace/plugins \
  ?plugin_type=llm_driven
```

### List Learnable Plugins (for adaptive systems)

```bash
curl http://localhost:8765/api/v1/marketplace/plugins \
  ?learnable=true
```

---

## Roadmap: LLM Plugins Coming

**v1.2 (Q4 2026):**
- [ ] LLM backend integration (Claude API)
- [ ] 3 LLM-driven pilot plugins
- [ ] Skill 2.0 grading loop

**v1.3 (Q1 2027):**
- [ ] Plugin swarm orchestration
- [ ] Multi-plugin reasoning
- [ ] Collaborative decision making

**v1.4 (Q2 2027):**
- [ ] Community LLM plugins
- [ ] Plugin marketplace for smart agents
- [ ] Transfer learning across plugins

---

## Best Practices

✅ **DO:**
- Use Deterministic for anything on the critical path
- Use LLM-Driven for complex reasoning
- Monitor LLM plugin latency closely
- Grade LLM plugins with Skill 2.0

❌ **DON'T:**
- Put LLM plugins on critical path
- Call LLM plugins synchronously
- Skip health checks for LLM plugins
- Ignore circuit breaker signals

---

**Questions?**
See `plugin_base.py` for implementation details.
See `plugin.json` schema for manifest structure.
