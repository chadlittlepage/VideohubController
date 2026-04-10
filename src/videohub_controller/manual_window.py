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
Videohub Controller v0.2.0 - User Manual
==========================================

OVERVIEW
Videohub Controller is a native macOS application for controlling
a Blackmagic Videohub 10x10 SDI router over Ethernet. It provides
a crosspoint matrix GUI, editable input/output labels, routing
presets with hotkey recall, a hardware-style LCD display, and
customizable font sizes - all in a single window.

When you click a cell in the matrix, the routing command is sent
over TCP to the Videohub hardware. The front panel LEDs update
instantly to match. Changes made on the hardware buttons are
reflected back in the GUI in real time.


GETTING STARTED
1. Connect your Videohub 10x10 to the same network as your Mac.
2. Launch Videohub Controller.
3. Enter the Videohub's IP address in the top bar.
4. Click Connect.
5. The matrix and labels will populate from the hardware's
   current state.


LCD DISPLAY
The center of the title bar features a simulated LCD display
that mirrors the information shown on the Videohub hardware's
built-in screen.

When idle:
  Shows "VIDEOHUB 10x10 12G" and "No route selected"

When a route is selected:
  Top row:    Source number and label name
  Bottom row: Destination number and label name

  Example:
    02 | SRC     Camera 1
    -------------------------
    01 | DEST    Monitor A

The LCD updates live when you:
  - Click a crosspoint cell in the matrix
  - Recall a preset (via button, hotkey, or click)
  - Rename an input or output label

The display font size is adjustable in Settings.


CROSSPOINT MATRIX
The 10x10 grid represents all possible input-to-output routes.

  Columns = Inputs (IN 1 through IN 10)
  Rows    = Outputs (OUT 1 through OUT 10)

  Yellow dot = active route (that input feeds that output)
  Dark cell  = inactive route

To change a route:
  Click any cell in a row to route that input to that output.
  The previous route on that output is replaced immediately.
  The hardware LEDs update at the same time.

Crosshair guides:
  When you hover over the grid, yellow crosshair lines appear
  showing which input column and output row you are targeting.
  The crosshairs remain visible after clicking a cell to
  confirm the selected route.


INPUT / OUTPUT LABELS
The left panel shows editable names for all 10 inputs and
10 outputs. These correspond to the labels stored on the
Videohub hardware itself.

To rename:
  1. Click a label field and type the new name.
  2. Press Return/Enter to confirm, or Tab to the next field.
  3. The name is sent to the Videohub and the LCD display
     updates immediately.

Label names are saved locally and sent to the Videohub when
connected. They persist across app restarts.


PRESETS (SALVOS)
Presets let you save and recall complete routing snapshots.

  Save:   Click Save. A dialog appears to name the preset.
          The current routing table is stored to disk.

  Recall: Select a preset from the dropdown, click Recall.
          All 10 routes are applied. The grid, LCD display,
          and hardware LEDs update. Works offline too -
          the grid updates locally and routes are sent to
          hardware when connected.

  Delete: Select a preset, click Delete. A confirmation
          dialog appears. If the preset was assigned to a
          hotkey, the hotkey binding is also cleared.

The preset dropdown shows hotkey assignments:
  [1]  Studio A     (assigned to key 1)
  [2]  Show Mode    (assigned to key 2)
  Camera Setup      (no hotkey)


HOTKEY PRESETS (1-0)
Assign any preset to keyboard keys 1 through 0 for instant
one-touch recall. There are 10 slots total.

Setup:
  1. Open Settings (Cmd+,)
  2. Under "Hotkey Presets", use the dropdown for each key
     to select a preset (or "None" to clear)
  3. Changes take effect immediately

Using hotkeys:
  - Press 1-9 or 0 on the keyboard to instantly recall
    the assigned preset
  - Click the number indicators in the matrix title area
    for the same effect
  - Hotkeys only work when no text field is focused.
    Click the grid or press Escape to deactivate text fields.

Hotkey indicator states (in the matrix title area):
  Grey background   = No preset assigned
  Yellow background  = Preset assigned, not active
  Green background   = Preset currently active

The preset dropdown and hotkey indicator update together.
Recalling via the Recall button also highlights the
corresponding hotkey number in green.


SETTINGS (Cmd+,)
Open from the app menu or press Cmd+, to customize:

Font Sizes:
  Display Font Size         Scales the LCD display and
                            title bar height
  Input/Output Labels       Scales the label text in the
                            left panel
  Grid IN/OUT Headers       Scales the IN/OUT column and
                            row headers

  All sliders are live - changes apply instantly.
  The window grows automatically to fit larger fonts.

Hotkey Presets:
  Assign presets to keys 1-0 for instant recall.
  See "HOTKEY PRESETS" section above.

