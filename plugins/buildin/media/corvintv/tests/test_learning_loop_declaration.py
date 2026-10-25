"""The plugin's ``learning_loops:`` declaration is valid for CorvinOS (ADR-0906).

CorvinOS validates the section when the plugin is installed and DROPS an entry that fails (a malformed
declaration costs the plugin its loop, never the install), so a typo here would not break anything loudly -
the loop would simply never appear in the Learning Loops panel. This test fails first. It restates the
CorvinOS schema constraints instead of importing them: a plugin test must not need the host's packages.
"""
import re
from pathlib import Path

import pytest
import yaml

PLUGIN_YAML = Path(__file__).resolve().parents[1] / "plugin.yaml"
FEEDBACK_TYPES = {"outcome_feedback", "preference_feedback", "confidence_score", "metric_observed"}
AGGREGATIONS = {"rolling_mean_7d", "rolling_mean_30d", "percentile_p50", "percentile_p95", "percentile_p99",
                "count_events_7d", "count_events_30d"}


def problems(loop: dict) -> list:
    """Everything wrong with one declared loop, by the constraints CorvinOS enforces at install."""
    found = []
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", str(loop.get("id", ""))):
        found.append("id")
    if not 10 <= len(str(loop.get("description", ""))) <= 500:
        found.append("description")
    if not re.fullmatch(r"[A-Za-z]\w*\.\w+", str(loop.get("event_source", ""))):
        found.append("event_source")
    kinds = loop.get("feedback_types") or []
    if not kinds or not set(kinds) <= FEEDBACK_TYPES:
        found.append("feedback_types")
    if loop.get("aggregation") not in AGGREGATIONS:
        found.append("aggregation")
    threshold = loop.get("health_threshold")
    if threshold is not None and not 0.0 <= threshold <= 1.0:
        found.append("health_threshold")
    if not 1 <= int(loop.get("dormancy_alert_hours", 24)) <= 8760:
        found.append("dormancy_alert_hours")
    return found


@pytest.fixture(scope="module")
def loops():
    manifest = yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8"))
    declared = manifest.get("learning_loops")
    assert isinstance(declared, list) and declared, "plugin.yaml declares no learning_loops"
    return declared


def test_every_declared_loop_satisfies_the_corvinos_schema(loops):
    assert [(loop["id"], problems(loop)) for loop in loops] == [(loop["id"], []) for loop in loops]


def test_loop_ids_are_unique(loops):
    ids = [loop["id"] for loop in loops]
    assert len(ids) == len(set(ids))


def test_the_loop_names_the_skill_whose_events_measure_it(loops):
    """A loop with no owner skill is listed as 'not measured': it must name the skill that records the
    plugin's ratings (the host records them as ``os.video_producer``)."""
    assert [loop.get("owner_skill") for loop in loops] == ["os.video_producer"]


def test_the_checker_finds_what_is_wrong_positive_control():
    bad = {"id": "Bad Id!", "description": "short", "event_source": "no-dot", "feedback_types": [],
           "aggregation": "nope", "health_threshold": 2, "dormancy_alert_hours": 0}
    assert problems(bad) == ["id", "description", "event_source", "feedback_types", "aggregation",
                             "health_threshold", "dormancy_alert_hours"]
