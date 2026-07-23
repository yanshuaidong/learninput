"""macOS 光标/组字区域位置（Accessibility API）。"""

from __future__ import annotations

import platform
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Optional


@dataclass(frozen=True)
class CaretRect:
    x: float
    y: float
    width: float
    height: float


@contextmanager
def _autorelease_pool() -> Iterator[None]:
    """后台线程调用 Cocoa/AX 时必须排水，否则临时对象会无限堆积。"""
    if platform.system() != "Darwin":
        yield
        return

    try:
        import objc
    except ImportError:
        from Foundation import NSAutoreleasePool

        pool = NSAutoreleasePool.alloc().init()
        try:
            yield
        finally:
            del pool
        return

    with objc.autorelease_pool():
        yield


def _debug_window_candidates() -> list[dict[str, Any]]:
    import Quartz

    options = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    candidates = []
    for order, window in enumerate(windows or []):
        bounds = window.get(Quartz.kCGWindowBounds, {})
        width = float(bounds.get("Width", 0))
        height = float(bounds.get("Height", 0))
        layer = int(window.get(Quartz.kCGWindowLayer, 0))
        if width <= 0 or height <= 0 or width > 1200 or height > 350:
            continue
        if layer == 0 and height > 100:
            continue
        candidates.append(
            {
                "order": order,
                "owner": str(window.get(Quartz.kCGWindowOwnerName, "")),
                "layer": layer,
                "bounds": {
                    "x": float(bounds.get("X", 0)),
                    "y": float(bounds.get("Y", 0)),
                    "width": width,
                    "height": height,
                },
            }
        )
        if len(candidates) >= 20:
            break
    return candidates


def debug_caret_snapshot() -> dict[str, Any]:
    """采集各定位来源，仅供当前光标定位调试。"""
    with _autorelease_pool():
        return _debug_caret_snapshot_impl()


def _debug_caret_snapshot_impl() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"platform": platform.system()}

    import ApplicationServices as AS

    def rect_data(rect: Optional[CaretRect]) -> Optional[dict[str, float]]:
        if rect is None:
            return None
        return {
            "x": rect.x,
            "y": rect.y,
            "width": rect.width,
            "height": rect.height,
        }

    result: dict[str, Any] = {}
    try:
        from AppKit import NSWorkspace

        frontmost = NSWorkspace.sharedWorkspace().frontmostApplication()
        result["frontmost_app"] = {
            "name": str(frontmost.localizedName()) if frontmost else None,
            "bundle_id": str(frontmost.bundleIdentifier()) if frontmost else None,
        }
    except Exception as exc:
        result["frontmost_app_error"] = f"{type(exc).__name__}: {exc}"

    system = AS.AXUIElementCreateSystemWide()
    err, element = AS.AXUIElementCopyAttributeValue(
        system, AS.kAXFocusedUIElementAttribute, None
    )
    result["focused_error"] = int(err)
    if err != AS.kAXErrorSuccess or element is None:
        result["mouse"] = rect_data(_get_mouse_fallback())
        try:
            result["ime_anchor"] = rect_data(_get_ime_candidate_anchor())
        except Exception as exc:
            result["ime_anchor_error"] = f"{type(exc).__name__}: {exc}"
        try:
            result["window_candidates"] = _debug_window_candidates()
        except Exception as exc:
            result["window_probe_error"] = f"{type(exc).__name__}: {exc}"
        return result

    for name, attr in (
        ("role", AS.kAXRoleAttribute),
        ("subrole", AS.kAXSubroleAttribute),
    ):
        attr_err, attr_value = AS.AXUIElementCopyAttributeValue(element, attr, None)
        result[name] = {
            "error": int(attr_err),
            "value": str(attr_value) if attr_value is not None else None,
        }

    for name, attr in (
        ("marked", "AXMarkedTextRange"),
        ("selected", AS.kAXSelectedTextRangeAttribute),
    ):
        range_err, range_val = AS.AXUIElementCopyAttributeValue(element, attr, None)
        item: dict[str, Any] = {"range_error": int(range_err)}
        if range_err == AS.kAXErrorSuccess and range_val is not None:
            rect = _bounds_for_range(element, range_val)
            item["bounds"] = rect_data(
                _normalize_range_caret(rect) if rect else None
            )
            ok, selected_range = AS.AXValueGetValue(
                range_val, AS.kAXValueCFRangeType, None
            )
            if ok:
                from CoreFoundation import CFRangeMake

                location, length = selected_range
                item["range"] = {"location": location, "length": length}
                adjacent_locations = {
                    "before": location - 1 if location > 0 else None,
                    "after": location,
                }
                adjacent: dict[str, Any] = {}
                for adjacent_name, adjacent_location in adjacent_locations.items():
                    if adjacent_location is None:
                        adjacent[adjacent_name] = None
                        continue
                    adjacent_value = AS.AXValueCreate(
                        AS.kAXValueCFRangeType,
                        CFRangeMake(adjacent_location, 1),
                    )
                    adjacent_rect = _bounds_for_range(element, adjacent_value)
                    adjacent[adjacent_name] = rect_data(adjacent_rect)
                item["adjacent_bounds"] = adjacent
        result[name] = item

    frame_err, frame_val = AS.AXUIElementCopyAttributeValue(
        element, "AXFrame", None
    )
    result["element_frame_error"] = int(frame_err)
    result["element_frame"] = rect_data(
        _ax_value_to_rect(frame_val)
        if frame_err == AS.kAXErrorSuccess and frame_val is not None
        else None
    )
    result["mouse"] = rect_data(_get_mouse_fallback())

    try:
        from AppKit import NSScreen
        import Quartz

        result["screens"] = [
            {
                "frame": {
                    "x": screen.frame().origin.x,
                    "y": screen.frame().origin.y,
                    "width": screen.frame().size.width,
                    "height": screen.frame().size.height,
                },
                "scale": screen.backingScaleFactor(),
            }
            for screen in NSScreen.screens()
        ]

        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        windows = Quartz.CGWindowListCopyWindowInfo(
            options, Quartz.kCGNullWindowID
        )
        compact_windows = []
        for order, window in enumerate(windows or []):
            bounds = window.get(Quartz.kCGWindowBounds, {})
            width = float(bounds.get("Width", 0))
            height = float(bounds.get("Height", 0))
            layer = int(window.get(Quartz.kCGWindowLayer, 0))
            if width <= 0 or height <= 0 or width > 1200 or height > 350:
                continue
            if layer == 0 and height > 100:
                continue
            compact_windows.append(
                {
                    "order": order,
                    "owner": str(window.get(Quartz.kCGWindowOwnerName, "")),
                    "layer": layer,
                    "bounds": {
                        "x": float(bounds.get("X", 0)),
                        "y": float(bounds.get("Y", 0)),
                        "width": width,
                        "height": height,
                    },
                }
            )
            if len(compact_windows) >= 20:
                break
        result["window_candidates"] = compact_windows
    except Exception as exc:
        result["window_probe_error"] = f"{type(exc).__name__}: {exc}"

    return result


