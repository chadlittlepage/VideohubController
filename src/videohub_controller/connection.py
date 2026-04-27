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


def _enumerate_local_ipv4() -> list[tuple]:
    """Return list of (local_ip, subnet) pairs for every active IPv4 interface,
    excluding loopback. Tries netifaces first, then falls back to parsing
    `ifconfig`."""
    import ipaddress

    pairs: list[tuple[str, ipaddress.IPv4Network]] = []
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            for info in addrs.get(netifaces.AF_INET, []):
                ip = info.get("addr", "")
                mask = info.get("netmask", "")
                if not ip or ip.startswith("127."):
                    continue
                try:
                    net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                    pairs.append((ip, net))
                except Exception:
                    pass
        return pairs
    except ImportError:
        pass

    import subprocess
    try:
        out = subprocess.check_output(["ifconfig"], text=True)
        for line in out.splitlines():
            if "inet " not in line or "127.0.0.1" in line:
                continue
            parts = line.split()
            try:
                ip_idx = parts.index("inet") + 1
                ip = parts[ip_idx]
                mask_idx = parts.index("netmask") + 1 if "netmask" in parts else -1
                if mask_idx <= 0:
                    continue
                mask_hex = parts[mask_idx]
                mask_int = int(mask_hex, 16)
                mask_str = str(ipaddress.IPv4Address(mask_int))
                net = ipaddress.IPv4Network(f"{ip}/{mask_str}", strict=False)
                pairs.append((ip, net))
            except Exception:
                pass
    except Exception as e:
        print(f"[discovery] Failed to enumerate interfaces: {e}")
    return pairs


def prime_local_network_permission() -> None:
    """Force macOS to register the app in Privacy & Security → Local Network.

    On macOS 15+, an app only appears in the Local Network permission list
    AFTER it has attempted to communicate with a private-IP LAN address.
    Bonjour browse alone is insufficient — it must be a real socket attempt
    to a private IPv4. Without this, a non-admin user who has never granted
    permission cannot find the toggle in System Settings.

    We open a non-blocking TCP socket to a benign private-network address
    that is guaranteed to fail fast. The kernel's failure path is exactly
    what registers us in the TCC list.
    """
    targets = [
        "169.254.255.255",  # link-local broadcast
        "192.168.255.255",  # common home/office reserved
        "10.255.255.255",   # corp/datacenter reserved
    ]
    for ip in targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.05)
            try:
                s.connect((ip, 9))  # port 9 = Discard, conventional no-op
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass
        except Exception:
            pass
    print("[permission] Local Network trigger sent — app should now appear "
          "in System Settings → Privacy & Security → Local Network")


# ---------------------------------------------------------------------------
# Transport abstraction
# ---------------------------------------------------------------------------
# VideohubConnection used to talk POSIX sockets directly. POSIX TCP to a
# private IP is gated by macOS 15's per-user Local Network permission, which
# is what blocks non-admin users even though Bonjour discovery succeeds.
#
# We now have two transports:
#   _SocketTransport   — original raw TCP. Used when the user types an IP
#                        manually (no NSNetService available).
#   _NSStreamTransport — opens the connection via Apple's NSNetService
#                        getInputStream:outputStream: API. Apple's brokered
#                        Bonjour path may bypass the per-user Local Network
#                        gate (Sequoia tightened this; not 100% guaranteed
#                        but worth attempting for the standard-user case).
#
# Both transports expose the same minimal API:
#   start(on_data: callable(bytes), on_close: callable())
#   send(data: bytes)
#   close()
# and run the inbound read loop on whatever thread/run-loop they prefer.
# ---------------------------------------------------------------------------


