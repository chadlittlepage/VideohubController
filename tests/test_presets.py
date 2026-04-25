"""Tests for the per-device presets/registry layer.

Specifically guards against the bugs hit during 0.5.x development:
- save_device_state writing one device's data under another device's uid
- register_device_metadata clobbering existing presets/sessions
- get_known_devices returning a live reference that callers could mutate
"""

import pathlib

import pytest

import videohub_controller.presets as presets_mod
from videohub_controller.presets import PresetManager


@pytest.fixture
def pm(tmp_path, monkeypatch):
    cfg = pathlib.Path(tmp_path) / "videohub_controller.json"
    # The PresetManager looks at module-level CONFIG_PATH (pathlib.Path)
    monkeypatch.setattr(presets_mod, "CONFIG_PATH", cfg)
    monkeypatch.setattr(presets_mod, "_LEGACY_PATH", cfg.with_suffix(".legacy.json"))
    return PresetManager()


def test_save_device_state_isolates_devices(pm):
    pm.save_device_state(
        "uid_A", friendly_name="A", model_name="Videohub 10x10 12G",
        ip="10.0.0.1", num_inputs=10, num_outputs=10,
    )
    pm.save_device_state(
        "uid_B", friendly_name="B", model_name="Videohub Mini 8x4 12G",
        ip="169.254.0.1", num_inputs=8, num_outputs=4,
    )
    devs = pm.get_known_devices()
    assert devs["uid_A"]["model_name"] == "Videohub 10x10 12G"
    assert devs["uid_A"]["ip"] == "10.0.0.1"
    assert devs["uid_A"]["num_inputs"] == 10
    assert devs["uid_B"]["model_name"] == "Videohub Mini 8x4 12G"
    assert devs["uid_B"]["ip"] == "169.254.0.1"
    assert devs["uid_B"]["num_outputs"] == 4


def test_register_device_metadata_creates_then_upserts(pm):
    changed = pm.register_device_metadata(
        "uid_X", model_name="Videohub 10x10 12G",
        ip="10.0.0.1", num_inputs=10, num_outputs=10,
    )
    assert changed is True
    assert "uid_X" in pm.devices

    # Same metadata: no change reported, no rewrite
    changed = pm.register_device_metadata(
        "uid_X", model_name="Videohub 10x10 12G",
        ip="10.0.0.1", num_inputs=10, num_outputs=10,
    )
    assert changed is False

    # IP changed (DHCP shuffle): updates ip but preserves model
    changed = pm.register_device_metadata("uid_X", ip="10.0.0.2")
    assert changed is True
    assert pm.devices["uid_X"]["ip"] == "10.0.0.2"
    assert pm.devices["uid_X"]["model_name"] == "Videohub 10x10 12G"


def test_register_metadata_does_not_clobber_presets(pm):
    pm.save_device_state(
        "uid_X", model_name="Videohub 10x10 12G",
        ip="10.0.0.1", num_inputs=10, num_outputs=10,
    )
    pm.devices["uid_X"]["presets"] = {"My Preset": {"routing": [0, 1, 2]}}
    pm._write()

    # Re-registering should NOT wipe presets
    pm.register_device_metadata("uid_X", model_name="Videohub 10x10 12G",
                                ip="10.0.0.99")
    assert pm.devices["uid_X"]["presets"] == {"My Preset": {"routing": [0, 1, 2]}}
    assert pm.devices["uid_X"]["ip"] == "10.0.0.99"


def test_register_metadata_with_empty_uid_is_noop(pm):
    assert pm.register_device_metadata("") is False
    assert pm.devices == {}


def test_get_known_devices_returns_copy(pm):
    pm.save_device_state("uid_X", model_name="A", num_inputs=10, num_outputs=10)
    devs = pm.get_known_devices()
    devs["uid_X"]["model_name"] = "MUTATED"
    # Underlying registry must be unchanged
    assert pm.devices["uid_X"]["model_name"] == "A"


def test_load_device_state_round_trip(pm):
    pm.save_device_state("uid_X", model_name="A", ip="1.1.1.1",
                         num_inputs=10, num_outputs=10)
    pm.devices["uid_X"]["presets"] = {"P": {"routing": [3, 2, 1]}}
    pm._write()

    pm.presets = {}
    loaded = pm.load_device_state("uid_X")
    assert loaded is True
    assert pm.presets == {"P": {"routing": [3, 2, 1]}}