def get_caret_rect(*, prefer_selected: bool = False) -> Optional[CaretRect]:
    with _autorelease_pool():
        if platform.system() != "Darwin":
            return None
        try:
            return (
                _get_caret_ax(prefer_selected=prefer_selected)
                or _get_ime_candidate_anchor()
                or _get_mouse_fallback()
            )
        except Exception:
            return _get_ime_candidate_anchor() or _get_mouse_fallback()


def get_selected_text() -> Optional[str]:
    """读取当前焦点控件中的选中文案（Accessibility）。"""
    with _autorelease_pool():
        if platform.system() != "Darwin":
            return None
        try:
            return _get_selected_text_ax()
        except Exception:
            return None


_CLIPBOARD_TEXT_TYPES = (
    "public.utf8-plain-text",
    "public.plain-text",
    "NSStringPboardType",
)

_CLIPBOARD_NON_TEXT_TYPES = (
    "public.png",
    "public.tiff",
    "NSFilenamesPboardType",
    "public.file-url",
)


def _pasteboard_types() -> frozenset[str]:
    from AppKit import NSPasteboard

    pasteboard = NSPasteboard.generalPasteboard()
    return frozenset(str(item) for item in (pasteboard.types() or ()))


def is_clipboard_plain_text() -> bool:
    """剪贴板是否包含可用的纯文本（排除仅有图片/文件的情况）。"""
    if platform.system() != "Darwin":
        return False
    try:
        types = _pasteboard_types()
    except Exception:
        return False
    if any(text_type in types for text_type in _CLIPBOARD_TEXT_TYPES):
        return True
    return not any(non_text_type in types for non_text_type in _CLIPBOARD_NON_TEXT_TYPES)


def get_clipboard_text() -> Optional[str]:
    """读取系统剪贴板中的纯文本。"""
    with _autorelease_pool():
        if platform.system() != "Darwin" or not is_clipboard_plain_text():
            return None
        try:
            from AppKit import NSPasteboard

            pasteboard = NSPasteboard.generalPasteboard()
            for text_type in _CLIPBOARD_TEXT_TYPES:
                value = pasteboard.stringForType_(text_type)
                if value:
                    text = str(value).strip()
                    if text:
                        return text
        except Exception:
            return None
        return None


