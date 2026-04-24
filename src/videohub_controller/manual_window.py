"""In-app manual window for Videohub Controller.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSMakeSize,
    NSObject,
    NSScrollView,
    NSTextView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)

_RETAINED = []  # singleton — only keep the latest window


MANUAL_TEXT = """\
Videohub Controller v0.4.0 - User Manual
==========================================

OVERVIEW
Videohub Controller is a native macOS application for controlling
Blackmagic Videohub SDI routers over Ethernet. It supports ALL
Videohub models from Mini 4x2 to 80x80 with dynamic I/O sizing,
a crosspoint matrix GUI, editable labels, routing presets with
hotkey recall, Bonjour device discovery, and a hardware-style
LCD display.


GETTING STARTED
1. Launch Videohub Controller.
2. Click Discover to find Videohubs on your network automatically,
   or enter the IP address manually.
3. The app auto-connects on launch if a saved IP exists.
4. The matrix and labels populate from the hardware's current state.


DEVICE MODEL SELECTION
Open Settings (Cmd+,) and choose your Videohub model from the
Device Model dropdown:

  Auto-Detect          Detects from hardware on connect
  Videohub Mini 4x2    4 inputs, 2 outputs
  Videohub Mini 6x2    6 inputs, 2 outputs
  Videohub Mini 8x4    8 inputs, 4 outputs
  Videohub 10x10       10 inputs, 10 outputs
  CleanSwitch 12x12    12 inputs, 12 outputs
  Videohub 20x20       20 inputs, 20 outputs
  Videohub 40x40       40 inputs, 40 outputs
  Videohub 80x80       80 inputs, 80 outputs

The entire GUI rebuilds dynamically when you change models:
matrix grid, labels panel, headers, and crosshairs all resize.
The model selection persists across restarts.


BONJOUR DISCOVERY
Click Discover to find Videohubs on your local network via
Bonjour/mDNS (_videohub._tcp). The first device found is
auto-filled into the IP field and connected.

  - Click Discover again (shows "Cancel") or press Escape
    to stop a discovery in progress
  - Discovery also triggers the macOS Local Network permission
    prompt, which helps avoid connection issues on macOS 15


AUTO-CONNECT
If you've connected before, the app automatically connects on
launch using the saved IP address. No clicks needed.


LCD DISPLAY
The center of the title bar shows a simulated LCD display:

When idle:
  Shows the connected model name and "No route selected"

When a route is selected:
  Top row:    Source number and label name
  Bottom row: Destination number and label name

When hovering over the matrix:
  Right side shows the crosshair position in yellow:
    IN: 5
    OUT: 3

The LCD updates live when you click, hover, recall a preset,
or rename a label. Font size is adjustable in Settings.


CROSSPOINT MATRIX
The grid represents all possible input-to-output routes.

  Columns = Inputs    Rows = Outputs
  Yellow = active route    Dark = inactive route

  10x10 and under: "IN 1" / "OUT 1" headers with grid lines
  Over 10: Number-only headers with "IN" / "OUT" corner markers
  Over 12x12: Scrollable matrix with scrollbars

To change a route:
  Click any cell to route that input to that output.

Crosshair guides:
  Yellow crosshair lines follow your cursor showing the
  target input column and output row. The crosshair position
  also shows in the LCD display. Crosshairs remain visible
  after clicking to confirm the route.


INPUT / OUTPUT LABELS
The left panel shows editable names for all inputs and outputs.
For models over 10 I/O, labels appear in two columns (IN left,
OUT right). The panel scrolls when labels overflow.

To rename:
  1. Click a label field and type the new name.
  2. Press Return/Enter to confirm, or Tab to the next field.
  3. The LCD display updates immediately.

Labels persist across restarts and are sent to the Videohub
when connected. Copy/paste supported (Cmd+C/V).


PRESETS (SALVOS)
Save and recall complete routing snapshots.

  Save:   Click Save, enter a name. Routing table stored to disk.
  Recall: Select from dropdown, click Recall. Works offline too.
          The LCD display shows the preset name when recalled.
  Delete: Select and click Delete. Confirms before deleting.
          Any hotkey binding is automatically cleared.
  Rename: Right-click (or Control-click) the preset dropdown,
          then click "Rename..." to change the preset name.
          The hotkey binding and dropdown position are preserved.

Presets are model-specific: only presets saved for the current
I/O size appear in the dropdown. Switch to a different model
and you see only that model's presets.

