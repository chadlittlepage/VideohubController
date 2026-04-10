"""Preset (salvo) save/recall for routing snapshots.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".videohub_controller.json"


class PresetManager:
    """Save and recall routing presets to disk."""

    def __init__(self) -> None:
        self.presets: dict = {}
        self.last_ip: str = ""
        self.settings: dict = {}
        self.session: dict = {}
        self._load()

    def _load(self) -> None:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                self.presets = data.get("presets", {})
                self.last_ip = data.get("last_ip", "")
                self.settings = data.get("settings", {})
                self.session = data.get("session", {})
            except Exception:
                pass

    def _write(self) -> None:
        data = {
            "last_ip": self.last_ip,
            "presets": self.presets,
            "settings": self.settings,
            "session": self.session,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2))

    def save_session(self, routing: list, input_labels: list, output_labels: list,
                     selected_preset: str = "", lcd_output: int | None = None,
                     active_hotkey: str | None = None) -> None:
        self.session = {
            "routing": list(routing),
            "input_labels": list(input_labels),
            "output_labels": list(output_labels),
            "selected_preset": selected_preset,
            "lcd_output": lcd_output,
            "active_hotkey": active_hotkey,
        }
        self._write()

    def get_session(self) -> dict:
        return dict(self.session)

    def save_ip(self, ip: str) -> None:
        self.last_ip = ip
        self._write()

    def save(self, name: str, routing: list, input_labels: list, output_labels: list) -> None:
        self.presets[name] = {
            "routing": list(routing),
            "input_labels": list(input_labels),
            "output_labels": list(output_labels),
        }
        self._write()

    def delete(self, name: str) -> None:
        self.presets.pop(name, None)
        self._write()

    def get(self, name: str) -> dict | None:
        return self.presets.get(name)

    def names(self) -> list[str]:
        return list(self.presets.keys())

    def get_setting(self, key: str, default: float = 0.0) -> float:
        return float(self.settings.get(key, default))

    def set_setting(self, key: str, value: float) -> None:
        self.settings[key] = value
        self._write()

    def get_key_bindings(self) -> dict[str, str]:
        return dict(self.settings.get("key_bindings", {}))

    def set_key_binding(self, key: str, preset_name: str) -> None:
        bindings = self.settings.get("key_bindings", {})
        if preset_name:
            bindings[key] = preset_name
        else:
            bindings.pop(key, None)
        self.settings["key_bindings"] = bindings
        self._write()
