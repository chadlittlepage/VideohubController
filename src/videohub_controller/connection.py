"""TCP connection manager for Blackmagic Videohub protocol.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import socket
import threading

VIDEOHUB_PORT = 9990
VIDEOHUB_BONJOUR_TYPE = "_videohub._tcp."
NUM_IO = 10  # default, overridden by hardware or settings

# Known Videohub models and their I/O configurations
VIDEOHUB_MODELS = {
    "Auto-Detect": (10, 10),
    "Videohub Mini 4x2 12G": (4, 2),
    "Videohub Mini 6x2 12G": (6, 2),
    "Videohub Mini 8x4 12G": (8, 4),
    "Videohub 10x10 12G": (10, 10),
    "Smart Videohub CleanSwitch 12x12": (12, 12),
    "Videohub 20x20 12G": (20, 20),
    "Videohub 40x40 12G": (40, 40),
    "Videohub 80x80 12G": (80, 80),
}
MODEL_NAMES = list(VIDEOHUB_MODELS.keys())


def discover_videohubs(timeout: float = 3.0, callback=None,
                       cancel_event: threading.Event = None) -> list[dict]:
    """Discover Videohubs on the local network via Bonjour/mDNS.

    Returns a list of dicts: [{"name": "...", "host": "...", "port": 9990}, ...]

    On macOS 15+, this Bonjour browse also triggers the Local Network
    permission prompt if it hasn't been granted yet, which ensures
    subsequent raw TCP connections work without the toggle issue.

    Args:
        timeout: How long to browse (seconds).
        callback: Optional callable(name, host, port) called per discovery.
        cancel_event: Optional threading.Event; set it to cancel the browse early.
    """
    from Foundation import NSObject, NSRunLoop, NSDate, NSDefaultRunLoopMode

    results = []

    class BrowseDelegate(NSObject):
        def netServiceBrowser_didFindService_moreComing_(self, browser, service, more):
            service.setDelegate_(self)
            service.resolveWithTimeout_(5.0)

        def netServiceDidResolveAddress_(self, service):
            name = str(service.name())
            host = str(service.hostName()).rstrip(".")
            port = service.port()
            entry = {"name": name, "host": host, "port": port}
            results.append(entry)
            print(f"[discovery] Found: {name} at {host}:{port}")
            if callback:
                try:
                    callback(name, host, port)
                except Exception:
                    pass

        def netServiceBrowser_didNotSearch_(self, browser, error):
            print(f"[discovery] Browse error: {error}")

    try:
        from AppKit import NSNetServiceBrowser
        delegate = BrowseDelegate.alloc().init()
        browser = NSNetServiceBrowser.alloc().init()
        browser.setDelegate_(delegate)
        browser.searchForServicesOfType_inDomain_(VIDEOHUB_BONJOUR_TYPE, "local.")

        # Pump run loop for the timeout duration, checking for cancel
        deadline = NSDate.dateWithTimeIntervalSinceNow_(timeout)
        while NSDate.date().compare_(deadline) < 0:
            if cancel_event and cancel_event.is_set():
                print("[discovery] Cancelled by user")
                break
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.1),
            )

        browser.stop()
        print(f"[discovery] Browse complete: {len(results)} device(s) found")
    except Exception as e:
        print(f"[discovery] Bonjour browse failed: {e}")

    return results


class VideohubConnection:
    """Manages TCP connection to a Blackmagic Videohub."""

    def __init__(
        self,
        on_state_update: callable = None,
        on_connect: callable = None,
        on_disconnect: callable = None,
        num_inputs: int = NUM_IO,
        num_outputs: int = NUM_IO,
    ):
        self.sock: socket.socket | None = None
        self.connected = False
        # Device info (populated from VIDEOHUB DEVICE: block)
        self.model_name: str = ""
        self.friendly_name: str = ""
        self.unique_id: str = ""
        self.device_present: bool = False
        self.num_inputs: int = num_inputs
        self.num_outputs: int = num_outputs
        self.protocol_version: str = ""
        # Dynamic I/O arrays sized to the current configuration
        self.input_labels = [f"Input {i + 1}" for i in range(num_inputs)]
        self.output_labels = [f"Output {i + 1}" for i in range(num_outputs)]
        self.routing = [0] * num_outputs  # routing[output_idx] = input_idx
        self.on_state_update = on_state_update
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self._stop = threading.Event()
        self.lock = threading.Lock()

    def connect(self, ip: str, retries: int = 3) -> bool | str:
        """Connect to the Videohub with automatic retry.

        Retries up to `retries` times with a 1-second delay between
        attempts to handle transient network issues (adapter wake,
        route not yet established, etc.).
        Returns True on success, error string on failure.
        """
        import time as _time
        # Trigger a quick Bonjour browse to ensure Local Network permission
        # is granted before attempting raw TCP (macOS 15+ requirement)
        try:
            discover_videohubs(timeout=0.5)
        except Exception:
            pass
        last_error = ""
        print(f"[connection] Connecting to {ip}:{VIDEOHUB_PORT} (up to {retries} attempts)...")
        for attempt in range(retries):
            try:
                print(f"[connection] Attempt {attempt + 1}/{retries}...")
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5)
                self.sock.connect((ip, VIDEOHUB_PORT))
                self.sock.settimeout(None)
                self.connected = True
                self._stop.clear()
                t = threading.Thread(target=self._recv_loop, daemon=True)
                t.start()
                print(f"[connection] Connected to {ip}:{VIDEOHUB_PORT}")
                if self.on_connect:
                    self.on_connect()
                return True
            except Exception as e:
                last_error = str(e)
                print(f"[connection] Attempt {attempt + 1} failed: {last_error}")
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                if attempt < retries - 1:
                    print("[connection] Retrying in 1s...")
                    _time.sleep(1)
        print(f"[connection] All {retries} attempts failed: {last_error}")
        self.connected = False
        return last_error

    def disconnect(self) -> None:
        print("[connection] Disconnecting...")
        self._stop.set()
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        if self.on_disconnect:
            self.on_disconnect()

    def _recv_loop(self) -> None:
        print("[connection] Receive loop started")
        buf = ""
        while not self._stop.is_set():
            try:
                data = self.sock.recv(4096)
                if not data:
                    print("[connection] Remote closed connection")
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    self._parse_block(block.strip())
            except Exception:
                break
        self.connected = False
        if self.on_disconnect:
            self.on_disconnect()

    def _parse_block(self, block: str) -> None:
        lines = block.split("\n")
        if not lines:
            return
        header = lines[0].rstrip(":")
        data = lines[1:]

        with self.lock:
            if header == "PROTOCOL PREAMBLE":
                for line in data:
                    if line.startswith("Version:"):
                        self.protocol_version = line.split(":", 1)[1].strip()
                        print(f"[connection] Protocol version: {self.protocol_version}")

            elif header == "VIDEOHUB DEVICE":
                for line in data:
                    if ": " in line:
                        key, val = line.split(": ", 1)
                        key = key.strip()
                        val = val.strip()
                        if key == "Device present":
                            self.device_present = (val == "true")
                        elif key == "Model name":
                            self.model_name = val
                            print(f"[connection] Model: {val}")
                        elif key == "Friendly name":
                            self.friendly_name = val
                        elif key == "Unique ID":
                            self.unique_id = val
                        elif key == "Video inputs":
                            try:
                                new_in = int(val)
                                if new_in != self.num_inputs:
                                    self.num_inputs = new_in
                                    self.input_labels = [
                                        f"Input {i + 1}" for i in range(new_in)
                                    ]
                                    print(f"[connection] Resized inputs to {new_in}")
                            except ValueError:
                                pass
                        elif key == "Video outputs":
                            try:
                                new_out = int(val)
                                if new_out != self.num_outputs:
                                    self.num_outputs = new_out
                                    self.output_labels = [
                                        f"Output {i + 1}" for i in range(new_out)
                                    ]
                                    self.routing = [0] * new_out
                                    print(f"[connection] Resized outputs to {new_out}")
                            except ValueError:
                                pass

            elif header == "INPUT LABELS":
                for line in data:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        try:
                            idx = int(parts[0])
                        except ValueError:
                            continue
                        if 0 <= idx < self.num_inputs:
                            self.input_labels[idx] = parts[1]
            elif header == "OUTPUT LABELS":
                for line in data:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        try:
                            idx = int(parts[0])
                        except ValueError:
                            continue
                        if 0 <= idx < self.num_outputs:
                            self.output_labels[idx] = parts[1]
            elif header == "VIDEO OUTPUT ROUTING":
                for line in data:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        try:
                            out_idx = int(parts[0])
                            in_idx = int(parts[1])
                        except ValueError:
                            continue
                        if 0 <= out_idx < self.num_outputs and 0 <= in_idx < self.num_inputs:
                            self.routing[out_idx] = in_idx

        if self.on_state_update:
            self.on_state_update()

    def set_route(self, output_idx: int, input_idx: int) -> None:
        if not self.connected:
            return
        cmd = f"VIDEO OUTPUT ROUTING:\n{output_idx} {input_idx}\n\n"
        try:
            self.sock.sendall(cmd.encode("utf-8"))
        except Exception:
            pass

    def set_input_label(self, idx: int, label: str) -> None:
        with self.lock:
            self.input_labels[idx] = label
        if not self.connected:
            return
        cmd = f"INPUT LABELS:\n{idx} {label}\n\n"
        try:
            self.sock.sendall(cmd.encode("utf-8"))
        except Exception:
            pass

    def set_output_label(self, idx: int, label: str) -> None:
        with self.lock:
            self.output_labels[idx] = label
        if not self.connected:
            return
        cmd = f"OUTPUT LABELS:\n{idx} {label}\n\n"
        try:
            self.sock.sendall(cmd.encode("utf-8"))
        except Exception:
            pass
