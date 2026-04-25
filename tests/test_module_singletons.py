"""Guard against the 'objc.error: ResetDelegate is overriding existing
Objective-C class' family of bugs.

PyObjC registers NSObject subclasses globally by name. Defining a delegate
class inside a function body works ONCE; the second call crashes silently
inside a worker thread (BrowseDelegate) or aborts the window build
(ResetDelegate). Both bugs caused user-visible regressions in 0.5.x:
- Discover button stopped working after first click
- Settings window refused to reopen after device switch invalidated it

Catching them at import time is enough — if the symbols exist at module
scope, repeat invocations are safe.
"""

from videohub_controller import settings_window
from videohub_controller import connection


def test_reset_delegate_is_module_level():
    assert hasattr(settings_window, "ResetDelegate"), \
        "ResetDelegate must live at module scope; defining it inside " \
        "show_settings_window() crashes PyObjC on the second open."


def test_browse_delegate_helper_is_module_level():
    assert hasattr(connection, "_get_browse_delegate_class"), \
        "Bonjour browse delegate must be defined once at module scope; " \
        "redefining inside discover_videohubs() crashes on the second call."
    cls = connection._get_browse_delegate_class()
    # Calling twice must return the same class (idempotent)
    assert connection._get_browse_delegate_class() is cls


def test_other_settings_delegates_are_module_level():
    # These were already module-level but lock them in
    for name in ("SliderDelegate", "DeviceNameDelegate", "ModelSelectDelegate",
                 "ToggleDelegate", "HotkeyDelegate"):
        assert hasattr(settings_window, name), \
            f"{name} must live at module scope to allow Settings reopen."
