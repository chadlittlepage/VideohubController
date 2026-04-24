"""Preset (salvo) save/recall for routing snapshots.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import json
from pathlib import Path

# Shared config path readable/writable by all users on the Mac
_SHARED_DIR = Path("/Users/Shared/Videohub Controller")
_SHARED_PATH = _SHARED_DIR / "videohub_controller.json"

# Legacy per-user path (migrated on first load)
_LEGACY_PATH = Path.home() / ".videohub_controller.json"

CONFIG_PATH = _SHARED_PATH


class PresetManager:
    """Save and recall routing presets to disk."""

    def __init__(self) -> None:
        self.presets: dict = {}
        self.last_ip: str = ""
        self.settings: dict = {}
        self.session: dict = {}
        self._load()

    def _load(self) -> None:
        # Migrate legacy per-user config to shared location
        if not CONFIG_PATH.exists() and _LEGACY_PATH.exists():
            try:
                _SHARED_DIR.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(str(_LEGACY_PATH), str(CONFIG_PATH))
                print(f"[presets] Migrated config from {_LEGACY_PATH} to {CONFIG_PATH}")
            except Exception as e:
                print(f"[presets] Migration failed: {e}")

        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                self.presets = data.get("presets", {})
                self.last_ip = data.get("last_ip", "")
                self.settings = data.get("settings", {})
                self.session = data.get("session", {})
                print(f"[presets] Loaded config: {len(self.presets)} presets, ip={self.last_ip}, model={self.settings.get('device_model', 'Auto-Detect')}")
            except Exception as e:
                print(f"[presets] Failed to load config: {e}")
        else:
            print(f"[presets] No config file found at {CONFIG_PATH}")

    def _write(self) -> None:
        data = {
            "last_ip": self.last_ip,
            "presets": self.presets,
            "settings": self.settings,
            "session": self.session,
        }
        try:
            _SHARED_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            CONFIG_PATH.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"[presets] Failed to write config: {e}")

    def save_session(self, routing: list, input_labels: list, output_labels: list,
                     selected_preset: str = "", lcd_output: int | None = None,
                     active_hotkey: str | None = None,
                     num_inputs: int = 10, num_outputs: int = 10,
                     font_sizes: dict | None = None) -> None:
        model_key = f"{num_inputs}x{num_outputs}"
        model_data = {
            "routing": list(routing),
            "input_labels": list(input_labels),
            "output_labels": list(output_labels),
            "selected_preset": selected_preset,
            "lcd_output": lcd_output,
            "active_hotkey": active_hotkey,
        }
        if font_sizes:
            model_data["font_sizes"] = font_sizes
        # Store per-model session state
        if not isinstance(self.session, dict) or "models" not in self.session:
            # Migrate old flat session to per-model format
            self.session = {"models": {}}
        self.session["models"][model_key] = model_data
        self.session["current_model"] = model_key
        self._write()

    def get_session(self, num_inputs: int = None, num_outputs: int = None) -> dict:
        """Get session state for a specific model, or the current model."""
        if not isinstance(self.session, dict):
            return {}
        # Per-model session
        if "models" in self.session:
            if num_inputs is not None and num_outputs is not None:
                key = f"{num_inputs}x{num_outputs}"
            else:
                key = self.session.get("current_model", "10x10")
            return dict(self.session.get("models", {}).get(key, {}))
        # Legacy flat session — treat as 10x10
        return dict(self.session)

    def save_ip(self, ip: str) -> None:
        self.last_ip = ip
        self._write()

    def save(self, name: str, routing: list, input_labels: list, output_labels: list,
             num_inputs: int = 10, num_outputs: int = 10) -> None:
        self.presets[name] = {
            "routing": list(routing),
            "input_labels": list(input_labels),
            "output_labels": list(output_labels),
            "num_inputs": num_inputs,
            "num_outputs": num_outputs,
        }
        self._write()

    def delete(self, name: str) -> None:
        self.presets.pop(name, None)
        self._write()

    def get(self, name: str) -> dict | None:
        return self.presets.get(name)

    def names(self, num_inputs: int = None, num_outputs: int = None) -> list[str]:
        """Return preset names, optionally filtered by I/O count."""
        if num_inputs is None and num_outputs is None:
            return list(self.presets.keys())
        result = []
        for name, data in self.presets.items():
            p_in = data.get("num_inputs", 10)
            p_out = data.get("num_outputs", 10)
            if p_in == num_inputs and p_out == num_outputs:
                result.append(name)
        return result

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
