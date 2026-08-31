"""macOS implementations of the desktop-window helper API.

Quartz provides read-only window enumeration and geometry.  AppKit is used for
the Qt-created pet windows, while moving another application's window is a
best-effort Accessibility operation and requires user approval in System
Settings.
"""

from __future__ import annotations

import ctypes
from typing import Any

try:
    import AppKit
    import ApplicationServices
    import objc
    import Quartz

    _MACOS_APIS_OK = True
except Exception:  # pragma: no cover - depends on the host environment
    AppKit = None  # type: ignore[assignment]
    ApplicationServices = None  # type: ignore[assignment]
    Quartz = None  # type: ignore[assignment]
    objc = None  # type: ignore[assignment]
    _MACOS_APIS_OK = False


DEFAULT_THEME_COLOR = (0x00, 0x7A, 0xFF, 0xFF)

# CGWindowID -> NSWindow for windows created by this process.  Quartz window
# numbers are stable for the lifetime of an NSWindow and are also what the
# desktop-window enumeration returns.
_native_windows: dict[int, Any] = {}


def is_available() -> bool:
    return _MACOS_APIS_OK


def is_accessibility_trusted() -> bool:
    if not _MACOS_APIS_OK:
        return False
    try:
        return bool(ApplicationServices.AXIsProcessTrusted())
    except Exception:
        return False


def _ns_window(qt_window):
    if not _MACOS_APIS_OK or qt_window is None:
        return None
    try:
        view = objc.objc_object(
            c_void_p=ctypes.c_void_p(int(qt_window.winId()))
        )
        return view.window()
    except Exception:
        return None


def getWindowHandle(qt_window) -> int:
    """Return the CGWindowID corresponding to a top-level Qt widget."""
    window = _ns_window(qt_window)
    if window is None:
        try:
            return int(qt_window.winId())
        except Exception:
            return 0
    try:
        handle = int(window.windowNumber())
        _native_windows[handle] = window
        return handle
    except Exception:
        return 0


def _window_options() -> int:
    return int(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )


def _all_window_info() -> list[dict]:
    if not _MACOS_APIS_OK:
        return []
    try:
        windows = Quartz.CGWindowListCopyWindowInfo(
            _window_options(), Quartz.kCGNullWindowID
        )
        return [dict(window) for window in (windows or [])]
    except Exception:
        return []


def _window_info(handle: int) -> dict | None:
    if not _MACOS_APIS_OK or not handle:
        return None
    try:
        windows = Quartz.CGWindowListCreateDescriptionFromArray([int(handle)])
        if not windows:
            return None
        for window in windows:
            info = dict(window)
            if int(info.get(Quartz.kCGWindowNumber, 0)) == int(handle):
                return info
        return None
    except Exception:
        return None


def _bounds(info: dict) -> tuple[int, int, int, int] | None:
    try:
        raw = dict(info[Quartz.kCGWindowBounds])
        left = round(float(raw["X"]))
        top = round(float(raw["Y"]))
        width = round(float(raw["Width"]))
        height = round(float(raw["Height"]))
        if width <= 0 or height <= 0:
            return None
        return (left, top, left + width, top + height)
    except Exception:
        return None


def _is_normal_window(info: dict) -> bool:
    try:
        if int(info.get(Quartz.kCGWindowLayer, 0)) != 0:
            return False
        if not bool(info.get(Quartz.kCGWindowIsOnscreen, True)):
            return False
        if float(info.get(Quartz.kCGWindowAlpha, 1.0)) <= 0:
            return False
        return _bounds(info) is not None
    except Exception:
        return False


def get_theme_color(hex: bool = False) -> tuple[int, int, int, int] | str:
    r, g, b, a = DEFAULT_THEME_COLOR
    if _MACOS_APIS_OK:
        try:
            color = AppKit.NSColor.controlAccentColor().colorUsingColorSpace_(
                AppKit.NSColorSpace.sRGBColorSpace()
            )
            if color is not None:
                r = round(float(color.redComponent()) * 255)
                g = round(float(color.greenComponent()) * 255)
                b = round(float(color.blueComponent()) * 255)
                a = round(float(color.alphaComponent()) * 255)
        except Exception:
            pass
    if hex:
        return f"#{r:02X}{g:02X}{b:02X}{a:02X}"
    return r, g, b, a


