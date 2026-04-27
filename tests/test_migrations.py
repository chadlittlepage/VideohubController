"""Forward-compat tests: a config JSON written by an older version of the app
must still load cleanly in the current version, with no exceptions and no
device-registry corruption.

This is the test we wish had existed when v0.5.x ate the 10x10's registry
entry from a stale unique_id. Each shipped config shape goes here as the
last release ships, and the test asserts the current PresetManager can read
it without raising and that the device registry survives untouched.
"""

import json
import pathlib

import pytest

import videohub_controller.presets as presets_mod
from videohub_controller.presets import PresetManager


def _write_cfg(tmp_path, payload):
    p = pathlib.Path(tmp_path) / "videohub_controller.json"
    p.write_text(json.dumps(payload, indent=2))
    return p


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    cfg = pathlib.Path(tmp_path) / "videohub_controller.json"
    monkeypatch.setattr(presets_mod, "CONFIG_PATH", cfg)
    monkeypatch.setattr(presets_mod, "_LEGACY_PATH", cfg.with_suffix(".legacy.json"))
    return cfg


# ---------------------------------------------------------------------------
# Each block below is a real-shape config from a shipped version. Adding a
# new shipped shape here on each release prevents future regressions.
# ---------------------------------------------------------------------------


V040_LEGACY_FLAT = {
    # Pre-multi-device era: a single hub, no devices dict
    "presets": {"My Preset": {"routing": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]}},
    "settings": {
        "device_model": "Videohub 10x10 12G",
        "lcd_font_size": 20.0,
        "label_font_size": 11.0,
        "grid_header_font_size": 16.0,
        "key_bindings": {"1": "My Preset"},
    },
    "session": {
        "routing": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        "input_labels": ["Quad 1", "Quad 2", "Quad 3", "Quad 4",
                         "hold", "hold", "hold", "hold", "hold", "hold"],
        "output_labels": ["XMP550 (1)", "XMP550 (2)", "XMP551 (1)", "XMP550 (3)",
                          "TV1", "TV2", "TV3", "TV4", "hold", "hold"],
    },
    "last_ip": "10.203.188.57",
}


V050_MULTI_DEVICE = {
    "presets": {},
    "settings": {"device_model": "Videohub 10x10 12G"},
    "session": {},
    "last_ip": "10.203.188.57",
    "last_device_id": "11E8065C84EE4B2EBC5B62C24D3EF533",
    "devices": {
        "11E8065C84EE4B2EBC5B62C24D3EF533": {
            "friendly_name": "Blackmagic Videohub 10x10 12G",
            "model_name": "Blackmagic Videohub 10x10 12G",
            "ip": "10.203.188.57",
            "num_inputs": 10, "num_outputs": 10,
            "presets": {"1 Preset": {"routing": [0] * 10}},
            "settings": {"key_bindings": {"1": "1 Preset"}},
            "session": {},
        },
        "5A34FA412C6245189EAAE25A8434266D": {
            "friendly_name": "Videohub Mini 8x4 12G",
            "model_name": "Videohub Mini 8x4 12G",
            "ip": "169.254.205.84",
            "num_inputs": 8, "num_outputs": 4,
            "presets": {},
            "settings": {},
            "session": {},
        },
    },
}


V052_WITH_LEGACY_ENTRY = {
    # User upgraded mid-cycle and has BOTH a legacy entry and a real device
    "presets": {},
    "settings": {},
    "session": {},
    "last_ip": "",
    "last_device_id": "11E8065C84EE4B2EBC5B62C24D3EF533",
    "devices": {
        "legacy": {
            "friendly_name": "", "model_name": "", "ip": "",
            "num_inputs": 10, "num_outputs": 10,
            "presets": {"Old": {"routing": [0] * 10}},
            "settings": {},
            "session": {},
        },
        "11E8065C84EE4B2EBC5B62C24D3EF533": {
            "friendly_name": "Blackmagic Videohub 10x10 12G",
            "model_name": "Blackmagic Videohub 10x10 12G",
            "ip": "10.203.188.57",
            "num_inputs": 10, "num_outputs": 10,
            "presets": {}, "settings": {}, "session": {},
        },
    },
}


@pytest.mark.parametrize("payload", [V040_LEGACY_FLAT, V050_MULTI_DEVICE, V052_WITH_LEGACY_ENTRY])
def test_old_config_loads_without_error(isolated_paths, payload):
    isolated_paths.write_text(json.dumps(payload, indent=2))
    pm = PresetManager()  # MUST NOT raise
    # Whatever the source shape, get_known_devices must return a usable dict
    devs = pm.get_known_devices()
    assert isinstance(devs, dict)


def test_v050_devices_survive_load(isolated_paths):
    isolated_paths.write_text(json.dumps(V050_MULTI_DEVICE, indent=2))
    pm = PresetManager()
    devs = pm.get_known_devices()
    assert "11E8065C84EE4B2EBC5B62C24D3EF533" in devs
    assert "5A34FA412C6245189EAAE25A8434266D" in devs

    # The 10x10 must still claim 10x10 — guards against the v0.5.0 bug where
    # switching devices clobbered the OLD device's registry entry with the
    # NEW device's IO count and an empty model name.
    tenx10 = devs["11E8065C84EE4B2EBC5B62C24D3EF533"]
    assert tenx10["model_name"] == "Blackmagic Videohub 10x10 12G"
    assert tenx10["num_inputs"] == 10
    assert tenx10["num_outputs"] == 10
    assert tenx10["ip"] == "10.203.188.57"

    # The 8x4 must still claim 8x4
    eightx4 = devs["5A34FA412C6245189EAAE25A8434266D"]
    assert eightx4["model_name"] == "Videohub Mini 8x4 12G"
    assert eightx4["num_inputs"] == 8
    assert eightx4["num_outputs"] == 4


def test_v040_flat_config_does_not_lose_session(isolated_paths):
    isolated_paths.write_text(json.dumps(V040_LEGACY_FLAT, indent=2))
    pm = PresetManager()
    # v0.4.0 had no devices dict — session lived at top level. Loader must
    # preserve it so labels survive the upgrade.
    assert pm.session.get("input_labels", [])[0] == "Quad 1"
    assert pm.session.get("output_labels", [])[0] == "XMP550 (1)"
    assert pm.last_ip == "10.203.188.57"


def test_save_after_load_does_not_corrupt(isolated_paths):
    """Round-trip: load a real shape, save state for one device, reload, and
    confirm the OTHER device is untouched. This is the regression guard for
    the 'switch devices and lose the 10x10' bug."""
    isolated_paths.write_text(json.dumps(V050_MULTI_DEVICE, indent=2))
    pm = PresetManager()
    # Simulate connecting to the 8x4 and writing its current state
    pm.save_device_state(
        "5A34FA412C6245189EAAE25A8434266D",
        friendly_name="Videohub Mini 8x4 12G",
        model_name="Videohub Mini 8x4 12G",
        ip="169.254.205.84",
        num_inputs=8, num_outputs=4,
    )
    # Now reload from disk and check the 10x10 entry is unchanged
    pm2 = PresetManager()
    tenx10 = pm2.get_known_devices()["11E8065C84EE4B2EBC5B62C24D3EF533"]
    assert tenx10["model_name"] == "Blackmagic Videohub 10x10 12G"
    assert tenx10["num_inputs"] == 10
    assert tenx10["ip"] == "10.203.188.57"
