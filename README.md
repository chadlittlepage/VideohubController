![Videohub Controller](screenshot.png)

# Videohub Controller

Native macOS routing control application for the Blackmagic Videohub 10x10 SDI router.

## Features

- **10x10 crosspoint matrix** -- click any cell to route an input to an output instantly
- **Hardware-style LCD display** -- simulated display in the title bar shows source and destination labels for the selected route, matching the Videohub's built-in screen
- **Crosshair guides** -- yellow crosshair lines follow your cursor over the grid showing which input/output you are targeting; crosshairs persist after clicking to confirm the route
- **Bidirectional hardware sync** -- routes set in the GUI update the hardware LEDs; changes made on the front panel buttons are reflected back in real time
- **Editable labels** -- rename any input or output directly in the app; names update in the LCD display immediately and are sent to the Videohub when connected
- **Preset (salvo) save and recall** -- snapshot the full routing table to disk, then recall with a single click or hotkey
- **Hotkey presets (1-0)** -- assign up to 10 presets to keyboard keys 1 through 0 for instant one-touch recall; click the number indicators in the matrix title area or press the key
- **Three-state hotkey indicators** -- grey (unassigned), yellow (assigned), green (active) number badges show hotkey status at a glance
- **Settings panel (Cmd+,)** -- live font-size sliders for the LCD display, input/output labels, and grid headers; hotkey preset assignments; all settings persist across restarts
- **Full session persistence** -- IP address, all labels, routing grid, selected preset, active hotkey, LCD state, and all settings are saved on quit and restored on launch
- **Real-time connection status** -- green/red indicator dot with automatic detection of connection drops
- **Resizable and full screen** -- dark native Cocoa GUI with square matrix cells at every window size; Cmd+F for full screen
- **Copy and paste** -- full Edit menu with Cmd+C/V/X/A for IP address and label fields
- **Console logging** -- all connection events, route changes, label edits, and errors are captured to a timestamped log file with automatic rotation
- **In-app manual** -- full user guide accessible from the Help menu
- **About window** -- version info and credits with background artwork overlay

## Requirements

| Requirement | Minimum |
|---|---|
| macOS | 15.0 (Sequoia) or later |
| Python | 3.12+ |
| Hardware | Blackmagic Videohub (10x10 or compatible) on the same network |

## Installation

### Development mode

```bash
git clone https://github.com/chadlittlepage/VideohubController.git
cd VideohubController
pip3 install -e .
videohub-controller
```

### Standalone .app bundle (py2app)

```bash
pip3 install py2app
python3 setup.py py2app
```

The built application is placed at `dist/Videohub Controller.app`. The bundle is configured for code signing and notarization via the included `build_and_sign.sh` script and `entitlements.plist`.

## Usage

### Connect

1. Launch the app (or run `videohub-controller` from the terminal).
2. Enter the Videohub's IP address in the top bar (paste with Cmd+V).
3. Click **Connect**. The matrix and labels populate from the hardware's current state.
4. The IP address is saved automatically and pre-filled on next launch.

### Route

Click any cell in the 10x10 matrix. A yellow dot marks the active route for each output row. Crosshair guides follow your cursor to help target the right cell. The corresponding hardware LED updates immediately.

The LCD display in the title bar shows the source and destination labels for the last clicked route.

### Rename labels

Click an input or output label field, type a new name, and press Return. The LCD display updates immediately. When connected, the name is sent to the Videohub hardware. Labels persist across app restarts.

### Presets

- **Save** -- Click Save and enter a preset name. The current routing table is written to disk.
- **Recall** -- Select a preset from the dropdown, click Recall. All 10 routes are applied to the grid and sent to the hardware. Works offline too.
- **Delete** -- Select a preset and click Delete. A confirmation dialog appears. Any hotkey binding for the deleted preset is automatically cleared.

The preset dropdown shows hotkey assignments: `[1]  Studio A` means that preset is bound to key 1.

### Hotkey presets

Assign presets to keys 1-9 and 0 for instant recall:

1. Open **Settings** (Cmd+,)
2. Under **Hotkey Presets**, select a preset for each key
3. Press the number key or click the indicator badge in the matrix title area

Indicator states:
- **Grey** -- no preset assigned
- **Yellow** -- preset assigned, not currently active
- **Green** -- preset currently active

### Settings

Open with **Cmd+,** or from the app menu:

- **Display Font Size** -- scales the LCD display and title bar
- **Input/Output Labels Font Size** -- scales label text in the left panel
- **Grid IN/OUT Header Font Size** -- scales column and row headers
- **Hotkey Presets** -- assign presets to keys 1-0

All settings apply instantly and persist across restarts.

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Cmd+Q | Quit |
| Cmd+H | Hide |
| Cmd+F | Toggle full screen |
| Cmd+, | Open Settings |
| Cmd+C/V/X/A | Copy, paste, cut, select all (in text fields) |
| 1-9, 0 | Recall hotkey preset (when no text field is focused) |
| Return/Enter | Confirm label rename |
| Tab | Move to next label field |

## Videohub Protocol

Videohub Controller communicates over the Blackmagic Videohub Ethernet Protocol on **TCP port 9990**. The connection is fully bidirectional: commands are sent to the hardware and state updates are pushed back to every connected client.

Multiple clients (including Blackmagic Videohub Software and Smart Control) can connect simultaneously and share the same live state.

### Compatible models

- Blackmagic Videohub 10x10 12G (primary target)
- Any Blackmagic Videohub with 10 or fewer I/O
- Larger models are supported but only the first 10 inputs and outputs are shown

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| GUI framework | PyObjC / AppKit (native Cocoa) |
| Graphics | Quartz CGColor for layer-backed views |
| Bundling | py2app |
| Distribution | Code-signed and notarized .app bundle |
| Networking | Raw TCP sockets, threaded receive loop |

## File Locations

| Path | Contents |
|---|---|
| `~/.videohub_controller.json` | Presets, session state, settings, hotkey bindings, and last-used IP |
| `~/Library/Application Support/Videohub Controller/logs/console.log` | Current session log |
| `~/Library/Application Support/Videohub Controller/logs/console.log.old` | Previous archived log |

Logs auto-rotate after 30 days or when the file exceeds 10 MB (truncated to 5 MB).

## Project Structure

```
VideohubController/
  src/videohub_controller/
    __init__.py          Package version
    app.py               Main Cocoa GUI and AppController
    connection.py        TCP connection manager (Videohub protocol)
    presets.py           Preset save/recall and session persistence
    settings_window.py   Settings panel (font sizes, hotkey bindings)
    console_log.py       Tee stdout/stderr to timestamped log file
    manual_window.py     In-app manual window
    about_window.py      About window with background image overlay
  assets/
    about_background.jpg
  app_entry.py           Entry point for py2app bundle
  setup.py               py2app build configuration
  pyproject.toml         Package metadata and dependencies
  build_and_sign.sh      Code signing and notarization script
  entitlements.plist     macOS entitlements for distribution
```

## Author

**Chad Littlepage**
chad.littlepage@gmail.com
323.974.0444

## License

MIT
