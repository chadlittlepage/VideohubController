"""Guard the disconnect-clears-identity invariant.

If VideohubConnection.disconnect() leaves unique_id/model_name set, the next
connect-to-different-device's _on_device_identified() callback fires with the
PREVIOUS hub's unique_id and writes the new device's data into the old
device's registry slot. That bug ate the user's 10x10 entry in 0.5.0.
"""

from videohub_controller.connection import VideohubConnection


def test_disconnect_clears_identification_fields():
    conn = VideohubConnection()
    conn.unique_id = "DEAD_BEEF_OLD_HUB_UID"
    conn.model_name = "Blackmagic Videohub 10x10 12G"
    conn.friendly_name = "Edit Suite A"
    conn.device_present = True
    conn.connected = True

    conn.disconnect()

    assert conn.unique_id == "", \
        "unique_id must be reset on disconnect or the next connect's " \
        "identification callback will write the new device's data under " \
        "this old uid."
    assert conn.model_name == ""
    assert conn.friendly_name == ""
    assert conn.device_present is False
    assert conn.connected is False