class _SocketTransport:
    """Raw POSIX TCP transport. Requires Local Network permission on macOS 15+."""

    def __init__(self):
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_data = None
        self._on_close = None

    def open(self, ip: str, port: int = VIDEOHUB_PORT, timeout: float = 5.0) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.settimeout(None)
        self._sock = s

    def start(self, on_data, on_close) -> None:
        self._on_data = on_data
        self._on_close = on_close
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def send(self, data: bytes) -> None:
        if not self._sock:
            raise IOError("Socket transport not open")
        self._sock.sendall(data)

    def close(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _loop(self) -> None:
        print("[transport-sock] read loop started")
        while not self._stop.is_set():
            try:
                data = self._sock.recv(4096)
                if not data:
                    print("[transport-sock] remote closed")
                    break
                if self._on_data:
                    self._on_data(data)
            except Exception as e:
                print(f"[transport-sock] read error: {e}")
                break
        print("[transport-sock] read loop ended")
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass


_StreamDelegate = None  # lazily-defined module-level NSObject subclass


def _get_stream_delegate_class():
    """Module-level NSStream delegate factory. Defining inside a function
    crashes PyObjC on the second instantiation (same trap as BrowseDelegate /
    ResetDelegate)."""
    global _StreamDelegate
    if _StreamDelegate is not None:
        return _StreamDelegate

    from Foundation import NSObject

    NSStreamEventOpenCompleted = 1 << 0  # 1
    NSStreamEventHasBytesAvailable = 1 << 1  # 2
    NSStreamEventErrorOccurred = 1 << 3  # 8
    NSStreamEventEndEncountered = 1 << 4  # 16

    class StreamDelegate(NSObject):
        def stream_handleEvent_(self, stream, event):
            transport = self._transport
            if transport is None:
                return
            if event == NSStreamEventOpenCompleted:
                pass
            elif event == NSStreamEventHasBytesAvailable:
                # Drain everything available in this event
                buf = bytearray(8192)
                # NSInputStream.read:maxLength: -> (bytesRead, buffer)
                try:
                    n, data = stream.read_maxLength_(None, 8192)
                except TypeError:
                    # Older PyObjC signature variant
                    n = stream.read_maxLength_(buf, 8192)
                    data = bytes(buf[:n]) if n > 0 else b""
                if n > 0:
                    if not isinstance(data, (bytes, bytearray)):
                        try:
                            data = bytes(data)
                        except Exception:
                            data = bytes(buf[:n])
                    if transport._on_data:
                        try:
                            transport._on_data(bytes(data[:n]))
                        except Exception as e:
                            print(f"[transport-stream] on_data raised: {e}")
                elif n == 0:
                    # EOF
                    transport._notify_closed()
            elif event == NSStreamEventErrorOccurred:
                err = stream.streamError()
                print(f"[transport-stream] error: {err}")
                transport._notify_closed()
            elif event == NSStreamEventEndEncountered:
                print("[transport-stream] end of stream")
                transport._notify_closed()

    _StreamDelegate = StreamDelegate
    return _StreamDelegate


class _NSStreamTransport:
    """Bonjour-mediated transport. Opens NSStream pairs via
    NSNetService.getInputStream:outputStream:. The connection flows through
    Apple's brokered Bonjour path which historically did not require the
    per-user Local Network permission. macOS 15 may have tightened this —
    this transport is the experiment to find out."""

    def __init__(self, ns_service):
        self._service = ns_service
        self._in = None
        self._out = None
        self._delegate = None
        self._on_data = None
        self._on_close = None
        self._closed = False
        self._loop_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._opened = threading.Event()

    def open(self) -> None:
        ok, in_stream, out_stream = self._service.getInputStream_outputStream_(None, None)
        if not ok or in_stream is None or out_stream is None:
            raise IOError("NSNetService.getInputStream:outputStream: returned no streams")
        self._in = in_stream
        self._out = out_stream

    def start(self, on_data, on_close) -> None:
        self._on_data = on_data
        self._on_close = on_close
        self._closed = False
        delegate_cls = _get_stream_delegate_class()
        self._delegate = delegate_cls.alloc().init()
        self._delegate._transport = self
        self._in.setDelegate_(self._delegate)
        self._out.setDelegate_(self._delegate)

        # Run the streams on their own NSRunLoop in a background thread so
        # we don't depend on the main run loop being pumped on time.
        self._stop.clear()
        self._opened.clear()
        self._loop_thread = threading.Thread(target=self._run, daemon=True)
        self._loop_thread.start()
        # Wait for streams to register before any send attempt
        self._opened.wait(timeout=2.0)

    def _run(self) -> None:
        from Foundation import NSRunLoop, NSDate, NSDefaultRunLoopMode
        loop = NSRunLoop.currentRunLoop()
        self._in.scheduleInRunLoop_forMode_(loop, NSDefaultRunLoopMode)
        self._out.scheduleInRunLoop_forMode_(loop, NSDefaultRunLoopMode)
        self._in.open()
        self._out.open()
        self._opened.set()
        print("[transport-stream] streams opened on dedicated run loop")
        while not self._stop.is_set():
            loop.runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.1),
            )
        try:
            self._in.close()
            self._out.close()
        except Exception:
            pass
        print("[transport-stream] run loop exited")

    def send(self, data: bytes) -> None:
        if not self._out:
            raise IOError("Stream transport not open")
        # NSOutputStream.write:maxLength: -> int (bytes written or -1)
        n = self._out.write_maxLength_(data, len(data))
        if n < 0:
            err = self._out.streamError()
            raise IOError(f"NSStream write failed: {err}")
        if n != len(data):
            # Short write — write the rest
            remaining = data[n:]
            while remaining:
                n2 = self._out.write_maxLength_(remaining, len(remaining))
                if n2 <= 0:
                    err = self._out.streamError()
                    raise IOError(f"NSStream short-write follow-up failed: {err}")
                remaining = remaining[n2:]

    def close(self) -> None:
        self._stop.set()

    def _notify_closed(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass


def _arp_known_ipv4_neighbors() -> list[str]:
    """Parse the kernel ARP table and return all IPv4 neighbor IPs that have
    a resolved MAC (skip 'incomplete' entries). Catches direct-connected gear
    on any interface — including Videohubs on link-local 169.254/16 — without
    needing to scan a full /16."""
    import subprocess
    import re

    ips: list[str] = []
    try:
        out = subprocess.check_output(["arp", "-an"], text=True, timeout=2.0)
    except Exception as e:
        print(f"[discovery] arp -an failed: {e}")
        return ips

    # Format: "? (169.254.125.9) at 60:d0:39:9c:e9:c6 on en14 [ethernet]"
    pat = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+)\s")
    for line in out.splitlines():
        m = pat.search(line)
        if not m:
            continue
        ip = m.group(1)
        mac = m.group(2)
        if mac == "(incomplete)" or "incomplete" in line.lower():
            continue
        if ip.endswith(".255") or ip.endswith(".0"):
            continue
        ips.append(ip)
    return ips


