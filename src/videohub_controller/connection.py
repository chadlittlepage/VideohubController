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
NUM_IO = 10


class VideohubConnection:
    """Manages TCP connection to a Blackmagic Videohub."""

    def __init__(
        self,
        on_state_update: callable = None,
        on_connect: callable = None,
        on_disconnect: callable = None,
    ):
        self.sock: socket.socket | None = None
        self.connected = False
        self.input_labels = [f"Input {i + 1}" for i in range(NUM_IO)]
        self.output_labels = [f"Output {i + 1}" for i in range(NUM_IO)]
        self.routing = [0] * NUM_IO  # routing[output_idx] = input_idx
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
            if header == "INPUT LABELS":
                for line in data:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        try:
                            idx = int(parts[0])
                        except ValueError:
                            continue
                        if 0 <= idx < NUM_IO:
                            self.input_labels[idx] = parts[1]
            elif header == "OUTPUT LABELS":
                for line in data:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        try:
                            idx = int(parts[0])
                        except ValueError:
                            continue
                        if 0 <= idx < NUM_IO:
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
                        if 0 <= out_idx < NUM_IO and 0 <= in_idx < NUM_IO:
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