The dropdown shows hotkey assignments: [1] Studio A


HOTKEY PRESETS (1-0)
Assign presets to keys 1-0 for instant one-touch recall.

Setup (Settings > Hotkey Presets):
  Select a preset for each key slot (1-9, 0)

Usage:
  - Press the number key on the keyboard
  - Or click the number indicator in the matrix title area

Indicator states:
  Grey   = No preset assigned
  Yellow = Preset assigned, not active
  Green  = Preset currently active

Hotkeys work when no text field is focused. Click the grid
or press Escape to deactivate text fields.


SETTINGS (Cmd+,)
Press Cmd+, to open (toggles open/close). Press Escape to close.
The Settings window floats above the main window.

Device Model:
  Select your Videohub model. GUI rebuilds dynamically.
  Hotkey preset dropdowns update to show only presets for
  the selected model.

Font Sizes:
  Display Font Size       Scales LCD display and title bar
  Input/Output Labels     Scales label text in left panel
  Grid IN/OUT Headers     Scales grid header font and cell size

  Font sizes are saved per-model. Each device model remembers
  its own font preferences independently.

Window & Hotkey Behavior:
  Keep on Top             Float above other apps like Resolve
  Global Hotkeys          Keys 1-0 work even when app is not
                          focused (requires Accessibility
                          permission: System Settings > Privacy
                          & Security > Accessibility)

Hotkey Presets:
  Assign presets to keys 1-0. Only presets for the current
  device model appear in the dropdowns.

Reset This Device Model:
  Erases ALL Labels, Presets, and Hotkey Bindings for the
  currently selected model ONLY. Other device models are
  not affected. Resets font sizes to defaults.

All settings persist per-model across restarts.


EXPORT / IMPORT SETTINGS
File menu:
  Export Settings (Shift+Cmd+E)  Save all config as JSON
  Import Settings (Shift+Cmd+I)  Load config from JSON

Exports include: IP address, all presets, hotkey bindings,
font sizes, session state, device model. Use this to transfer
settings between machines or back up your configuration.


SESSION PERSISTENCE
Everything saves per-model on quit and restores on relaunch:
  IP address, labels, routing grid, selected preset, active
  hotkey, LCD state, font sizes, hotkey bindings, device model

Each device model has its own independent session. Switching
from 10x10 to 20x20 saves the 10x10 state and loads the 20x20
state. Switching back restores exactly where you left off.

Config stored at:
  /Users/Shared/Videohub Controller/videohub_controller.json
  (shared by all users on the Mac)


CONNECTION STATUS
  Red dot + "Disconnected"  = not connected
  Green dot + "Connected"   = active TCP connection

The connection is bidirectional: your changes go to the hardware
instantly, and hardware changes are reflected in the GUI.

The app auto-retries (3 attempts, 1-second delays) on connection
failure.


MENU BAR

App menu:
  About, Settings (Cmd+,), Hide (Cmd+H), Quit (Cmd+Q)

File menu:
  Export Settings (Shift+Cmd+E)
  Import Settings (Shift+Cmd+I)

Edit menu:
  Cut (Cmd+X), Copy (Cmd+C), Paste (Cmd+V), Select All (Cmd+A)

View menu:
  Enter Full Screen (Cmd+F)

Help menu:
  Videohub Controller Help, Export Console Log


KEYBOARD SHORTCUTS
  Cmd+Q            Quit
  Cmd+H            Hide
  Cmd+F            Toggle full screen
  Cmd+,            Open/close Settings
  Escape           Close Settings / cancel discovery
  Shift+Cmd+E      Export Settings
  Shift+Cmd+I      Import Settings
  Cmd+C/V/X/A      Copy, paste, cut, select all
  1-9, 0           Recall hotkey preset
  Return/Enter     Confirm label rename
  Tab              Next label field
  Right-click      Rename selected preset (on preset dropdown)
  Control-click    Same as right-click


SUPPORTED MODELS
  Videohub Mini 4x2 12G       4 in / 2 out
  Videohub Mini 6x2 12G       6 in / 2 out
  Videohub Mini 8x4 12G       8 in / 4 out
  Videohub 10x10 12G          10 in / 10 out
  Smart Videohub CleanSwitch   12 in / 12 out
  Videohub 20x20 12G          20 in / 20 out
  Videohub 40x40 12G          40 in / 40 out
  Videohub 80x80 12G          80 in / 80 out

