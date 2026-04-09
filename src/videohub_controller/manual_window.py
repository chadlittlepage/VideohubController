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

_RETAINED = []


MANUAL_TEXT = """\
Videohub Controller - User Manual
==================================

OVERVIEW
Videohub Controller is a native macOS application for controlling
a Blackmagic Videohub 10x10 SDI router over Ethernet. It provides
a crosspoint matrix GUI, editable input/output labels, and routing
presets (salvos) - all in a single window.

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

Cells always stay square and yellow regardless of window focus.


INPUT / OUTPUT LABELS
The left panel shows editable names for all 10 inputs and
10 outputs. These correspond to the labels stored on the
Videohub hardware itself.

To rename:
  1. Click a label field and type the new name.
  2. Press Return or Enter to confirm.
  3. The name is sent to the Videohub and stored on the hardware.

Label names are persistent on the Videohub - they survive
power cycles and are visible to all connected clients
(including Blackmagic's own software).


PRESETS (SALVOS)
Presets let you save and recall complete routing snapshots.

  Save:   Type a name in the Presets dropdown, click Save.
          A dialog appears to confirm the name. The current
          routing table + all labels are stored to disk.

  Recall: Select a preset from the dropdown, click Recall.
          All 10 routes are sent to the Videohub in sequence.
          The hardware LEDs update as each route is applied.

  Delete: Select a preset, click Delete. The preset is
          removed from disk.

Presets are saved to:
  ~/.videohub_controller.json

The last-used IP address is also saved here and auto-filled
on next launch.


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


RESIZING
The window is fully resizable:
  - Labels panel stays pinned to the top-left
  - Matrix cells stay square at all sizes
  - The window cannot be shrunk smaller than the label
    content height

The minimum window width is 900 pixels.


VIDEOHUB PROTOCOL
Videohub Controller uses the Blackmagic Videohub Ethernet
Protocol (TCP port 9990). This is the same protocol used by:
  - Blackmagic Videohub Software
  - Blackmagic Smart Control
  - Third-party automation systems

Multiple clients can connect simultaneously. All clients
see the same state and receive the same updates.

Supported Videohub models:
  - Videohub 10x10 (primary target)
  - Any Blackmagic Videohub with 10 or fewer I/O
  - Larger models will work but only the first 10 I/O
    are shown


MENU BAR

App menu (Videohub Controller):
  Quit (Cmd+Q) - close the application

Help menu:
  Videohub Controller Help - opens this manual
  Export Console Log...    - saves the session log file
                             for debugging


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

App won't open (Gatekeeper warning)
  Right-click the app and choose Open. This bypasses
  Gatekeeper for the first launch on unsigned builds.


FILE LOCATIONS
~/.videohub_controller.json
    Presets and last-used IP address

~/Library/Application Support/Videohub Controller/
    logs/
        console.log         Current session log
        console.log.old     Previous archive


KEYBOARD SHORTCUTS
  Cmd+Q          Quit
  Return/Enter   Confirm label rename (deselects field)


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

    _RETAINED.append((controller, window))
