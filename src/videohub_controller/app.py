"""Native macOS Cocoa GUI for Videohub Controller.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import math
import time
import threading

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSBox,
    NSBoxSeparator,
    NSButton,
    NSCenterTextAlignment,
    NSColor,
    NSEvent,
    NSFont,
    NSKeyDownMask,
    NSLeftTextAlignment,
    NSLineBreakByTruncatingTail,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSPopUpButton,
    NSRightTextAlignment,
    NSTextField,
    NSTextFieldCell,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
from Quartz import CGColorCreateGenericRGB

from videohub_controller import __version__
from videohub_controller.connection import (
    VideohubConnection, NUM_IO,
)
from videohub_controller.about_window import show_about_window
from Quartz import CATransaction
from videohub_controller.console_log import setup_logging, get_log_path
from videohub_controller.manual_window import show_manual_window
from videohub_controller.presets import PresetManager
from videohub_controller.settings_window import (
    show_settings_window,
    invalidate_settings_window,
    refresh_hotkey_popups,
    refresh_font_sliders,
    DEFAULT_LCD_SIZE,
    DEFAULT_LABEL_SIZE,
    DEFAULT_GRID_HEADER_SIZE,
)


def _cg(r, g, b, a=1.0):
    """Create a CGColor from RGBA values."""
    return CGColorCreateGenericRGB(r, g, b, a)


def _colored_view(frame, r, g, b, corner_radius=0):
    """Create an NSView with a layer-backed background color."""
    v = NSView.alloc().initWithFrame_(frame)
    v.setWantsLayer_(True)
    v.layer().setBackgroundColor_(_cg(r, g, b))
    if corner_radius > 0:
        v.layer().setCornerRadius_(corner_radius)
        v.layer().setMasksToBounds_(True)
    return v

# -- Colors (grey + yellow) -- raw RGBA tuples for CGColor, NSColor for text --
BG_DARK_RGB = (0.12, 0.12, 0.12)
BG_PANEL_RGB = (0.17, 0.17, 0.17)
HEADER_BG_RGB = (0.06, 0.06, 0.06)
INACTIVE_RGB = (0.22, 0.22, 0.22)

BG_DARK = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.12, 0.12, 1.0)
TEXT_WHITE = NSColor.whiteColor()
TEXT_DIM = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.60, 0.60, 0.58, 1.0)
GREEN = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.78, 0.33, 1.0)
RED = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.91, 0.27, 0.38, 1.0)
FIELD_BG = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.14, 0.14, 0.14, 1.0)

# Layout
MATRIX_CELL = 52
def _strip_hotkey_prefix(title: str) -> str:
    """Extract preset name from dropdown title like '[2]  My Preset' or 'My Preset'."""
    if title.startswith("[") and "]  " in title:
        return title.split("]  ", 1)[1]
    return title

LABEL_COL_W = 230
HEADER_H = 70
CONN_BAR_H = 44
ROW_LABEL_W = 100
BOTTOM_BAR_H = 28


class VCenterCell(NSTextFieldCell):
    """NSTextFieldCell that vertically centers its text."""

    def titleRectForBounds_(self, rect):
        r = objc.super(VCenterCell, self).titleRectForBounds_(rect)
        text_h = self.cellSizeForBounds_(rect).height
        offset = (rect.size.height - text_h) / 2.0
        return NSMakeRect(r.origin.x, rect.origin.y + offset, r.size.width, text_h)

    def drawInteriorWithFrame_inView_(self, frame, view):
        objc.super(VCenterCell, self).drawInteriorWithFrame_inView_(
            self.titleRectForBounds_(frame), view
        )

    def editWithFrame_inView_editor_delegate_event_(self, rect, view, editor, delegate, event):
        objc.super(VCenterCell, self).editWithFrame_inView_editor_delegate_event_(
            self.titleRectForBounds_(rect), view, editor, delegate, event
        )

    def selectWithFrame_inView_editor_delegate_start_length_(self, rect, view, editor, delegate, start, length):
        objc.super(VCenterCell, self).selectWithFrame_inView_editor_delegate_start_length_(
            self.titleRectForBounds_(rect), view, editor, delegate, start, length
        )


def _label(frame, text, size=12, bold=False, color=TEXT_WHITE, align=NSLeftTextAlignment):
    """Create a non-editable text label with vertically centered text."""
    tf = NSTextField.alloc().initWithFrame_(frame)
    cell = VCenterCell.alloc().initTextCell_(text)
    tf.setCell_(cell)
    tf.setStringValue_(text)
    tf.setBezeled_(False)
    tf.setDrawsBackground_(False)
    tf.setEditable_(False)
    tf.setSelectable_(False)
    tf.setTextColor_(color)
    tf.setAlignment_(align)
    weight = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    tf.setFont_(weight)
    return tf


# Map wrapper view id -> NSTextField for _editable fields
_WRAPPER_FIELDS = {}


def _editable(frame, text="", placeholder="", size=12):
    """Create an editable text field. Returns (tf, tf) for backward compat."""
    tf = NSTextField.alloc().initWithFrame_(frame)
    cell = VCenterCell.alloc().initTextCell_(text)
    cell.setEditable_(True)
    cell.setScrollable_(False)
    tf.setCell_(cell)
    tf.setStringValue_(text)
    tf.setPlaceholderString_(placeholder)
    tf.setFont_(NSFont.systemFontOfSize_(size))
    tf.setBezeled_(True)
    tf.setBezelStyle_(1)  # NSTextFieldSquareBezel
    tf.setDrawsBackground_(True)
    tf.setBackgroundColor_(FIELD_BG)
    tf.setTextColor_(TEXT_WHITE)
    tf.setEditable_(True)
    tf.setFocusRingType_(1)  # NSFocusRingTypeNone
    return tf, tf


CROSSHAIR_COLOR = _cg(0.90, 0.78, 0.10, 0.45)  # yellow, semi-transparent


class PassthroughView(NSView):
    """An NSView that ignores all mouse clicks (passes them through)."""

    def hitTest_(self, point):
        return None


class FlippedView(NSView):
    """NSView with y=0 at the top. Used as NSScrollView document view."""

    def isFlipped(self):
        return True


class MatrixOverlayView(NSView):
    """Transparent overlay that tracks mouse movement over the grid."""

    def initWithFrame_(self, frame):
        self = objc.super(MatrixOverlayView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = None
        self._tracking_area = None
        self._setup_tracking()
        return self

    def _setup_tracking(self):
        from AppKit import NSTrackingArea
        if self._tracking_area:
            self.removeTrackingArea_(self._tracking_area)
        self._tracking_area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(),
            0x01 | 0x02 | 0x20,  # MouseMoved | MouseEnteredAndExited | ActiveInKeyWindow
            self,
            None,
        )
        self.addTrackingArea_(self._tracking_area)

    def updateTrackingAreas(self):
        objc.super(MatrixOverlayView, self).updateTrackingAreas()
        self._setup_tracking()

    @objc.python_method
    def setController_(self, controller):
        self._controller = controller

    def hitTest_(self, point):
        # Return None so clicks pass through to the matrix buttons underneath
        return None

    def mouseMoved_(self, event):
        if self._controller:
            pt = self.convertPoint_fromView_(event.locationInWindow(), None)
            self._controller._handle_matrix_hover(pt)

    def mouseExited_(self, event):
        if self._controller:
            self._controller._hide_crosshairs()


class PresetPopUpButton(NSPopUpButton):
    """NSPopUpButton that shows a Rename context menu on right-click."""

    _controller = objc.ivar("_controller")

    @objc.python_method
    def _showRenameMenu(self, event):
        if self.indexOfSelectedItem() <= 0:
            return
        from AppKit import NSMenu, NSMenuItem
        ctx = NSMenu.alloc().init()
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Rename\u2026", "renamePresetFromMenu:", ""
        )
        item.setTarget_(self._controller)
        ctx.addItem_(item)
        NSMenu.popUpContextMenu_withEvent_forView_(ctx, event, self)

    def rightMouseDown_(self, event):
        self._showRenameMenu(event)

    def mouseDown_(self, event):
        # Control-click = right-click
        if event.modifierFlags() & (1 << 18):  # NSEventModifierFlagControl
            self._showRenameMenu(event)
        else:
            objc.super(PresetPopUpButton, self).mouseDown_(event)


class DevicePopUpButton(NSPopUpButton):
    """NSPopUpButton that shows a Rename context menu on right-click."""

    _controller = objc.ivar("_controller")

    @objc.python_method
    def _showRenameMenu(self, event):
        idx = self.indexOfSelectedItem()
        ids = getattr(self._controller, '_device_popup_ids', [])
        if idx < 0 or idx >= len(ids) or ids[idx] is None:
            return
        from AppKit import NSMenu, NSMenuItem
        ctx = NSMenu.alloc().init()
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Rename\u2026", "renameDeviceFromMenu:", ""
        )
        item.setTarget_(self._controller)
        ctx.addItem_(item)
        NSMenu.popUpContextMenu_withEvent_forView_(ctx, event, self)

    def rightMouseDown_(self, event):
        self._showRenameMenu(event)

    def mouseDown_(self, event):
        if event.modifierFlags() & (1 << 18):  # Control-click
            self._showRenameMenu(event)
        else:
            objc.super(DevicePopUpButton, self).mouseDown_(event)


class MatrixButton(NSButton):
    """A crosspoint matrix button that knows its output/input indices."""

    output_idx = objc.ivar("output_idx", objc._C_INT)
    input_idx = objc.ivar("input_idx", objc._C_INT)

    def hitTest_(self, point):
        # Unborderd buttons only hit-test on the title text area.
        # Override to accept clicks anywhere within the full button frame.
        if self.isHidden():
            return None
        local = self.convertPoint_fromView_(point, self.superview())
        if 0 <= local.x <= self.bounds().size.width and 0 <= local.y <= self.bounds().size.height:
            return self
        return None


class InputLabelDelegate(NSObject):
    """Handles Return/focus-out on input label fields."""

    idx = objc.ivar("idx", objc._C_INT)
    controller = objc.ivar("controller")

    @objc.python_method
    def initWithIndex_controller_(self, idx, controller):
        self = self.init()
        if self:
            self.idx = idx
            self.controller = controller
        return self

    def controlTextDidEndEditing_(self, notification):
        tf = notification.object()
        new_name = tf.stringValue().strip()
        if new_name:
            old_name = self.controller.hub.input_labels[self.idx] if self.idx < len(self.controller.hub.input_labels) else ""
            self.controller.hub.set_input_label(self.idx, new_name)
            self.controller.refresh_matrix_headers()
            self.controller.set_status(f"Renamed Input {self.idx + 1}: {new_name}")
            print(f"[label] Input {self.idx + 1}: '{old_name}' -> '{new_name}' (sent={'yes' if self.controller.hub.connected else 'offline'})")
            # Refresh LCD if this input is currently displayed
            if self.controller._lcd_selected_out is not None:
                self.controller._update_lcd(self.controller._lcd_selected_out)
        # Only resign focus on Return (16), not Tab (17) or click-away
        movement = notification.userInfo().get("NSTextMovement", 0)
        if movement == 16:  # NSReturnTextMovement
            self.controller.performSelector_withObject_afterDelay_(
                objc.selector(self.controller.resignFocus_, signature=b"v@:@"), None, 0.0
            )


class OutputLabelDelegate(NSObject):
    """Handles Return/focus-out on output label fields."""

    idx = objc.ivar("idx", objc._C_INT)
    controller = objc.ivar("controller")

    @objc.python_method
    def initWithIndex_controller_(self, idx, controller):
        self = self.init()
        if self:
            self.idx = idx
            self.controller = controller
        return self

    def controlTextDidEndEditing_(self, notification):
        tf = notification.object()
        new_name = tf.stringValue().strip()
        if new_name:
            old_name = self.controller.hub.output_labels[self.idx] if self.idx < len(self.controller.hub.output_labels) else ""
            self.controller.hub.set_output_label(self.idx, new_name)
            self.controller.refresh_matrix_headers()
            self.controller.set_status(f"Renamed Output {self.idx + 1}: {new_name}")
            print(f"[label] Output {self.idx + 1}: '{old_name}' -> '{new_name}' (sent={'yes' if self.controller.hub.connected else 'offline'})")
            # Refresh LCD if this output is currently displayed
            if self.controller._lcd_selected_out is not None:
                self.controller._update_lcd(self.controller._lcd_selected_out)
        movement = notification.userInfo().get("NSTextMovement", 0)
        if movement == 16:  # NSReturnTextMovement
            self.controller.performSelector_withObject_afterDelay_(
                objc.selector(self.controller.resignFocus_, signature=b"v@:@"), None, 0.0
            )


class AppController(NSObject):
    """Main application controller."""

    def init(self):
        self = objc.super(AppController, self).init()
        if self is None:
            return None

        self.presets = PresetManager()
        # Apply saved device model for initial I/O size
        from videohub_controller.connection import VIDEOHUB_MODELS
        saved_model = self.presets.settings.get("device_model", "Auto-Detect")
        init_in, init_out = VIDEOHUB_MODELS.get(saved_model, (NUM_IO, NUM_IO))
        print(f"[app] Init model={saved_model} ({init_in}x{init_out})")
        self.hub = VideohubConnection(
            on_state_update=self._on_state_update,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            num_inputs=init_in,
            num_outputs=init_out,
        )
        self.matrix_buttons: dict[tuple[int, int], MatrixButton] = {}
        self.col_headers: list[NSTextField] = []
        self.row_headers: list[NSTextField] = []
        self.input_entries: list[NSTextField] = []
        self.output_entries: list[NSTextField] = []
        self._label_delegates: list = []  # prevent GC
        self._active_hotkey: str | None = None
        self._lcd_idle: bool = True
        self._last_window_size: tuple = (0, 0)
        self._num_inputs: int = self.hub.num_inputs
        self._num_outputs: int = self.hub.num_outputs
        self._current_device_id: str | None = self.presets.get_last_device_id() or None
        self._device_identified: bool = False
        self._discovered_devices: list = []  # cache of last discovery results

        self._build_window()
        self._install_key_monitor()
        return self

    def _build_window(self):
        # Autoresizing mask constants
        W_SIZABLE = 2        # NSViewWidthSizable
        H_SIZABLE = 16       # NSViewHeightSizable
        MIN_Y = 8            # NSViewMinYMargin
        MAX_Y = 32           # NSViewMaxYMargin

        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        n_in = self.hub.num_inputs
        n_out = self.hub.num_outputs
        win_w = max(920, min(1400, LABEL_COL_W + ROW_LABEL_W + (n_in * (MATRIX_CELL + 2)) + 60))
        win_h = min(900, HEADER_H + CONN_BAR_H + 40 + (n_out * (MATRIX_CELL + 2)) + 80 + BOTTOM_BAR_H)

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(200, 100, win_w, win_h),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_(f"Videohub Controller v{__version__}")
        # Remember window size/position across launches
        self.window.setFrameAutosaveName_("VideohubControllerMain")
        # Min height: capped so large grids don't force a huge window
        min_h = HEADER_H + CONN_BAR_H + 300 + BOTTOM_BAR_H
        self.window.setMinSize_((920, min_h))
        self.window.setBackgroundColor_(BG_DARK)
        # Force dark appearance so the app looks correct even in light mode
        from AppKit import NSAppearance
        dark = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
        if dark:
            self.window.setAppearance_(dark)

        cv = self.window.contentView()
        cv.setAutoresizesSubviews_(True)
        content_h = int(cv.frame().size.height)
        content_w = int(cv.frame().size.width)

        y = content_h

        # -- Title bar area (pin to top, stretch width) --
        y -= HEADER_H
        self.title_bg = _colored_view(NSMakeRect(0, y, content_w, HEADER_H), *HEADER_BG_RGB)
        self.title_bg.setAutoresizingMask_(W_SIZABLE | MIN_Y)
        self.title_bg.setAutoresizesSubviews_(False)
        cv.addSubview_(self.title_bg)

        self.title_label = _label(
            NSMakeRect(20, 12, 300, 24),
            "VIDEOHUB CONTROLLER", size=16, bold=True, color=TEXT_WHITE,
        )
        self.title_bg.addSubview_(self.title_label)

        self.status_label = _label(
            NSMakeRect(content_w - 200, 12, 180, 24),
            "Disconnected", size=12, color=TEXT_DIM, align=NSRightTextAlignment,
        )
        self.title_bg.addSubview_(self.status_label)

        self.status_dot = _label(
            NSMakeRect(content_w - 130, 12, 20, 24),
            "\u25cf", size=14, color=RED, align=NSCenterTextAlignment,
        )
        self.title_bg.addSubview_(self.status_dot)

        # -- LCD route display (centered in title bar, horizontal layout) --
        lcd_w = 300
        lcd_h = 46
        lcd_x = (content_w - lcd_w) // 2
        lcd_y = (HEADER_H - lcd_h) // 2

        self.lcd_view = NSView.alloc().initWithFrame_(NSMakeRect(lcd_x, lcd_y, lcd_w, lcd_h))
        self.lcd_view.setWantsLayer_(True)
        self.lcd_view.layer().setCornerRadius_(5)
        self.lcd_view.layer().setBackgroundColor_(_cg(0.08, 0.10, 0.07))
        self.lcd_view.setAutoresizesSubviews_(False)
        self.title_bg.addSubview_(self.lcd_view)

        lcd_dim = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.55, 0.50, 1.0)
        lcd_bright = TEXT_WHITE

        # Source row: header left, name right
        self.lcd_src_header = _label(
            NSMakeRect(0, 0, 120, 18), "", size=9, bold=True, color=lcd_dim,
        )
        self.lcd_view.addSubview_(self.lcd_src_header)

        self.lcd_src_name = _label(
            NSMakeRect(0, 0, 240, 18), "", size=13, bold=True, color=lcd_bright,
        )
        self.lcd_view.addSubview_(self.lcd_src_name)

        # Divider line
        self.lcd_divider = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 1))
        self.lcd_divider.setWantsLayer_(True)
        self.lcd_divider.layer().setBackgroundColor_(_cg(0.30, 0.30, 0.28))
        self.lcd_view.addSubview_(self.lcd_divider)

        # Destination row: header left, name right
        self.lcd_dest_header = _label(
            NSMakeRect(0, 0, 120, 18), "", size=9, bold=True, color=lcd_dim,
        )
        self.lcd_view.addSubview_(self.lcd_dest_header)

        self.lcd_dest_name = _label(
            NSMakeRect(0, 0, 240, 18), "", size=13, bold=True, color=lcd_bright,
        )
        self.lcd_view.addSubview_(self.lcd_dest_name)

        # Hover position indicator (right side of LCD, yellow)
        lcd_hover_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.90, 0.78, 0.10, 1.0)
        self.lcd_hover_label = _label(
            NSMakeRect(0, 0, 100, 40), "", size=15, bold=True, color=lcd_hover_color,
            align=NSRightTextAlignment,
        )
        self.lcd_view.addSubview_(self.lcd_hover_label)

        self._lcd_selected_out = None
        self._update_lcd_idle()

        # -- Connection bar (pin to top, stretch width) --
        y -= CONN_BAR_H
        self.conn_bg = _colored_view(NSMakeRect(0, y, content_w, CONN_BAR_H), *BG_PANEL_RGB)
        self.conn_bg.setAutoresizingMask_(W_SIZABLE | MIN_Y)
        cv.addSubview_(self.conn_bg)

        lx = 10
        self.conn_bg.addSubview_(
            _label(NSMakeRect(lx, 10, 30, 24), "IP:", size=12, color=TEXT_DIM)
        )
        lx += 30

        ip_wrapper, self.ip_field = _editable(NSMakeRect(lx, 10, 140, 24), placeholder="192.168.1.100")
        self.conn_bg.addSubview_(ip_wrapper)
        lx += 145

        self.connect_btn = NSButton.alloc().initWithFrame_(NSMakeRect(lx, 8, 90, 28))
        self.connect_btn.setTitle_("Connect")
        self.connect_btn.setBezelStyle_(NSBezelStyleRounded)
        self.connect_btn.setTarget_(self)
        self.connect_btn.setAction_(objc.selector(self.toggleConnection_, signature=b"v@:@"))
        self.conn_bg.addSubview_(self.connect_btn)
        lx += 95

        self.discover_btn = NSButton.alloc().initWithFrame_(NSMakeRect(lx, 8, 80, 28))
        self.discover_btn.setTitle_("Discover")
        self.discover_btn.setBezelStyle_(NSBezelStyleRounded)
        self.discover_btn.setTarget_(self)
        self.discover_btn.setAction_(objc.selector(self.discoverDevices_, signature=b"v@:@"))
        self.conn_bg.addSubview_(self.discover_btn)

        # Right-side controls: laid out right-to-left, all pinned to right edge
        r = content_w
        gap = 5
        x = r - 12

        x -= 65
        del_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 65, 28))
        del_btn.setTitle_("Delete")
        del_btn.setBezelStyle_(NSBezelStyleRounded)
        del_btn.setTarget_(self)
        del_btn.setAction_(objc.selector(self.deletePreset_, signature=b"v@:@"))
        del_btn.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(del_btn)

        x -= gap + 58
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 58, 28))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_(objc.selector(self.savePreset_, signature=b"v@:@"))
        save_btn.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(save_btn)

        x -= gap + 65
        recall_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 65, 28))
        recall_btn.setTitle_("Recall")
        recall_btn.setBezelStyle_(NSBezelStyleRounded)
        recall_btn.setTarget_(self)
        recall_btn.setAction_(objc.selector(self.recallPreset_, signature=b"v@:@"))
        recall_btn.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(recall_btn)

        x -= gap + 150
        self.preset_popup = PresetPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, 8, 150, 28), False
        )
        self.preset_popup._controller = self
        self.preset_popup.setBezelStyle_(1)
        self._refresh_preset_popup()
        self.preset_popup.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(self.preset_popup)

        x -= gap + 180
        self.device_popup = DevicePopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, 8, 180, 28), False
        )
        self.device_popup._controller = self
        self.device_popup.setTarget_(self)
        self.device_popup.setAction_(objc.selector(self.deviceSelected_, signature=b"v@:@"))
        self.device_popup.setAutoresizingMask_(1)  # pin to right
        self.conn_bg.addSubview_(self.device_popup)
        self._refresh_device_popup()

        # -- Main area (labels + matrix) -- built dynamically
        y -= 4
        self._main_area_top = y
        self._cv_autoresize_W = W_SIZABLE
        self._cv_autoresize_H = H_SIZABLE
        self._cv_autoresize_MIN_Y = MIN_Y

        # Create panel containers (rebuilt by _rebuild_io)
        labels_h = y - BOTTOM_BAR_H
        content_w_val = content_w
        self.labels_bg = _colored_view(NSMakeRect(8, BOTTOM_BAR_H, LABEL_COL_W, labels_h), *BG_PANEL_RGB, corner_radius=8)
        self.labels_bg.setAutoresizingMask_(H_SIZABLE)
        cv.addSubview_(self.labels_bg)

        matrix_x = LABEL_COL_W + 12
        self.matrix_bg = _colored_view(
            NSMakeRect(matrix_x, BOTTOM_BAR_H, content_w_val - matrix_x - 8, labels_h),
            *BG_PANEL_RGB, corner_radius=8,
        )
        self.matrix_bg.setAutoresizingMask_(W_SIZABLE | H_SIZABLE)
        self.matrix_bg.setAutoresizesSubviews_(False)
        cv.addSubview_(self.matrix_bg)

        # Static matrix elements (title, subtitle, hotkeys)
        self.matrix_title = _label(
            NSMakeRect(10, 0, 200, 20),
            "CROSSPOINT MATRIX", size=11, bold=True, color=TEXT_DIM,
        )
        self.matrix_bg.addSubview_(self.matrix_title)

        self.matrix_subtitle = _label(
            NSMakeRect(10, 0, 350, 16),
            "",
            size=10, color=TEXT_DIM,
        )
        self.matrix_bg.addSubview_(self.matrix_subtitle)

        self.hotkey_labels = []
        for i, key in enumerate("1234567890"):
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 22, 20))
            btn.setTitle_(key)
            btn.setBordered_(False)
            btn.setWantsLayer_(True)
            btn.layer().setCornerRadius_(3)
            btn.setFont_(NSFont.boldSystemFontOfSize_(11))
            btn.setTag_(i)
            btn.setTarget_(self)
            btn.setAction_(objc.selector(self.hotkeyClicked_, signature=b"v@:@"))
            self.matrix_bg.addSubview_(btn)
            self.hotkey_labels.append(btn)

        # Crosshairs
        self.crosshair_h = PassthroughView.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 2))
        self.crosshair_h.setWantsLayer_(True)
        self.crosshair_h.layer().setBackgroundColor_(CROSSHAIR_COLOR)
        self.crosshair_h.setHidden_(True)
        self.matrix_bg.addSubview_(self.crosshair_h)

        self.crosshair_v = PassthroughView.alloc().initWithFrame_(NSMakeRect(0, 0, 2, 0))
        self.crosshair_v.setWantsLayer_(True)
        self.crosshair_v.layer().setBackgroundColor_(CROSSHAIR_COLOR)
        self.crosshair_v.setHidden_(True)
        self.matrix_bg.addSubview_(self.crosshair_v)

        # Overlay
        mw_init = int(self.matrix_bg.frame().size.width)
        mh_init = int(self.matrix_bg.frame().size.height)
        self.matrix_overlay = MatrixOverlayView.alloc().initWithFrame_(
            NSMakeRect(0, 0, mw_init, mh_init)
        )
        self.matrix_overlay.setAutoresizingMask_(W_SIZABLE | H_SIZABLE)
        self.matrix_overlay.setController_(self)
        self.matrix_bg.addSubview_(self.matrix_overlay)

        self._grid_x = 0
        self._grid_start_y = 0
        self._grid_cell = MATRIX_CELL
        self._grid_gap = 2

        # Build labels and matrix for current I/O count
        self._rebuild_io(self.hub.num_inputs, self.hub.num_outputs)

        # -- Bottom status bar (pin to bottom, stretch width) --
        bottom_bg = _colored_view(NSMakeRect(0, 0, content_w, BOTTOM_BAR_H), *HEADER_BG_RGB)
        bottom_bg.setAutoresizingMask_(W_SIZABLE | MAX_Y)
        bottom_bg.setAutoresizesSubviews_(True)
        cv.addSubview_(bottom_bg)

        self.info_label = _label(
            NSMakeRect(15, 4, content_w - 30, 18),
            "Ready", size=11, color=TEXT_DIM,
        )
        self.info_label.setAutoresizingMask_(W_SIZABLE)
        bottom_bg.addSubview_(self.info_label)

        # Initial layout of matrix grid
        self._layout_matrix()
        self.refresh_matrix()
        self.apply_font_settings()

        # Watch for window resize
        from Foundation import NSNotificationCenter
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self,
            objc.selector(self.windowDidResize_, signature=b"v@:@"),
            "NSWindowDidResizeNotification",
            self.window,
        )

    @objc.python_method
    def _rebuild_io(self, num_in, num_out):
        """Tear down and rebuild label entries and matrix buttons for a new I/O count."""
        print(f"[ui] Rebuilding GUI: {self._num_inputs}x{self._num_outputs} -> {num_in}x{num_out} ({num_in * num_out} cells)")
        # Note: caller (ModelSelectDelegate) saves session before resetting hub
        if hasattr(self, 'info_label'):
            total = num_in * num_out
            if total > 400:
                self.set_status(f"Building {num_in}x{num_out} grid ({total} cells)...")
                self.info_label.display()
        self._num_inputs = num_in
        self._num_outputs = num_out
        large = max(num_in, num_out) > 10  # two-column layout for large models

        # --- Clear existing ---
        if hasattr(self, 'labels_inner') and self.labels_inner:
            self.labels_inner.removeFromSuperview()
        self.input_entries = []
        self.output_entries = []
        self._label_delegates = []
        for btn in self.matrix_buttons.values():
            btn.removeFromSuperview()
        self.matrix_buttons = {}
        for lbl in self.col_headers:
            lbl.removeFromSuperview()
        self.col_headers = []
        for lbl in self.row_headers:
            lbl.removeFromSuperview()
        self.row_headers = []

        # --- Determine label panel width ---
        if large:
            col_w = LABEL_COL_W // 2 - 4
            label_panel_w = LABEL_COL_W
        else:
            col_w = LABEL_COL_W - 14
            label_panel_w = LABEL_COL_W

        # --- Rebuild label entries (pinned to top of labels panel) ---
        labels_h = int(self.labels_bg.frame().size.height)
        entry_h = 24
        spacing = 28
        max_rows = max(num_in, num_out)
        self._labels_scroll = None

        # Fixed header + content area
        header_h = 22

        # Remove old header/content if rebuilding
        if hasattr(self, '_labels_header_view') and self._labels_header_view:
            self._labels_header_view.removeFromSuperview()
        if hasattr(self, '_labels_scroll_view') and self._labels_scroll_view:
            self._labels_scroll_view.removeFromSuperview()
            self._labels_scroll_view = None

        # Fixed header pinned to top
        self._labels_header_view = NSView.alloc().initWithFrame_(
            NSMakeRect(0, labels_h - header_h, label_panel_w, header_h)
        )
        self._labels_header_view.setAutoresizingMask_(8)  # pin to top
        if large:
            left_x = 4
            right_x = LABEL_COL_W // 2 + 2
            self._labels_header_view.addSubview_(
                _label(NSMakeRect(left_x, 2, col_w, 18), "INPUT LABELS", size=10, bold=True, color=TEXT_DIM)
            )
            self._labels_header_view.addSubview_(
                _label(NSMakeRect(right_x, 2, col_w, 18), "OUTPUT LABELS", size=10, bold=True, color=TEXT_DIM)
            )
        else:
            self._labels_header_view.addSubview_(
                _label(NSMakeRect(10, 2, 200, 18), "INPUT / OUTPUT LABELS", size=11, bold=True, color=TEXT_DIM)
            )
        self.labels_bg.addSubview_(self._labels_header_view)

        # Content height for entries
        if large:
            entries_h = (max_rows * spacing) + 10
        else:
            entries_h = (num_in * spacing) + 20 + (num_out * spacing) + 10

        content_area_h = labels_h - header_h

        # Always use scroll view — shows scrollbar only when needed
        from AppKit import NSScrollView
        self._labels_scroll_view = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, 0, label_panel_w, content_area_h)
        )
        self._labels_scroll_view.setHasVerticalScroller_(True)
        self._labels_scroll_view.setAutohidesScrollers_(True)
        self._labels_scroll_view.setHasHorizontalScroller_(False)
        self._labels_scroll_view.setAutoresizingMask_(2 | 16)  # W + H
        self._labels_scroll_view.setDrawsBackground_(False)
        self._labels_scroll_view.setBorderType_(0)

        # Flipped document view — y=0 at top, content flows downward
        self.labels_inner = FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, label_panel_w, entries_h)
        )
        self._labels_scroll_view.setDocumentView_(self.labels_inner)
        self.labels_bg.addSubview_(self._labels_scroll_view)

        if large:
            # Two-column layout: IN on left, OUT on right (top-down in flipped view)
            left_x = 4
            right_x = LABEL_COL_W // 2 + 2
            ly = 4

            for i in range(max_rows):
                # Input column
                if i < num_in:
                    self.labels_inner.addSubview_(
                        _label(NSMakeRect(left_x, ly, 20, entry_h), f"{i+1}.", size=10, color=TEXT_DIM)
                    )
                    text = self.hub.input_labels[i] if i < len(self.hub.input_labels) else f"Input {i+1}"
                    wrapper, tf = _editable(
                        NSMakeRect(left_x + 20, ly, col_w - 24, entry_h),
                        text=text, placeholder=f"In {i+1}", size=10,
                    )
                    delegate = InputLabelDelegate.alloc().initWithIndex_controller_(i, self)
                    tf.setDelegate_(delegate)
                    self._label_delegates.append(delegate)
                    self.labels_inner.addSubview_(wrapper)
                    self.input_entries.append(tf)
                # Output column
                if i < num_out:
                    self.labels_inner.addSubview_(
                        _label(NSMakeRect(right_x, ly, 20, entry_h), f"{i+1}.", size=10, color=TEXT_DIM)
                    )
                    text = self.hub.output_labels[i] if i < len(self.hub.output_labels) else f"Output {i+1}"
                    wrapper, tf = _editable(
                        NSMakeRect(right_x + 20, ly, col_w - 24, entry_h),
                        text=text, placeholder=f"Out {i+1}", size=10,
                    )
                    delegate = OutputLabelDelegate.alloc().initWithIndex_controller_(i, self)
                    tf.setDelegate_(delegate)
                    self._label_delegates.append(delegate)
                    self.labels_inner.addSubview_(wrapper)
                    self.output_entries.append(tf)
                ly += spacing
        else:
            # Single-column layout (top-down in flipped view)
            ly = 4
            for i in range(num_in):
                self.labels_inner.addSubview_(
                    _label(NSMakeRect(10, ly, 24, entry_h), f"{i+1}.", size=11, color=TEXT_DIM)
                )
                text = self.hub.input_labels[i] if i < len(self.hub.input_labels) else f"Input {i+1}"
                wrapper, tf = _editable(
                    NSMakeRect(34, ly, LABEL_COL_W - 48, entry_h),
                    text=text, placeholder=f"Input {i+1}", size=11,
                )
                delegate = InputLabelDelegate.alloc().initWithIndex_controller_(i, self)
                tf.setDelegate_(delegate)
                self._label_delegates.append(delegate)
                self.labels_inner.addSubview_(wrapper)
                self.input_entries.append(tf)
                ly += spacing

            ly += 10
            sep = NSBox.alloc().initWithFrame_(NSMakeRect(12, ly, LABEL_COL_W - 24, 1))
            sep.setBoxType_(NSBoxSeparator)
            self.labels_inner.addSubview_(sep)

            ly += 10
            for i in range(num_out):
                self.labels_inner.addSubview_(
                    _label(NSMakeRect(10, ly, 24, entry_h), f"{i+1}.", size=11, color=TEXT_DIM)
                )
                text = self.hub.output_labels[i] if i < len(self.hub.output_labels) else f"Output {i+1}"
                wrapper, tf = _editable(
                    NSMakeRect(34, ly, LABEL_COL_W - 48, entry_h),
                    text=text, placeholder=f"Output {i+1}", size=11,
                )
                delegate = OutputLabelDelegate.alloc().initWithIndex_controller_(i, self)
                tf.setDelegate_(delegate)
                self._label_delegates.append(delegate)
                self.labels_inner.addSubview_(wrapper)
                self.output_entries.append(tf)
                ly += spacing

        # Tab order
        all_fields = [self.ip_field] + self.input_entries + self.output_entries
        for i in range(len(all_fields) - 1):
            all_fields[i].setNextKeyView_(all_fields[i + 1])




        # --- Grid scroll view (for large grids that overflow) ---
        if hasattr(self, '_grid_scroll') and self._grid_scroll:
            self._grid_scroll.removeFromSuperview()
            self._grid_scroll = None
        if hasattr(self, '_grid_container') and self._grid_container:
            self._grid_container.removeFromSuperview()
            self._grid_container = None

        # For >12x12, use a scroll view inside matrix_bg below the title area
        from AppKit import NSScrollView
        mw = int(self.matrix_bg.frame().size.width)
        mh = int(self.matrix_bg.frame().size.height)
        title_area = 30  # space for CROSSPOINT MATRIX title + hotkeys
        if num_in > 12 or num_out > 12:
            self._grid_scroll = NSScrollView.alloc().initWithFrame_(
                NSMakeRect(0, 0, mw, mh - title_area)
            )
            self._grid_scroll.setHasVerticalScroller_(True)
            self._grid_scroll.setHasHorizontalScroller_(True)
            self._grid_scroll.setAutohidesScrollers_(True)
            self._grid_scroll.setAutoresizingMask_(2 | 16)  # W + H
            self._grid_scroll.setDrawsBackground_(False)
            self._grid_scroll.setBorderType_(0)
            # Use a large container; _layout_matrix will size it
            self._grid_container = NSView.alloc().initWithFrame_(
                NSMakeRect(0, 0, mw, mh)
            )
            self._grid_scroll.setDocumentView_(self._grid_container)
            self.matrix_bg.addSubview_(self._grid_scroll)
            grid_parent = self._grid_container
        else:
            self._grid_scroll = None
            self._grid_container = None
            grid_parent = self.matrix_bg

        # --- Rebuild matrix headers and buttons ---
        # Remove old IN/OUT marker labels
        if hasattr(self, '_in_marker') and self._in_marker:
            self._in_marker.removeFromSuperview()
        if hasattr(self, '_out_marker') and self._out_marker:
            self._out_marker.removeFromSuperview()

        # IN/OUT marker labels — in grid_parent so they scroll with the grid
        self._in_marker = _label(
            NSMakeRect(0, 0, 30, 16), "IN \u25B6", size=9, bold=True, color=TEXT_DIM,
        )
        grid_parent.addSubview_(self._in_marker)
        self._out_marker = _label(
            NSMakeRect(0, 0, 30, 16), "OUT \u25BC", size=9, bold=True, color=TEXT_DIM,
        )
        grid_parent.addSubview_(self._out_marker)

        # Column headers — numbers for large, "IN N" for small
        for i in range(num_in):
            text = str(i + 1) if large else f"IN {i + 1}"
            align = NSCenterTextAlignment
            lbl = _label(
                NSMakeRect(0, 0, MATRIX_CELL, 28),
                text, size=9, bold=True, color=TEXT_WHITE if large else TEXT_DIM,
                align=align,
            )
            lbl.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
            grid_parent.addSubview_(lbl)
            self.col_headers.append(lbl)

        # Row headers — numbers for large, "OUT N" for small
        for out_idx in range(num_out):
            text = str(out_idx + 1) if large else f"OUT {out_idx + 1}"
            row_lbl = _label(
                NSMakeRect(0, 0, ROW_LABEL_W - 8, MATRIX_CELL),
                text, size=9, bold=True, color=TEXT_WHITE if large else TEXT_DIM,
                align=NSRightTextAlignment,
            )
            row_lbl.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
            grid_parent.addSubview_(row_lbl)
            self.row_headers.append(row_lbl)

        # Create ALL buttons — batch with CATransaction for speed
        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        inactive_bg = _cg(*INACTIVE_RGB)
        click_sel = objc.selector(self.matrixClicked_, signature=b"v@:@")
        for out_idx in range(num_out):
            for in_idx in range(num_in):
                btn = MatrixButton.alloc().initWithFrame_(NSMakeRect(0, 0, MATRIX_CELL, MATRIX_CELL))
                btn.output_idx = out_idx
                btn.input_idx = in_idx
                btn.setTitle_("")
                btn.setBordered_(False)
                btn.setWantsLayer_(True)
                if not large:
                    btn.layer().setCornerRadius_(4)
                btn.layer().setBackgroundColor_(inactive_bg)
                btn.setTarget_(self)
                btn.setAction_(click_sel)
                grid_parent.addSubview_(btn)
                self.matrix_buttons[(out_idx, in_idx)] = btn
        CATransaction.commit()

        # Crosshairs and overlay — always present on ALL grid sizes
        if hasattr(self, 'crosshair_h'):
            self.crosshair_h.removeFromSuperview()
            grid_parent.addSubview_(self.crosshair_h)
        if hasattr(self, 'crosshair_v'):
            self.crosshair_v.removeFromSuperview()
            grid_parent.addSubview_(self.crosshair_v)
        if hasattr(self, 'matrix_overlay'):
            self.matrix_overlay.removeFromSuperview()
            self.matrix_overlay.setController_(self)
            grid_parent.addSubview_(self.matrix_overlay)

        # Layout and refresh
        self._last_hover = (-1, -1)
        self._layout_matrix()
        self.refresh_matrix()
        self.apply_font_settings()
        self._refresh_preset_popup()
        refresh_hotkey_popups(self)
        # Restore the target model's saved session (routing, labels, etc.)
        self._restore_session()

    def windowDidResize_(self, notification):
        f = self.window.frame()
        size = (int(f.size.width), int(f.size.height))
        if size == self._last_window_size:
            return
        self._last_window_size = size
        self._layout_on_resize()

    @objc.python_method
    def _layout_on_resize(self):
        """Reposition only the elements that autoresizing can't handle."""
        tb_w = int(self.title_bg.frame().size.width)
        tb_h = int(self.title_bg.frame().size.height)

        # Re-center LCD within title bar
        lcd_frame = self.lcd_view.frame()
        lcd_w = int(lcd_frame.size.width)
        lcd_h = int(lcd_frame.size.height)
        self.lcd_view.setFrame_(NSMakeRect((tb_w - lcd_w) // 2, (tb_h - lcd_h) // 2, lcd_w, lcd_h))

        # Re-center title, status label, dot vertically
        center_y = (tb_h - 24) // 2
        self.title_label.setFrame_(NSMakeRect(20, center_y, 300, 24))
        self.status_label.setFrame_(NSMakeRect(tb_w - 200, center_y, 180, 24))
        self.status_dot.setFrame_(NSMakeRect(tb_w - 130, center_y, 20, 24))

        # Relayout the matrix grid
        self._layout_matrix()

    @objc.python_method
    def _layout_matrix(self):
        """Recalculate and reposition all matrix elements based on current panel size."""
        mw = int(self.matrix_bg.frame().size.width)
        mh = int(self.matrix_bg.frame().size.height)

        col_header_h = 28
        title_area_h = 50  # space for title + subtitle

        # Position title and subtitle at top of matrix_bg (always visible)
        self.matrix_title.setFrame_(NSMakeRect(10, mh - 28, 200, 20))
        self.matrix_subtitle.setFrame_(NSMakeRect(10, mh - 46, 350, 16))

        # Position hotkey indicators right-justified in title area
        if hasattr(self, 'hotkey_labels'):
            hk_w = 22
            hk_gap = 4
            total_hk_w = 10 * hk_w + 9 * hk_gap
            hk_x = mw - total_hk_w - 15
            for i, lbl in enumerate(self.hotkey_labels):
                lbl.setFrame_(NSMakeRect(hk_x + i * (hk_w + hk_gap), mh - 28, hk_w, 20))
            self._refresh_hotkey_indicators()

        n_cols = self._num_inputs
        n_rows = self._num_outputs
        large = max(n_cols, n_rows) > 10

        # Fit to window — cell size scales with header font setting
        from videohub_controller.settings_window import DEFAULT_GRID_HEADER_SIZE
        grid_font = self.presets.get_setting("grid_header_font_size", DEFAULT_GRID_HEADER_SIZE)
        font_scale = grid_font / DEFAULT_GRID_HEADER_SIZE
        gap = 1 if max(n_cols, n_rows) > 20 else 2
        base_min = 12 if n_cols >= 80 or n_rows >= 80 else 20
        min_cell = max(base_min, int(base_min * font_scale))
        row_lbl_w = 40 if large else ROW_LABEL_W
        available_w = mw - row_lbl_w - 20
        available_h = mh - title_area_h - col_header_h - 20
        has_scroll = hasattr(self, '_grid_scroll') and self._grid_scroll is not None

        if has_scroll:
            # Scrollable grid — use min_cell, grid can exceed visible area
            cell = min_cell
            grid_w = n_cols * cell + (n_cols - 1) * gap
            grid_h = n_rows * cell + (n_rows - 1) * gap

            # Resize scroll view to fill below title
            scroll_h = mh - 30  # below title
            self._grid_scroll.setFrame_(NSMakeRect(0, 0, mw, scroll_h))

            # Size container to fit full grid
            container_w = max(mw, row_lbl_w + grid_w + 20)
            container_h = max(scroll_h, col_header_h + grid_h + 20)
            self._grid_container.setFrame_(NSMakeRect(0, 0, container_w, container_h))

            # Position grid in container (bottom-left origin)
            grid_x = row_lbl_w
            col_header_y = container_h - col_header_h
            grid_start_y = col_header_y

            # Scroll to top-left
            self._grid_container.scrollPoint_((0, container_h))
        else:
            # Fit to window
            cell_from_w = (available_w - gap * (n_cols - 1)) // max(n_cols, 1)
            if max(n_cols, n_rows) <= 20:
                # Up to 20x20: size by width only, grid clips at bottom if needed
                cell = max(min_cell, cell_from_w)
            else:
                cell_from_h = (available_h - gap * (n_rows - 1)) // max(n_rows, 1)
                cell = max(min_cell, min(cell_from_w, cell_from_h))

            grid_w = n_cols * cell + (n_cols - 1) * gap
            grid_h = n_rows * cell + (n_rows - 1) * gap
            grid_x = row_lbl_w + max(0, (available_w - grid_w) // 2)
            col_header_y = mh - title_area_h - col_header_h
            grid_start_y = col_header_y

        # Store geometry for crosshair hover
        self._grid_x = grid_x
        self._grid_start_y = grid_start_y
        self._grid_cell = cell
        self._grid_gap = gap
        self._grid_w = grid_w
        self._grid_h = grid_h

        # Column headers
        # Column headers
        stride = cell + gap
        # Position IN/OUT marker labels — stacked, right-justified, arrow over arrow
        if hasattr(self, '_in_marker') and self._in_marker:
            self._in_marker.setAlignment_(NSRightTextAlignment)
            self._in_marker.setFrame_(NSMakeRect(grid_x - row_lbl_w, col_header_y + 14, row_lbl_w - 4, 12))
        if hasattr(self, '_out_marker') and self._out_marker:
            self._out_marker.setAlignment_(NSRightTextAlignment)
            self._out_marker.setFrame_(NSMakeRect(grid_x - row_lbl_w, col_header_y + 1, row_lbl_w - 4, 12))

        if n_cols > 10:
            # Large grid — show number on every cell at fixed 8pt
            num_font = NSFont.boldSystemFontOfSize_(8)
            for i in range(n_cols):
                if i < len(self.col_headers):
                    x = grid_x + i * stride
                    self.col_headers[i].setFont_(num_font)
                    self.col_headers[i].setAlignment_(NSCenterTextAlignment)
                    self.col_headers[i].setFrame_(NSMakeRect(x, col_header_y, stride, col_header_h))
                    self.col_headers[i].setHidden_(False)
        else:
            hdr_font = NSFont.boldSystemFontOfSize_(min(grid_font, max(9, cell * 0.35)))
            for i in range(n_cols):
                if i < len(self.col_headers):
                    x = grid_x + i * stride
                    self.col_headers[i].setFont_(hdr_font)
                    self.col_headers[i].setFrame_(NSMakeRect(x, col_header_y, cell, col_header_h))
                    self.col_headers[i].setHidden_(False)

        # Row headers + button grid
        small_headers = n_rows > 10

        for out_idx in range(n_rows):
            row_y = grid_start_y - (out_idx + 1) * stride

            # Row header
            if out_idx < len(self.row_headers):
                if small_headers:
                    self.row_headers[out_idx].setFont_(num_font)
                    self.row_headers[out_idx].setFrame_(
                        NSMakeRect(grid_x - row_lbl_w, row_y, row_lbl_w - 4, cell))
                    self.row_headers[out_idx].setHidden_(False)
                else:
                    self.row_headers[out_idx].setFont_(hdr_font)
                    self.row_headers[out_idx].setFrame_(
                        NSMakeRect(grid_x - row_lbl_w, row_y, row_lbl_w - 4, cell))
                    self.row_headers[out_idx].setHidden_(False)

            # Buttons for this row
            for in_idx in range(n_cols):
                if (out_idx, in_idx) in self.matrix_buttons:
                    x = grid_x + in_idx * stride
                    self.matrix_buttons[(out_idx, in_idx)].setFrame_(
                        NSMakeRect(x, row_y, cell, cell))

        # Refresh overlay tracking area to match grid bounds
        if hasattr(self, 'matrix_overlay'):
            if has_scroll and self._grid_container:
                cf = self._grid_container.frame()
                self.matrix_overlay.setFrame_(NSMakeRect(0, 0, cf.size.width, cf.size.height))
            else:
                self.matrix_overlay.setFrame_(NSMakeRect(0, 0, mw, mh))
            self.matrix_overlay._setup_tracking()
            self._hide_crosshairs()

    # -- Actions --

    def discoverDevices_(self, sender):
        """Discover Videohubs on the local network via Bonjour. Toggle to cancel."""
        if hasattr(self, '_discover_cancel') and self._discover_cancel and not self._discover_cancel.is_set():
            # Already discovering — cancel it
            self._discover_cancel.set()
            self.discover_btn.setTitle_("Discover")
            self.set_status("Discovery cancelled.")
            return
        if self.hub.connected:
            model = self.hub.model_name or "Videohub"
            ip = self.ip_field.stringValue().strip()
            self.set_status(f"Already connected to {model} at {ip}")
            print("[discovery] Already connected — skipping")
            return
        self._discover_cancel = threading.Event()
        self.discover_btn.setTitle_("Cancel")
        self.set_status("Discovering Videohubs on the network...")
        print("[discovery] Starting Bonjour browse...")
        threading.Thread(target=self._do_discover, daemon=True).start()

    def cancelOperation_(self, sender):
        """Called by Cocoa when Escape is pressed."""
        if hasattr(self, '_discover_cancel') and self._discover_cancel and not self._discover_cancel.is_set():
            self._discover_cancel.set()
            self.discover_btn.setTitle_("Discover")
            self.set_status("Discovery cancelled.")

    @objc.python_method
    def _do_discover(self):
        from videohub_controller.connection import discover_videohubs, scan_port_9990, probe_device_info
        from PyObjCTools import AppHelper
        devices = discover_videohubs(timeout=5.0, cancel_event=self._discover_cancel)
        if not devices and not (self._discover_cancel and self._discover_cancel.is_set()):
            # Bonjour found nothing — fall back to scanning port 9990 on local subnets
            print("[discovery] Bonjour found nothing, falling back to port 9990 scan...")
            AppHelper.callAfter(self.set_status, "No Bonjour response — scanning network for Videohubs...")
            devices = scan_port_9990(cancel_event=self._discover_cancel)
        # Probe each device for detailed info (unique_id, friendly_name)
        for dev in devices:
            if self._discover_cancel and self._discover_cancel.is_set():
                break
            info = probe_device_info(dev["host"])
            if info:
                dev.update(info)
        AppHelper.callAfter(self._discoveryDoneList_, devices)

    @objc.python_method
    def _discoveryDoneList_(self, devices):
        """Called via AppHelper.callAfter with a plain Python list."""
        self._discoveryDone_(devices)

    def _discoveryDone_(self, devices):
        self.discover_btn.setTitle_("Discover")
        cancelled = self._discover_cancel and self._discover_cancel.is_set()
        self._discover_cancel = None
        if cancelled:
            print("[discovery] Cancelled by user")
            return
        if not devices or len(devices) == 0:
            # Last resort: if there's an IP in the field, try connecting to it
            ip = self.ip_field.stringValue().strip()
            if ip:
                print(f"[discovery] No devices found — trying IP in field: {ip}")
                self.set_status(f"No devices found — trying {ip}...")
                self.connect_btn.setEnabled_(False)
                threading.Thread(target=self._do_connect, args=(ip,), daemon=True).start()
            else:
                print("[discovery] No devices found, no IP in field")
                self.set_status("No Videohubs found. Enter IP manually.")
            return

        # Cache discovered devices and refresh picker
        self._discovered_devices = devices
        self._refresh_device_popup()
        print(f"[discovery] Found {len(devices)} device(s)")

        if len(devices) == 1:
            # Single device — auto-connect
            dev = devices[0]
            ip = dev["host"]
            name = dev.get("model_name", dev.get("name", "Videohub"))
            print(f"[discovery] Auto-connecting to {name} at {ip}")
            self.ip_field.setStringValue_(ip)
            self.set_status(f"Found: {name} — connecting...")
            self.connect_btn.setEnabled_(False)
            threading.Thread(target=self._do_connect, args=(ip,), daemon=True).start()
        else:
            # Multiple devices — check if last device is among them
            last_id = self.presets.get_last_device_id()
            auto_dev = None
            for dev in devices:
                if dev.get("unique_id") == last_id:
                    auto_dev = dev
                    break
            if auto_dev:
                ip = auto_dev["host"]
                name = auto_dev.get("model_name", "Videohub")
                print(f"[discovery] Auto-connecting to last device: {name} at {ip}")
                self.ip_field.setStringValue_(ip)
                self.set_status(f"Found {len(devices)} devices — reconnecting to {name}...")
                self.connect_btn.setEnabled_(False)
                threading.Thread(target=self._do_connect, args=(ip,), daemon=True).start()
            else:
                names = [d.get("model_name", d.get("name", "?")) for d in devices]
                self.set_status(f"Found {len(devices)} devices: {', '.join(names)} — select one")

    def toggleConnection_(self, sender):
        if self.hub.connected:
            print("[ui] Disconnect clicked")
            self.hub.disconnect()
        else:
            ip = self.ip_field.stringValue().strip()
            if not ip:
                self.set_status("Enter an IP address")
                return
            print(f"[ui] Connect clicked: {ip}")
            self.set_status(f"Connecting to {ip}...")
            self.connect_btn.setEnabled_(False)
            threading.Thread(target=self._do_connect, args=(ip,), daemon=True).start()

    @objc.python_method
    def _do_connect(self, ip):
        result = self.hub.connect(ip)
        if result is True:
            self.presets.save_ip(ip)
        else:
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                objc.selector(self.connectionFailed_, signature=b"v@:@"),
                str(result),
                False,
            )

    def connectionFailed_(self, msg):
        self.connect_btn.setEnabled_(True)
        msg_str = str(msg)
        print(f"[connection] Failed: {msg_str}")
        if "No route to host" in msg_str or "Network is unreachable" in msg_str:
            self.set_status(
                "Connection failed: No route to host. "
                "Toggle Local Network OFF/ON — opening Settings..."
            )
            # Open System Settings directly to Local Network privacy pane
            import subprocess
            subprocess.Popen([
                "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_LocalNetwork"
            ])
        else:
            self.set_status(f"Connection failed: {msg}")

    @objc.python_method
    def _on_connect(self):
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(self.uiConnected_, signature=b"v@:@"),
            None,
            False,
        )

    def uiConnected_(self, _):
        self.connect_btn.setTitle_("Disconnect")
        self.connect_btn.setEnabled_(True)
        self.ip_field.setEditable_(False)
        model = self.hub.model_name or "Videohub"
        self.status_label.setStringValue_("Connected")
        self.status_dot.setTextColor_(GREEN)
        self.set_status(f"Connected to {model}")
        print(f"[ui] Connected — model={model}, id={self.hub.unique_id}, inputs={self.hub.num_inputs}, outputs={self.hub.num_outputs}")

    @objc.python_method
    def _on_disconnect(self):
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(self.uiDisconnected_, signature=b"v@:@"),
            None,
            False,
        )

    def uiDisconnected_(self, _):
        self.connect_btn.setTitle_("Connect")
        self.connect_btn.setEnabled_(True)
        self.ip_field.setEditable_(True)
        self.status_label.setStringValue_("Disconnected")
        self.status_dot.setTextColor_(RED)
        self.set_status("Disconnected")
        print("[ui] Disconnected")
        self._lcd_selected_out = None
        self._device_identified = False
        self._update_lcd_idle()

    @objc.python_method
    def _on_state_update(self):
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(self.refreshAll_, signature=b"v@:@"),
            None,
            False,
        )

    def refreshAll_(self, _):
        # Auto-detect: if Device Model is Auto-Detect and hardware reported a model,
        # switch the setting to match so presets/hotkeys/fonts are model-specific
        saved_model = self.presets.settings.get("device_model", "Auto-Detect")
        if saved_model == "Auto-Detect" and self.hub.model_name:
            from videohub_controller.connection import VIDEOHUB_MODELS
            for model_key, (m_in, m_out) in VIDEOHUB_MODELS.items():
                if model_key == "Auto-Detect":
                    continue
                if m_in == self.hub.num_inputs and m_out == self.hub.num_outputs:
                    print(f"[ui] Auto-detected model: {model_key} ({m_in}x{m_out})")
                    self.presets.settings["device_model"] = model_key
                    self.presets._write()
                    # Refresh settings window and hotkey popups for new model
                    invalidate_settings_window(self)
                    self._refresh_preset_popup()
                    self._refresh_hotkey_indicators()
                    refresh_hotkey_popups(self)
                    refresh_font_sliders(self)
                    # Update status bar with detected model
                    ip = self.ip_field.stringValue().strip()
                    self.set_status(f"Connected to {model_key} at {ip}")
                    break

        # Device identification: once unique_id arrives, save/load per-device config
        if self.hub.unique_id and not self._device_identified:
            self._on_device_identified(self.hub.unique_id)

        # Update status bar if model name arrived after initial connect
        if self.hub.connected and self.hub.model_name:
            current_status = self.info_label.stringValue() if hasattr(self, 'info_label') else ""
            if current_status == "Connected to Videohub":
                ip = self.ip_field.stringValue().strip()
                self.set_status(f"Connected to {self.hub.model_name} at {ip}")

        # Check if hardware reported different I/O count — rebuild if needed
        if (self.hub.num_inputs != self._num_inputs or
                self.hub.num_outputs != self._num_outputs):
            print(f"[ui] Hardware I/O changed: {self._num_inputs}x{self._num_outputs} -> {self.hub.num_inputs}x{self.hub.num_outputs}")
            self._save_session()
            self._rebuild_io(self.hub.num_inputs, self.hub.num_outputs)
            self._update_lcd_idle()
            return
        self.refresh_labels()
        self.refresh_matrix()
        if self._lcd_selected_out is not None:
            self._update_lcd(self._lcd_selected_out)

    def matrixClicked_(self, sender):
        # Resign text field focus so hotkeys work after clicking the grid
        self.window.makeFirstResponder_(None)
        self._active_hotkey = None
        self._refresh_hotkey_indicators()
        out_idx = sender.output_idx
        in_idx = sender.input_idx
        with self.hub.lock:
            old_in = self.hub.routing[out_idx] if out_idx < len(self.hub.routing) else -1
            self.hub.routing[out_idx] = in_idx
            in_name = self.hub.input_labels[in_idx]
            out_name = self.hub.output_labels[out_idx]
        self.hub.set_route(out_idx, in_idx)
        self.refresh_matrix()
        self.set_status(f"Routed: {in_name} -> {out_name}")
        print(f"[route] OUT {out_idx + 1} ({out_name}): IN {old_in + 1} -> IN {in_idx + 1} ({in_name}) (sent={'yes' if self.hub.connected else 'offline'})")
        self._show_crosshairs_at(out_idx, in_idx)
        self._update_lcd(out_idx)

    def hotkeyClicked_(self, sender):
        self.window.makeFirstResponder_(None)
        keys = "1234567890"
        key = keys[sender.tag()]
        self._recall_preset_by_key(key)

    def recallPreset_(self, sender):
        self.window.makeFirstResponder_(None)
        idx = self.preset_popup.indexOfSelectedItem()
        if idx <= 0:
            self.set_status("Select a preset to recall")
            return
        # Strip hotkey suffix like "  [1]" from the display title
        raw = self.preset_popup.titleOfSelectedItem()
        name = _strip_hotkey_prefix(raw)
        # Find if this preset is bound to a hotkey and mark it active
        self._active_hotkey = None
        bindings = self.presets.get_key_bindings()
        for key, bound_name in bindings.items():
            if bound_name == name:
                self._active_hotkey = key
                break
        self._recall_preset_by_name(name)
        self._refresh_hotkey_indicators()

    def savePreset_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Save Preset")
        alert.setInformativeText_("Enter a name for this routing preset:")
        alert.addButtonWithTitle_("Save")
        alert.addButtonWithTitle_("Cancel")
        name_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        raw = self.preset_popup.titleOfSelectedItem() or ""
        name_field.setStringValue_(_strip_hotkey_prefix(raw))
        alert.setAccessoryView_(name_field)
        alert.window().setAppearance_(self.window.appearance())
        result = alert.runModal()
        if result == NSAlertFirstButtonReturn:
            name = name_field.stringValue().strip()
            if name:
                with self.hub.lock:
                    routing = list(self.hub.routing)
                    in_labels = list(self.hub.input_labels)
                    out_labels = list(self.hub.output_labels)
                self.presets.save(
                    name, routing, in_labels, out_labels,
                    num_inputs=self._num_inputs, num_outputs=self._num_outputs,
                )
                self._refresh_preset_popup()
                self._refresh_hotkey_indicators()
                invalidate_settings_window(self)
                self.set_status(f"Saved preset: {name}")
                print(f"[preset] Saved '{name}' ({self._num_inputs}x{self._num_outputs})")

    def renamePresetFromMenu_(self, sender):
        """Rename the selected preset (triggered from right-click context menu)."""
        idx = self.preset_popup.indexOfSelectedItem()
        if idx <= 0:
            self.set_status("Select a preset to rename")
            return
        raw = self.preset_popup.titleOfSelectedItem()
        old_name = _strip_hotkey_prefix(raw)

        alert = NSAlert.alloc().init()
        alert.setMessageText_('Rename Preset')
        alert.setInformativeText_(f'Enter a new name for "{old_name}":')
        alert.addButtonWithTitle_("Rename")
        alert.addButtonWithTitle_("Cancel")
        name_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        name_field.setStringValue_(old_name)
        alert.setAccessoryView_(name_field)
        alert.window().setAppearance_(self.window.appearance())
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        new_name = name_field.stringValue().strip()
        if not new_name or new_name == old_name:
            return

        # Rename in-place preserving order
        preset_data = self.presets.get(old_name)
        if not preset_data:
            return
        new_presets = {}
        for k, v in self.presets.presets.items():
            if k == old_name:
                new_presets[new_name] = v
            else:
                new_presets[k] = v
        self.presets.presets = new_presets

        # Update hotkey bindings that pointed to old name
        bindings = self.presets.get_key_bindings()
        for key, bound_name in list(bindings.items()):
            if bound_name == old_name:
                self.presets.set_key_binding(key, new_name)

        self.presets._write()
        self._refresh_preset_popup()
        # Re-select the renamed preset
        for i in range(self.preset_popup.numberOfItems()):
            if _strip_hotkey_prefix(self.preset_popup.itemTitleAtIndex_(i)) == new_name:
                self.preset_popup.selectItemAtIndex_(i)
                break
        self._refresh_hotkey_indicators()
        invalidate_settings_window(self)
        refresh_hotkey_popups(self)
        self.set_status(f'Renamed: "{old_name}" \u2192 "{new_name}"')
        print(f"[preset] Renamed '{old_name}' -> '{new_name}'")

    def deletePreset_(self, sender):
        idx = self.preset_popup.indexOfSelectedItem()
        if idx <= 0:
            self.set_status("Select a preset to delete")
            return
        raw = self.preset_popup.titleOfSelectedItem()
        name = _strip_hotkey_prefix(raw)

        # Confirmation dialog
        alert = NSAlert.alloc().init()
        alert.setMessageText_('Delete Preset')
        alert.setInformativeText_(f'Are you sure you want to delete "{name}"?')
        alert.addButtonWithTitle_("Delete")
        alert.addButtonWithTitle_("Cancel")
        alert.window().setAppearance_(self.window.appearance())
        result = alert.runModal()
        if result != NSAlertFirstButtonReturn:
            return

        # Clear any hotkey bindings pointing to this preset
        bindings = self.presets.get_key_bindings()
        for key, bound_name in list(bindings.items()):
            if bound_name == name:
                self.presets.set_key_binding(key, "")

        # Always clear active hotkey if it pointed to deleted preset
        if self._active_hotkey:
            old_bindings = self.presets.get_key_bindings()
            if not old_bindings.get(self._active_hotkey):
                self._active_hotkey = None

        self.presets.delete(name)
        self._refresh_preset_popup()
        self._refresh_hotkey_indicators()
        invalidate_settings_window(self)
        self._save_session()
        self.set_status(f"Deleted preset: {name}")
        print(f"[preset] Deleted '{name}'")

    def resignFocus_(self, _):
        self.window.makeFirstResponder_(None)

    def showAbout_(self, sender):
        show_about_window()

    def showManual_(self, sender):
        show_manual_window()

    def showSettings_(self, sender):
        from videohub_controller.settings_window import _settings_window
        if _settings_window is not None and _settings_window.isVisible():
            _settings_window.close()
        else:
            show_settings_window(self)

    def exportSettings_(self, sender):
        """Export all settings (presets, IP, hotkeys, session) to a JSON file."""
        from AppKit import NSSavePanel
        self._save_session()
        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_("VideohubController_settings.json")
        try:
            panel.setAllowedFileTypes_(["json"])
        except Exception:
            pass
        if panel.runModal() == 1:
            try:
                from videohub_controller.presets import CONFIG_PATH
                import shutil
                shutil.copy2(str(CONFIG_PATH), str(panel.URL().path()))
                self.set_status(f"Settings exported to {panel.URL().path()}")
                print(f"[export] Settings exported to {panel.URL().path()}")
            except Exception as e:
                self.set_status(f"Export failed: {e}")
                print(f"[export] Failed: {e}")

    def importSettings_(self, sender):
        """Import all settings from a JSON file."""
        from AppKit import NSOpenPanel
        import json
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setMessage_("Choose a Videohub Controller settings file to import")
        try:
            panel.setAllowedFileTypes_(["json"])
        except Exception:
            pass
        if panel.runModal() == 1:
            urls = panel.URLs()
            if urls and len(urls) > 0:
                source = str(urls[0].path())
                try:
                    with open(source, encoding="utf-8") as f:
                        data = json.loads(f.read())
                    # Validate it looks like our config
                    if "presets" not in data and "settings" not in data:
                        self.set_status("Import failed: not a valid settings file")
                        print(f"[import] Rejected — not a valid settings file: {source}")
                        return
                    from videohub_controller.presets import CONFIG_PATH, _SHARED_DIR
                    _SHARED_DIR.mkdir(parents=True, exist_ok=True)
                    CONFIG_PATH.write_text(json.dumps(data, indent=2))
                    # Reload everything
                    self.presets._load()
                    self._restore_session()
                    self._refresh_preset_popup()
                    self._refresh_hotkey_indicators()
                    invalidate_settings_window(self)
                    self.set_status(f"Settings imported from {source}")
                    print(f"[import] Settings imported from {source}")
                except Exception as e:
                    self.set_status(f"Import failed: {e}")
                    print(f"[import] Failed: {e}")

    def exportConsole_(self, sender):
        """Export console log via NSSavePanel."""
        from AppKit import NSSavePanel
        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_("videohub_console.log")
        panel.setAllowedContentTypes_([])
        result = panel.runModal()
        if result == 1:  # NSModalResponseOK
            import shutil
            src = get_log_path()
            if src.exists():
                shutil.copy2(str(src), str(panel.URL().path()))
                self.set_status(f"Console log exported to {panel.URL().path()}")
                print(f"[export] Console log exported to {panel.URL().path()}")
            else:
                self.set_status("No console log found")
                print("[export] No console log file found")

    # -- Refresh helpers --

    @objc.python_method
    def refresh_labels(self):
        for i in range(self._num_inputs):
            if i < len(self.input_entries) and i < len(self.hub.input_labels):
                self.input_entries[i].setStringValue_(self.hub.input_labels[i])
        for i in range(self._num_outputs):
            if i < len(self.output_entries) and i < len(self.hub.output_labels):
                self.output_entries[i].setStringValue_(self.hub.output_labels[i])
        self.refresh_matrix_headers()

    @objc.python_method
    def refresh_matrix_headers(self):
        large = max(self._num_inputs, self._num_outputs) > 10
        for i in range(len(self.col_headers)):
            self.col_headers[i].setStringValue_(str(i + 1) if large else f"IN {i + 1}")
        for i in range(len(self.row_headers)):
            self.row_headers[i].setStringValue_(str(i + 1) if large else f"OUT {i + 1}")

    @objc.python_method
    def refresh_matrix(self):
        active_cg = _cg(0.90, 0.78, 0.10)
        inactive_cg = _cg(*INACTIVE_RGB)
        small = self._grid_cell < 20
        with self.hub.lock:
            routing_snapshot = list(self.hub.routing)
        # Suppress CA animations for faster batch update
        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        for out_idx in range(self._num_outputs):
            active_in = routing_snapshot[out_idx] if out_idx < len(routing_snapshot) else -1
            for in_idx in range(self._num_inputs):
                if (out_idx, in_idx) not in self.matrix_buttons:
                    continue
                btn = self.matrix_buttons[(out_idx, in_idx)]
                if in_idx == active_in:
                    btn.setTitle_("" if small else "\u25cf")
                    btn.layer().setBackgroundColor_(active_cg)
                else:
                    btn.setTitle_("")
                    btn.layer().setBackgroundColor_(inactive_cg)
        CATransaction.commit()

    @objc.python_method
    def _update_lcd(self, out_idx):
        """Update the LCD display to show the route for the given output."""
        self._lcd_selected_out = out_idx
        self._lcd_idle = False
        with self.hub.lock:
            if out_idx >= len(self.hub.routing):
                return
            in_idx = self.hub.routing[out_idx]
            out_name = self.hub.output_labels[out_idx] if out_idx < len(self.hub.output_labels) else f"Output {out_idx + 1}"
            in_name = self.hub.input_labels[in_idx] if in_idx < len(self.hub.input_labels) else f"Input {in_idx + 1}"
        self.lcd_src_header.setStringValue_(f"{in_idx + 1:02d} | SRC")
        self.lcd_src_name.setStringValue_(in_name)
        self.lcd_src_name.setAlignment_(NSLeftTextAlignment)
        self.lcd_dest_header.setStringValue_(f"{out_idx + 1:02d} | DEST")
        self.lcd_dest_name.setStringValue_(out_name)
        self.lcd_dest_name.setAlignment_(NSLeftTextAlignment)
        if hasattr(self, 'conn_bg'):
            self._layout_lcd_internals()

    @objc.python_method
    def _update_lcd_idle(self):
        """Set the LCD to its idle/disconnected state."""
        self._lcd_idle = True
        saved_model = self.presets.settings.get("device_model", "Auto-Detect")
        model = self.hub.model_name or (saved_model if saved_model != "Auto-Detect" else f"Videohub {self._num_inputs}x{self._num_outputs}")
        self.lcd_src_header.setStringValue_("")
        self.lcd_src_name.setStringValue_(model)
        self.lcd_src_name.setAlignment_(NSCenterTextAlignment)
        self.lcd_dest_header.setStringValue_("")
        self.lcd_dest_name.setStringValue_("No route selected")
        self.lcd_dest_name.setAlignment_(NSCenterTextAlignment)
        if hasattr(self, 'conn_bg'):
            self._layout_lcd_internals()

    @objc.python_method
    def _layout_lcd_internals(self):
        """Reposition LCD text labels based on idle/active state without full relayout."""
        lcd_size = self.presets.get_setting("lcd_font_size", DEFAULT_LCD_SIZE)
        scale = lcd_size / DEFAULT_LCD_SIZE
        row_h = int(20 * scale)
        lcd_w = int(self.lcd_view.frame().size.width)
        lcd_h = int(self.lcd_view.frame().size.height)

        pad = 8
        hdr_col_w = int(lcd_w * 0.25)
        name_col_w = lcd_w - hdr_col_w - pad * 2
        divider_gap = 3
        content_h = row_h * 2 + 1 + divider_gap * 2
        y_offset = (lcd_h - content_h) // 2

        src_y = y_offset + row_h + 1 + divider_gap
        is_idle = getattr(self, '_lcd_idle', True)
        if is_idle:
            self.lcd_src_header.setFrame_(NSMakeRect(0, 0, 0, 0))
            self.lcd_src_name.setFrame_(NSMakeRect(pad, src_y, lcd_w - pad * 2, row_h))
            self.lcd_dest_header.setFrame_(NSMakeRect(0, 0, 0, 0))
        else:
            self.lcd_src_header.setFrame_(NSMakeRect(pad, src_y, hdr_col_w, row_h))
            self.lcd_src_name.setFrame_(NSMakeRect(pad + hdr_col_w, src_y, name_col_w, row_h))

        div_y = y_offset + row_h + divider_gap
        self.lcd_divider.setFrame_(NSMakeRect(pad, div_y, lcd_w - pad * 2, 1))

        dest_y = y_offset
        if is_idle:
            self.lcd_dest_name.setFrame_(NSMakeRect(pad, dest_y, lcd_w - pad * 2, row_h))
        else:
            self.lcd_dest_header.setFrame_(NSMakeRect(pad, dest_y, hdr_col_w, row_h))
            self.lcd_dest_name.setFrame_(NSMakeRect(pad + hdr_col_w, dest_y, name_col_w, row_h))

        # Hover position label — right side of LCD, full height
        if hasattr(self, 'lcd_hover_label'):
            hover_w = 90
            self.lcd_hover_label.setFrame_(
                NSMakeRect(lcd_w - hover_w - pad, y_offset, hover_w, content_h)
            )

    @objc.python_method
    def _handle_matrix_hover(self, pt):
        """Show crosshair lines at the hovered grid cell."""
        cell = self._grid_cell
        gap = self._grid_gap
        stride = max(cell + gap, 1)

        # Which column (input) and row (output)?
        col = math.floor((pt.x - self._grid_x) / stride)
        row = math.floor((self._grid_start_y - pt.y) / stride)

        # Skip if same cell as last hover (throttle for large grids)
        last = getattr(self, '_last_hover', (-1, -1))
        if (col, row) == last:
            return
        self._last_hover = (col, row)

        if 0 <= col < self._num_inputs and 0 <= row < self._num_outputs:
            CATransaction.begin()
            CATransaction.setDisableActions_(True)

            cx = self._grid_x + col * stride
            ry = self._grid_start_y - (row + 1) * stride + gap

            vx = cx + cell // 2
            vy = self._grid_start_y - self._num_outputs * stride + gap
            self.crosshair_v.setFrame_(NSMakeRect(vx - 1, vy, 2, self._grid_h))
            self.crosshair_v.setHidden_(False)

            hy = ry + cell // 2
            self.crosshair_h.setFrame_(NSMakeRect(self._grid_x, hy - 1, self._grid_w, 2))
            self.crosshair_h.setHidden_(False)

            CATransaction.commit()

            # Show hover position in LCD display
            if hasattr(self, 'lcd_hover_label'):
                self.lcd_hover_label.setStringValue_(f"IN: {col + 1}\nOUT: {row + 1}")
        else:
            self._hide_crosshairs()
            if hasattr(self, 'lcd_hover_label'):
                self.lcd_hover_label.setStringValue_("")

    @objc.python_method
    def _show_crosshairs_at(self, row, col):
        """Show crosshair lines at a specific grid row/col."""
        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        cell = self._grid_cell
        gap = self._grid_gap
        stride = cell + gap

        cx = self._grid_x + col * stride
        ry = self._grid_start_y - (row + 1) * stride + gap

        vx = cx + cell // 2
        vy = self._grid_start_y - self._num_outputs * stride + gap
        self.crosshair_v.setFrame_(NSMakeRect(vx - 1, vy, 2, self._grid_h))
        self.crosshair_v.setHidden_(False)

        hy = ry + cell // 2
        self.crosshair_h.setFrame_(NSMakeRect(self._grid_x, hy - 1, self._grid_w, 2))
        self.crosshair_h.setHidden_(False)
        CATransaction.commit()

    @objc.python_method
    def _hide_crosshairs(self):
        """Hide the crosshair lines."""
        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        self.crosshair_h.setHidden_(True)
        self.crosshair_v.setHidden_(True)
        CATransaction.commit()

    @objc.python_method
    def set_status(self, msg):
        self.info_label.setStringValue_(msg)

    @objc.python_method
    def apply_font_settings(self):
        """Apply persisted font sizes to LCD, labels, and grid headers. Only called on font change."""
        lcd_size = self.presets.get_setting("lcd_font_size", DEFAULT_LCD_SIZE)
        label_size = self.presets.get_setting("label_font_size", DEFAULT_LABEL_SIZE)
        grid_size = self.presets.get_setting("grid_header_font_size", DEFAULT_GRID_HEADER_SIZE)

        # LCD display fonts
        header_size = max(9, lcd_size * 0.75)
        name_size = lcd_size
        self.lcd_src_header.setFont_(NSFont.boldSystemFontOfSize_(header_size))
        self.lcd_src_name.setFont_(NSFont.boldSystemFontOfSize_(name_size))
        self.lcd_dest_header.setFont_(NSFont.boldSystemFontOfSize_(header_size))
        self.lcd_dest_name.setFont_(NSFont.boldSystemFontOfSize_(name_size))

        # Resize LCD view and title bar based on font size
        scale = lcd_size / DEFAULT_LCD_SIZE
        row_h = int(20 * scale)
        lcd_h = row_h * 2 + 7  # two rows + divider + padding
        lcd_w = int(300 * scale)
        header_h = int(HEADER_H * max(scale, 1.0))

        cv = self.window.contentView()
        cv_w = int(cv.frame().size.width)
        cv_h = int(cv.frame().size.height)

        # Resize title bar and pin to top
        self.title_bg.setFrame_(NSMakeRect(0, cv_h - header_h, cv_w, header_h))

        # Resize and re-center LCD within title bar
        lcd_x = (cv_w - lcd_w) // 2
        lcd_y = (header_h - lcd_h) // 2
        self.lcd_view.setFrame_(NSMakeRect(lcd_x, lcd_y, lcd_w, lcd_h))

        # Layout LCD text content
        self._layout_lcd_internals()

        # Shrink title text as display font grows to avoid overlap with LCD
        title_size = max(10, 16 - (lcd_size - DEFAULT_LCD_SIZE) * 0.6)
        self.title_label.setFont_(NSFont.boldSystemFontOfSize_(title_size))

        # Vertically center title, status label, and dot within the title bar
        title_text_h = 24
        center_y = (header_h - title_text_h) // 2
        self.title_label.setFrame_(NSMakeRect(20, center_y, 300, title_text_h))
        self.status_label.setFrame_(NSMakeRect(cv_w - 200, center_y, 180, title_text_h))
        self.status_dot.setFrame_(NSMakeRect(cv_w - 130, center_y, 20, title_text_h))

        # Update minimum window height
        min_h = header_h + CONN_BAR_H + 300 + BOTTOM_BAR_H
        self.window.setMinSize_((920, min_h))

        # Grow the window if it's now smaller than the minimum
        win_frame = self.window.frame()
        if win_frame.size.height < min_h:
            # Grow upward (keep bottom edge fixed)
            new_y = win_frame.origin.y - (min_h - win_frame.size.height)
            self.window.setFrame_display_(
                NSMakeRect(win_frame.origin.x, new_y, win_frame.size.width, min_h), True
            )
            cv_h = int(self.window.contentView().frame().size.height)
            self._last_window_size = (int(win_frame.size.width), min_h)

        # Push connection bar and content panels below the resized title bar
        conn_y = cv_h - header_h - CONN_BAR_H
        self.conn_bg.setFrame_(NSMakeRect(0, conn_y, cv_w, CONN_BAR_H))

        content_h = conn_y - 4 - BOTTOM_BAR_H
        self.labels_bg.setFrame_(NSMakeRect(8, BOTTOM_BAR_H, LABEL_COL_W, content_h))
        matrix_x = LABEL_COL_W + 12
        self.matrix_bg.setFrame_(NSMakeRect(matrix_x, BOTTOM_BAR_H, cv_w - matrix_x - 8, content_h))
        self._layout_matrix()

        # Input/output label entries
        for tf in self.input_entries:
            tf.setFont_(NSFont.systemFontOfSize_(label_size))
        for tf in self.output_entries:
            tf.setFont_(NSFont.systemFontOfSize_(label_size))

        # Grid column/row headers — only override font for small grids
        # Large grids have their font set by _layout_matrix
        if max(self._num_inputs, self._num_outputs) <= 10:
            for lbl in self.col_headers:
                lbl.setFont_(NSFont.boldSystemFontOfSize_(grid_size))
            for lbl in self.row_headers:
                lbl.setFont_(NSFont.boldSystemFontOfSize_(grid_size))

    @objc.python_method
    def _refresh_preset_popup(self):
        # Preserve current selection
        old_raw = self.preset_popup.titleOfSelectedItem() or ""
        old_name = _strip_hotkey_prefix(old_raw)

        # Only show presets matching current I/O count
        filtered_names = self.presets.names(
            num_inputs=self._num_inputs, num_outputs=self._num_outputs
        )

        # Build reverse map: preset name -> hotkey
        bindings = self.presets.get_key_bindings()
        filtered_set = set(filtered_names)
        name_to_key = {}
        for key, bound_name in bindings.items():
            if bound_name and bound_name in filtered_set:
                name_to_key[bound_name] = key

        self.preset_popup.removeAllItems()
        self.preset_popup.addItemWithTitle_("\u2014 Select Preset \u2014")
        for name in filtered_names:
            hotkey = name_to_key.get(name, "")
            if hotkey:
                self.preset_popup.addItemWithTitle_(f"[{hotkey}]  {name}")
            else:
                self.preset_popup.addItemWithTitle_(name)

        # Restore selection
        if old_name:
            for i in range(self.preset_popup.numberOfItems()):
                if _strip_hotkey_prefix(self.preset_popup.itemTitleAtIndex_(i)) == old_name:
                    self.preset_popup.selectItemAtIndex_(i)
                    break

    @objc.python_method
    def _save_session(self):
        """Save full session state to disk."""
        # Get current preset name from dropdown (strip hotkey suffix)
        raw = self.preset_popup.titleOfSelectedItem() or ""
        selected = _strip_hotkey_prefix(raw)
        if selected.startswith("\u2014"):
            selected = ""
        print(f"[session] Saving {self._num_inputs}x{self._num_outputs} state (preset='{selected}')")
        with self.hub.lock:
            routing = list(self.hub.routing)
            in_labels = list(self.hub.input_labels)
            out_labels = list(self.hub.output_labels)
        self.presets.save_session(
            routing=routing,
            input_labels=in_labels,
            output_labels=out_labels,
            selected_preset=selected,
            lcd_output=self._lcd_selected_out,
            active_hotkey=self._active_hotkey,
            num_inputs=self._num_inputs,
            num_outputs=self._num_outputs,
            font_sizes={
                "lcd_font_size": self.presets.get_setting("lcd_font_size", DEFAULT_LCD_SIZE),
                "label_font_size": self.presets.get_setting("label_font_size", DEFAULT_LABEL_SIZE),
                "grid_header_font_size": self.presets.get_setting("grid_header_font_size", DEFAULT_GRID_HEADER_SIZE),
            },
        )

    @objc.python_method
    def _restore_session(self):
        """Restore session state from disk."""
        print(f"[session] Restoring {self._num_inputs}x{self._num_outputs} state...")
        # Clean up orphaned key bindings (pointing to deleted presets)
        bindings = self.presets.get_key_bindings()
        preset_names = set(self.presets.names())
        for key, bound_name in list(bindings.items()):
            if bound_name and bound_name not in preset_names:
                self.presets.set_key_binding(key, "")
        self._refresh_preset_popup()

        session = self.presets.get_session(
            num_inputs=self._num_inputs, num_outputs=self._num_outputs
        )
        if not session:
            print("[session] No saved session for this model")
            return

        # Restore routing and labels under lock (recv loop may be active)
        with self.hub.lock:
            routing = session.get("routing", [])
            for i, in_idx in enumerate(routing):
                if i < self._num_outputs and 0 <= in_idx < self._num_inputs:
                    self.hub.routing[i] = in_idx
            for i, lbl in enumerate(session.get("input_labels", [])):
                if i < self.hub.num_inputs:
                    self.hub.input_labels[i] = lbl
            for i, lbl in enumerate(session.get("output_labels", [])):
                if i < self.hub.num_outputs:
                    self.hub.output_labels[i] = lbl

        self.refresh_labels()
        self.refresh_matrix()

        # Restore selected preset in dropdown
        selected = session.get("selected_preset", "")
        if selected:
            for i in range(self.preset_popup.numberOfItems()):
                title = self.preset_popup.itemTitleAtIndex_(i)
                if _strip_hotkey_prefix(title) == selected:
                    self.preset_popup.selectItemAtIndex_(i)
                    break

        # Restore active hotkey (validate binding still exists)
        saved_hotkey = session.get("active_hotkey")
        if saved_hotkey:
            bindings = self.presets.get_key_bindings()
            bound_name = bindings.get(saved_hotkey, "")
            if bound_name and self.presets.get(bound_name):
                self._active_hotkey = saved_hotkey
            else:
                self._active_hotkey = None
        else:
            self._active_hotkey = None
        self._refresh_hotkey_indicators()

        # Restore LCD display
        lcd_out = session.get("lcd_output")
        if lcd_out is not None and 0 <= lcd_out < self._num_outputs:
            self._update_lcd(lcd_out)

        # Restore per-model font sizes
        font_sizes = session.get("font_sizes")
        if font_sizes:
            for key, val in font_sizes.items():
                self.presets.settings[key] = val
            self.apply_font_settings()
            refresh_font_sliders(self)

    @objc.python_method
    def _refresh_hotkey_indicators(self):
        """Update hotkey indicator buttons — three states: grey/yellow/green."""
        from AppKit import NSAttributedString, NSForegroundColorAttributeName, NSFontAttributeName
        bindings = self.presets.get_key_bindings()
        active_key = getattr(self, '_active_hotkey', None)

        YELLOW = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.90, 0.78, 0.10, 1.0)
        GREEN = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.78, 0.33, 1.0)
        yellow_bg = _cg(0.90, 0.78, 0.10, 0.25)
        green_bg = _cg(0.0, 0.78, 0.33, 0.30)
        grey_bg = _cg(0.25, 0.25, 0.25)
        bold11 = NSFont.boldSystemFontOfSize_(11)

        preset_names = set(self.presets.names(
            num_inputs=self._num_inputs, num_outputs=self._num_outputs
        ))
        for i, key in enumerate("1234567890"):
            btn = self.hotkey_labels[i]
            bound_name = bindings.get(key, "")
            has_binding = bool(bound_name) and bound_name in preset_names
            is_selected = (key == active_key)

            if is_selected and has_binding:
                color = GREEN
                bg = green_bg
            elif has_binding:
                color = YELLOW
                bg = yellow_bg
            else:
                color = TEXT_DIM
                bg = grey_bg

            btn.layer().setBackgroundColor_(bg)
            attrs = {NSForegroundColorAttributeName: color, NSFontAttributeName: bold11}
            btn.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(key, attrs))

    @objc.python_method
    def _install_key_monitor(self):
        """Install a local key event monitor for hotkey preset recall."""
        from AppKit import NSTextView

        def handler(event):
            # Only handle events for our window
            if event.window() != self.window:
                return event

            # Skip if a text field is focused (field editor is an NSTextView)
            first = self.window.firstResponder()
            if isinstance(first, NSTextView):
                return event

            key = event.charactersIgnoringModifiers()
            # Ignore if any modifier except shift is held
            flags = event.modifierFlags()
            if flags & (1 << 20 | 1 << 18 | 1 << 19):  # Cmd, Ctrl, Option
                return event

            if key in "1234567890":
                self._recall_preset_by_key(key)
                return None  # consume the event
            return event

        self._key_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSKeyDownMask, handler
        )

    @objc.python_method
    def _recall_preset_by_key(self, key):
        """Recall a preset bound to the given key (1-0)."""
        bindings = self.presets.get_key_bindings()
        name = bindings.get(key, "")
        if not name:
            print(f"[hotkeys] Key {key} pressed — no preset assigned")
            self.set_status(f"No preset assigned to Key {key}")
            return
        print(f"[hotkeys] Key {key} pressed — recalling '{name}'")
        # Only recall if preset matches current I/O size
        valid_names = set(self.presets.names(
            num_inputs=self._num_inputs, num_outputs=self._num_outputs
        ))
        if name not in valid_names:
            self.set_status(f"Key {key}: preset '{name}' is for a different model")
            return
        self._active_hotkey = key
        self._recall_preset_by_name(name)
        self._refresh_hotkey_indicators()

    @objc.python_method
    def _recall_preset_by_name(self, name):
        """Recall a preset by name."""
        preset = self.presets.get(name)
        if not preset:
            print(f"[preset] Recall failed — '{name}' not found")
            self.set_status(f"Preset '{name}' not found")
            return
        print(f"[preset] Recalling '{name}' (connected={'yes' if self.hub.connected else 'no'})")
        routing = preset.get("routing", [])

        # Update routing only — preserve current labels
        with self.hub.lock:
            for out_idx, in_idx in enumerate(routing):
                if out_idx < self._num_outputs and 0 <= in_idx < self._num_inputs:
                    self.hub.routing[out_idx] = in_idx
        self.refresh_matrix()

        # Sync the preset dropdown to show the recalled preset
        for i in range(self.preset_popup.numberOfItems()):
            title = self.preset_popup.itemTitleAtIndex_(i)
            if _strip_hotkey_prefix(title) == name:
                self.preset_popup.selectItemAtIndex_(i)
                break

        # Show preset name in LCD
        self._lcd_idle = True
        saved_model = self.presets.settings.get("device_model", "Auto-Detect")
        model = self.hub.model_name or (saved_model if saved_model != "Auto-Detect" else f"Videohub {self._num_inputs}x{self._num_outputs}")
        self.lcd_src_header.setStringValue_("")
        self.lcd_src_name.setStringValue_(model)
        self.lcd_src_name.setAlignment_(NSCenterTextAlignment)
        self.lcd_dest_header.setStringValue_("")
        self.lcd_dest_name.setStringValue_(f"Preset: {name}")
        self.lcd_dest_name.setAlignment_(NSCenterTextAlignment)
        if hasattr(self, 'conn_bg'):
            self._layout_lcd_internals()

        # Send to hardware if connected
        if self.hub.connected:
            self.set_status(f"Recalling preset: {name}...")

            def _apply():
                for out_idx, in_idx in enumerate(routing):
                    self.hub.set_route(out_idx, in_idx)
                    time.sleep(0.05)

            threading.Thread(target=_apply, daemon=True).start()
        else:
            self.set_status(f"Preset loaded: {name} (offline)")

    @objc.python_method
    def _apply_global_hotkeys(self, on):
        """Toggle global hotkey monitoring (captures 1-0 even when app is not focused)."""
        # Remove existing global monitor if any
        if hasattr(self, '_global_key_monitor') and self._global_key_monitor:
            NSEvent.removeMonitor_(self._global_key_monitor)
            self._global_key_monitor = None
            print("[hotkeys] Global hotkey monitor removed")

        if on:
            # Check if we have Accessibility permission; open Settings if not
            import subprocess
            trusted = False
            try:
                import ctypes
                cf = ctypes.cdll.LoadLibrary(
                    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
                )
                cf.AXIsProcessTrusted.restype = ctypes.c_bool
                trusted = cf.AXIsProcessTrusted()
            except Exception:
                trusted = True  # assume trusted if we can't check

            if not trusted:
                from AppKit import NSAlert, NSAlertFirstButtonReturn, NSAppearance
                alert = NSAlert.alloc().init()
                alert.setMessageText_("Accessibility Permission Required")
                alert.setInformativeText_(
                    "Global Hotkeys need Accessibility permission to capture "
                    "keyboard shortcuts when the app is in the background.\n\n"
                    "Click Open Settings, then toggle Videohub Controller ON "
                    "in the Accessibility list."
                )
                alert.addButtonWithTitle_("Open Settings")
                alert.addButtonWithTitle_("Not Now")
                dark = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
                if dark:
                    alert.window().setAppearance_(dark)
                result = alert.runModal()
                if result == NSAlertFirstButtonReturn:
                    subprocess.Popen([
                        "open",
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
                    ])
                    print("[hotkeys] User accepted — opened Accessibility settings")
                    self.set_status("Toggle Videohub Controller ON in Accessibility, then re-enable Global Hotkeys")
                else:
                    print("[hotkeys] User declined Accessibility prompt")
                    self.presets.settings["global_hotkeys"] = False
                    self.presets._write()
                    self.set_status("Global Hotkeys disabled — enable in Settings when ready")
                    return

            def global_handler(event):
                try:
                    key = event.charactersIgnoringModifiers()
                    flags = event.modifierFlags()
                    # Ignore if Cmd/Ctrl/Option held
                    if flags & (1 << 20 | 1 << 18 | 1 << 19):
                        return
                    if key in "1234567890":
                        print(f"[hotkeys] Global key detected: {key}")
                        # Use AppHelper to safely call back to main thread
                        from PyObjCTools import AppHelper
                        AppHelper.callAfter(self._recall_preset_by_key, key)
                except Exception as e:
                    print(f"[hotkeys] Global handler error: {e}")

            self._global_key_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSKeyDownMask, global_handler
            )
            print("[hotkeys] Global hotkey monitor installed")


    @objc.python_method
    def _apply_keep_on_top(self, on):
        """Toggle the main window floating above all other apps."""
        from AppKit import NSFloatingWindowLevel, NSNormalWindowLevel
        print(f"[settings] Keep on Top: {'ON' if on else 'OFF'}")
        if on:
            self.window.setLevel_(NSFloatingWindowLevel)
        else:
            self.window.setLevel_(NSNormalWindowLevel)

    def show(self):
        # Session already restored by _rebuild_io during _build_window
        # Apply persisted window/hotkey settings
        if self.presets.settings.get("keep_on_top", False):
            self._apply_keep_on_top(True)
        if self.presets.settings.get("global_hotkeys", False):
            self._apply_global_hotkeys(True)
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        self.window.orderFrontRegardless()
        # macOS 15+: activate() replaces deprecated activateIgnoringOtherApps_
        if hasattr(NSApp, "activate"):
            NSApp.activate()
        else:
            NSApp.activateIgnoringOtherApps_(True)
        # Delay resign focus until after the window is fully displayed
        self.performSelector_withObject_afterDelay_(
            objc.selector(self.resignFocus_, signature=b"v@:@"), None, 0.1
        )
        # Auto-discover and connect on launch
        if not self.hub.connected:
            from PyObjCTools import AppHelper
            AppHelper.callLater(0.5, self._autoDiscover)

    @objc.python_method
    def _autoDiscover(self):
        """Auto-discover on launch: try Bonjour first, fall back to saved IP."""
        if self.hub.connected:
            return
        ip = self.ip_field.stringValue().strip()
        print(f"[app] Auto-discover on launch (saved IP: '{ip}')...")
        self.set_status("Discovering Videohubs on the network...")
        self._discover_cancel = threading.Event()
        threading.Thread(target=self._do_auto_discover, args=(ip,), daemon=True).start()

    @objc.python_method
    def _do_auto_discover(self, fallback_ip):
        """Background: Bonjour browse, then fall back to saved IP."""
        from videohub_controller.connection import discover_videohubs
        devices = discover_videohubs(timeout=5.0, cancel_event=self._discover_cancel)
        if devices:
            dev = devices[0]
            ip = dev["host"]
            name = dev["name"]
            print(f"[app] Auto-discovered: {name} at {ip}")
            from PyObjCTools import AppHelper
            AppHelper.callAfter(self._autoConnectTo_, ip, name)
        elif fallback_ip:
            print(f"[app] No Bonjour response — falling back to saved IP: {fallback_ip}")
            from PyObjCTools import AppHelper
            AppHelper.callAfter(self._autoConnectTo_, fallback_ip, None)
        else:
            print("[app] No devices found and no saved IP")
            from PyObjCTools import AppHelper
            AppHelper.callAfter(self.set_status, "No Videohubs found. Click Discover or enter IP.")
        self._discover_cancel = None

    @objc.python_method
    def _autoConnectTo_(self, ip, name=None):
        """Main thread: update UI and connect to discovered/saved IP."""
        self.ip_field.setStringValue_(ip)
        if name:
            self.set_status(f"Found: {name} — connecting...")
        else:
            self.set_status(f"Auto-connecting to {ip}...")
        self.connect_btn.setEnabled_(False)
        threading.Thread(target=self._do_connect, args=(ip,), daemon=True).start()


    # -- Multi-device support --

    @objc.python_method
    def _refresh_device_popup(self):
        """Rebuild the device picker dropdown from known + discovered devices."""
        self.device_popup.removeAllItems()

        # Merge known devices with discovered devices, deduplicate by unique_id and IP
        all_devices = {}
        known_ips = set()
        for uid, dev in self.presets.get_known_devices().items():
            if uid == "legacy":
                continue
            all_devices[uid] = dev
            ip = dev.get("ip", "")
            if ip:
                known_ips.add(ip)
        for dev in self._discovered_devices:
            uid = dev.get("unique_id", "")
            ip = dev.get("host", "")
            # Skip if already known by unique_id or IP
            if uid and uid in all_devices:
                continue
            if ip and ip in known_ips:
                continue
            key = uid or ip
            if key:
                all_devices[key] = {
                    "friendly_name": dev.get("friendly_name", ""),
                    "model_name": dev.get("name", dev.get("model_name", "Videohub")),
                    "ip": ip,
                    "unique_id": uid,
                }

        self._device_popup_ids = []
        self._device_short_names = []

        # Add placeholder only if no devices or multiple devices
        if len(all_devices) != 1:
            self.device_popup.addItemWithTitle_("\u2014 Select Device \u2014")
            self._device_popup_ids.append(None)
            self._device_short_names.append("\u2014 Select Device \u2014")

        for uid, dev in all_devices.items():
            fname = dev.get("friendly_name", "")
            model = dev.get("model_name", "Videohub")
            ip = dev.get("ip", "")
            # Short name for selected display (no IP)
            if fname and fname != model:
                short = fname
            else:
                short = model
            # Menu item shows "Model  (IP)" — IP in dimmer text
            if ip:
                menu_title = f"{short}  ({ip})"
            else:
                menu_title = short
            self.device_popup.addItemWithTitle_(menu_title)
            item = self.device_popup.lastItem()
            if item and ip:
                # Style the IP portion dimmer
                from AppKit import NSMutableAttributedString, NSFontAttributeName, NSForegroundColorAttributeName
                font = NSFont.systemFontOfSize_(13)
                dim_font = NSFont.systemFontOfSize_(11)
                astr = NSMutableAttributedString.alloc().initWithString_attributes_(
                    menu_title, {NSFontAttributeName: font}
                )
                ip_start = len(short) + 2  # after "  "
                ip_len = len(menu_title) - ip_start
                astr.addAttribute_value_range_(NSForegroundColorAttributeName, TEXT_DIM, (ip_start, ip_len))
                astr.addAttribute_value_range_(NSFontAttributeName, dim_font, (ip_start, ip_len))
                item.setAttributedTitle_(astr)
            self._device_popup_ids.append(uid)
            self._device_short_names.append(short)

        # Pre-select current device and show short name on button
        if self._current_device_id and self._current_device_id in self._device_popup_ids:
            idx = self._device_popup_ids.index(self._current_device_id)
            self.device_popup.selectItemAtIndex_(idx)
            self.device_popup.setTitle_(self._device_short_names[idx])
        elif self.device_popup.numberOfItems() == 0 or not self._current_device_id:
            # No matching device — show "None"
            if self.device_popup.numberOfItems() == 0:
                self.device_popup.addItemWithTitle_("None")
                self._device_popup_ids.append(None)
                self._device_short_names.append("None")
            self.device_popup.setTitle_("None")

        # Auto-size width to fit the selected title
        self._resize_device_popup()

    @objc.python_method
    def _resize_device_popup(self):
        """Resize device popup width to fit the current title."""
        idx = self.device_popup.indexOfSelectedItem()
        if 0 <= idx < len(self._device_short_names):
            title = self._device_short_names[idx]
        else:
            title = self.device_popup.titleOfSelectedItem() or ""
        from AppKit import NSAttributedString, NSFontAttributeName
        font = self.device_popup.font() or NSFont.systemFontOfSize_(13)
        attrs = {NSFontAttributeName: font}
        text_w = NSAttributedString.alloc().initWithString_attributes_(title, attrs).size().width
        new_w = max(int(text_w) + 45, 120)  # padding for dropdown arrow + bezel
        f = self.device_popup.frame()
        right_edge = f.origin.x + f.size.width
        f.origin.x = right_edge - new_w
        f.size.width = new_w
        self.device_popup.setFrame_(f)

    def renameDeviceFromMenu_(self, sender):
        """Rename the selected device (triggered from right-click context menu)."""
        idx = self.device_popup.indexOfSelectedItem()
        if idx < 0 or idx >= len(self._device_popup_ids):
            return
        uid = self._device_popup_ids[idx]
        if uid is None:
            return
        old_name = self._device_short_names[idx] if idx < len(self._device_short_names) else ""

        from AppKit import NSAlert, NSAlertFirstButtonReturn, NSAppearance
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Rename Device")
        alert.setInformativeText_(f'Enter a custom name for "{old_name}":')
        alert.addButtonWithTitle_("Rename")
        alert.addButtonWithTitle_("Cancel")
        name_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 250, 24))
        name_field.setStringValue_(old_name)
        alert.setAccessoryView_(name_field)
        dark = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
        if dark:
            alert.window().setAppearance_(dark)
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        new_name = name_field.stringValue().strip()
        if not new_name or new_name == old_name:
            return

        # Update the device entry in config
        dev = self.presets.devices.get(uid)
        if dev:
            dev["friendly_name"] = new_name
            self.presets._write()
            print(f"[device] Renamed '{old_name}' -> '{new_name}' (id={uid})")
        self._refresh_device_popup()
        self.set_status(f'Device renamed: "{new_name}"')

    def deviceSelected_(self, sender):
        """Handle device picker dropdown selection."""
        idx = sender.indexOfSelectedItem()
        # Show short name (no IP) on the button face
        if 0 <= idx < len(self._device_short_names):
            sender.setTitle_(self._device_short_names[idx])
        self._resize_device_popup()
        if idx < 0 or idx >= len(self._device_popup_ids):
            return
        uid = self._device_popup_ids[idx]
        if uid is None:
            return  # placeholder selected
        if uid == self._current_device_id and self.hub.connected:
            return  # already connected to this device

        dev = self.presets.get_known_devices().get(uid)
        if dev:
            ip = dev.get("ip", "")
        else:
            # From discovered devices
            for d in self._discovered_devices:
                if d.get("unique_id") == uid or d.get("host") == uid:
                    ip = d.get("host", "")
                    break
            else:
                return

        if not ip:
            self.set_status("No IP address for this device")
            return

        print(f"[device] Switching to device {uid} at {ip}")
        self._switch_device(uid, ip)

    @objc.python_method
    def _switch_device(self, unique_id, ip):
        """Save current device state, disconnect, load new device state, connect."""
        # Save current device
        if self._current_device_id and self.hub.connected:
            self._save_session()
            self.presets.save_device_state(
                self._current_device_id,
                friendly_name=self.hub.friendly_name,
                model_name=self.hub.model_name,
                ip=self.ip_field.stringValue().strip(),
                num_inputs=self._num_inputs,
                num_outputs=self._num_outputs,
            )

        # Disconnect
        if self.hub.connected:
            self.hub.disconnect()

        # Load new device state
        self._current_device_id = unique_id
        self._device_identified = False
        loaded = self.presets.load_device_state(unique_id)

        if loaded:
            # Restore model/IO from device config
            from videohub_controller.connection import VIDEOHUB_MODELS
            saved_model = self.presets.settings.get("device_model", "Auto-Detect")
            num_in, num_out = VIDEOHUB_MODELS.get(saved_model, (10, 10))
            dev = self.presets.devices.get(unique_id, {})
            num_in = dev.get("num_inputs", num_in)
            num_out = dev.get("num_outputs", num_out)
            self.hub.num_inputs = num_in
            self.hub.num_outputs = num_out
            self.hub.input_labels = [f"Input {i+1}" for i in range(num_in)]
            self.hub.output_labels = [f"Output {i+1}" for i in range(num_out)]
            self.hub.routing = [0] * num_out
            self._rebuild_io(num_in, num_out)
            invalidate_settings_window(self)

        # Connect to new device
        self.ip_field.setStringValue_(ip)
        self.set_status(f"Connecting to {ip}...")
        self.connect_btn.setEnabled_(False)
        threading.Thread(target=self._do_connect, args=(ip,), daemon=True).start()

    @objc.python_method
    def _on_device_identified(self, unique_id):
        """Called once per connection when VIDEOHUB DEVICE block provides unique_id."""
        if self._device_identified:
            return
        self._device_identified = True

        old_id = self._current_device_id
        self._current_device_id = unique_id

        # If this is the legacy entry, migrate it
        if old_id == "legacy" and "legacy" in self.presets.devices:
            self.presets.save_device_state(
                unique_id,
                friendly_name=self.hub.friendly_name,
                model_name=self.hub.model_name,
                ip=self.ip_field.stringValue().strip(),
                num_inputs=self.hub.num_inputs,
                num_outputs=self.hub.num_outputs,
            )
        elif old_id != unique_id:
            # Connected to a different device than expected — save old, load new
            if old_id:
                self.presets.save_device_state(
                    old_id,
                    friendly_name="",
                    model_name=self.presets.settings.get("device_model", ""),
                    ip="",
                    num_inputs=self._num_inputs,
                    num_outputs=self._num_outputs,
                )
            loaded = self.presets.load_device_state(unique_id)
            if loaded:
                self._restore_session()
        else:
            # Same device as expected — just update metadata
            pass

        # Always update device metadata and sync device_model setting
        self.presets.save_device_state(
            unique_id,
            friendly_name=self.hub.friendly_name,
            model_name=self.hub.model_name,
            ip=self.ip_field.stringValue().strip(),
            num_inputs=self.hub.num_inputs,
            num_outputs=self.hub.num_outputs,
        )
        # Ensure device_model setting matches the connected hardware
        from videohub_controller.connection import VIDEOHUB_MODELS
        for model_key, (m_in, m_out) in VIDEOHUB_MODELS.items():
            if model_key == "Auto-Detect":
                continue
            if m_in == self.hub.num_inputs and m_out == self.hub.num_outputs:
                self.presets.settings["device_model"] = model_key
                break
        self.presets.set_last_device_id(unique_id)
        self._refresh_device_popup()
        invalidate_settings_window(self)
        print(f"[device] Identified: {self.hub.model_name} ({self.hub.friendly_name}) id={unique_id}")


