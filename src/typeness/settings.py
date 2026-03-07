"""Persistent settings for Typeness.

Stored as JSON in ~/Library/Application Support/Typeness/settings.json.
"""

import json
from pathlib import Path

_SETTINGS_DIR = Path.home() / "Library" / "Application Support" / "Typeness"
_SETTINGS_PATH = _SETTINGS_DIR / "settings.json"

_DEFAULTS: dict[str, bool | str | int | list] = {
    "show_menubar_icon_always": False,
    "debug_mode": False,
    "show_floating_window": True,
    "floating_window_position": "bottom_right",
    "confirm_before_inserting": False,
    "shortcut_push_to_talk": [{"name": "alt"}, {"name": "space"}], # Option + Space
    "shortcut_toggle_mode": [{"name": "shift"}, {"name": "cmd"}, {"vk": 0, "name": "a"}],
}


class Settings:
    """Simple key-value settings store backed by a JSON file."""

    def __init__(self) -> None:
        self._data: dict[str, bool | str | int | list] = dict(_DEFAULTS)
        self._load()

    def _load(self) -> None:
        if _SETTINGS_PATH.exists():
            try:
                on_disk = json.loads(_SETTINGS_PATH.read_text())
                for key in _DEFAULTS:
                    if key in on_disk:
                        self._data[key] = on_disk[key]
            except Exception as exc:
                print(f"[settings] Failed to load settings: {exc}")

    def save(self) -> None:
        try:
            _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            _SETTINGS_PATH.write_text(json.dumps(self._data, indent=2))
        except Exception as exc:
            print(f"[settings] Failed to save settings: {exc}")

    # Properties

    @property
    def show_menubar_icon_always(self) -> bool:
        return bool(self._data.get("show_menubar_icon_always", False))

    @show_menubar_icon_always.setter
    def show_menubar_icon_always(self, value: bool) -> None:
        self._data["show_menubar_icon_always"] = value
        self.save()

    @property
    def debug_mode(self) -> bool:
        return bool(self._data.get("debug_mode", False))

    @debug_mode.setter
    def debug_mode(self, value: bool) -> None:
        self._data["debug_mode"] = value
        self.save()

    @property
    def show_floating_window(self) -> bool:
        return bool(self._data.get("show_floating_window", True))

    @show_floating_window.setter
    def show_floating_window(self, value: bool) -> None:
        self._data["show_floating_window"] = value
        self.save()

    @property
    def floating_window_position(self) -> str:
        return str(self._data.get("floating_window_position", "bottom_right"))

    @floating_window_position.setter
    def floating_window_position(self, value: str) -> None:
        self._data["floating_window_position"] = value
        self.save()

    @property
    def confirm_before_inserting(self) -> bool:
        return bool(self._data.get("confirm_before_inserting", False))

    @confirm_before_inserting.setter
    def confirm_before_inserting(self, value: bool) -> None:
        self._data["confirm_before_inserting"] = value
        self.save()

    @property
    def shortcut_push_to_talk(self) -> list:
        return list(self._data.get("shortcut_push_to_talk", _DEFAULTS["shortcut_push_to_talk"]))

    @shortcut_push_to_talk.setter
    def shortcut_push_to_talk(self, value: list) -> None:
        self._data["shortcut_push_to_talk"] = value
        self.save()

    @property
    def shortcut_toggle_mode(self) -> list:
        return list(self._data.get("shortcut_toggle_mode", _DEFAULTS["shortcut_toggle_mode"]))

    @shortcut_toggle_mode.setter
    def shortcut_toggle_mode(self, value: list) -> None:
        self._data["shortcut_toggle_mode"] = value
        self.save()

# Global settings instance
app_settings = Settings()
