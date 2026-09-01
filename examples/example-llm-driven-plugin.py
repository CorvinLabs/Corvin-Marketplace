"""
Example: LLM-Driven Plugin

Intelligent, adaptive, learns from feedback.
Tolerates 100-500ms latency.
Perfect for decision-making, not real-time critical.
"""

from corvin_plugins.plugin_base import LLMDrivenPlugin, PluginTier
from dataclasses import dataclass
from typing import Optional


@dataclass
class ErrorContext:
    error_type: str
    message: str
    stack_trace: str
    affected_component: str
    impact_level: str  # low, medium, high, critical


class IntelligentErrorHealer(LLMDrivenPlugin):
    """
    LLM-powered error analysis and healing.

    When an error occurs:
    1. Analyze with Claude
    2. Suggest healing strategy
    3. Learn from outcome
    4. Improve recommendations over time
    """

    def get_tier(self) -> PluginTier:
        return PluginTier.HIGH

    def get_max_latency_ms(self) -> int:
        return 500  # Allow 500ms for LLM reasoning

    async def initialize(self, context):
        """Setup LLM-driven plugin."""
        self.context = context

        # In real implementation, would get from config
        # For now, mock setup
        print(f"✅ {self.__class__.__name__} initialized (LLM-driven, 500ms SLA)")

    async def on_error(self, error: ErrorContext):
        """
        When an error occurs, use LLM to analyze and recommend healing.

        NON-BLOCKING: This runs asynchronously, doesn't block Brain.
        """

        # Build reasoning prompt
        prompt = f"""
        Error Analysis Request:

        Error Type: {error.error_type}
        Message: {error.message}
        Affected Component: {error.affected_component}
        Impact Level: {error.impact_level}

        Available Healing Strategies:
        1. Retry with exponential backoff
        2. Fallback to cached/default value
        3. Graceful degradation
        4. Escalate to human operator
        5. No action (log only)

        Which strategy is most appropriate?
        Consider: impact level, error frequency, user impact.
        Return: strategy name + confidence (0.0-1.0) + reasoning.
        """

        # Use LLM to reason (100-300ms round-trip)
        decision = await self.reason(
            prompt,
            tools={
                "check_error_history": self.check_error_history,
                "get_system_health": self.get_system_health,
                "list_cached_values": self.list_cached_values,
            },
        )

        # Execute the recommended healing strategy
        healing_result = await self.execute_healing_strategy(decision, error)

        # Monitor outcome (for learning)
        outcome = await self.monitor_healing_outcome(healing_result)

        # Learn from this experience (Skill 2.0)
        await self.learn_from_outcome(
            decision_id=decision.id,
            outcome_score=outcome.success_rate,  # 0.0-1.0
            feedback=f"Healing {decision.strategy} worked with {outcome.success_rate:.1%} success",
        )

    async def check_error_history(self, error_type: str) -> dict:
        """Tool: Check historical errors of this type."""
        # In real impl, would query audit log
        return {
            "count_last_hour": 5,
            "count_last_day": 23,
            "most_common_fix": "retry",
        }

    async def get_system_health(self) -> dict:
        """Tool: Check current system health."""
        # Would query Brain health metrics
        return {
            "cpu_usage": 0.45,
            "memory_usage": 0.60,
            "error_rate": 0.02,  # 2%
            "response_time_ms": 120,
        }

    async def list_cached_values(self) -> list:
        """Tool: List available cached fallback values."""
        # Would check context cache
        return [
            "default_user_model",
            "last_successful_context",
            "fallback_decision",
        ]

    async def execute_healing_strategy(self, decision, error: ErrorContext):
        """Execute the LLM-recommended healing strategy."""

        strategy = decision.strategy  # e.g., "retry", "fallback", "escalate"
        confidence = decision.confidence

        if strategy == "retry":
            result = await self._retry_operation(error, decision.retry_config)
        elif strategy == "fallback":
            result = await self._use_fallback(error, decision.fallback_value)
        elif strategy == "escalate":
            result = await self._escalate_to_operator(error, decision.escalation_reason)
        else:
            result = {"status": "logged", "strategy": strategy}

        return result

    async def _retry_operation(self, error, retry_config):
        """Retry the failed operation with backoff."""
        import asyncio

        for attempt in range(retry_config.get("max_attempts", 3)):
            backoff = 2 ** attempt  # Exponential backoff
            await asyncio.sleep(backoff / 1000)  # Convert to seconds

            try:
                # Would retry actual operation here
                return {"status": "success", "attempt": attempt + 1}
            except Exception:
                continue

        return {"status": "failed_after_retries", "attempts": retry_config["max_attempts"]}

    async def _use_fallback(self, error, fallback_value):
        """Use cached fallback value."""
        return {"status": "fallback_used", "value": fallback_value}

    async def _escalate_to_operator(self, error, reason):
        """Escalate to human operator."""
        # Would send to operator queue
        return {"status": "escalated", "reason": reason}

    async def monitor_healing_outcome(self, result):
        """Monitor the healing outcome to measure success."""
        # In real impl, would check:
        # - Did operation succeed?
        # - What was the latency impact?
        # - Did user notice?
        return {
            "success_rate": 0.92,  # 92% success
            "latency_added_ms": 120,
            "user_impact": "none",
        }

    async def on_health_check(self):
        """Report plugin health."""
        from corvin_plugins.protocol import HealthStatus

        # Check LLM backend connectivity
        backend_ok = self.llm_backend is not None
        recent_success_rate = getattr(self, "recent_success_rate", 0.90)

        return HealthStatus(
            ok=backend_ok and recent_success_rate > 0.70,
            message=f"LLM backend: {'✓' if backend_ok else '✗'}, success rate: {recent_success_rate:.1%}",
        )

    async def shutdown(self):
        """Cleanup."""
        print(f"ℹ️ {self.__class__.__name__} shut down")


# Usage in marketplace plugin.json:
"""
{
  "id": "plugin:buildin-integration-intelligent_error_healer",
  "type": "plugin",
  "name": "Intelligent Error Healer (LLM-Driven)",
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
  "description": "LLM-powered intelligent error analysis and adaptive healing",
  "tags": ["ai-learning", "adaptive", "intelligence"]
}
"""