class AppDelegate(NSObject):
    """NSApplication delegate to keep the controller alive and handle lifecycle."""

    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.controller = None
        return self

    def applicationDidFinishLaunching_(self, notification):
        print("[app] applicationDidFinishLaunching")
        self.controller = AppController.alloc().init()
        self.controller.show()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True

    def applicationWillTerminate_(self, notification):
        print("[app] applicationWillTerminate — saving session...")
        if self.controller:
            self.controller._save_session()
            if hasattr(self.controller, '_key_monitor') and self.controller._key_monitor:
                NSEvent.removeMonitor_(self.controller._key_monitor)
            if hasattr(self.controller, '_global_key_monitor') and self.controller._global_key_monitor:
                NSEvent.removeMonitor_(self.controller._global_key_monitor)
            if self.controller.hub.connected:
                self.controller.hub.disconnect()

    # Forward menu actions to controller
    def showAbout_(self, sender):
        if self.controller:
            self.controller.showAbout_(sender)

    def showManual_(self, sender):
        if self.controller:
            self.controller.showManual_(sender)

    def exportConsole_(self, sender):
        if self.controller:
            self.controller.exportConsole_(sender)

    def showSettings_(self, sender):
        if self.controller:
            self.controller.showSettings_(sender)

    def exportSettings_(self, sender):
        if self.controller:
            self.controller.exportSettings_(sender)

    def importSettings_(self, sender):
        if self.controller:
            self.controller.importSettings_(sender)