def scan_port_9990(cancel_event: threading.Event = None) -> list[dict]:
    """Scan local subnets and ARP-known neighbors for devices listening on
    port 9990.

    Strategy:
    1. Probe every IPv4 neighbor the OS already knows about (ARP table) —
       cheap and finds direct-connected Videohubs on link-local 169.254/16
       regardless of which interface they came in on.
    2. Probe each interface's subnet, narrowing subnets larger than /24 to a
       /24 window around the local IP (so a /18 corporate subnet or /16
       link-local subnet doesn't blow up to 65k hosts).

    All probes run in parallel via ThreadPoolExecutor so a typical scan
    completes in 1-3 seconds.
    """
    import ipaddress
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: list[dict] = []

    pairs = _enumerate_local_ipv4()
    if not pairs:
        print("[discovery] No active subnets found for port scan")
        return results

    # Build scan target list — start with ARP neighbors (fast hits), then add
    # subnet sweeps narrowed to /24 around the local IP.
    arp_ips = _arp_known_ipv4_neighbors()
    if arp_ips:
        print(f"[discovery] {len(arp_ips)} ARP-known neighbor(s) to probe: "
              f"{', '.join(arp_ips[:8])}{'...' if len(arp_ips) > 8 else ''}")

    scan_nets: list[ipaddress.IPv4Network] = []
    for local_ip, net in pairs:
        if net.num_addresses <= 256:
            scan_nets.append(net)
        else:
            narrow = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
            print(f"[discovery] {net} too large ({net.num_addresses} hosts); "
                  f"scanning narrowed window {narrow} around {local_ip}")
            scan_nets.append(narrow)

    own_ips = {ip for ip, _ in pairs}
    host_strs: list[str] = []
    seen: set[str] = set()
    for ip in arp_ips:
        if ip in own_ips or ip in seen:
            continue
        seen.add(ip)
        host_strs.append(ip)
    for net in scan_nets:
        for h in net.hosts():
            s = str(h)
            if s in own_ips or s in seen:
                continue
            seen.add(s)
            host_strs.append(s)

    if not host_strs:
        print("[discovery] No hosts to scan")
        return results

    print(f"[discovery] Port-scanning {len(host_strs)} host(s)...")

    PER_HOST_TIMEOUT = 0.3
    MAX_WORKERS = 128
    SCAN_DEADLINE = 20

    import time as _time
    deadline = _time.time() + SCAN_DEADLINE

    def _probe(host_str: str) -> str | None:
        if cancel_event and cancel_event.is_set():
            return None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(PER_HOST_TIMEOUT)
            s.connect((host_str, VIDEOHUB_PORT))
            s.close()
            return host_str
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_probe, h): h for h in host_strs}
        try:
            for fut in as_completed(futures, timeout=SCAN_DEADLINE):
                if cancel_event and cancel_event.is_set():
                    print("[discovery] Port scan cancelled")
                    break
                if _time.time() > deadline:
                    print("[discovery] Port scan deadline hit")
                    break
                hit = fut.result()
                if hit:
                    print(f"[discovery] Port 9990 open: {hit}")
                    results.append({"name": "Videohub", "host": hit, "port": VIDEOHUB_PORT})
        except Exception as e:
            print(f"[discovery] Port scan iteration error: {e}")

    print(f"[discovery] Port scan complete: {len(results)} device(s) found")
    return results


