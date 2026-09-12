"""Settings persistence — Load/save config from ~/.corvin/video-producer/config.json."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "output_folder": "~/.corvin/video-producer/videos",
    "tts_engine": "azure",
    "max_duration_minutes": 60,
    "youtube_enabled": False,
    "youtube_playlist_id": None,
}


class SettingsManager:
    """Manages persistent settings for Video Producer plugin."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.expanduser("~/.corvin/video-producer/config.json")

        self.config_path = Path(config_path)
        self.config_dir = self.config_path.parent
        self.settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from config file (or defaults if not found)."""

        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)
                    # Merge with defaults (defaults for any missing keys)
                    merged = {**DEFAULT_SETTINGS, **loaded}
                    logger.info(f"Settings loaded from {self.config_path}")
                    return merged
            except Exception as e:
                logger.warning(f"Failed to load settings: {e}. Using defaults.")

        logger.info("Using default settings")
        return DEFAULT_SETTINGS.copy()

    def save_settings(self, updates: Dict[str, Any]) -> bool:
        """Save settings to config file."""

        try:
            # Validate updates
            for key, value in updates.items():
                if key == "output_folder":
                    # Validate path
                    expanded = os.path.expanduser(value)
                    if not os.path.isabs(expanded):
                        return False  # Path must be absolute or ~-relative

                elif key == "tts_engine":
                    if value not in ["azure", "google", "local"]:
                        return False

                elif key == "max_duration_minutes":
                    if not isinstance(value, int) or value < 0:
                        return False

            # Update settings
            self.settings.update(updates)

            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)

            # Write to disk
            with open(self.config_path, "w") as f:
                json.dump(self.settings, f, indent=2)

            logger.info(f"Settings saved to {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a single setting value."""
        return self.settings.get(key, default)

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings."""
        return self.settings.copy()

    def reset_to_defaults(self) -> bool:
        """Reset all settings to defaults."""
        self.settings = DEFAULT_SETTINGS.copy()
        return self.save_settings({})


# Global settings manager instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager(config_path: Optional[str] = None) -> SettingsManager:
    """Get or create global settings manager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager(config_path)
    return _settings_manager


def reset_settings_manager():
    """Reset global settings manager (for testing)."""
    global _settings_manager
    _settings_manager = None
