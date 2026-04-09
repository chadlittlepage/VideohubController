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
        self._load()

    def _load(self) -> None:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                self.presets = data.get("presets", {})
                self.last_ip = data.get("last_ip", "")
            except Exception:
                pass

    def _write(self) -> None:
        data = {
            "last_ip": self.last_ip,
            "presets": self.presets,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2))

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
