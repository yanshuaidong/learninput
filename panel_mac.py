"""macOS 面板：非激活显示，不抢输入法焦点。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from caret import CaretRect
    from webview.window import Window


_debug_caret_panel = None


def show_debug_caret_box(rect: CaretRect) -> None:
    """用红框标出 AX 返回的光标矩形，仅供定位调试。"""
    from webview.platforms.cocoa import AppHelper

    def _do() -> None:
        global _debug_caret_panel

        from AppKit import (
            NSBackingStoreBuffered,
            NSColor,
            NSMakeRect,
            NSPanel,
            NSScreen,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowStyleMaskBorderless,
            NSPopUpMenuWindowLevel,
        )

        screens = NSScreen.screens()
        if not screens:
            return

        padding = 6.0
        x = rect.x - padding
        y = rect.y - padding
        width = max(rect.width, 2.0) + padding * 2
        height = max(rect.height, 2.0) + padding * 2
        primary_top = screens[0].frame().origin.y + screens[0].frame().size.height
        cocoa_y = primary_top - y - height
        frame = NSMakeRect(x, cocoa_y, width, height)

        if _debug_caret_panel is None:
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                frame,
                NSWindowStyleMaskBorderless,
                NSBackingStoreBuffered,
                False,
            )
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setHasShadow_(False)
            panel.setIgnoresMouseEvents_(True)
            panel.setLevel_(NSPopUpMenuWindowLevel)
            panel.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
            )
            view = panel.contentView()
            view.setWantsLayer_(True)
            view.layer().setBorderColor_(NSColor.systemRedColor().CGColor())
            view.layer().setBorderWidth_(3.0)
            view.layer().setCornerRadius_(3.0)
            _debug_caret_panel = panel

        _debug_caret_panel.setFrame_display_(frame, True)
        _debug_caret_panel.orderFrontRegardless()

    AppHelper.callAfter(_do)


def show_without_focus(window: Window) -> None:
    ns_window = window.native
    if ns_window is None:
        window.show()
        return

    from webview.platforms.cocoa import AppHelper

    def _do() -> None:
        ns_window.orderFront_(None)

    AppHelper.callAfter(_do)


def hide_panel(window: Window) -> None:
    ns_window = window.native
    if ns_window is None:
        window.hide()
        return

    from webview.platforms.cocoa import AppHelper

    AppHelper.callAfter(ns_window.orderOut_, ns_window)
