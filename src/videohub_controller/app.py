"""Native macOS Cocoa GUI for Videohub Controller.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

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
    NSFont,
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
LABEL_COL_W = 230
HEADER_H = 50
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
    """Create an editable text field with rounded corners, dim border, and centered text.
    Returns (wrapper_view, text_field) tuple."""
    inset = 2
    wrapper = NSView.alloc().initWithFrame_(frame)
    wrapper.setWantsLayer_(True)
    wrapper.layer().setCornerRadius_(4)
    wrapper.layer().setBorderWidth_(0.5)
    wrapper.layer().setBorderColor_(_cg(0.30, 0.30, 0.30))
    wrapper.layer().setBackgroundColor_(_cg(0.14, 0.14, 0.14))
    wrapper.layer().setMasksToBounds_(True)

    tf = NSTextField.alloc().initWithFrame_(
        NSMakeRect(inset, 0, frame.size.width - inset * 2, frame.size.height)
    )
    cell = VCenterCell.alloc().initTextCell_(text)
    cell.setEditable_(True)
    cell.setScrollable_(False)
    tf.setCell_(cell)
    tf.setStringValue_(text)
    tf.setPlaceholderString_(placeholder)
    tf.setFont_(NSFont.systemFontOfSize_(size))
    tf.setBezeled_(False)
    tf.setDrawsBackground_(False)
    tf.setTextColor_(TEXT_WHITE)
    tf.setEditable_(True)
    tf.setFocusRingType_(1)  # NSFocusRingTypeNone
    wrapper.addSubview_(tf)

    return wrapper, tf


class MatrixButton(NSButton):
    """A crosspoint matrix button that knows its output/input indices."""

    output_idx = objc.ivar("output_idx", objc._C_INT)
    input_idx = objc.ivar("input_idx", objc._C_INT)


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

        self._build_window()
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
        title_bg = _colored_view(NSMakeRect(0, y, content_w, HEADER_H), *HEADER_BG_RGB)
        title_bg.setAutoresizingMask_(W_SIZABLE | MIN_Y)
        title_bg.setAutoresizesSubviews_(True)
        cv.addSubview_(title_bg)

        title = _label(
            NSMakeRect(20, 12, 300, 24),
            "VIDEOHUB CONTROLLER", size=16, bold=True, color=TEXT_WHITE,
        )
        title_bg.addSubview_(title)

        self.status_label = _label(
            NSMakeRect(content_w - 200, 12, 180, 24),
            "Disconnected", size=12, color=TEXT_DIM, align=NSRightTextAlignment,
        )
        self.status_label.setAutoresizingMask_(1)  # NSViewMinXMargin - pin to right
        title_bg.addSubview_(self.status_label)

        self.status_dot = _label(
            NSMakeRect(content_w - 130, 12, 20, 24),
            "\u25cf", size=14, color=RED, align=NSCenterTextAlignment,
        )
        self.status_dot.setAutoresizingMask_(1)  # pin to right
        title_bg.addSubview_(self.status_dot)

        # -- Connection bar (pin to top, stretch width) --
        y -= CONN_BAR_H
        conn_bg = _colored_view(NSMakeRect(0, y, content_w, CONN_BAR_H), *BG_PANEL_RGB)
        conn_bg.setAutoresizingMask_(W_SIZABLE | MIN_Y)
        cv.addSubview_(conn_bg)

        conn_bg.addSubview_(
            _label(NSMakeRect(20, 10, 80, 24), "IP Address:", size=12, color=TEXT_DIM)
        )

        ip_wrapper, self.ip_field = _editable(NSMakeRect(100, 10, 160, 24), placeholder="192.168.1.100")
        conn_bg.addSubview_(ip_wrapper)

        if self.presets.last_ip:
            self.ip_field.setStringValue_(self.presets.last_ip)

        self.connect_btn = NSButton.alloc().initWithFrame_(NSMakeRect(270, 8, 90, 28))
        self.connect_btn.setTitle_("Connect")
        self.connect_btn.setBezelStyle_(NSBezelStyleRounded)
        self.connect_btn.setTarget_(self)
        self.connect_btn.setAction_(objc.selector(self.toggleConnection_, signature=b"v@:@"))
        conn_bg.addSubview_(self.connect_btn)

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
        conn_bg.addSubview_(del_btn)

        x -= gap + 55
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 55, 28))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setTarget_(self)
        save_btn.setAction_(objc.selector(self.savePreset_, signature=b"v@:@"))
        save_btn.setAutoresizingMask_(1)
        conn_bg.addSubview_(save_btn)

        x -= gap + 60
        recall_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 8, 60, 28))
        recall_btn.setTitle_("Recall")
        recall_btn.setBezelStyle_(NSBezelStyleRounded)
        recall_btn.setTarget_(self)
        recall_btn.setAction_(objc.selector(self.recallPreset_, signature=b"v@:@"))
        recall_btn.setAutoresizingMask_(1)
        conn_bg.addSubview_(recall_btn)

        x -= gap + 180
        self.preset_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, 8, 180, 28), False
        )
        self.preset_popup.removeAllItems()
        self.preset_popup.addItemWithTitle_("\u2014 Select Preset \u2014")
        for name in self.presets.names():
            self.preset_popup.addItemWithTitle_(name)
        self.preset_popup.setAutoresizingMask_(1)
        conn_bg.addSubview_(self.preset_popup)

        x -= gap + 50
        preset_lbl = _label(
            NSMakeRect(x, 10, 50, 24), "Preset:", size=12, color=TEXT_DIM
        )
        preset_lbl.setAutoresizingMask_(1)
        conn_bg.addSubview_(preset_lbl)

        # -- Main area --
        y -= 4

        # Left panel: labels (pin to left, stretch height; content pinned to top)
        labels_h = y - BOTTOM_BAR_H
        labels_bg = _colored_view(NSMakeRect(8, BOTTOM_BAR_H, LABEL_COL_W, labels_h), *BG_PANEL_RGB, corner_radius=8)
        labels_bg.setAutoresizingMask_(H_SIZABLE)  # stretch height, pin left
        cv.addSubview_(labels_bg)

        # Inner container pinned to top of labels panel
        entry_h = 24
        spacing = 28
        inner_h = 30 + 6 + (NUM_IO * spacing) + 20 + 24 + 6 + (NUM_IO * spacing) + 10
        self.labels_inner = NSView.alloc().initWithFrame_(
            NSMakeRect(0, labels_h - inner_h, LABEL_COL_W, inner_h)
        )
        self.labels_inner.setAutoresizingMask_(MIN_Y)  # pin to top
        labels_bg.addSubview_(self.labels_inner)
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

        # Set up tab order: IP -> Input 1-10 -> Output 1-10 -> IP
        all_fields = [self.ip_field] + self.input_entries + self.output_entries
        for i in range(len(all_fields)):
            all_fields[i].setNextKeyView_(all_fields[(i + 1) % len(all_fields)])

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

        # Watch for window resize
        from Foundation import NSNotificationCenter
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self,
            objc.selector(self.windowDidResize_, signature=b"v@:@"),
            "NSWindowDidResizeNotification",
            self.window,
        )

    def windowDidResize_(self, notification):
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

        # Column headers
        for i in range(NUM_IO):
            x = grid_x + i * (cell + gap)
            self.col_headers[i].setFrame_(NSMakeRect(x, col_header_y, cell, col_header_h))

        # Row headers and buttons (top row = out_idx 0, placed highest)
        for out_idx in range(NUM_IO):
            row_y = grid_start_y - (out_idx + 1) * (cell + gap)
            self.row_headers[out_idx].setFrame_(NSMakeRect(4, row_y, ROW_LABEL_W - 8, cell))

            for in_idx in range(NUM_IO):
                x = grid_x + in_idx * (cell + gap)
                btn = self.matrix_buttons[(out_idx, in_idx)]
                btn.setFrame_(NSMakeRect(x, row_y, cell, cell))

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

    def matrixClicked_(self, sender):
        out_idx = sender.output_idx
        in_idx = sender.input_idx
        self.hub.set_route(out_idx, in_idx)
        self.hub.routing[out_idx] = in_idx
        self.refresh_matrix()
        in_name = self.hub.input_labels[in_idx]
        out_name = self.hub.output_labels[out_idx]
        self.set_status(f"Routed: {in_name} -> {out_name}")

    def recallPreset_(self, sender):
        name = self.preset_popup.titleOfSelectedItem()
        if not name:
            self.set_status("Select a preset to recall")
            return
        preset = self.presets.get(name)
        if not preset:
            self.set_status("Preset not found")
            return
        if not self.hub.connected:
            self.set_status("Connect to Videohub first")
            return
        routing = preset["routing"]
        self.set_status(f"Recalling preset: {name}...")

        def _apply():
            for out_idx, in_idx in enumerate(routing):
                self.hub.set_route(out_idx, in_idx)
                time.sleep(0.05)

        threading.Thread(target=_apply, daemon=True).start()

    def savePreset_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Save Preset")
        alert.setInformativeText_("Enter a name for this routing preset:")
        alert.addButtonWithTitle_("Save")
        alert.addButtonWithTitle_("Cancel")
        name_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        name_field.setStringValue_(self.preset_popup.titleOfSelectedItem() or "")
        alert.setAccessoryView_(name_field)
        result = alert.runModal()
        if result == NSAlertFirstButtonReturn:
            name = name_field.stringValue().strip()
            if name:
                self.presets.save(
                    name, self.hub.routing, self.hub.input_labels, self.hub.output_labels
                )
                self._refresh_preset_popup()
                self.set_status(f"Saved preset: {name}")

    def deletePreset_(self, sender):
        name = self.preset_popup.titleOfSelectedItem()
        if not name:
            return
        self.presets.delete(name)
        self._refresh_preset_popup()
        self.set_status(f"Deleted preset: {name}")

    def resignFocus_(self, _):
        self.window.makeFirstResponder_(None)

    def showAbout_(self, sender):
        show_about_window()

    def showManual_(self, sender):
        show_manual_window()

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
    def set_status(self, msg):
        self.info_label.setStringValue_(msg)

    @objc.python_method
    def _refresh_preset_popup(self):
        self.preset_popup.removeAllItems()
        self.preset_popup.addItemWithTitle_("\u2014 Select Preset \u2014")
        for name in self.presets.names():
            self.preset_popup.addItemWithTitle_(name)

    def show(self):
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        self.window.orderFrontRegardless()
        # macOS 15+: activate() replaces deprecated activateIgnoringOtherApps_
        if hasattr(NSApp, "activate"):
            NSApp.activate()
        else:
            NSApp.activateIgnoringOtherApps_(True)


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
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit Videohub Controller", "terminate:", "q"
    )
    app_menu.addItem_(quit_item)
    app_menu_item.setSubmenu_(app_menu)

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
