"""Storyboard narration validator — the ONE primitive for structural +
didactic checks (ADR-0004).

Before this module existed, ``generate_storyboard_with_llm()`` re-implemented
ad hoc checks inline (scene count, total duration) as call-site band-aids.
Every new rule (text budget, per-scene timing, narrative flow) would have
grown that same function. This module is the single place those rules live;
callers get one ``validate()`` and one result shape, never a scattered set of
``if ...: raise ValueError`` statements duplicated across call sites.

Two severities:
  - ``errors``   — structural violations the pipeline must refuse (hard caps
                   from ADR-0003: total duration, scene count, per-scene
                   character ceiling). These always raise.
  - ``warnings`` — didactic soft targets from the video-production analysis
                   (per-strategy character budget, per-scene timing window,
                   narrative flow). These are reported, never fatal — a
                   storyboard that ignores them still renders, just worse.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

try:
    from .models import Storyboard
except ImportError:  # standalone script use (no package context)
    from models import Storyboard


# Hard limits (ADR-0003) — violating these makes the storyboard unusable,
# not just suboptimal.
MAX_SCENES = 100
MAX_CHARS_PER_SCENE_HARD = 500
MIN_DURATION_MS_HARD = 1000
MAX_DURATION_MS_HARD = 30000

# Soft targets per didactic strategy (video-production analysis,
# /home/shumway/projects/videos: minimal_visual measured ~177 chars/scene @
# 1.6 shapes/scene; rich_visual measured ~340 chars/scene @ 16-20 shapes/scene).
CHAR_BUDGETS = {
    "minimal_visual": {"min": 100, "target": 150, "max": 250},
    "rich_visual": {"min": 200, "target": 300, "max": 400},
}
SOFT_MIN_DURATION_MS = 8000   # below this, a viewer can't read + absorb
SOFT_MAX_DURATION_MS = 20000  # above this, attention drifts


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    scene_id: str
    rule: str
    message: str


@dataclass
class ValidationResult:
    valid: bool
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def raise_if_invalid(self) -> None:
        if not self.valid:
            messages = "; ".join(f"{i.scene_id}: {i.message}" for i in self.errors)
            raise ValueError(f"Storyboard validation failed: {messages}")


def validate_storyboard_dict(storyboard_json: Dict[str, Any], max_duration_minutes: int) -> ValidationResult:
    """Validate a raw storyboard dict (as parsed from the LLM, before it
    becomes a Storyboard object). This is the ONLY place total-duration and
    scene-count are checked — callers must not re-implement these checks."""
    errors: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []

    scenes = storyboard_json.get("scenes", [])
    if not scenes:
        errors.append(ValidationIssue("error", "global", "no_scenes", "Storyboard has no scenes"))
        return ValidationResult(valid=False, errors=errors, warnings=warnings, metrics={})

    if len(scenes) > MAX_SCENES:
        errors.append(ValidationIssue(
            "error", "global", "max_scenes",
            f"Too many scenes: {len(scenes)} > {MAX_SCENES}",
        ))

    max_ms = max_duration_minutes * 60000
    total_duration = sum(s.get("duration_ms", 0) for s in scenes)
    if total_duration > max_ms:
        errors.append(ValidationIssue(
            "error", "global", "max_total_duration",
            f"Storyboard too long: {total_duration}ms > {max_ms}ms",
        ))

    strategy = storyboard_json.get("didactic_strategy", "rich_visual")
    budget = CHAR_BUDGETS.get(strategy, CHAR_BUDGETS["rich_visual"])

    char_counts: List[int] = []
    durations: List[int] = []

    for scene in scenes:
        scene_id = scene.get("id", "?")
        narration = scene.get("narration_text") or ""
        duration_ms = scene.get("duration_ms", 0)
        char_count = len(narration)
        char_counts.append(char_count)
        durations.append(duration_ms)

        if char_count > MAX_CHARS_PER_SCENE_HARD:
            errors.append(ValidationIssue(
                "error", scene_id, "max_chars_hard",
                f"Narration exceeds hard limit: {char_count}ch > {MAX_CHARS_PER_SCENE_HARD}ch",
            ))
        elif char_count > budget["max"]:
            warnings.append(ValidationIssue(
                "warning", scene_id, "char_budget_high",
                f"Narration {char_count}ch exceeds {strategy} target ({budget['max']}ch) — consider splitting",
            ))
        elif char_count < budget["min"] and scene.get("kind") != "title":
            warnings.append(ValidationIssue(
                "warning", scene_id, "char_budget_low",
                f"Narration {char_count}ch below {strategy} target ({budget['min']}ch) — scene may feel thin",
            ))

        if duration_ms < MIN_DURATION_MS_HARD:
            errors.append(ValidationIssue(
                "error", scene_id, "min_duration_hard",
                f"Scene duration {duration_ms}ms below hard minimum {MIN_DURATION_MS_HARD}ms",
            ))
        elif duration_ms < SOFT_MIN_DURATION_MS and scene.get("kind") != "title":
            warnings.append(ValidationIssue(
                "warning", scene_id, "min_duration_soft",
                f"Scene duration {duration_ms}ms below comfortable minimum {SOFT_MIN_DURATION_MS}ms",
            ))
        if duration_ms > SOFT_MAX_DURATION_MS:
            warnings.append(ValidationIssue(
                "warning", scene_id, "max_duration_soft",
                f"Scene duration {duration_ms}ms exceeds comfortable maximum {SOFT_MAX_DURATION_MS}ms — attention may drift",
            ))

    # Narrative flow: a storyboard with >= 4 scenes should open with context
    # and close with a summary/anchor (video-production analysis pattern).
    kinds = [s.get("kind", "") for s in scenes]
    if len(scenes) >= 4:
        if kinds[-1] not in ("summary", "anchor", "solution"):
            warnings.append(ValidationIssue(
                "warning", kinds[-1] or "last", "missing_closing_anchor",
                "Last scene is not a summary/anchor — consider ending with a memorable recap",
            ))

    metrics = {
        "total_scenes": len(scenes),
        "total_duration_s": total_duration / 1000,
        "avg_chars_per_scene": sum(char_counts) // len(char_counts) if char_counts else 0,
        "avg_duration_per_scene_s": (sum(durations) / len(durations) / 1000) if durations else 0,
        "didactic_strategy": strategy,
        "scenes_in_budget": sum(1 for c in char_counts if budget["min"] <= c <= budget["max"]),
        "scenes_over_budget": sum(1 for c in char_counts if c > budget["max"]),
        "scenes_under_budget": sum(1 for c in char_counts if c < budget["min"]),
    }

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings, metrics=metrics)


def validate_storyboard(storyboard: Storyboard, max_duration_minutes: int) -> ValidationResult:
    """Validate an already-constructed Storyboard object (post-parse)."""
    storyboard_json = {
        "didactic_strategy": storyboard.didactic_strategy,
        "scenes": [s.to_dict() for s in storyboard.scenes],
    }
    return validate_storyboard_dict(storyboard_json, max_duration_minutes)
