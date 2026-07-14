import string
import threading
from typing import Callable, Optional

from pynput import keyboard

# 按住这些修饰键时视为快捷键，不参与拼音组字（如 Cmd+C / Cmd+V）。
_MODIFIER_KEYS = frozenset(
    {
        keyboard.Key.cmd,
        keyboard.Key.cmd_r,
        keyboard.Key.ctrl,
        keyboard.Key.ctrl_r,
        keyboard.Key.alt,
        keyboard.Key.alt_r,
    }
)


class PinyinListener:
    """旁听 a-z 按键，维护拼音 buffer。

    生命周期对齐输入法组字：
    - 开始输入字母 → on_compose（面板出现）
    - 继续输入 / 退格 → on_compose（面板更新）
    - 停顿 → on_pause（查询释义，面板仍可见）
    - 空格 / 回车 / Esc / 标点 / 数字选词 → on_compose_end（面板消失）
    """

    def __init__(
        self,
        on_compose: Callable[[str], None],
        on_compose_end: Callable[[], None],
        on_pause: Callable[[str], None],
        debounce_ms: int = 400,
        min_length: int = 2,
    ):
        self.on_compose = on_compose
        self.on_compose_end = on_compose_end
        self.on_pause = on_pause
        self.debounce_ms = debounce_ms
        self.min_length = min_length
        self._buffer = ""
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._listener: Optional[keyboard.Listener] = None
        self._modifiers_held: set[keyboard.Key] = set()

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
        self._cancel_timer()

    def _cancel_timer(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def _schedule_flush(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_ms / 1000, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            pinyin = self._buffer
            self._timer = None

        if len(pinyin) >= self.min_length:
            self.on_pause(pinyin)

    def _end_composition(self) -> None:
        with self._lock:
            had_content = bool(self._buffer)
            self._buffer = ""
        self._cancel_timer()
        if had_content:
            self.on_compose_end()

    def _clear_buffer(self) -> None:
        self._end_composition()

    def _append_char(self, char: str) -> None:
        with self._lock:
            self._buffer += char
            buf = self._buffer
        self._schedule_flush()
        self.on_compose(buf)

    def _pop_char(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            self._buffer = self._buffer[:-1]
            buf = self._buffer

        if buf:
            self._schedule_flush()
            self.on_compose(buf)
        else:
            self._cancel_timer()
            self.on_compose_end()

    def _on_release(self, key) -> None:
        if key in _MODIFIER_KEYS:
            self._modifiers_held.discard(key)

    def _on_press(self, key) -> None:
        if key in _MODIFIER_KEYS:
            self._modifiers_held.add(key)
            return

        if self._modifiers_held:
            return

        if key == keyboard.Key.backspace:
            self._pop_char()
            return

        if key == keyboard.Key.esc:
            self._end_composition()
            return

        if key in (keyboard.Key.space, keyboard.Key.enter, keyboard.Key.tab):
            self._end_composition()
            return

        char = getattr(key, "char", None)
        if not char:
            return

        if char.isdigit():
            self._end_composition()
            return

        if char in string.ascii_letters:
            self._append_char(char.lower())
            return

        if char in string.punctuation:
            self._end_composition()
