"""进程内存巡检：启动记一条，之后按天写入日志，便于对照是否泄漏。"""

from __future__ import annotations

import os
import resource
import subprocess
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

_ROOT = os.path.dirname(__file__)
DEFAULT_LOG_PATH = os.path.join(_ROOT, "logs", "memory.log")
DEFAULT_INTERVAL_S = 24 * 60 * 60


def _rss_mb() -> Optional[float]:
    """当前进程常驻内存（MB）。优先 ps；失败则退回 ru_maxrss（峰值）。"""
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        kb = int(out.strip() or "0")
        if kb > 0:
            return round(kb / 1024.0, 2)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass

    try:
        # macOS：ru_maxrss 单位是字节；Linux 是 KB。
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if os.uname().sysname == "Darwin":
            return round(peak / (1024.0 * 1024.0), 2)
        return round(peak / 1024.0, 2)
    except Exception:
        return None


def append_memory_log(
    reason: str,
    *,
    log_path: str = DEFAULT_LOG_PATH,
    panel_visible: Optional[bool] = None,
) -> None:
    rss = _rss_mb()
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    parts = [
        ts,
        f"pid={os.getpid()}",
        f"reason={reason}",
        f"rss_mb={rss if rss is not None else 'n/a'}",
    ]
    if panel_visible is not None:
        parts.append(f"panel_visible={int(panel_visible)}")
    line = " ".join(parts) + "\n"

    try:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as stream:
            stream.write(line)
    except OSError:
        pass


class MemoryWatch:
    def __init__(
        self,
        *,
        log_path: str = DEFAULT_LOG_PATH,
        interval_s: float = DEFAULT_INTERVAL_S,
        is_panel_visible: Optional[Callable[[], bool]] = None,
    ):
        self._log_path = log_path
        self._interval_s = max(60.0, float(interval_s))
        self._is_panel_visible = is_panel_visible
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._thread = None
        visible = self._is_panel_visible() if self._is_panel_visible else None
        append_memory_log(
            "shutdown",
            log_path=self._log_path,
            panel_visible=visible,
        )

    def _run(self) -> None:
        visible = self._is_panel_visible() if self._is_panel_visible else None
        append_memory_log(
            "startup",
            log_path=self._log_path,
            panel_visible=visible,
        )
        while not self._stop.wait(self._interval_s):
            visible = self._is_panel_visible() if self._is_panel_visible else None
            append_memory_log(
                "daily",
                log_path=self._log_path,
                panel_visible=visible,
            )