The model is auto-detected from the hardware on connect
(VIDEOHUB DEVICE protocol block) or manually selected in
Settings.


VIDEOHUB PROTOCOL
Uses the Blackmagic Videohub Ethernet Protocol on TCP port 9990.
Compatible with Blackmagic Videohub Software, Smart Control,
and third-party automation systems. Multiple clients can connect
simultaneously.


TROUBLESHOOTING

Can't connect
  - Click Discover to find devices via Bonjour
  - Verify the Videohub is powered on and on the network
  - Try pinging the IP from Terminal
  - The app retries 3 times automatically

"No route to host" after app update
  - macOS 15 may invalidate Local Network permission after
    re-signing. The app opens System Settings automatically.
    Toggle Videohub Controller OFF then ON.

Hotkeys not working
  - Click the grid to deactivate text fields
  - For Global Hotkeys: grant Accessibility permission in
    System Settings > Privacy & Security > Accessibility

Installing for non-admin users
  - Admin must install once to /Applications, or drag to
    ~/Applications or Desktop

Large grid (40x40, 80x80) is slow
  - Switching models takes a few seconds for large grids
  - Scrolling 6,400 cells has inherent overhead
  - Use full screen (Cmd+F) for more space


FILE LOCATIONS
/Users/Shared/Videohub Controller/videohub_controller.json
    All settings, presets, session state (shared by all users)

~/Library/Application Support/Videohub Controller/logs/
    console.log         Current session log
    console.log.old     Previous archive


CREDITS
Created by Chad Littlepage
chad.littlepage@gmail.com
323.974.0444

\u00a9 2026 Chad Littlepage
"""


class ManualController(NSObject):
    """Controller for the manual window."""

    def init(self):
        self = objc.super(ManualController, self).init()
        if self is not None:
            self.window = None
        return self

    def closeClicked_(self, sender):
        if self.window:
            self.window.close()


def show_manual_window() -> None:
    """Show the manual window with scrollable text content."""
    controller = ManualController.alloc().init()

    win_w, win_h = 760, 720
    style = (
        NSWindowStyleMaskTitled
        | NSWindowStyleMaskClosable
        | NSWindowStyleMaskResizable
        | NSWindowStyleMaskMiniaturizable
    )

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, win_w, win_h),
        style,
        NSBackingStoreBuffered,
        False,
    )
    window.setTitle_("Videohub Controller - Manual")
    window.setMinSize_(NSMakeSize(500, 400))
    window.center()
    controller.window = window

    content = window.contentView()

    btn_h = 28
    margin = 16
    scroll_y = margin + btn_h + 16
    scroll_h = win_h - margin - 16 - scroll_y
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(margin, scroll_y, win_w - 2 * margin, scroll_h)
    )
    scroll.setHasVerticalScroller_(True)
    scroll.setBorderType_(2)  # NSBezelBorder
    scroll.setAutoresizingMask_(2 | 16)  # flexible W + H

    text_view = NSTextView.alloc().initWithFrame_(
        NSMakeRect(0, 0, win_w - 2 * margin - 20, scroll_h)
    )
    text_view.setEditable_(False)
    text_view.setSelectable_(True)
    text_view.setDrawsBackground_(True)
    text_view.setBackgroundColor_(NSColor.textBackgroundColor())
    text_view.setRichText_(False)
    text_view.setFont_(NSFont.fontWithName_size_("Menlo", 12) or NSFont.systemFontOfSize_(12))
    text_view.setString_(MANUAL_TEXT)
    text_view.setAutoresizingMask_(2 | 16)

    scroll.setDocumentView_(text_view)
    content.addSubview_(scroll)

    close_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 100, margin, 100, btn_h)
    )
    close_btn.setTitle_("Close")
    close_btn.setBezelStyle_(1)
    close_btn.setKeyEquivalent_("\r")
    close_btn.setTarget_(controller)
    close_btn.setAction_("closeClicked:")
    close_btn.setAutoresizingMask_(1 | 32)
    content.addSubview_(close_btn)

    from AppKit import NSFloatingWindowLevel
    window.setLevel_(NSFloatingWindowLevel + 1)
    window.makeKeyAndOrderFront_(None)
    if hasattr(NSApp, "activate"):
        NSApp.activate()
    else:
        NSApp.activateIgnoringOtherApps_(True)

    _RETAINED.clear()
    _RETAINED.append((controller, window))
