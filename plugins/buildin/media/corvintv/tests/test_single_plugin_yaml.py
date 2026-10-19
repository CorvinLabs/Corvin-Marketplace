"""A buildin plugin tree must hold exactly ONE plugin.yaml.

CorvinOS registers every ``plugin.yaml`` below a buildin root at boot (``bootstrap._builtin_plugin_dirs`` is a recursive
glob) and the marketplace index generator treats each as a loadable plugin that must be indexed. CorvinTV moved from the
contributor tier (where only the top manifest counted) to buildin on 2026-10-19; its release-lint fixtures carried five
more plugin.yaml files, all with plugin_id video_producer. They are now ``plugin.yaml.fixture``.
"""
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent


def test_the_plugin_tree_has_exactly_one_loadable_plugin_yaml():
    found = sorted(p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("plugin.yaml")
                   if ".venv" not in p.parts and "node_modules" not in p.parts)
    assert found == ["plugin.yaml"], found


def test_the_lint_fixtures_still_carry_a_manifest_under_the_fixture_name():
    fixtures = sorted((PLUGIN / "tests" / "fixtures" / "release_lint").glob("*/plugin/plugin.yaml.fixture"))
    assert len(fixtures) == 5