_BrowseDelegate = None  # lazily-defined module-level NSObject subclass


def _get_browse_delegate_class():
    """Return the module-level BrowseDelegate class, defining it on first use.
    Defining it once at module scope (not inside discover_videohubs) avoids
    `objc.error: BrowseDelegate is overriding existing Objective-C class` on
    repeat calls."""
    global _BrowseDelegate
    if _BrowseDelegate is not None:
        return _BrowseDelegate

    from Foundation import NSObject

    class BrowseDelegate(NSObject):
        def netServiceBrowser_didFindService_moreComing_(self, browser, service, more):
            print(f"[discovery] Service found: {service.name()} (resolving...)")
            self._pending_services.append(service)
            self._state["resolves_outstanding"] += 1
            service.setDelegate_(self)
            service.resolveWithTimeout_(8.0)

        def netServiceDidResolveAddress_(self, service):
            self._state["resolves_outstanding"] = max(0, self._state["resolves_outstanding"] - 1)
            name = str(service.name())
            if name in self._resolved_names:
                return
            self._resolved_names.add(name)
            hostname = str(service.hostName()).rstrip(".")
            port = service.port()
            ip = hostname
            try:
                addr_info = socket.getaddrinfo(hostname, port, socket.AF_INET)
                if addr_info:
                    ip = addr_info[0][4][0]
                    print(f"[discovery] Resolved hostname {hostname} -> {ip}")
            except Exception as e:
                print(f"[discovery] DNS resolve failed for {hostname}: {e}")
            entry = {"name": name, "host": ip, "port": port,
                     "_nsnetservice": service}
            self._results.append(entry)
            print(f"[discovery] Found: {name} at {ip}:{port}")
            cb = self._callback
            if cb:
                try:
                    cb(name, ip, port)
                except Exception as e:
                    print(f"[discovery] Callback error: {e}")

        def netService_didNotResolve_(self, service, error):
            self._state["resolves_outstanding"] = max(0, self._state["resolves_outstanding"] - 1)
            print(f"[discovery] Failed to resolve {service.name()}: {error}")

        def netServiceBrowser_didNotSearch_(self, browser, error):
            print(f"[discovery] Browse error: {error}")

    _BrowseDelegate = BrowseDelegate
    return _BrowseDelegate


