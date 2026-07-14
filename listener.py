import string
import threading
from dataclasses import dataclass
from typing import Callable, FrozenSet, Optional

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
        keyboard.Key.shift,
        keyboard.Key.shift_r,
    }
)

_MODIFIER_TO_NAME = {
    keyboard.Key.cmd: "cmd",
    keyboard.Key.cmd_r: "cmd",
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.alt: "alt",
    keyboard.Key.alt_r: "alt",
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_r: "shift",
}

_HOTKEY_MOD_ALIAS = {
    "option": "alt",
    "opt": "alt",
    "command": "cmd",
    "control": "ctrl",
}

# macOS ANSI 虚拟键码；Option 会改 char，但 vk 通常不变。
_MAC_VK = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "o": 31,
    "u": 32,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "k": 40,
    "n": 45,
    "m": 46,
}


@dataclass(frozen=True)
class HotkeyBinding:
    modifiers: FrozenSet[str]
    key: str


def parse_hotkey(spec: str) -> HotkeyBinding:
    """解析 `alt+e` / `ctrl+shift+t` 等快捷键配置。"""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"快捷键至少需要修饰键+主键，例如 alt+e，收到：{spec!r}")

    key = parts[-1]
    mods = frozenset(_HOTKEY_MOD_ALIAS.get(m, m) for m in parts[:-1])
    return HotkeyBinding(modifiers=mods, key=key)


class PinyinListener:
    """旁听 a-z 按键，维护拼音 buffer。

    生命周期对齐输入法组字：
    - 开始输入字母 → on_compose（面板出现）
    - 继续输入 / 退格 → on_compose（面板更新）
    - 停顿 → on_pause（查询释义，面板仍可见）
    - 空格 / 回车 / Esc / 标点 / 数字选词 → on_compose_end（面板消失）
    - 翻译快捷键 → on_translate_hotkey（选中文案译英）
    """

    def __init__(
        self,
        on_compose: Callable[[str], None],
        on_compose_end: Callable[[], None],
        on_pause: Callable[[str], None],
        debounce_ms: int = 400,
        min_length: int = 2,
        on_translate_hotkey: Optional[Callable[[], None]] = None,
        translate_hotkey: str = "alt+e",
        is_panel_visible: Optional[Callable[[], bool]] = None,
    ):
        self.on_compose = on_compose
        self.on_compose_end = on_compose_end
        self.on_pause = on_pause
        self.on_translate_hotkey = on_translate_hotkey
        self.is_panel_visible = is_panel_visible or (lambda: False)
        self.debounce_ms = debounce_ms
        self.min_length = min_length
        self._buffer = ""
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._listener: Optional[keyboard.Listener] = None
        self._modifiers_held: set[keyboard.Key] = set()
        self._hotkey_binding: Optional[HotkeyBinding] = None
        if on_translate_hotkey and translate_hotkey.strip():
            self._hotkey_binding = parse_hotkey(translate_hotkey)

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

    def _held_modifier_names(self) -> set[str]:
        return {
            _MODIFIER_TO_NAME[key]
            for key in self._modifiers_held
            if key in _MODIFIER_TO_NAME
        }

    def _modifiers_match(self, required: FrozenSet[str]) -> bool:
        return self._held_modifier_names() == set(required)

    def _key_matches_binding(self, key) -> bool:
        if not self._hotkey_binding:
            return False

        target = self._hotkey_binding.key
        char = getattr(key, "char", None)
        if char and char.lower() == target:
            return True

        vk = getattr(key, "vk", None)
        if vk is not None and _MAC_VK.get(target) == vk:
            return True

        name = getattr(key, "name", None)
        return bool(name and name.lower() == target)

    def _fire_translate_hotkey(self) -> None:
        with self._lock:
            self._buffer = ""
            if self._timer:
                self._timer.cancel()
                self._timer = None
        if self.on_translate_hotkey:
            self.on_translate_hotkey()

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
        if had_content or self.is_panel_visible():
            self.on_compose_end()

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
            if self.is_panel_visible():
                self.on_compose_end()

    def _on_release(self, key) -> None:
        if key in _MODIFIER_KEYS:
            self._modifiers_held.discard(key)

    def _on_press(self, key) -> None:
        if key in _MODIFIER_KEYS:
            self._modifiers_held.add(key)
            return

        if self._modifiers_held:
            if (
                self._hotkey_binding
                and self._modifiers_match(self._hotkey_binding.modifiers)
                and self._key_matches_binding(key)
            ):
                self._fire_translate_hotkey()
            return

        if key == keyboard.Key.backspace:
            self._pop_char()
            return

        if key == keyboard.Key.esc:
            with self._lock:
                had_content = bool(self._buffer)
                self._buffer = ""
            self._cancel_timer()
            if had_content or self.is_panel_visible():
                self.on_compose_end()
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