def write_clipboard_text(text: str) -> None:
    """写入纯文本到系统剪贴板。"""
    with _autorelease_pool():
        from AppKit import NSPasteboard

        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, "public.utf8-plain-text")


def resolve_selection_text() -> Optional[str]:
    """AX 选中文案优先，读不到时回退剪贴板纯文本。"""
    text = get_selected_text()
    if text:
        return text
    return get_clipboard_text()


def _get_selected_text_ax() -> Optional[str]:
    import ApplicationServices as AS

    system = AS.AXUIElementCreateSystemWide()
    err, element = AS.AXUIElementCopyAttributeValue(
        system, AS.kAXFocusedUIElementAttribute, None
    )
    if err != AS.kAXErrorSuccess or element is None:
        return None

    err, selected = AS.AXUIElementCopyAttributeValue(
        element, AS.kAXSelectedTextAttribute, None
    )
    if err == AS.kAXErrorSuccess and selected:
        text = str(selected).strip()
        if text:
            return text

    err, range_val = AS.AXUIElementCopyAttributeValue(
        element, AS.kAXSelectedTextRangeAttribute, None
    )
    if err != AS.kAXErrorSuccess or range_val is None:
        return None

    ok, selected_range = AS.AXValueGetValue(
        range_val, AS.kAXValueCFRangeType, None
    )
    if not ok:
        return None

    location, length = selected_range
    if length <= 0:
        return None

    err, value = AS.AXUIElementCopyAttributeValue(
        element, AS.kAXValueAttribute, None
    )
    if err != AS.kAXErrorSuccess or value is None:
        return None

    full = str(value)
    end = min(location + length, len(full))
    if location < 0 or location >= len(full):
        return None
    text = full[location:end].strip()
    return text or None


def _get_caret_ax(*, prefer_selected: bool = False) -> Optional[CaretRect]:
    import ApplicationServices as AS

    system = AS.AXUIElementCreateSystemWide()
    err, element = AS.AXUIElementCopyAttributeValue(
        system, AS.kAXFocusedUIElementAttribute, None
    )
    if err != AS.kAXErrorSuccess or element is None:
        return None

    marked = "AXMarkedTextRange"
    selected = AS.kAXSelectedTextRangeAttribute
    attrs = (selected, marked) if prefer_selected else (marked, selected)
    element_frame = _copy_element_frame(element)

    for attr in attrs:
        err, range_val = AS.AXUIElementCopyAttributeValue(element, attr, None)
        if err != AS.kAXErrorSuccess or range_val is None:
            continue
        rect = _bounds_for_range(element, range_val)
        if rect is not None:
            caret = _normalize_range_caret(rect)
            if element_frame is None or _caret_within_element(caret, element_frame):
                return caret

    return _get_ime_candidate_anchor() or _get_element_frame(element)


def _get_ime_candidate_anchor() -> Optional[CaretRect]:
    """AX 不可用时，以当前输入法候选窗左上角作为稳定锚点。"""
    import Quartz

    options = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    for window in windows or []:
        layer = int(window.get(Quartz.kCGWindowLayer, 0))
        bounds = window.get(Quartz.kCGWindowBounds, {})
        width = float(bounds.get("Width", 0))
        height = float(bounds.get("Height", 0))

        # 输入法候选窗位于特殊高层级；排除状态图标等小窗口。
        if layer < 1000 or width < 120 or height < 30:
            continue
        if width > 1200 or height > 200:
            continue

        return CaretRect(
            float(bounds.get("X", 0)),
            float(bounds.get("Y", 0)),
            2.0,
            height,
        )
    return None


def _bounds_for_range(element: Any, range_val: Any) -> Optional[CaretRect]:
    import ApplicationServices as AS

    err, bounds = AS.AXUIElementCopyParameterizedAttributeValue(
        element,
        AS.kAXBoundsForRangeParameterizedAttribute,
        range_val,
        None,
    )
    if err != AS.kAXErrorSuccess or bounds is None:
        return None
    return _ax_value_to_rect(bounds)


def _ax_value_to_rect(value) -> Optional[CaretRect]:
    import ApplicationServices as AS

    ok, rect = AS.AXValueGetValue(
        value, AS.kAXValueCGRectType, None
    )
    if not ok:
        return None
    return CaretRect(
        rect.origin.x, rect.origin.y, rect.size.width, rect.size.height
    )


