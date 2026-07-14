import json
import os
import platform
import threading
import time

import webview
from dotenv import load_dotenv

from caret import (
    debug_caret_snapshot,
    get_caret_rect,
    get_selected_text,
    panel_position,
)
from listener import PinyinListener
from panel_mac import hide_panel, show_debug_caret_box, show_without_focus
from translator import Translator

load_dotenv()

UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
DEBOUNCE_MS = int(os.getenv("DEBOUNCE_MS", "200"))
TRANSLATE_HOTKEY = os.getenv("TRANSLATE_HOTKEY", "alt+e")
SELECTION_LABEL_MAX = 18

WIN_W = 480
MIN_WIN_H = 40
MAX_WIN_H = 120
# 与当前输入行留出足够距离，避免面板压住文字或系统候选框。
CARET_GAP = 16
UI_FLUSH_MS = 30
CARET_POLL_MS = int(os.getenv("CARET_POLL_MS", "50"))
DEBUG_LOG_PATH = os.path.join(
    os.path.dirname(__file__), ".cursor", "debug-fa4dbd.log"
)


# region agent log
def _write_debug_log(message: str, data: dict, hypothesis_id: str) -> None:
    payload = {
        "sessionId": "fa4dbd",
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": "main.py:_monitor_caret",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
# endregion


class App:
    def __init__(self):
        self.window = None
        self.translator = Translator()
        self._listener: PinyinListener | None = None
        self._compose_gen = 0
        self._visible = False
        self._pending_pinyin: str | None = None
        self._ui_timer: threading.Timer | None = None
        self._timers_lock = threading.Lock()
        self._panel_position: tuple[int, int] | None = None
        self._panel_height = MIN_WIN_H
        self._position_lock = threading.Lock()
        self._caret_monitor_stop = threading.Event()
        self._caret_monitor: threading.Thread | None = None
        self._debug_probe_samples = 0
        self._anchor_selected = False
        self._panel_mode = "idle"

    def on_compose(self, pinyin: str) -> None:
        if self._panel_mode == "selection":
            self._dismiss_panel()
        self._panel_mode = "composing"
        self._anchor_selected = False
        if pinyin == "aaa":
            self._debug_probe_samples = 4
        with self._timers_lock:
            self._pending_pinyin = pinyin
            self._schedule_ui_flush_locked()

    def on_compose_end(self) -> None:
        self._dismiss_panel()

    def _dismiss_panel(self) -> None:
        self._compose_gen += 1
        self._anchor_selected = False
        self._panel_mode = "idle"
        self._cancel_ui_flush()
        self._hide()
        self._run_js_and_resize("resetPanel")

    def on_pinyin_pause(self, pinyin: str) -> None:
        gen = self._compose_gen
        self._run_js_and_resize("setLoading", pinyin)

        def work():
            result = self.translator.translate(pinyin)
            if gen != self._compose_gen:
                return
            self._run_js_and_resize("updatePanel", pinyin, result)

        threading.Thread(target=work, daemon=True).start()

    def on_translate_hotkey(self) -> None:
        text = get_selected_text()
        self._compose_gen += 1
        gen = self._compose_gen
        self._panel_mode = "selection"
        self._anchor_selected = True
        self._cancel_ui_flush()

        if not text:
            self._run_js_and_resize(
                "updatePanel",
                "选中",
                "未读到选中文案（可重试，或检查辅助功能权限）",
            )
            self._show()
            return

        label = text if len(text) <= SELECTION_LABEL_MAX else text[:SELECTION_LABEL_MAX] + "…"
        self._run_js_and_resize("setLoading", label)
        self._show()

        def work():
            result = self.translator.translate_selection(text)
            if gen != self._compose_gen:
                return
            self._run_js_and_resize("updatePanel", label, result)

        threading.Thread(target=work, daemon=True).start()

    def _schedule_ui_flush_locked(self) -> None:
        if self._ui_timer:
            self._ui_timer.cancel()
        self._ui_timer = threading.Timer(UI_FLUSH_MS / 1000, self._flush_ui)
        self._ui_timer.daemon = True
        self._ui_timer.start()

    def _cancel_ui_flush(self) -> None:
        with self._timers_lock:
            if self._ui_timer:
                self._ui_timer.cancel()
                self._ui_timer = None
            self._pending_pinyin = None

    def _flush_ui(self) -> None:
        with self._timers_lock:
            pinyin = self._pending_pinyin
            self._pending_pinyin = None
            self._ui_timer = None

        if not pinyin:
            return

        self._run_js_and_resize("showComposing", pinyin)
        self._show()

    def _calculate_panel_position(self, rect) -> tuple[int, int]:
        panel_height = self._panel_height
        try:
            from AppKit import NSScreen
        except ImportError:
            x, y = panel_position(
                rect, WIN_W, panel_height, CARET_GAP, visible_top=0
            )
            return x, max(y, 0)

        screen = NSScreen.mainScreen()
        if screen is None:
            x, y = panel_position(
                rect, WIN_W, panel_height, CARET_GAP, visible_top=0
            )
            return x, max(y, 0)

        frame = screen.frame()
        visible = screen.visibleFrame()
        screen_h = int(frame.size.height)

        # visible frame 在 top-left 坐标系中的可用范围
        # NSScreen visibleFrame: origin.y 从屏幕底部算，转换为 top-left：
        x_min = int(visible.origin.x)
        x_max = int(visible.origin.x + visible.size.width - WIN_W)
        y_min = int(screen_h - (visible.origin.y + visible.size.height))
        y_max = int(screen_h - visible.origin.y - panel_height)

        x, y = panel_position(
            rect,
            WIN_W,
            panel_height,
            CARET_GAP,
            visible_top=y_min,
            visible_bottom=y_max,
        )

        x = max(x_min, min(x, x_max))
        y = max(y_min, min(y, y_max))
        return x, y

    def _prefer_selected_anchor(self) -> bool:
        if self._anchor_selected:
            return True
        # 面板隐藏通常表示组字已提交。此时优先读取真实插入点，
        # 避免部分应用残留的 AXMarkedTextRange 把位置锁在上一行。
        return not self._visible

    def _monitor_caret(self) -> None:
        while not self._caret_monitor_stop.is_set():
            rect = get_caret_rect(prefer_selected=self._prefer_selected_anchor())
            if rect:
                position = self._calculate_panel_position(rect)

                if self._debug_probe_samples > 0:
                    sample = 5 - self._debug_probe_samples
                    try:
                        snapshot = debug_caret_snapshot()
                    except Exception as exc:
                        snapshot = {
                            "probe_error": type(exc).__name__,
                            "probe_message": str(exc),
                        }
                    # region agent log
                    _write_debug_log(
                        "aaa 光标定位采样",
                        {
                            "sample": sample,
                            "visible": self._visible,
                            "chosen": {
                                "x": rect.x,
                                "y": rect.y,
                                "width": rect.width,
                                "height": rect.height,
                            },
                            "panel_position": {
                                "x": position[0],
                                "y": position[1],
                            },
                            "candidates": snapshot,
                        },
                        "H1-H5",
                    )
                    # endregion
                    show_debug_caret_box(rect)
                    self._debug_probe_samples -= 1

                with self._position_lock:
                    changed = position != self._panel_position
                    self._panel_position = position

                # 隐藏时也提前移动，显示时窗口已在最新光标附近。
                if changed and self.window:
                    self.window.move(*position)

            self._caret_monitor_stop.wait(CARET_POLL_MS / 1000)

    def _start_caret_monitor(self) -> None:
        if self._caret_monitor and self._caret_monitor.is_alive():
            return
        self._caret_monitor_stop.clear()
        self._caret_monitor = threading.Thread(target=self._monitor_caret, daemon=True)
        self._caret_monitor.start()

    def _stop_caret_monitor(self) -> None:
        self._caret_monitor_stop.set()
        if self._caret_monitor and self._caret_monitor.is_alive():
            self._caret_monitor.join(timeout=1)
        self._caret_monitor = None

    def _show(self) -> None:
        if not self.window or self._visible:
            return

        # 仿照 IMK 候选框：显示前先向宿主读取一次最新插入点，
        # 避免后台轮询尚未完成时窗口在默认位置闪现。
        rect = get_caret_rect(prefer_selected=self._prefer_selected_anchor())
        if rect:
            position = self._calculate_panel_position(rect)
            with self._position_lock:
                self._panel_position = position

        with self._position_lock:
            position = self._panel_position
        if position:
            self.window.move(*position)
        if platform.system() == "Darwin":
            show_without_focus(self.window)
        else:
            self.window.show()
        self._visible = True

    def _hide(self) -> None:
        if not self.window or not self._visible:
            return
        if platform.system() == "Darwin":
            hide_panel(self.window)
        else:
            self.window.hide()
        self._visible = False

    def _run_js(self, fn: str, *args) -> object | None:
        if not self.window:
            return None
        payload = ", ".join(json.dumps(arg, ensure_ascii=False) for arg in args)
        return self.window.evaluate_js(f"{fn}({payload})")

    def _run_js_and_resize(self, fn: str, *args) -> None:
        preferred_height = self._run_js(fn, *args)
        if not self.window or preferred_height is None:
            return

        try:
            height = int(preferred_height)
        except (TypeError, ValueError):
            return
        height = max(MIN_WIN_H, min(height, MAX_WIN_H))
        if height == self._panel_height:
            return

        self._panel_height = height
        self.window.resize(WIN_W, height)

        # 高度变化后立即重新锚定，避免面板向上扩展时偏离当前光标。
        rect = get_caret_rect(prefer_selected=self._prefer_selected_anchor())
        if not rect:
            return
        position = self._calculate_panel_position(rect)
        with self._position_lock:
            self._panel_position = position
        self.window.move(*position)

    def start_listener(self) -> None:
        self._start_caret_monitor()
        self._listener = PinyinListener(
            on_compose=self.on_compose,
            on_compose_end=self.on_compose_end,
            on_pause=self.on_pinyin_pause,
            debounce_ms=DEBOUNCE_MS,
            on_translate_hotkey=self.on_translate_hotkey,
            translate_hotkey=TRANSLATE_HOTKEY,
            is_panel_visible=lambda: self._visible,
        )
        self._listener.start()

    def stop_listener(self) -> None:
        if self._listener:
            self._listener.stop()
        self._stop_caret_monitor()


app = App()


def main() -> None:
    app.window = webview.create_window(
        title="learninput",
        url=os.path.join(UI_DIR, "index.html"),
        width=WIN_W,
        height=MIN_WIN_H,
        x=None,
        y=None,
        resizable=False,
        frameless=True,
        easy_drag=False,
        on_top=True,
        hidden=True,
        focus=False,
    )

    app.window.events.loaded += lambda: app.start_listener()

    webview.start(debug=False)
    app.stop_listener()


if __name__ == "__main__":
    main()
