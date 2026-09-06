"""Marketplace-wide test bootstrap.

Every plugin lives in ``plugins/<tier>/<category>/<name>/`` with its
implementation under ``src/`` and its tests under ``tests/``. The tests import
the implementation by bare module name (``from vibe_session_history import
...``), which only resolves when that plugin's ``src/`` is on ``sys.path``.

Some tests used to do that themselves with an absolute, machine-specific
``sys.path.insert(0, '/home/<user>/projects/Corvin-Marketplace/.../src')`` —
portable to nobody. This conftest puts every plugin ``src/`` on the path once,
relative to the checkout, so the suite runs on any machine and in CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PLUGINS = _ROOT / "plugins"

# Builtin plugins subclass ``corvin_plugins.plugin_base.DeterministicPlugin``
# and return ``corvin_plugins.protocol.HealthStatus`` — the REAL host contract,
# which lives in the CorvinOS repo (``core/plugins/``). Ten test modules used
# to replace that package with ``MagicMock()`` in ``sys.modules``, so every
# ``HealthStatus(...).ok`` assertion compared a MagicMock and could not pass.
# Resolve the sibling checkout (``CORVINOS_ROOT`` env, else ``../CorvinOS``)
# and put its plugin package + repo root on the path; tests that need the host
# skip cleanly when it is absent (see ``corvinos_available``).
import os

_CORVINOS = Path(os.environ.get("CORVINOS_ROOT") or (_ROOT.parent / "CorvinOS")).resolve()
CORVINOS_AVAILABLE = (_CORVINOS / "core" / "plugins" / "corvin_plugins").is_dir()
if CORVINOS_AVAILABLE:
    for _p in (str(_CORVINOS / "core" / "plugins"), str(_CORVINOS)):
        if _p not in sys.path:
            sys.path.append(_p)

for _src in sorted(_PLUGINS.glob("*/*/*/src")):
    _p = str(_src)
    if _src.is_dir() and _p not in sys.path:
        sys.path.append(_p)


import pytest


@pytest.fixture(scope="session")
def corvinos_available() -> bool:
    return CORVINOS_AVAILABLE


def pytest_collection_modifyitems(config, items):
    """Skip host-contract tests when no CorvinOS checkout is resolvable."""
    if CORVINOS_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="CorvinOS checkout not found (set CORVINOS_ROOT)")
    for item in items:
        if "requires_corvinos" in item.keywords:
            item.add_marker(skip)
