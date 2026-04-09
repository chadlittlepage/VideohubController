"""Console logging - captures stdout/stderr to a file for debugging.

Tees output to both terminal and a timestamped log file under
~/Library/Application Support/Videohub Controller/logs/console.log.
Auto-rotates when the log exceeds 30 days or 10 MB.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Videohub Controller"
LOG_DIR = APP_SUPPORT_DIR / "logs"
LOG_PATH = LOG_DIR / "console.log"

LOG_MAX_AGE_DAYS = 30
LOG_MAX_SIZE_BYTES = 10 * 1024 * 1024
LOG_TRUNCATE_TO_BYTES = 5 * 1024 * 1024


def _rotate_log_if_needed() -> None:
    try:
        if not LOG_PATH.exists():
            return
        stat = LOG_PATH.stat()
        age_days = (time.time() - stat.st_mtime) / 86400
        if age_days > LOG_MAX_AGE_DAYS:
            backup = LOG_PATH.with_suffix(".log.old")
            try:
                if backup.exists():
                    backup.unlink()
                LOG_PATH.rename(backup)
            except Exception:
                try:
                    LOG_PATH.write_text("", encoding="utf-8")
                except Exception:
                    pass
            return
        if stat.st_size > LOG_MAX_SIZE_BYTES:
            try:
                with LOG_PATH.open("rb") as f:
                    f.seek(-LOG_TRUNCATE_TO_BYTES, 2)
                    f.readline()
                    tail = f.read()
                LOG_PATH.write_bytes(
                    b"=== log truncated (rolling 5 MB cap) ===\n" + tail
                )
            except Exception:
                pass
    except Exception:
        pass


class _Tee:
    """File-like object that writes to multiple streams with timestamps."""

    def __init__(self, *streams, log_stream=None):
        self._streams = streams
        self._log_stream = log_stream
        self._log_at_line_start = True

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
        if self._log_stream is not None:
            self._write_log(data)

    def _write_log(self, data):
        try:
            now = datetime.now()
            ms = now.microsecond // 1000
            stamp = now.strftime(f"[%H:%M:%S.{ms:03d}] ")
            i = 0
            n = len(data)
            while i < n:
                if self._log_at_line_start:
                    self._log_stream.write(stamp)
                    self._log_at_line_start = False
                nl = data.find("\n", i)
                if nl == -1:
                    self._log_stream.write(data[i:])
                    break
                self._log_stream.write(data[i:nl + 1])
                self._log_at_line_start = True
                i = nl + 1
            self._log_stream.flush()
        except Exception:
            pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass
        if self._log_stream is not None:
            try:
                self._log_stream.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def setup_logging() -> None:
    """Redirect stdout/stderr to both terminal AND a log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _rotate_log_if_needed()

    try:
        log_file = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    except Exception:
        return

    log_file.write(f"\n{'=' * 70}\n")
    log_file.write(f"Session started: {datetime.now().isoformat()}\n")
    log_file.write(f"{'=' * 70}\n")
    log_file.flush()

    sys.stdout = _Tee(sys.__stdout__, log_stream=log_file)
    sys.stderr = _Tee(sys.__stderr__, log_stream=log_file)


def get_log_path() -> Path:
    return LOG_PATH


def get_recent_log(max_bytes: int = 200_000) -> str:
    if not LOG_PATH.exists():
        return ""
    try:
        size = LOG_PATH.stat().st_size
        with LOG_PATH.open("rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, 2)
                f.readline()
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
