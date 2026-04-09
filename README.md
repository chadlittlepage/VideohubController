![Videohub Controller](screenshot.png)

# Videohub Controller

Native macOS routing control application for the Blackmagic Videohub 10x10 SDI router.

## Features

- **10x10 crosspoint matrix** -- click any cell to route an input to an output instantly
- **Bidirectional hardware sync** -- routes set in the GUI update the hardware LEDs; changes made on the front panel buttons are reflected back in real time
- **Editable labels synced to hardware** -- rename any input or output directly in the app; names are written to the Videohub and persist across power cycles
- **Preset (salvo) save and recall** -- snapshot the full routing table and all labels to disk, then recall them with a single click
- **Real-time connection status** -- green/red indicator dot with automatic detection of connection drops
- **Resizable native Cocoa GUI** -- dark theme, square matrix cells at every window size, minimum 900px width
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
2. Enter the Videohub's IP address in the top bar.
3. Click **Connect**. The matrix and labels populate from the hardware's current state.
4. The last-used IP address is saved automatically and pre-filled on next launch.

### Route

Click any cell in the 10x10 matrix. A yellow dot marks the active route for each output row. The corresponding hardware LED updates immediately.

### Rename labels

Click an input or output label field, type a new name, and press Return. The name is sent to the Videohub hardware and stored persistently.

### Presets

- **Save** -- Type a preset name, click Save. The current routing table and all labels are written to disk.
- **Recall** -- Select a preset from the dropdown, click Recall. All 10 routes are sent to the hardware in sequence.
- **Delete** -- Select a preset and click Delete to remove it from disk.

## Videohub Protocol

Videohub Controller communicates over the Blackmagic Videohub Ethernet Protocol on **TCP port 9990**. The connection is fully bidirectional: commands are sent to the hardware and state updates are pushed back to every connected client.

Multiple clients (including Blackmagic Videohub Software and Smart Control) can connect simultaneously and share the same live state.

### Compatible models

- Blackmagic Videohub 10x10 (primary target)
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
| `~/.videohub_controller.json` | Presets and last-used IP address |
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
    presets.py           Preset (salvo) save/recall to JSON
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
