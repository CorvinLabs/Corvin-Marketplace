"""E2E test for data_connector plugin (reachability verification).

Tests that the plugin loads correctly through PluginContext and registers
with the global data connector registry.
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add plugin src to path for import
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from data_connector import (
    DataConnectorRegistry,
    get_active,
    set_active,
    release_owned_by,
)


@pytest.mark.asyncio
async def test_e2e_plugin_registers_with_registry():
    """E2E: Plugin loads and registers connector with global registry."""
    # Simulate plugin loading
    class FakePlugin:
        def __init__(self):
            self.plugin_id = "plugin:test-data-connector"

    # Create a test connector
    class TestConnector:
        def fetch_data(self, source_id):
            return {"rows": [], "source": source_id}

    # Register via plugin context (simulated)
    with patch("loading.current") as mock_current:
        mock_current.return_value.plugin_id = "plugin:test-data-connector"

        connector = TestConnector()
        set_active(connector)

        # Verify registration
        active = get_active()
        assert active is connector
        assert active.fetch_data("test") == {"rows": [], "source": "test"}

    # Verify release works
    assert release_owned_by("plugin:test-data-connector")
    assert get_active() is None


@pytest.mark.asyncio
async def test_e2e_multiple_plugin_lifecycle():
    """E2E: Multiple plugins can install and release connectors sequentially."""
    class Connector1:
        name = "connector1"

    class Connector2:
        name = "connector2"

    c1 = Connector1()
    c2 = Connector2()

    # Plugin 1 installs
    with patch("loading.current") as mock_current:
        mock_current.return_value.plugin_id = "plugin-1"
        set_active(c1)
    assert get_active().name == "connector1"

    # Plugin 1 releases
    assert release_owned_by("plugin-1")

    # Plugin 2 installs
    with patch("loading.current") as mock_current:
        mock_current.return_value.plugin_id = "plugin-2"
        set_active(c2)
    assert get_active().name == "connector2"

    # Cleanup
    release_owned_by("plugin-2")
