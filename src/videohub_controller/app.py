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
from videohub_controller.connection import VideohubConnection, NUM_IO
from videohub_controller.about_window import show_about_window
from videohub_controller.console_log import setup_logging, get_log_path
from videohub_controller.manual_window import show_manual_window
from videohub_controller.presets import PresetManager
from videohub_controller.settings_window import (
    show_settings_window,
    invalidate_settings_window,
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
            self.controller.hub.set_input_label(self.idx, new_name)
            self.controller.refresh_matrix_headers()
            self.controller.set_status(f"Renamed Input {self.idx + 1}: {new_name}")
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
            self.controller.hub.set_output_label(self.idx, new_name)
            self.controller.refresh_matrix_headers()
            self.controller.set_status(f"Renamed Output {self.idx + 1}: {new_name}")
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
        self.hub = VideohubConnection(
            on_state_update=self._on_state_update,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
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
        win_w = LABEL_COL_W + ROW_LABEL_W + (NUM_IO * (MATRIX_CELL + 2)) + 60
        win_h = HEADER_H + CONN_BAR_H + 40 + (NUM_IO * (MATRIX_CELL + 2)) + 80 + BOTTOM_BAR_H

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(200, 100, win_w, win_h),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_(f"Videohub Controller v{__version__}")
        # Min height: title + conn bar + all labels content + bottom bar + padding
        labels_content_h = 30 + 6 + (NUM_IO * 28) + 20 + 24 + 6 + (NUM_IO * 28) + 10
        min_h = HEADER_H + CONN_BAR_H + labels_content_h + BOTTOM_BAR_H + 50
        self.window.setMinSize_((900, min_h))
        self.window.setBackgroundColor_(BG_DARK)

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

        self._lcd_selected_out = None
        self._update_lcd_idle()

        # -- Connection bar (pin to top, stretch width) --
        y -= CONN_BAR_H
        self.conn_bg = _colored_view(NSMakeRect(0, y, content_w, CONN_BAR_H), *BG_PANEL_RGB)
        self.conn_bg.setAutoresizingMask_(W_SIZABLE | MIN_Y)
        cv.addSubview_(self.conn_bg)

        self.conn_bg.addSubview_(
            _label(NSMakeRect(20, 10, 80, 24), "IP Address:", size=12, color=TEXT_DIM)
        )

        ip_wrapper, self.ip_field = _editable(NSMakeRect(100, 10, 160, 24), placeholder="192.168.1.100")
        self.conn_bg.addSubview_(ip_wrapper)

        if self.presets.last_ip:
            self.ip_field.setStringValue_(self.presets.last_ip)

        self.connect_btn = NSButton.alloc().initWithFrame_(NSMakeRect(270, 8, 90, 28))
        self.connect_btn.setTitle_("Connect")
        self.connect_btn.setBezelStyle_(NSBezelStyleRounded)
        self.connect_btn.setTarget_(self)
        self.connect_btn.setAction_(objc.selector(self.toggleConnection_, signature=b"v@:@"))
        self.conn_bg.addSubview_(self.connect_btn)

        # Preset controls (right-justified, even spacing)
        r = content_w
        gap = 6
        x = r - 15

        x -= 60
        del_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 60, 28))
        del_btn.setTitle_("Delete")
        del_btn.setBezelStyle_(NSBezelStyleRounded)
        del_btn.setTarget_(self)
        del_btn.setAction_(objc.selector(self.deletePreset_, signature=b"v@:@"))
        del_btn.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(del_btn)

        x -= gap + 55
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 55, 28))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_(objc.selector(self.savePreset_, signature=b"v@:@"))
        save_btn.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(save_btn)

        x -= gap + 60
        recall_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 60, 28))
        recall_btn.setTitle_("Recall")
        recall_btn.setBezelStyle_(NSBezelStyleRounded)
        recall_btn.setTarget_(self)
        recall_btn.setAction_(objc.selector(self.recallPreset_, signature=b"v@:@"))
        recall_btn.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(recall_btn)

        x -= gap + 180
        self.preset_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, 8, 180, 28), False
        )
        self._refresh_preset_popup()
        self.preset_popup.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(self.preset_popup)

        x -= gap + 50
        preset_lbl = _label(
            NSMakeRect(x, 10, 50, 24), "Preset:", size=12, color=TEXT_DIM
        )
        preset_lbl.setAutoresizingMask_(1)
        self.conn_bg.addSubview_(preset_lbl)

        # -- Main area --
        y -= 4

        # Left panel: labels (pin to left, stretch height; content pinned to top)
        labels_h = y - BOTTOM_BAR_H
        self.labels_bg = _colored_view(NSMakeRect(8, BOTTOM_BAR_H, LABEL_COL_W, labels_h), *BG_PANEL_RGB, corner_radius=8)
        self.labels_bg.setAutoresizingMask_(H_SIZABLE)  # stretch height, pin left
        cv.addSubview_(self.labels_bg)

        # Inner container pinned to top of labels panel
        entry_h = 24
        spacing = 28
        inner_h = 30 + 6 + (NUM_IO * spacing) + 20 + 24 + 6 + (NUM_IO * spacing) + 10
        self.labels_inner = NSView.alloc().initWithFrame_(
            NSMakeRect(0, labels_h - inner_h, LABEL_COL_W, inner_h)
        )
        self.labels_inner.setAutoresizingMask_(MIN_Y)  # pin to top
        self.labels_bg.addSubview_(self.labels_inner)
        labels_inner = self.labels_inner

        ly = inner_h - 30

        labels_inner.addSubview_(
            _label(NSMakeRect(10, ly, 200, 18), "INPUT LABELS", size=11, bold=True, color=TEXT_DIM)
        )
        ly -= 6

        for i in range(NUM_IO):
            ly -= spacing
            labels_inner.addSubview_(
                _label(NSMakeRect(10, ly, 24, entry_h), f"{i + 1}.", size=11, color=TEXT_DIM)
            )
            wrapper, tf = _editable(
                NSMakeRect(34, ly, LABEL_COL_W - 48, entry_h),
                text=self.hub.input_labels[i],
                placeholder=f"Input {i + 1}",
                size=11,
            )
            delegate = InputLabelDelegate.alloc().initWithIndex_controller_(i, self)
            tf.setDelegate_(delegate)
            self._label_delegates.append(delegate)
            labels_inner.addSubview_(wrapper)
            self.input_entries.append(tf)

        ly -= 20

        sep = NSBox.alloc().initWithFrame_(NSMakeRect(12, ly, LABEL_COL_W - 24, 1))
        sep.setBoxType_(NSBoxSeparator)
        labels_inner.addSubview_(sep)

        ly -= 24
        labels_inner.addSubview_(
            _label(NSMakeRect(10, ly, 200, 18), "OUTPUT LABELS", size=11, bold=True, color=TEXT_DIM)
        )
        ly -= 6

        for i in range(NUM_IO):
            ly -= spacing
            labels_inner.addSubview_(
                _label(NSMakeRect(10, ly, 24, entry_h), f"{i + 1}.", size=11, color=TEXT_DIM)
            )
            wrapper, tf = _editable(
                NSMakeRect(34, ly, LABEL_COL_W - 48, entry_h),
                text=self.hub.output_labels[i],
                placeholder=f"Output {i + 1}",
                size=11,
            )
            delegate = OutputLabelDelegate.alloc().initWithIndex_controller_(i, self)
            tf.setDelegate_(delegate)
            self._label_delegates.append(delegate)
            labels_inner.addSubview_(wrapper)
            self.output_entries.append(tf)

        # Set up tab order: IP -> Input 1-10 -> Output 1-10 (no loop back)
        all_fields = [self.ip_field] + self.input_entries + self.output_entries
        for i in range(len(all_fields) - 1):
            all_fields[i].setNextKeyView_(all_fields[i + 1])

        # Right panel: crosspoint matrix (stretch both width and height)
        matrix_x = LABEL_COL_W + 12
        self.matrix_bg = _colored_view(
            NSMakeRect(matrix_x, BOTTOM_BAR_H, content_w - matrix_x - 8, labels_h),
            *BG_PANEL_RGB, corner_radius=8,
        )
        self.matrix_bg.setAutoresizingMask_(W_SIZABLE | H_SIZABLE)
        self.matrix_bg.setAutoresizesSubviews_(False)  # we handle layout manually
        cv.addSubview_(self.matrix_bg)

        self.matrix_title = _label(
            NSMakeRect(10, 0, 200, 20),
            "CROSSPOINT MATRIX", size=11, bold=True, color=TEXT_DIM,
        )
        self.matrix_bg.addSubview_(self.matrix_title)

        self.matrix_subtitle = _label(
            NSMakeRect(10, 0, 350, 16),
            "Click a cell to route that input to that output",
            size=10, color=TEXT_DIM,
        )
        self.matrix_bg.addSubview_(self.matrix_subtitle)

        # Hotkey indicator buttons (1-9, 0) right-justified in title area
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

        # Column headers (inputs)
        for i in range(NUM_IO):
            lbl = _label(
                NSMakeRect(0, 0, MATRIX_CELL, 28),
                f"IN {i + 1}", size=9, bold=True, color=TEXT_DIM,
                align=NSCenterTextAlignment,
            )
            lbl.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
            self.matrix_bg.addSubview_(lbl)
            self.col_headers.append(lbl)

        # Matrix rows
        for out_idx in range(NUM_IO):
            row_lbl = _label(
                NSMakeRect(0, 0, ROW_LABEL_W - 8, MATRIX_CELL),
                f"OUT {out_idx + 1}", size=9, bold=True, color=TEXT_DIM,
                align=NSRightTextAlignment,
            )
            row_lbl.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
            self.matrix_bg.addSubview_(row_lbl)
            self.row_headers.append(row_lbl)

            for in_idx in range(NUM_IO):
                btn = MatrixButton.alloc().initWithFrame_(NSMakeRect(0, 0, MATRIX_CELL, MATRIX_CELL))
                btn.output_idx = out_idx
                btn.input_idx = in_idx
                btn.setTitle_("")
                btn.setBordered_(False)
                btn.setWantsLayer_(True)
                btn.layer().setCornerRadius_(4)
                btn.layer().setBackgroundColor_(_cg(*INACTIVE_RGB))
                btn.setTarget_(self)
                btn.setAction_(objc.selector(self.matrixClicked_, signature=b"v@:@"))
                self.matrix_bg.addSubview_(btn)
                self.matrix_buttons[(out_idx, in_idx)] = btn

        # Crosshair lines (hidden until hover, pass through clicks)
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

        # Transparent overlay for mouse tracking (must be on top)
        mw_init = int(self.matrix_bg.frame().size.width)
        mh_init = int(self.matrix_bg.frame().size.height)
        self.matrix_overlay = MatrixOverlayView.alloc().initWithFrame_(
            NSMakeRect(0, 0, mw_init, mh_init)
        )
        self.matrix_overlay.setAutoresizingMask_(W_SIZABLE | H_SIZABLE)
        self.matrix_overlay.setController_(self)
        self.matrix_bg.addSubview_(self.matrix_overlay)

        # Store grid geometry for hover calculations
        self._grid_x = 0
        self._grid_start_y = 0
        self._grid_cell = MATRIX_CELL
        self._grid_gap = 2

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

        gap = 2
        col_header_h = 28
        title_area_h = 50  # space for title + subtitle

        # Position title and subtitle at top
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

        # Available space for the grid (below titles + column headers, above bottom margin)
        available_w = mw - ROW_LABEL_W - 20
        available_h = mh - title_area_h - col_header_h - 20  # 20 = margins

        # Cell size: smallest of width-fit and height-fit, always square
        cell_from_w = (available_w - gap * (NUM_IO - 1)) // NUM_IO
        cell_from_h = (available_h - gap * (NUM_IO - 1)) // NUM_IO
        cell = max(30, min(cell_from_w, cell_from_h))

        # Grid dimensions
        grid_w = NUM_IO * cell + (NUM_IO - 1) * gap
        grid_h = NUM_IO * cell + (NUM_IO - 1) * gap

        # Pin grid to top-left: column headers right below title area
        grid_x = ROW_LABEL_W + (available_w - grid_w) // 2
        col_header_y = mh - title_area_h - col_header_h
        grid_start_y = col_header_y  # first row starts just below column headers

        # Store geometry for crosshair hover
        self._grid_x = grid_x
        self._grid_start_y = grid_start_y
        self._grid_cell = cell
        self._grid_gap = gap
        self._grid_w = grid_w
        self._grid_h = grid_h

        # Column headers
        for i in range(NUM_IO):
            x = grid_x + i * (cell + gap)
            self.col_headers[i].setFrame_(NSMakeRect(x, col_header_y, cell, col_header_h))

        # Row headers and buttons (top row = out_idx 0, placed highest)
        for out_idx in range(NUM_IO):
            row_y = grid_start_y - (out_idx + 1) * (cell + gap)
            self.row_headers[out_idx].setFrame_(NSMakeRect(grid_x - ROW_LABEL_W, row_y, ROW_LABEL_W - 8, cell))

            for in_idx in range(NUM_IO):
                x = grid_x + in_idx * (cell + gap)
                btn = self.matrix_buttons[(out_idx, in_idx)]
                btn.setFrame_(NSMakeRect(x, row_y, cell, cell))

        # Refresh overlay tracking area to match new bounds
        if hasattr(self, 'matrix_overlay'):
            self.matrix_overlay.setFrame_(NSMakeRect(0, 0, mw, mh))
            self.matrix_overlay._setup_tracking()
            self._hide_crosshairs()

    # -- Actions --

    def toggleConnection_(self, sender):
        if self.hub.connected:
            self.hub.disconnect()
        else:
            ip = self.ip_field.stringValue().strip()
            if not ip:
                self.set_status("Enter an IP address")
                return
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
        self.status_label.setStringValue_("Connected")
        self.status_dot.setTextColor_(GREEN)
        self.set_status("Connected to Videohub")

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
        self._lcd_selected_out = None
        self._update_lcd_idle()

    @objc.python_method
    def _on_state_update(self):
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(self.refreshAll_, signature=b"v@:@"),
            None,
            False,
        )

    def refreshAll_(self, _):
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
        self.hub.set_route(out_idx, in_idx)
        self.hub.routing[out_idx] = in_idx
        self.refresh_matrix()
        in_name = self.hub.input_labels[in_idx]
        out_name = self.hub.output_labels[out_idx]
        self.set_status(f"Routed: {in_name} -> {out_name}")
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
        result = alert.runModal()
        if result == NSAlertFirstButtonReturn:
            name = name_field.stringValue().strip()
            if name:
                self.presets.save(
                    name, self.hub.routing, self.hub.input_labels, self.hub.output_labels
                )
                self._refresh_preset_popup()
                self._refresh_hotkey_indicators()
                invalidate_settings_window()
                self.set_status(f"Saved preset: {name}")

    def deletePreset_(self, sender):
        idx = self.preset_popup.indexOfSelectedItem()
        if idx <= 0:
            self.set_status("Select a preset to delete")
            return
        raw = self.preset_popup.titleOfSelectedItem()
        name = _strip_hotkey_prefix(raw)

        # Confirmation dialog
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f'Delete Preset')
        alert.setInformativeText_(f'Are you sure you want to delete "{name}"?')
        alert.addButtonWithTitle_("Delete")
        alert.addButtonWithTitle_("Cancel")
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
        invalidate_settings_window()
        self._save_session()
        self.set_status(f"Deleted preset: {name}")

    def resignFocus_(self, _):
        self.window.makeFirstResponder_(None)

    def showAbout_(self, sender):
        show_about_window()

    def showManual_(self, sender):
        show_manual_window()

    def showSettings_(self, sender):
        show_settings_window(self)

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
            else:
                self.set_status("No console log found")

    # -- Refresh helpers --

    @objc.python_method
    def refresh_labels(self):
        for i in range(NUM_IO):
            self.input_entries[i].setStringValue_(self.hub.input_labels[i])
            self.output_entries[i].setStringValue_(self.hub.output_labels[i])
        self.refresh_matrix_headers()

    @objc.python_method
    def refresh_matrix_headers(self):
        # Always show IN/OUT abbreviated format in the matrix
        for i in range(NUM_IO):
            self.col_headers[i].setStringValue_(f"IN {i + 1}")
            self.row_headers[i].setStringValue_(f"OUT {i + 1}")

    @objc.python_method
    def refresh_matrix(self):
        active_cg = _cg(0.90, 0.78, 0.10)
        inactive_cg = _cg(*INACTIVE_RGB)
        for out_idx in range(NUM_IO):
            active_in = self.hub.routing[out_idx]
            for in_idx in range(NUM_IO):
                btn = self.matrix_buttons[(out_idx, in_idx)]
                if in_idx == active_in:
                    btn.setTitle_("\u25cf")
                    btn.layer().setBackgroundColor_(active_cg)
                else:
                    btn.setTitle_("")
                    btn.layer().setBackgroundColor_(inactive_cg)

    @objc.python_method
    def _update_lcd(self, out_idx):
        """Update the LCD display to show the route for the given output."""
        self._lcd_selected_out = out_idx
        self._lcd_idle = False
        in_idx = self.hub.routing[out_idx]
        out_name = self.hub.output_labels[out_idx]
        in_name = self.hub.input_labels[in_idx]
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
        self.lcd_src_header.setStringValue_("")
        self.lcd_src_name.setStringValue_("VIDEOHUB 10x10 12G")
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

    @objc.python_method
    def _handle_matrix_hover(self, pt):
        """Show crosshair lines at the hovered grid cell."""
        cell = self._grid_cell
        gap = self._grid_gap
        stride = cell + gap

        # Which column (input) and row (output)?
        # Use floor (not int) so positions left of / above the grid give -1, not 0
        col = math.floor((pt.x - self._grid_x) / stride)
        row = math.floor((self._grid_start_y - pt.y) / stride)

        if 0 <= col < NUM_IO and 0 <= row < NUM_IO:
            # Cell origin
            cx = self._grid_x + col * stride
            ry = self._grid_start_y - (row + 1) * stride + gap

            # Vertical line: center of column, spans full grid height
            vx = cx + cell // 2
            vy = self._grid_start_y - NUM_IO * stride + gap
            self.crosshair_v.setFrame_(NSMakeRect(vx - 1, vy, 2, self._grid_h))
            self.crosshair_v.setHidden_(False)

            # Horizontal line: center of row, spans full grid width
            hy = ry + cell // 2
            self.crosshair_h.setFrame_(NSMakeRect(self._grid_x, hy - 1, self._grid_w, 2))
            self.crosshair_h.setHidden_(False)
        else:
            self._hide_crosshairs()

    @objc.python_method
    def _show_crosshairs_at(self, row, col):
        """Show crosshair lines at a specific grid row/col."""
        cell = self._grid_cell
        gap = self._grid_gap
        stride = cell + gap

        cx = self._grid_x + col * stride
        ry = self._grid_start_y - (row + 1) * stride + gap

        vx = cx + cell // 2
        vy = self._grid_start_y - NUM_IO * stride + gap
        self.crosshair_v.setFrame_(NSMakeRect(vx - 1, vy, 2, self._grid_h))
        self.crosshair_v.setHidden_(False)

        hy = ry + cell // 2
        self.crosshair_h.setFrame_(NSMakeRect(self._grid_x, hy - 1, self._grid_w, 2))
        self.crosshair_h.setHidden_(False)

    @objc.python_method
    def _hide_crosshairs(self):
        """Hide the crosshair lines."""
        self.crosshair_h.setHidden_(True)
        self.crosshair_v.setHidden_(True)

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

        # Update minimum window height to account for resized title bar
        labels_content_h = 30 + 6 + (NUM_IO * 28) + 20 + 24 + 6 + (NUM_IO * 28) + 10
        min_h = header_h + CONN_BAR_H + labels_content_h + BOTTOM_BAR_H + 50
        self.window.setMinSize_((900, min_h))

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

        # Grid column/row headers
        for lbl in self.col_headers:
            lbl.setFont_(NSFont.boldSystemFontOfSize_(grid_size))
        for lbl in self.row_headers:
            lbl.setFont_(NSFont.boldSystemFontOfSize_(grid_size))

    @objc.python_method
    def _refresh_preset_popup(self):
        # Preserve current selection
        old_raw = self.preset_popup.titleOfSelectedItem() or ""
        old_name = _strip_hotkey_prefix(old_raw)

        # Build reverse map: preset name -> hotkey
        bindings = self.presets.get_key_bindings()
        preset_names = set(self.presets.names())
        name_to_key = {}
        for key, bound_name in bindings.items():
            if bound_name and bound_name in preset_names:
                name_to_key[bound_name] = key

        self.preset_popup.removeAllItems()
        self.preset_popup.addItemWithTitle_("\u2014 Select Preset \u2014")
        for name in self.presets.names():
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
        self.presets.save_session(
            routing=self.hub.routing,
            input_labels=self.hub.input_labels,
            output_labels=self.hub.output_labels,
            selected_preset=selected,
            lcd_output=self._lcd_selected_out,
            active_hotkey=self._active_hotkey,
        )

    @objc.python_method
    def _restore_session(self):
        """Restore session state from disk."""
        # Clean up orphaned key bindings (pointing to deleted presets)
        bindings = self.presets.get_key_bindings()
        preset_names = set(self.presets.names())
        for key, bound_name in list(bindings.items()):
            if bound_name and bound_name not in preset_names:
                self.presets.set_key_binding(key, "")
        self._refresh_preset_popup()

        session = self.presets.get_session()
        if not session:
            return

        # Restore routing
        routing = session.get("routing", [])
        for i, in_idx in enumerate(routing):
            if i < NUM_IO and 0 <= in_idx < NUM_IO:
                self.hub.routing[i] = in_idx

        # Restore labels
        for i, lbl in enumerate(session.get("input_labels", [])):
            if i < NUM_IO:
                self.hub.input_labels[i] = lbl
        for i, lbl in enumerate(session.get("output_labels", [])):
            if i < NUM_IO:
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
        if lcd_out is not None and 0 <= lcd_out < NUM_IO:
            self._update_lcd(lcd_out)

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

        preset_names = set(self.presets.names())
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
            self.set_status(f"No preset assigned to Key {key}")
            return
        self._active_hotkey = key
        self._recall_preset_by_name(name)
        self._refresh_hotkey_indicators()

    @objc.python_method
    def _recall_preset_by_name(self, name):
        """Recall a preset by name."""
        preset = self.presets.get(name)
        if not preset:
            self.set_status(f"Preset '{name}' not found")
            return
        routing = preset.get("routing", [])

        # Update routing only — preserve current labels
        for out_idx, in_idx in enumerate(routing):
            if out_idx < NUM_IO and 0 <= in_idx < NUM_IO:
                self.hub.routing[out_idx] = in_idx
        self.refresh_matrix()

        # Sync the preset dropdown to show the recalled preset
        for i in range(self.preset_popup.numberOfItems()):
            title = self.preset_popup.itemTitleAtIndex_(i)
            if _strip_hotkey_prefix(title) == name:
                self.preset_popup.selectItemAtIndex_(i)
                break

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

    def show(self):
        self._restore_session()
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


class AppDelegate(NSObject):
    """NSApplication delegate to keep the controller alive and handle lifecycle."""

    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.controller = None
        return self

    def applicationDidFinishLaunching_(self, notification):
        self.controller = AppController.alloc().init()
        self.controller.show()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True

    def applicationWillTerminate_(self, notification):
        if self.controller:
            self.controller._save_session()
            if hasattr(self.controller, '_key_monitor'):
                NSEvent.removeMonitor_(self.controller._key_monitor)
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


def main():
    setup_logging()

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
