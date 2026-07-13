"""受控光标定位实验：绿色为 AppKit 基准，红色为 AX 读取结果。"""

from __future__ import annotations

import json
import os
import time

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSTextField,
    NSTextView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskBorderless,
    NSPopUpMenuWindowLevel,
)
from Foundation import NSObject

from caret import CaretRect, get_caret_rect


LOG_PATH = os.path.join(
    os.path.dirname(__file__), ".cursor", "debug-fa4dbd.log"
)


# region agent log
def write_log(message: str, data: dict) -> None:
    payload = {
        "sessionId": "fa4dbd",
        "runId": "controlled-experiment",
        "hypothesisId": "E1",
        "location": "caret_experiment.py:sample",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with open(LOG_PATH, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
# endregion


def rect_data(rect: CaretRect | None) -> dict | None:
    if rect is None:
        return None
    return {
        "x": rect.x,
        "y": rect.y,
        "width": rect.width,
        "height": rect.height,
    }


class ExperimentDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _notification) -> None:
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(300, 500, 720, 260),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("光标定位对照实验")
        self.window.setDelegate_(self)

        instruction = NSTextField.labelWithString_(
            "请在下方输入任意文字。绿色框=AppKit真实位置，红色框=AX读取位置。"
        )
        instruction.setFrame_(NSMakeRect(30, 195, 660, 28))
        self.window.contentView().addSubview_(instruction)

        self.status = NSTextField.labelWithString_("等待输入…")
        self.status.setFrame_(NSMakeRect(30, 25, 660, 36))
        self.window.contentView().addSubview_(self.status)

        self.text_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(30, 90, 660, 70)
        )
        self.text_view.setFont_(NSFont.monospacedSystemFontOfSize_weight_(30, 0))
        self.text_view.setRichText_(False)
        self.text_view.setDelegate_(self)
        self.text_view.setString_("")
        self.window.contentView().addSubview_(self.text_view)

        self.panels = {}
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.text_view)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def textDidChange_(self, _notification) -> None:
        self.sample()

    def sample(self) -> None:
        selection = self.text_view.selectedRange()
        first_rect_result = (
            self.text_view.firstRectForCharacterRange_actualRange_(selection, None)
        )
        appkit_rect = (
            first_rect_result[0]
            if isinstance(first_rect_result, tuple)
            else first_rect_result
        )

        screens = NSScreen.screens()
        primary_top = (
            screens[0].frame().origin.y + screens[0].frame().size.height
        )
        expected = CaretRect(
            appkit_rect.origin.x,
            primary_top - appkit_rect.origin.y - appkit_rect.size.height,
            max(appkit_rect.size.width, 2.0),
            max(appkit_rect.size.height, 2.0),
        )
        actual = get_caret_rect(prefer_selected=True)

        self.show_box("expected", expected, NSColor.systemGreenColor())
        if actual is not None:
            self.show_box("actual", actual, NSColor.systemRedColor())

        delta = None
        passed = False
        if actual is not None:
            delta = {
                "x": actual.x - expected.x,
                "y": actual.y - expected.y,
            }
            passed = abs(delta["x"]) <= 3 and abs(delta["y"]) <= 3

        self.status.setStringValue_(
            f"{'通过' if passed else '未通过'} | "
            f"X误差={delta['x']:.1f}, Y误差={delta['y']:.1f}"
            if delta
            else "未通过 | AX 未返回光标位置"
        )
        # region agent log
        write_log(
            "受控光标定位对照",
            {
                "text_length": len(self.text_view.string()),
                "selection_location": selection.location,
                "expected": rect_data(expected),
                "actual": rect_data(actual),
                "delta": delta,
                "passed": passed,
            },
        )
        # endregion

    def show_box(self, key: str, rect: CaretRect, color) -> None:
        padding = 5.0
        x = rect.x - padding
        y = rect.y - padding
        width = max(rect.width, 2.0) + padding * 2
        height = max(rect.height, 2.0) + padding * 2
        primary_top = (
            NSScreen.screens()[0].frame().origin.y
            + NSScreen.screens()[0].frame().size.height
        )
        frame = NSMakeRect(x, primary_top - y - height, width, height)

        panel = self.panels.get(key)
        if panel is None:
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
            view = panel.contentView()
            view.setWantsLayer_(True)
            view.layer().setBorderColor_(color.CGColor())
            view.layer().setBorderWidth_(3.0)
            self.panels[key] = panel

        panel.setFrame_display_(frame, True)
        panel.orderFrontRegardless()

    def windowWillClose_(self, _notification) -> None:
        NSApplication.sharedApplication().terminate_(None)


def main() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = ExperimentDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
