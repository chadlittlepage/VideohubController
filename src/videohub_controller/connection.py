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

    def connect(self, ip: str) -> bool | str:
        """Connect to the Videohub. Returns True on success, error string on failure."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((ip, VIDEOHUB_PORT))
            self.sock.settimeout(None)
            self.connected = True
            self._stop.clear()
            t = threading.Thread(target=self._recv_loop, daemon=True)
            t.start()
            if self.on_connect:
                self.on_connect()
            return True
        except Exception as e:
            self.connected = False
            return str(e)

    def disconnect(self) -> None:
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
        buf = ""
        while not self._stop.is_set():
            try:
                data = self.sock.recv(4096)
                if not data:
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