get_windows_theme_color = get_theme_color


def getWindowsInZOrder() -> list[int]:
    """Return normal windows front-to-back, matching the Win32 contract."""
    result: list[int] = []
    for info in _all_window_info():
        if not _is_normal_window(info):
            continue
        try:
            result.append(int(info[Quartz.kCGWindowNumber]))
        except Exception:
            continue
    return result


def getWindowTitle(handle: int) -> str:
    info = _window_info(handle)
    if info is None:
        return ""
    # Without Screen Recording permission macOS may redact kCGWindowName.
    # The owning application name is still useful for collision tracking.
    value = (
        info.get(Quartz.kCGWindowName)
        or info.get(Quartz.kCGWindowOwnerName)
        or ""
    )
    return str(value)


def isWindowVisible(handle: int) -> bool:
    info = _window_info(handle)
    return info is not None and _is_normal_window(info)


def getWindowLogicalRect(
    handle: int,
) -> tuple[int | None, int | None, int | None, int | None]:
    info = _window_info(handle)
    if info is None:
        return (None, None, None, None)
    rect = _bounds(info)
    if rect is None:
        return (None, None, None, None)
    return rect


def getWindowRect(
    handle: int,
) -> tuple[int | None, int | None, int | None, int | None]:
    return getWindowLogicalRect(handle)


def getAllWindowsRects() -> list[tuple[str, int, int, int, int, int]]:
    rects: list[tuple[str, int, int, int, int, int]] = []
    for info in _all_window_info():
        if not _is_normal_window(info):
            continue
        rect = _bounds(info)
        if rect is None:
            continue
        try:
            handle = int(info[Quartz.kCGWindowNumber])
            title = str(
                info.get(Quartz.kCGWindowName)
                or info.get(Quartz.kCGWindowOwnerName)
                or ""
            )
        except Exception:
            continue
        if not title:
            continue
        left, top, right, bottom = rect
        rects.append(
            (title, handle, left, top, right - left, bottom - top)
        )
    return rects


def _copy_ax_attribute(element, attribute: str):
    try:
        error, value = ApplicationServices.AXUIElementCopyAttributeValue(
            element, attribute, None
        )
        if int(error) == 0:
            return value
    except Exception:
        pass
    return None


def _ax_point(value) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        ok, point = ApplicationServices.AXValueGetValue(
            value, ApplicationServices.kAXValueCGPointType, None
        )
        if ok:
            return float(point.x), float(point.y)
    except Exception:
        pass
    return None


def _ax_size(value) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        ok, size = ApplicationServices.AXValueGetValue(
            value, ApplicationServices.kAXValueCGSizeType, None
        )
        if ok:
            return float(size.width), float(size.height)
    except Exception:
        pass
    return None


def _find_ax_window(info: dict):
    if not is_accessibility_trusted():
        return None
    try:
        pid = int(info[Quartz.kCGWindowOwnerPID])
        app = ApplicationServices.AXUIElementCreateApplication(pid)
        windows = _copy_ax_attribute(
            app, ApplicationServices.kAXWindowsAttribute
        )
        if not windows:
            return None
    except Exception:
        return None

    target_id = int(info.get(Quartz.kCGWindowNumber, 0))
    for window in windows:
        # AXWindowNumber is not a public constant, but is exposed by the
        # accessibility server on current macOS releases.
        number = _copy_ax_attribute(window, "AXWindowNumber")
        if number is not None:
            try:
                if int(number) == target_id:
                    return window
            except Exception:
                pass

    target = _bounds(info)
    if target is None:
        return None
    target_left, target_top, target_right, target_bottom = target
    target_width = target_right - target_left
    target_height = target_bottom - target_top

    best_window = None
    best_score = float("inf")
    for window in windows:
        point = _ax_point(
            _copy_ax_attribute(
                window, ApplicationServices.kAXPositionAttribute
            )
        )
        size = _ax_size(
            _copy_ax_attribute(window, ApplicationServices.kAXSizeAttribute)
        )
        if point is None or size is None:
            continue
        score = (
            abs(point[0] - target_left)
            + abs(point[1] - target_top)
            + abs(size[0] - target_width)
            + abs(size[1] - target_height)
        )
        if score < best_score:
            best_score = score
            best_window = window
    return best_window if best_score <= 80 else None


