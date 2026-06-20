"""
Configuration management for SnapEdit.
Reads and writes settings from/to a JSON config file.
"""
import json
import os
from pathlib import Path


DEFAULT_CONFIG = {
    "hotkeys": {
        "fullscreen": "alt+shift+1",
        "region": "alt+shift+2"
    },
    "save_directory": str(Path.home() / "Pictures" / "SnapEdit"),
    "default_format": "png",
    "auto_copy_clipboard": False,
    "stroke_color": "#FF3B30",
    "stroke_width": 3,
    "bubble_color": "#FF3B30",
    "fill_shapes": False,
    "fill_opacity": 0.2
}


class Config:
    """Manages application configuration stored as JSON."""

    def __init__(self):
        self._config_dir = Path.home() / ".snapedit"
        self._config_path = self._config_dir / "config.json"
        self._data = {}
        self.load()

    def load(self):
        """Load configuration from file, or create defaults."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                # Merge missing keys from defaults
                self._merge_defaults(self._data, DEFAULT_CONFIG)
            except (json.JSONDecodeError, IOError):
                self._data = DEFAULT_CONFIG.copy()
                self.save()
        else:
            self._data = DEFAULT_CONFIG.copy()
            self.save()

        # Ensure save directory exists
        save_dir = Path(self._data.get("save_directory", DEFAULT_CONFIG["save_directory"]))
        save_dir.mkdir(parents=True, exist_ok=True)

    def _merge_defaults(self, current: dict, defaults: dict):
        """Recursively merge missing default keys into current config."""
        for key, value in defaults.items():
            if key not in current:
                current[key] = value
            elif isinstance(value, dict) and isinstance(current.get(key), dict):
                self._merge_defaults(current[key], value)

    def save(self):
        """Save current configuration to file."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default=None):
        """Get a config value by key. Supports dot notation (e.g., 'hotkeys.fullscreen')."""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value):
        """Set a config value by key. Supports dot notation."""
        keys = key.split(".")
        data = self._data
        for k in keys[:-1]:
            if k not in data or not isinstance(data[k], dict):
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value
        self.save()

    @property
    def hotkeys(self) -> dict:
        return self._data.get("hotkeys", DEFAULT_CONFIG["hotkeys"])

    @property
    def save_directory(self) -> str:
        return self._data.get("save_directory", DEFAULT_CONFIG["save_directory"])

    @save_directory.setter
    def save_directory(self, path: str):
        self.set("save_directory", path)

    @property
    def default_format(self) -> str:
        return self._data.get("default_format", "png")

    @property
    def stroke_color(self) -> str:
        return self._data.get("stroke_color", DEFAULT_CONFIG["stroke_color"])

    @property
    def stroke_width(self) -> int:
        return self._data.get("stroke_width", DEFAULT_CONFIG["stroke_width"])

    @property
    def bubble_color(self) -> str:
        return self._data.get("bubble_color", DEFAULT_CONFIG["bubble_color"])

    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        self._data = DEFAULT_CONFIG.copy()
        self.save()
