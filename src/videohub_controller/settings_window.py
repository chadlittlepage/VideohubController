"""Settings window with live font-size sliders.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSLeftTextAlignment,
    NSMakeRect,
    NSPopUpButton,
    NSSlider,
    NSTextField,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

BG_DARK = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.12, 0.12, 1.0)
TEXT_WHITE = NSColor.whiteColor()
TEXT_DIM = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.60, 0.60, 0.58, 1.0)

# Default font sizes
DEFAULT_LCD_SIZE = 12.0
DEFAULT_LABEL_SIZE = 11.0
DEFAULT_GRID_HEADER_SIZE = 9.0

_settings_window = None


def invalidate_settings_window():
    """Close and reset the settings window so it rebuilds with fresh preset lists."""
    global _settings_window
    if _settings_window is not None:
        _settings_window.close()
        _settings_window = None


class SliderDelegate(NSObject):
    """Handles slider value changes."""

    key = objc.ivar("key")
    controller = objc.ivar("controller")
    value_label = objc.ivar("value_label")

    @objc.python_method
    def initWithKey_controller_valueLabel_(self, key, controller, value_label):
        self = self.init()
        if self:
            self.key = key
            self.controller = controller
            self.value_label = value_label
        return self

    def sliderChanged_(self, sender):
        val = round(sender.doubleValue(), 1)
        self.value_label.setStringValue_(f"{val} pt")
        self.controller.presets.set_setting(self.key, val)
        self.controller.apply_font_settings()


def _make_label(frame, text, size=12, bold=False, color=TEXT_WHITE):
    tf = NSTextField.alloc().initWithFrame_(frame)
    tf.setStringValue_(text)
    tf.setBezeled_(False)
    tf.setDrawsBackground_(False)
    tf.setEditable_(False)
    tf.setSelectable_(False)
    tf.setTextColor_(color)
    tf.setAlignment_(NSLeftTextAlignment)
    weight = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    tf.setFont_(weight)
    return tf


def _make_slider_row(parent, y, label_text, key, default, min_val, max_val, controller, delegates):
    """Create a label + slider + value display row. Returns the current value."""
    current = controller.presets.get_setting(key, default)

    lbl = _make_label(NSMakeRect(20, y, 200, 20), label_text, size=12, color=TEXT_WHITE)
    parent.addSubview_(lbl)

    value_lbl = _make_label(NSMakeRect(330, y, 50, 20), f"{current} pt", size=11, color=TEXT_DIM)
    parent.addSubview_(value_lbl)

    slider = NSSlider.alloc().initWithFrame_(NSMakeRect(20, y - 28, 360, 28))
    slider.setMinValue_(min_val)
    slider.setMaxValue_(max_val)
    slider.setDoubleValue_(current)
    slider.setContinuous_(True)
    slider.cell().setControlSize_(0)  # NSControlSizeRegular - full size knob

    delegate = SliderDelegate.alloc().initWithKey_controller_valueLabel_(key, controller, value_lbl)
    slider.setTarget_(delegate)
    slider.setAction_(objc.selector(delegate.sliderChanged_, signature=b"v@:@"))
    delegates.append(delegate)
    parent.addSubview_(slider)

    return current


KEY_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
NONE_LABEL = "\u2014 None \u2014"


class ModelSelectDelegate(NSObject):
    """Handles device model popup changes."""

    controller = objc.ivar("controller")

    @objc.python_method
    def initWithController_(self, ctrl):
        self = self.init()
        if self:
            self.controller = ctrl
        return self

    def changed_(self, sender):
        from videohub_controller.connection import MODEL_NAMES, VIDEOHUB_MODELS
        idx = sender.indexOfSelectedItem()
        model_key = MODEL_NAMES[idx]
        self.controller.presets.settings["device_model"] = model_key
        self.controller.presets._write()
        num_in, num_out = VIDEOHUB_MODELS[model_key]
        if model_key != "Auto-Detect" and not self.controller.hub.connected:
            self.controller.hub.num_inputs = num_in
            self.controller.hub.num_outputs = num_out
            self.controller.hub.input_labels = [f"Input {i+1}" for i in range(num_in)]
            self.controller.hub.output_labels = [f"Output {i+1}" for i in range(num_out)]
            self.controller.hub.routing = [0] * num_out
            self.controller._rebuild_io(num_in, num_out)
            self.controller.set_status(f"Set to {model_key} ({num_in}x{num_out})")


class ToggleDelegate(NSObject):
    """Handles checkbox toggle for Keep on Top / Global Hotkeys."""

    controller = objc.ivar("controller")
    setting_key = objc.ivar("setting_key")
    method_name = objc.ivar("method_name")

    @objc.python_method
    def initWithController_key_method_(self, ctrl, key, method):
        self = self.init()
        if self:
            self.controller = ctrl
            self.setting_key = key
            self.method_name = method
        return self

    def toggled_(self, sender):
        on = bool(sender.state())
        self.controller.presets.settings[self.setting_key] = on
        self.controller.presets._write()
        getattr(self.controller, self.method_name)(on)


class HotkeyDelegate(NSObject):
    """Handles hotkey popup selection changes."""

    key = objc.ivar("key")
    controller = objc.ivar("controller")

    @objc.python_method
    def initWithKey_controller_(self, key, controller):
        self = self.init()
        if self:
            self.key = key
            self.controller = controller
        return self

    def popupChanged_(self, sender):
        selected = sender.titleOfSelectedItem()
        if selected == NONE_LABEL:
            self.controller.presets.set_key_binding(self.key, "")
        else:
            self.controller.presets.set_key_binding(self.key, selected)
        self.controller._refresh_preset_popup()
        self.controller._refresh_hotkey_indicators()


def show_settings_window(controller):
    """Show the settings window (singleton)."""
    global _settings_window

    if _settings_window is not None:
        _settings_window.makeKeyAndOrderFront_(None)
        return

    win_w, win_h = 400, 940
    style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable

    from AppKit import NSWindow, NSFloatingWindowLevel
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(300, 300, win_w, win_h), style, NSBackingStoreBuffered, False
    )
    win.setTitle_("Settings")
    win.setBackgroundColor_(BG_DARK)
    from AppKit import NSAppearance
    dark = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
    if dark:
        win.setAppearance_(dark)
    win.setReleasedWhenClosed_(False)
    win.setLevel_(NSFloatingWindowLevel)

    cv = win.contentView()
    delegates = []

    y = win_h - 40
    cv.addSubview_(_make_label(NSMakeRect(20, y, 360, 20), "Device Model", size=14, bold=True))

    y -= 30
    from videohub_controller.connection import MODEL_NAMES, VIDEOHUB_MODELS
    model_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(20, y, 360, 24), False
    )
    model_popup.removeAllItems()
    for name in MODEL_NAMES:
        num_in, num_out = VIDEOHUB_MODELS[name]
        if name == "Auto-Detect":
            model_popup.addItemWithTitle_("Auto-Detect (from hardware)")
        else:
            model_popup.addItemWithTitle_(f"{name}  ({num_in} in / {num_out} out)")
    # Select saved model
    saved_model = controller.presets.settings.get("device_model", "Auto-Detect")
    for i in range(model_popup.numberOfItems()):
        title = str(model_popup.itemTitleAtIndex_(i))
        if title.startswith(saved_model):
            model_popup.selectItemAtIndex_(i)
            break

    model_del = ModelSelectDelegate.alloc().initWithController_(controller)
    model_popup.setTarget_(model_del)
    model_popup.setAction_(objc.selector(model_del.changed_, signature=b"v@:@"))
    delegates.append(model_del)
    cv.addSubview_(model_popup)

    y -= 40
    cv.addSubview_(_make_label(NSMakeRect(20, y, 360, 20), "Font Sizes", size=14, bold=True))

    y -= 50
    _make_slider_row(cv, y, "Display Font Size", "lcd_font_size",
                     DEFAULT_LCD_SIZE, 8, 20, controller, delegates)

    y -= 70
    _make_slider_row(cv, y, "Input/Output Labels Font Size", "label_font_size",
                     DEFAULT_LABEL_SIZE, 8, 18, controller, delegates)

    y -= 70
    _make_slider_row(cv, y, "Grid IN/OUT Header Font Size", "grid_header_font_size",
                     DEFAULT_GRID_HEADER_SIZE, 7, 16, controller, delegates)

    # -- Window & Hotkey Behavior section --
    y -= 50
    cv.addSubview_(_make_label(NSMakeRect(20, y, 360, 20), "Window & Hotkey Behavior", size=14, bold=True))

    y -= 35
    from AppKit import NSButton
    keep_on_top_check = NSButton.alloc().initWithFrame_(NSMakeRect(20, y, 360, 20))
    keep_on_top_check.setButtonType_(3)  # NSSwitchButton
    keep_on_top_check.setTitle_("Keep on Top")
    keep_on_top_check.setFont_(NSFont.systemFontOfSize_(12))
    keep_on_top_check.setState_(
        1 if controller.presets.settings.get("keep_on_top", False) else 0
    )
    kot_delegate = ToggleDelegate.alloc().initWithController_key_method_(
        controller, "keep_on_top", "_apply_keep_on_top"
    )
    keep_on_top_check.setTarget_(kot_delegate)
    keep_on_top_check.setAction_(objc.selector(kot_delegate.toggled_, signature=b"v@:@"))
    delegates.append(kot_delegate)
    cv.addSubview_(keep_on_top_check)

    y -= 16
    cv.addSubview_(_make_label(
        NSMakeRect(36, y, 340, 14),
        "Float above other apps like DaVinci Resolve",
        size=10, color=TEXT_DIM,
    ))

    y -= 30
    global_hk_check = NSButton.alloc().initWithFrame_(NSMakeRect(20, y, 360, 20))
    global_hk_check.setButtonType_(3)  # NSSwitchButton
    global_hk_check.setTitle_("Global Hotkeys")
    global_hk_check.setFont_(NSFont.systemFontOfSize_(12))
    global_hk_check.setState_(
        1 if controller.presets.settings.get("global_hotkeys", False) else 0
    )
    ghk_delegate = ToggleDelegate.alloc().initWithController_key_method_(
        controller, "global_hotkeys", "_apply_global_hotkeys"
    )
    global_hk_check.setTarget_(ghk_delegate)
    global_hk_check.setAction_(objc.selector(ghk_delegate.toggled_, signature=b"v@:@"))
    delegates.append(ghk_delegate)
    cv.addSubview_(global_hk_check)

    y -= 16
    cv.addSubview_(_make_label(
        NSMakeRect(36, y, 340, 14),
        "Keys 1-0 trigger presets even when app is not focused",
        size=10, color=TEXT_DIM,
    ))
    y -= 14
    cv.addSubview_(_make_label(
        NSMakeRect(36, y, 340, 14),
        "System Settings > Privacy & Security > Accessibility",
        size=10, color=TEXT_DIM,
    ))

    # -- Hotkey Presets section --
    y -= 40
    cv.addSubview_(_make_label(NSMakeRect(20, y, 360, 20), "Hotkey Presets", size=14, bold=True))

    y -= 18
    cv.addSubview_(_make_label(
        NSMakeRect(20, y, 360, 16),
        "Press a number key (1-0) to instantly recall a preset",
        size=10, color=TEXT_DIM,
    ))

    bindings = controller.presets.get_key_bindings()
    preset_names = controller.presets.names()

    for i, key_label in enumerate(KEY_LABELS):
        y -= 30
        display_key = key_label
        cv.addSubview_(_make_label(
            NSMakeRect(20, y, 40, 24), f"Key {display_key}:", size=12, color=TEXT_WHITE
        ))

        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(80, y, 300, 24), False
        )
        popup.removeAllItems()
        popup.addItemWithTitle_(NONE_LABEL)
        for name in preset_names:
            popup.addItemWithTitle_(name)

        # Select current binding
        bound_name = bindings.get(key_label, "")
        if bound_name and bound_name in preset_names:
            popup.selectItemWithTitle_(bound_name)
        else:
            popup.selectItemAtIndex_(0)

        hk_delegate = HotkeyDelegate.alloc().initWithKey_controller_(key_label, controller)
        popup.setTarget_(hk_delegate)
        popup.setAction_(objc.selector(hk_delegate.popupChanged_, signature=b"v@:@"))
        delegates.append(hk_delegate)
        cv.addSubview_(popup)

    # prevent GC — store on controller (can't set attrs on NSWindow in bundled app)
    controller._settings_delegates = delegates

    _settings_window = win
    win.center()
    win.makeKeyAndOrderFront_(None)