def transformWindow(
    handle: int,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Best-effort move/resize; silently degrades without Accessibility."""
    info = _window_info(handle)
    if info is None:
        return
    window = _find_ax_window(info)
    if window is None:
        return
    rect = _bounds(info)
    if rect is None:
        return
    left, top, right, bottom = rect
    x = left if x is None else int(x)
    y = top if y is None else int(y)
    width = right - left if width is None else max(1, int(width))
    height = bottom - top if height is None else max(1, int(height))
    try:
        point = ApplicationServices.AXValueCreate(
            ApplicationServices.kAXValueCGPointType,
            Quartz.CGPoint(float(x), float(y)),
        )
        size = ApplicationServices.AXValueCreate(
            ApplicationServices.kAXValueCGSizeType,
            Quartz.CGSize(float(width), float(height)),
        )
        ApplicationServices.AXUIElementSetAttributeValue(
            window, ApplicationServices.kAXPositionAttribute, point
        )
        ApplicationServices.AXUIElementSetAttributeValue(
            window, ApplicationServices.kAXSizeAttribute, size
        )
    except Exception:
        return


def getDesktopBounds() -> tuple[int, int, int, int]:
    """Return the Qt logical-coordinate union of all attached displays."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        if screens:
            geometries = [screen.geometry() for screen in screens]
            left = min(rect.left() for rect in geometries)
            top = min(rect.top() for rect in geometries)
            right = max(rect.right() + 1 for rect in geometries)
            bottom = max(rect.bottom() + 1 for rect in geometries)
            return int(left), int(top), int(right), int(bottom)
    except Exception:
        pass

    if _MACOS_APIS_OK:
        try:
            frame = AppKit.NSScreen.mainScreen().frame()
            return (0, 0, round(frame.size.width), round(frame.size.height))
        except Exception:
            pass
    return (0, 0, 1920, 1080)


def getScreenSize() -> tuple[int, int]:
    left, top, right, bottom = getDesktopBounds()
    return right - left, bottom - top


def setWindowTopmost(handle: int, topmost: bool) -> bool:
    window = _native_windows.get(int(handle))
    if window is None:
        return False
    try:
        level = (
            AppKit.NSFloatingWindowLevel
            if topmost
            else AppKit.NSNormalWindowLevel
        )
        window.setLevel_(level)
        if topmost:
            window.orderFrontRegardless()
        return True
    except Exception:
        return False


def raiseWindowToTop(handle: int) -> bool:
    window = _native_windows.get(int(handle))
    if window is None:
        return False
    try:
        window.orderFrontRegardless()
        return True
    except Exception:
        return False


def setWindowZOrderAfter(handle: int, insert_after: int) -> bool:
    window = _native_windows.get(int(handle))
    if window is None:
        return False
    try:
        if int(insert_after) == 0:
            window.orderFrontRegardless()
        else:
            window.orderWindow_relativeTo_(
                AppKit.NSWindowBelow, int(insert_after)
            )
        return True
    except Exception:
        return False


def setWindowClickThrough(qt_window, enabled: bool) -> bool:
    window = _ns_window(qt_window)
    if window is None:
        return False
    try:
        window.setIgnoresMouseEvents_(bool(enabled))
        qt_window._click_through_applied = bool(enabled)
        return True
    except Exception:
        return False

