# Router Backend

## Overview

The Router Backend plugin implements message routing and delegation logic for distributing work across multiple worker engines (Claude Opus, Haiku, Hermes, etc.) based on task characteristics, availability, and cost constraints. It integrates with ADR-0255's worker engine framework to enable intelligent routing decisions, load balancing, and failover handling. The plugin manages routing state, tracks worker health, and adjusts strategy based on historical performance metrics.

## Use Case

**Scenario:** Intelligent task-to-worker delegation

- A task queue contains mixed-complexity requests: some need Opus for deep reasoning, others fit Haiku's speed/cost profile, a few need specialized Hermes capabilities—the router must classify and assign each to the optimal engine without manual intervention
- An organization needs to maintain SLA targets while minimizing LLM API costs—the router learns task complexity distributions and dynamically adjusts routing thresholds to balance cost and latency
- A multi-region deployment needs to route tasks to geographically proximate worker engines, with automatic failover when a region becomes unavailable

**Impact:** Complex tasks are routed to capable engines; cost-per-completion is minimized through intelligent classification; SLA targets are maintained automatically; single point of routing control enables cost monitoring and optimization.

## API Example

```python
from corvin_plugins.providers.router_backend import RouterBackend, RoutingRequest, RoutingPolicy

# Initialize router with worker engines and routing policy
router = RouterBackend(
    policy=RoutingPolicy(
        strategy="cost_aware",  # "cost_aware", "performance", "balanced"
        max_cost_per_task_usd=0.10,
        latency_sla_seconds=30,
        fallback_engine="opus"  # failover target
    ),
    worker_engines=[
        {"engine_id": "claude_opus", "cost_per_mtok": 0.015, "latency_p50_ms": 800},
        {"engine_id": "claude_haiku", "cost_per_mtok": 0.0008, "latency_p50_ms": 200},
        {"engine_id": "hermes_v2", "cost_per_mtok": 0.002, "latency_p50_ms": 150}
    ]
)

# Classify task and route to appropriate engine
async def route_and_execute():
    request = RoutingRequest(
        task_id="task-67890",
        instruction="Analyze this research paper and extract key findings",
        estimated_complexity="high",  # "low", "medium", "high"
        user_tier="premium",  # affects cost budget
        prefer_latency=False  # vs prefer_cost
    )
    
    # Router classifies and selects engine
    routing_decision = await router.route(request)
    print(f"Routing to: {routing_decision.selected_engine}")
    print(f"Estimated cost: ${routing_decision.estimated_cost:.4f}")
    print(f"Estimated latency: {routing_decision.estimated_latency_ms}ms")
    
    # Execute on selected engine
    result = await routing_decision.execute(
        prompt=request.instruction,
        max_tokens=2000
    )
    
    # Log decision and outcome for future routing optimization
    await router.record_outcome(
        request_id=request.task_id,
        engine=routing_decision.selected_engine,
        actual_cost=result.cost_usd,
        actual_latency_ms=result.latency_ms,
        success=result.error is None
    )

# Monitor router health and cost
stats = router.get_statistics()
print(f"Total tasks routed: {stats.total_tasks}")
print(f"Average cost per task: ${stats.average_cost:.4f}")
print(f"Engine utilization: {stats.engine_utilization}")
```

## Configuration

The Router Backend requires the following configuration in `tenant.corvin.yaml`:

```yaml
plugins:
  router_backend:
    enabled: true
    strategy: "cost_aware"  # "cost_aware", "performance", "balanced"
    max_cost_per_task_usd: 0.10
    latency_sla_seconds: 30
    fallback_engine: "opus"
    enable_learning: true  # Learn from historical performance
    learning_window_tasks: 1000
    worker_engines:
      - engine_id: "claude_opus"
        enabled: true
        cost_per_mtok: 0.015
        max_concurrent: 100
        region: "us-east"
      - engine_id: "claude_haiku"
        enabled: true
        cost_per_mtok: 0.0008
        max_concurrent: 500
        region: "us-east"
      - engine_id: "hermes_v2"
        enabled: true
        cost_per_mtok: 0.002
        max_concurrent: 50
        region: "us-west"
```

## Status

**Implementation:** Production Ready
**Tests:** 28 unit tests + 22 integration tests (50 total)
**Compliance:** ADR-0255 (Worker Engine Integration), ADR-0510 (Hub Wiring), ADR-0232 (Boot Tripwire)

---
**Plugin ID:** plugin:buildin-integration-router_backend
**Version:** 1.0.0 | **Boot Layer:** bundled
**Maintainer:** plugins@anthropic.com
**License:** Apache-2.0