All settings persist across app restarts.


SESSION PERSISTENCE
Everything is saved when you quit and restored on relaunch:

  - IP address
  - Input and output labels
  - Full routing grid state
  - Selected preset in dropdown
  - Active hotkey (green indicator)
  - LCD display state
  - All font size settings
  - All hotkey bindings

All data is stored in:
  ~/.videohub_controller.json


CONNECTION STATUS
The top-right corner shows connection state:

  Red dot + "Disconnected"  = not connected
  Green dot + "Connected"   = active TCP connection

The connection is bidirectional:
  - Commands you send (route changes, label edits) go to
    the Videohub immediately.
  - Changes made on the hardware (front panel buttons,
    other software clients) are received and reflected in
    the GUI automatically.

If the connection drops (cable pulled, Videohub rebooted),
the status updates to Disconnected. Click Connect to
reconnect.


RESIZING AND FULL SCREEN
The window is fully resizable:
  - Labels panel stays pinned to the left
  - Matrix cells stay square at all sizes
  - The window grows automatically when the display font
    size increases

Full screen mode: Press Cmd+F or use View > Enter Full Screen.
The entire layout scales to fill the screen.

The minimum window width is 900 pixels.


MENU BAR

App menu (Videohub Controller):
  About               About window
  Settings... (Cmd+,) Font sizes and hotkey bindings
  Hide (Cmd+H)        Hide the application
  Hide Others         Hide all other applications
  Show All            Show all hidden applications
  Quit (Cmd+Q)        Quit the application

View menu:
  Enter Full Screen (Cmd+F)

Help menu:
  Videohub Controller Help  Opens this manual
  Export Console Log...     Saves the session log for
                            debugging


KEYBOARD SHORTCUTS
  Cmd+Q          Quit
  Cmd+H          Hide
  Cmd+F          Toggle full screen
  Cmd+,          Open Settings
  1-9, 0         Recall hotkey preset (when no text
                 field is focused)
  Return/Enter   Confirm label rename
  Tab            Move to next label field


VIDEOHUB PROTOCOL
Videohub Controller uses the Blackmagic Videohub Ethernet
Protocol (TCP port 9990). This is the same protocol used by:
  - Blackmagic Videohub Software
  - Blackmagic Smart Control
  - Third-party automation systems

Multiple clients can connect simultaneously. All clients
see the same state and receive the same updates.

Supported Videohub models:
  - Videohub 10x10 12G (primary target)
  - Any Blackmagic Videohub with 10 or fewer I/O
  - Larger models will work but only the first 10 I/O
    are shown


CONSOLE LOG
The app captures all stdout/stderr to a timestamped log file:

  ~/Library/Application Support/Videohub Controller/logs/console.log

This log records:
  - Connection events (connect, disconnect, errors)
  - Route changes (which input routed to which output)
  - Label renames
  - Preset save/recall/delete actions
  - Any errors or exceptions

The log auto-rotates:
  - Archived after 30 days
  - Truncated to 5 MB if it exceeds 10 MB

Use Help > Export Console Log... to save a copy for
troubleshooting.


TROUBLESHOOTING

Can't connect
  - Verify the Videohub is powered on and connected to
    the network
  - Check the IP address (find it in the Videohub's front
    panel menu or your router's DHCP table)
  - Make sure port 9990 is not blocked by a firewall
  - Try pinging the IP from Terminal:
      ping 192.168.1.100

Connection drops frequently
  - Check your Ethernet cable
  - Verify the Videohub is not being power-cycled
  - Check for IP conflicts on the network

Labels don't update on hardware
  - Labels are only sent when you press Return/Enter
  - Verify the connection status shows green
  - Some older Videohub firmware may have label length
    limits

Matrix doesn't reflect hardware changes
  - The GUI updates in real time via TCP push notifications
  - If it stops updating, the connection may have dropped -
    check the status dot and reconnect

Hotkeys not working
  - Click the grid area or anywhere outside a text field
    to deactivate text input. Number keys are passed to
    text fields when one is focused.
  - Verify the preset is assigned in Settings > Hotkey Presets

App won't open (Gatekeeper warning)
  Right-click the app and choose Open. This bypasses
  Gatekeeper for the first launch on unsigned builds.


FILE LOCATIONS
~/.videohub_controller.json
    Presets, session state, settings, and last-used IP

~/Library/Application Support/Videohub Controller/
    logs/
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

    window.makeKeyAndOrderFront_(None)
    if hasattr(NSApp, "activate"):
        NSApp.activate()
    else:
        NSApp.activateIgnoringOtherApps_(True)

    _RETAINED.clear()
    _RETAINED.append((controller, window))
