"""将英文采纳进当前输入框：Esc 取消组字 + 剪贴板粘贴。"""

from __future__ import annotations

import platform
import threading
import time

from pynput import keyboard

_INJECT_DELAY_S = 0.04
_RESTORE_DELAY_S = 0.08

_injecting = False
_inject_lock = threading.Lock()
_controller = keyboard.Controller()


def is_injecting() -> bool:
    with _inject_lock:
        return _injecting


def accept_english(text: str) -> bool:
    """Esc 取消输入法组字，再将英文粘贴到焦点控件。"""
    if platform.system() != "Darwin":
        return False

    cleaned = text.strip()
    if not cleaned:
        return False

    with _inject_lock:
        global _injecting
        _injecting = True

    saved_clipboard: str | None = None
    try:
        saved_clipboard = _read_clipboard()
        _write_clipboard(cleaned)
        _controller.press(keyboard.Key.esc)
        _controller.release(keyboard.Key.esc)
        time.sleep(_INJECT_DELAY_S)
        with _controller.pressed(keyboard.Key.cmd):
            _controller.press("v")
            _controller.release("v")
        return True
    except Exception:
        return False
    finally:
        time.sleep(_RESTORE_DELAY_S)
        if saved_clipboard is not None:
            try:
                _write_clipboard(saved_clipboard)
            except Exception:
                pass
        with _inject_lock:
            _injecting = False


def _read_clipboard() -> str | None:
    from AppKit import NSPasteboard

    pasteboard = NSPasteboard.generalPasteboard()
    return pasteboard.stringForType_("public.utf8-plain-text")


def _write_clipboard(text: str) -> None:
    from AppKit import NSPasteboard

    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, "public.utf8-plain-text")