def discover_videohubs(timeout: float = 5.0, callback=None,
                       cancel_event: threading.Event = None) -> list[dict]:
    """Discover Videohubs on the local network via Bonjour/mDNS.

    Browses for `_videohub._tcp.` on every interface (default mDNSResponder
    behavior), then waits for ALL in-flight resolves to complete before
    returning. The browse phase runs the full `timeout`; we then drain the
    resolve phase for up to RESOLVE_DRAIN seconds. This guarantees devices
    that take longer to resolve their .local hostname (typical on
    direct-connected / link-local interfaces) are not dropped.

    On macOS 15+, this Bonjour browse also triggers the Local Network
    permission prompt if it hasn't been granted yet, which ensures
    subsequent raw TCP connections work without the toggle issue.

    Args:
        timeout: How long to browse for new services (seconds).
        callback: Optional callable(name, host, port) called per discovery.
        cancel_event: Optional threading.Event; set it to cancel the browse early.
    """
    from Foundation import NSRunLoop, NSDate, NSDefaultRunLoopMode

    results: list[dict] = []
    pending_services: list = []        # prevents GC of NSNetService refs being resolved
    resolved_names: set[str] = set()   # dedupe across multiple interface advertisements
    state = {"resolves_outstanding": 0}

    try:
        from AppKit import NSNetServiceBrowser
        delegate_class = _get_browse_delegate_class()
        delegate = delegate_class.alloc().init()
        # Per-call state attached to the instance so the module-level class
        # can be reused safely across repeat Discover clicks.
        delegate._results = results
        delegate._pending_services = pending_services
        delegate._resolved_names = resolved_names
        delegate._state = state
        delegate._callback = callback
        browser = NSNetServiceBrowser.alloc().init()
        browser.setDelegate_(delegate)
        print(f"[discovery] Browsing for {VIDEOHUB_BONJOUR_TYPE} in local. (timeout={timeout}s)")
        browser.searchForServicesOfType_inDomain_(VIDEOHUB_BONJOUR_TYPE, "local.")

        # Phase 1: full browse window. Don't shorten on first hit — Videohubs
        # on different interfaces (LAN vs link-local direct-connect) can
        # appear several hundred ms apart.
        browse_deadline = NSDate.dateWithTimeIntervalSinceNow_(timeout)
        while NSDate.date().compare_(browse_deadline) < 0:
            if cancel_event and cancel_event.is_set():
                print("[discovery] Cancelled by user")
                browser.stop()
                return results
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.1),
            )

        browser.stop()

        # Phase 2: drain pending resolves so devices that browsed late or
        # have slow .local lookups still land in results.
        RESOLVE_DRAIN = 8.0
        drain_deadline = NSDate.dateWithTimeIntervalSinceNow_(RESOLVE_DRAIN)
        while state["resolves_outstanding"] > 0 and NSDate.date().compare_(drain_deadline) < 0:
            if cancel_event and cancel_event.is_set():
                print("[discovery] Cancelled by user during resolve drain")
                break
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.1),
            )

        if state["resolves_outstanding"] > 0:
            print(f"[discovery] {state['resolves_outstanding']} resolve(s) still pending after drain")
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
        self._transport = None
        self._recv_buf: str = ""
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
        """Connect via raw TCP socket. Used when no NSNetService is available
        (manually-typed IP). Requires Local Network permission on macOS 15+."""
        import time as _time
        try:
            print("[connection] Pre-connect Bonjour probe (Local Network permission check)...")
            discover_videohubs(timeout=0.5)
        except Exception as e:
            print(f"[connection] Pre-connect probe failed: {e}")

        last_error = ""
        print(f"[connection] Connecting to {ip}:{VIDEOHUB_PORT} (up to {retries} attempts)...")
        for attempt in range(retries):
            try:
                print(f"[connection] Attempt {attempt + 1}/{retries}...")
                t = _SocketTransport()
                t.open(ip, VIDEOHUB_PORT, timeout=5)
                self._attach_transport(t)
                print(f"[connection] Connected to {ip}:{VIDEOHUB_PORT} via raw socket")
                if self.on_connect:
                    self.on_connect()
                return True
            except Exception as e:
                last_error = str(e)
                print(f"[connection] Attempt {attempt + 1} failed: {last_error}")
                if attempt < retries - 1:
                    print("[connection] Retrying in 1s...")
                    _time.sleep(1)
        print(f"[connection] All {retries} attempts failed: {last_error}")
        self.connected = False
        return last_error

    def connect_via_nsservice(self, ns_service) -> bool | str:
        """Connect via NSNetService.getInputStream:outputStream:. Apple's
        brokered Bonjour path may bypass macOS 15's per-user Local Network
        permission gate. Falls back to raw socket on the resolved IP if the
        stream open fails."""
        try:
            print("[connection] Connecting via NSNetService brokered streams...")
            t = _NSStreamTransport(ns_service)
            t.open()
            self._attach_transport(t)
            print("[connection] Connected via NSStream transport")
            if self.on_connect:
                self.on_connect()
            return True
        except Exception as e:
            err = str(e)
            print(f"[connection] NSStream connect failed: {err}; falling back to raw socket")
            # Fallback: raw socket on resolved IP
            try:
                addresses = ns_service.addresses()
                if addresses:
                    for addr_data in addresses:
                        raw = bytes(addr_data)
                        # sockaddr_in: family(2), port(2), addr(4)
                        if len(raw) >= 8 and raw[1] == 2:  # AF_INET
                            ip_bytes = raw[4:8]
                            ip = ".".join(str(b) for b in ip_bytes)
                            return self.connect(ip)
            except Exception as fallback_err:
                print(f"[connection] Fallback IP extraction failed: {fallback_err}")
            self.connected = False
            return err

    def _attach_transport(self, transport) -> None:
        """Wire a freshly-opened transport into the receive pipeline."""
        self._transport = transport
        self.connected = True
        self._stop.clear()
        self._recv_buf = ""
        transport.start(on_data=self._handle_bytes, on_close=self._handle_transport_close)

    def _handle_bytes(self, data: bytes) -> None:
        """Single byte-stream entry point — used by both transports."""
        try:
            self._recv_buf += data.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[connection] decode error: {e}")
            return
        while "\n\n" in self._recv_buf:
            block, self._recv_buf = self._recv_buf.split("\n\n", 1)
            try:
                self._parse_block(block.strip())
            except Exception as e:
                print(f"[connection] parse error: {e}")

    def _handle_transport_close(self) -> None:
        if not self.connected and self._transport is None:
            return
        self.connected = False
        if self.on_disconnect:
            try:
                self.on_disconnect()
            except Exception:
                pass

    def disconnect(self) -> None:
        print("[connection] Disconnecting...")
        self._stop.set()
        self.connected = False
        if self._transport:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None
        # Clear identification fields so a subsequent connection to a
        # different device cannot use stale values.
        self.unique_id = ""
        self.model_name = ""
        self.friendly_name = ""
        self.device_present = False
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
                            print(f"[connection] Device present: {val}")
                        elif key == "Model name":
                            self.model_name = val
                            print(f"[connection] Model name: {val}")
                        elif key == "Friendly name":
                            self.friendly_name = val
                            print(f"[connection] Friendly name: {val}")
                        elif key == "Unique ID":
                            self.unique_id = val
                            print(f"[connection] Unique ID: {val}")
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
                print(f"[connection] Received INPUT LABELS ({len(data)} entries)")
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
                print(f"[connection] Received OUTPUT LABELS ({len(data)} entries)")
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
                print(f"[connection] Received VIDEO OUTPUT ROUTING ({len(data)} entries)")
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
            self._transport.send(cmd.encode("utf-8"))
        except Exception as e:
            print(f"[connection] Send route failed: {e}")

    def set_input_label(self, idx: int, label: str) -> None:
        with self.lock:
            self.input_labels[idx] = label
        if not self.connected:
            return
        cmd = f"INPUT LABELS:\n{idx} {label}\n\n"
        try:
            self._transport.send(cmd.encode("utf-8"))
        except Exception as e:
            print(f"[connection] Send input label failed: {e}")

    def set_output_label(self, idx: int, label: str) -> None:
        with self.lock:
            self.output_labels[idx] = label
        if not self.connected:
            return
        cmd = f"OUTPUT LABELS:\n{idx} {label}\n\n"
        try:
            self._transport.send(cmd.encode("utf-8"))
        except Exception as e:
            print(f"[connection] Send output label failed: {e}")


