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


# Settings keys that are app-wide, NOT per-device
_GLOBAL_SETTINGS = {"keep_on_top", "global_hotkeys"}


class PresetManager:
    """Save and recall routing presets to disk."""

    def __init__(self) -> None:
        self.presets: dict = {}
        self.last_ip: str = ""
        self.settings: dict = {}
        self.session: dict = {}
        self.devices: dict = {}
        self.last_device_id: str = ""
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
                self.devices = data.get("devices", {})
                self.last_device_id = data.get("last_device_id", "")
                # Migrate pre-multi-device config: create a "legacy" device entry
                if not self.devices and (self.presets or self.session):
                    self.devices["legacy"] = {
                        "friendly_name": "",
                        "model_name": self.settings.get("device_model", ""),
                        "ip": self.last_ip,
                        "num_inputs": 10,
                        "num_outputs": 10,
                        "presets": dict(self.presets),
                        "settings": {k: v for k, v in self.settings.items()
                                     if k not in _GLOBAL_SETTINGS},
                        "session": dict(self.session),
                    }
                    self.last_device_id = "legacy"
                    print(f"[presets] Migrated config to multi-device format (legacy entry)")
                n_devices = len(self.devices)
                print(f"[presets] Loaded config: {len(self.presets)} presets, ip={self.last_ip}, "
                      f"model={self.settings.get('device_model', 'Auto-Detect')}, "
                      f"{n_devices} known device(s)")
            except Exception as e:
                print(f"[presets] Failed to load config: {e}")
        else:
            print(f"[presets] No config file found at {CONFIG_PATH}")

    def _write(self) -> None:
        data = {
            "last_ip": self.last_ip,
            "last_device_id": self.last_device_id,
            "presets": self.presets,
            "settings": self.settings,
            "session": self.session,
            "devices": self.devices,
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

    # -- Multi-device support --

    def save_device_state(self, unique_id: str, friendly_name: str = "",
                          model_name: str = "", ip: str = "",
                          num_inputs: int = 10, num_outputs: int = 10) -> None:
        """Snapshot current top-level presets/settings/session into devices[unique_id]."""
        # Preserve global settings (not per-device)
        device_settings = {k: v for k, v in self.settings.items()
                           if k not in _GLOBAL_SETTINGS}
        self.devices[unique_id] = {
            "friendly_name": friendly_name,
            "model_name": model_name,
            "ip": ip,
            "num_inputs": num_inputs,
            "num_outputs": num_outputs,
            "presets": dict(self.presets),
            "settings": device_settings,
            "session": dict(self.session),
        }
        self.last_device_id = unique_id
        # Remove legacy entry if we now have a real ID
        if unique_id != "legacy" and "legacy" in self.devices:
            del self.devices["legacy"]
            print(f"[presets] Migrated legacy device -> {unique_id}")
        self._write()
        print(f"[presets] Saved device state: {unique_id} ({model_name or friendly_name})")

    def load_device_state(self, unique_id: str) -> bool:
        """Load devices[unique_id] into top-level presets/settings/session.
        Returns True if device was found, False if new/unknown device."""
        dev = self.devices.get(unique_id)
        if not dev:
            print(f"[presets] No saved state for device {unique_id}")
            return False
        # Load per-device data into top-level (working copy)
        self.presets = dict(dev.get("presets", {}))
        # Merge device settings with global settings
        global_vals = {k: self.settings[k] for k in _GLOBAL_SETTINGS
                       if k in self.settings}
        self.settings = dict(dev.get("settings", {}))
        self.settings.update(global_vals)
        self.session = dict(dev.get("session", {}))
        self.last_ip = dev.get("ip", self.last_ip)
        self.last_device_id = unique_id
        self._write()
        print(f"[presets] Loaded device state: {unique_id} "
              f"({dev.get('model_name', '')} — {len(self.presets)} presets)")
        return True

    def get_known_devices(self) -> dict:
        """Return the devices dict {unique_id: {friendly_name, model_name, ip, ...}}."""
        return dict(self.devices)

    def get_last_device_id(self) -> str:
        return self.last_device_id

    def set_last_device_id(self, unique_id: str) -> None:
        self.last_device_id = unique_id
        self._write()