def _normalize_caret(rect: CaretRect) -> CaretRect:
    height = rect.height if rect.height > 0 else 18.0
    width = rect.width if rect.width > 0 else 2.0
    return CaretRect(rect.x, rect.y, width, height)


def _normalize_range_caret(rect: CaretRect) -> CaretRect:
    """将 AXBoundsForRange 的下边缘 Y 转为窗口使用的上边缘 Y。"""
    caret = _normalize_caret(rect)
    return CaretRect(
        caret.x,
        caret.y + caret.height,
        caret.width,
        caret.height,
    )


def _copy_element_frame(element) -> Optional[CaretRect]:
    import ApplicationServices as AS

    err, frame_val = AS.AXUIElementCopyAttributeValue(element, "AXFrame", None)
    if err != AS.kAXErrorSuccess or frame_val is None:
        return None
    return _ax_value_to_rect(frame_val)


def _caret_within_element(caret: CaretRect, frame: CaretRect) -> bool:
    tolerance = max(caret.height, 8.0)
    return (
        frame.x - tolerance <= caret.x <= frame.x + frame.width + tolerance
        and frame.y - tolerance
        <= caret.y
        <= frame.y + frame.height + tolerance
    )


def _get_element_frame(element) -> Optional[CaretRect]:
    import ApplicationServices as AS

    rect = _copy_element_frame(element)
    if rect is not None:
        return CaretRect(rect.x, rect.y, 2.0, min(rect.height, 24.0))

    err, pos_val = AS.AXUIElementCopyAttributeValue(
        element, AS.kAXPositionAttribute, None
    )
    err2, size_val = AS.AXUIElementCopyAttributeValue(
        element, AS.kAXSizeAttribute, None
    )
    if err != AS.kAXErrorSuccess or err2 != AS.kAXErrorSuccess:
        return None
    if pos_val is None or size_val is None:
        return None

    pos = _ax_value_to_point(pos_val)
    size = _ax_value_to_size(size_val)
    if pos is None or size is None:
        return None
    raw = CaretRect(pos[0], pos[1], 2.0, min(size[1], 24.0))
    return _quartz_to_screen(raw)


def _ax_value_to_point(value) -> Optional[tuple[float, float]]:
    import ApplicationServices as AS

    ok, point = AS.AXValueGetValue(
        value, AS.kAXValueCGPointType, None
    )
    if not ok:
        return None
    return point.x, point.y


def _ax_value_to_size(value) -> Optional[tuple[float, float]]:
    import ApplicationServices as AS

    ok, size = AS.AXValueGetValue(
        value, AS.kAXValueCGSizeType, None
    )
    if not ok:
        return None
    return size.width, size.height


def _quartz_to_screen(rect: CaretRect) -> CaretRect:
    """返回 pywebview 所需的左上原点坐标。

    AXBoundsForRange/AXFrame 使用 Quartz 全局屏幕坐标：主屏左上角为
    (0, 0)，Y 轴向下；pywebview 的 move(x, y) 也接收左上原点坐标。
    因此这里不能再翻转 Y，否则弹窗会沿屏幕中线镜像到错误位置。
    """
    return rect


def _get_mouse_fallback() -> Optional[CaretRect]:
    try:
        from AppKit import NSEvent, NSScreen
    except ImportError:
        return None

    loc = NSEvent.mouseLocation()
    screen = NSScreen.mainScreen()
    if screen is None:
        return CaretRect(loc.x, loc.y, 2.0, 18.0)

    frame = screen.frame()
    y = frame.size.height - loc.y
    return CaretRect(loc.x, y, 2.0, 18.0)


def panel_position(
    rect: CaretRect,
    win_w: int,
    win_h: int,
    gap: int,
    *,
    visible_top: int = 0,
    visible_bottom: Optional[int] = None,
) -> tuple[int, int]:
    """相对光标定位：优先显示在光标上方，空间不足时翻到下方。

    rect 的坐标已是 top-left 坐标系（y=0 在屏幕顶部）。
    返回值 (x, y) 也是 top-left 坐标系，直接传给 window.move()。
    """
    x = int(rect.x - gap)
    above = int(rect.y - win_h - gap)
    below = int(rect.y + rect.height + gap)

    if above >= visible_top:
        y = above
    elif visible_bottom is None or below <= visible_bottom:
        y = below
    else:
        # 两边都放不下时选择可用空间更多的一侧，最后由调用方钳制。
        space_above = rect.y - visible_top
        space_below = visible_bottom - (rect.y + rect.height)
        y = above if space_above >= space_below else below
    return x, y