def probe_device_info(ip: str, port: int = VIDEOHUB_PORT,
                      timeout: float = 2.0) -> dict | None:
    """Quick TCP connect to read VIDEOHUB DEVICE block without full connection.

    Returns dict with model_name, friendly_name, unique_id, num_inputs, num_outputs,
    or None on failure.
    """
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        buf = ""
        import time
        deadline = time.time() + timeout
        info = {}
        while time.time() < deadline:
            try:
                data = s.recv(4096)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    lines = block.strip().split("\n")
                    if not lines:
                        continue
                    header = lines[0].rstrip(":")
                    if header == "VIDEOHUB DEVICE":
                        for line in lines[1:]:
                            if ": " in line:
                                k, v = line.split(": ", 1)
                                k, v = k.strip(), v.strip()
                                if k == "Model name":
                                    info["model_name"] = v
                                elif k == "Friendly name":
                                    info["friendly_name"] = v
                                elif k == "Unique ID":
                                    info["unique_id"] = v
                                elif k == "Video inputs":
                                    info["num_inputs"] = int(v)
                                elif k == "Video outputs":
                                    info["num_outputs"] = int(v)
                        if info.get("unique_id"):
                            print(f"[probe] {ip}: {info.get('model_name', '?')} "
                                  f"({info.get('friendly_name', '')}) id={info['unique_id']}")
                            return info
                        return None
            except socket.timeout:
                break
    except Exception as e:
        print(f"[probe] {ip}: failed — {e}")
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass
    return None