def main():
    setup_logging()
    import platform
    print(f"[app] Videohub Controller v{__version__}")
    print(f"[app] macOS {platform.mac_ver()[0]} ({platform.machine()})")
    print(f"[app] Python {platform.python_version()}")

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    # Menu bar
    menubar = NSMenu.alloc().init()

    # App menu
    app_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(app_menu_item)
    app_menu = NSMenu.alloc().init()
    about_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "About Videohub Controller", "showAbout:", ""
    )
    app_menu.addItem_(about_item)
    app_menu.addItem_(NSMenuItem.separatorItem())
    settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Settings...", "showSettings:", ","
    )
    app_menu.addItem_(settings_item)
    app_menu.addItem_(NSMenuItem.separatorItem())
    hide_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Hide Videohub Controller", "hide:", "h"
    )
    app_menu.addItem_(hide_item)
    hide_others_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Hide Others", "hideOtherApplications:", "h"
    )
    hide_others_item.setKeyEquivalentModifierMask_(
        1 << 20 | 1 << 19  # NSEventModifierFlagCommand | NSEventModifierFlagOption
    )
    app_menu.addItem_(hide_others_item)
    show_all_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Show All", "unhideAllApplications:", ""
    )
    app_menu.addItem_(show_all_item)
    app_menu.addItem_(NSMenuItem.separatorItem())
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit Videohub Controller", "terminate:", "q"
    )
    app_menu.addItem_(quit_item)
    app_menu_item.setSubmenu_(app_menu)

    # File menu (Export / Import settings)
    file_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(file_menu_item)
    file_menu = NSMenu.alloc().initWithTitle_("File")
    export_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Export Settings\u2026", "exportSettings:", "e"
    )
    export_item.setKeyEquivalentModifierMask_(1 << 17 | 1 << 20)  # Shift+Cmd
    file_menu.addItem_(export_item)
    import_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Import Settings\u2026", "importSettings:", "i"
    )
    import_item.setKeyEquivalentModifierMask_(1 << 17 | 1 << 20)  # Shift+Cmd
    file_menu.addItem_(import_item)
    file_menu_item.setSubmenu_(file_menu)

    # Edit menu (required for Cmd+C/V/X/A in text fields)
    edit_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(edit_menu_item)
    edit_menu = NSMenu.alloc().initWithTitle_("Edit")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Undo", "undo:", "z")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Redo", "redo:", "Z")
    edit_menu.addItem_(NSMenuItem.separatorItem())
    edit_menu.addItemWithTitle_action_keyEquivalent_("Cut", "cut:", "x")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Copy", "copy:", "c")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Paste", "paste:", "v")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Select All", "selectAll:", "a")
    edit_menu_item.setSubmenu_(edit_menu)

    # View menu
    view_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(view_menu_item)
    view_menu = NSMenu.alloc().initWithTitle_("View")
    fullscreen_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Enter Full Screen", "toggleFullScreen:", "f"
    )
    view_menu.addItem_(fullscreen_item)
    view_menu_item.setSubmenu_(view_menu)

    # Help menu
    help_menu_item = NSMenuItem.alloc().init()
    menubar.addItem_(help_menu_item)
    help_menu = NSMenu.alloc().initWithTitle_("Help")
    manual_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Videohub Controller Help", "showManual:", ""
    )
    help_menu.addItem_(manual_item)
    help_menu.addItem_(NSMenuItem.separatorItem())
    console_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Export Console Log...", "exportConsole:", ""
    )
    help_menu.addItem_(console_item)
    help_menu_item.setSubmenu_(help_menu)

    app.setMainMenu_(menubar)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)

    if hasattr(app, "activate"):
        app.activate()
    else:
        app.activateIgnoringOtherApps_(True)
    app.run()
