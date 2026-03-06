"""Persistent settings for Typeness.

Stored as JSON in ~/Library/Application Support/Typeness/settings.json.
"""

import json
from pathlib import Path

_SETTINGS_DIR = Path.home() / "Library" / "Application Support" / "Typeness"
_SETTINGS_PATH = _SETTINGS_DIR / "settings.json"

_DEFAULTS: dict[str, bool | str | int] = {
    "show_menubar_icon_always": False,
    "debug_mode": False,
}


class Settings:
    """Simple key-value settings store backed by a JSON file."""

    def __init__(self) -> None:
        self._data: dict[str, bool | str | int] = dict(_DEFAULTS)
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
