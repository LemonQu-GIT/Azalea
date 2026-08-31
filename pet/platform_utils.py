"""跨平台窗口工具的统一入口。

Windows 上委托给 :mod:`pet.windows_utils`，Linux/X11 委托给
:mod:`pet.linux_utils`，macOS 委托给 :mod:`pet.macos_utils`。

对外暴露的 API：
    get_theme_color / get_windows_theme_color
    isWindowVisible, getWindowTitle
    getWindowRect, getWindowLogicalRect, getAllWindowsRects
    getWindowsInZOrder, transformWindow, getScreenSize
    setWindowTopmost, raiseWindowToTop, setWindowZOrderAfter
    setWindowClickThrough
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

if IS_WINDOWS:
    import win32con
    import win32gui

    import pet.windows_utils as _impl

    WINDOW_Z_TOP = win32con.HWND_TOP
    _SWP_FLAGS = (
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
    )
elif IS_LINUX:
    import pet.linux_utils as _impl

    WINDOW_Z_TOP = 0
    _SWP_FLAGS = 0
elif IS_MACOS:
    import pet.macos_utils as _impl

    WINDOW_Z_TOP = 0
    _SWP_FLAGS = 0
else:
    raise RuntimeError(f"Unsupported desktop platform: {sys.platform}")

def _detect_click_through_mode() -> str:
    """点击穿透的实现方式。

    - ``"dynamic"``  (Windows) 按指针位置实时切换 WS_EX_TRANSPARENT。
    - ``"dynamic"``  (macOS) 按指针位置实时切换 NSWindow 鼠标忽略状态。
    - ``"static-region"`` (Linux/X11) 用 SHAPE 扩展一次性设定输入区域。
      Wayland 会话里全局指针位置是陈旧的，动态方案会永久卡在穿透状态，
      所以这里必须用静态区域。
    - ``"none"``     没有可用方案，窗口整体可点击。
    """
    if IS_WINDOWS:
        return "dynamic"
    if IS_MACOS and _impl.is_available():
        return "dynamic"
    if IS_LINUX and _impl.has_input_shape():
        return "static-region"
    return "none"


CLICK_THROUGH_MODE = _detect_click_through_mode()

# 仅表示"支持按指针位置动态切换穿透"，pet_window 用它来决定是否启用 30ms 轮询。
CLICK_THROUGH_SUPPORTED = CLICK_THROUGH_MODE == "dynamic"


def get_theme_color(hex: bool = False) -> tuple[int, int, int, int] | str:
    return _impl.get_windows_theme_color(hex=hex)


# 兼容旧的调用点
get_windows_theme_color = get_theme_color


def isWindowVisible(handle: int) -> bool:
    return _impl.isWindowVisible(handle)


def getWindowTitle(handle: int) -> str:
    return _impl.getWindowTitle(handle)


def getWindowRect(
    handle: int,
) -> tuple[int | None, int | None, int | None, int | None]:
    return _impl.getWindowRect(handle)


def getWindowLogicalRect(
    handle: int,
) -> tuple[int | None, int | None, int | None, int | None]:
    return _impl.getWindowLogicalRect(handle)


def getWindowsInZOrder() -> list[int]:
    return _impl.getWindowsInZOrder()


def getAllWindowsRects() -> list[tuple[str, int, int, int, int, int]]:
    return _impl.getAllWindowsRects()


def transformWindow(
    handle: int,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    _impl.transformWindow(handle, x, y, width, height)


def getScreenSize() -> tuple[int, int]:
    return _impl.getScreenSize()


def getDesktopBounds() -> tuple[int, int, int, int]:
    """返回虚拟桌面的逻辑坐标边界。"""
    getter = getattr(_impl, "getDesktopBounds", None)
    if getter is not None:
        return getter()
    width, height = getScreenSize()
    return (0, 0, width, height)


def getWindowHandle(window) -> int:
    """返回平台窗口枚举所使用的原生句柄。"""
    getter = getattr(_impl, "getWindowHandle", None)
    if getter is not None:
        return int(getter(window))
    return int(window.winId())


def isAccessibilityTrusted() -> bool:
    checker = getattr(_impl, "is_accessibility_trusted", None)
    return bool(checker()) if checker is not None else True


def setWindowTopmost(handle: int, topmost: bool) -> bool:
    """把窗口设为置顶 / 取消置顶。"""
    if not handle:
        return False
    if IS_WINDOWS:
        try:
            win32gui.SetWindowPos(
                handle,
                win32con.HWND_TOPMOST if topmost else win32con.HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                _SWP_FLAGS,
            )
            return True
        except Exception:
            return False
    return _impl.setWindowTopmost(handle, topmost)


def raiseWindowToTop(handle: int) -> bool:
    """把窗口提到最前（气泡等临时窗口用）。"""
    if not handle:
        return False
    if IS_WINDOWS:
        try:
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            import ctypes

            ctypes.windll.user32.SetWindowPos(
                int(handle),
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            return True
        except Exception:
            return False
    return _impl.raiseWindowToTop(handle)


def setWindowZOrderAfter(handle: int, insert_after: int) -> bool:
    """把窗口插到 insert_after 之后（X11 上无对应能力，静默忽略）。"""
    if not handle:
        return False
    if IS_WINDOWS:
        try:
            win32gui.SetWindowPos(
                handle,
                insert_after,
                0,
                0,
                0,
                0,
                _SWP_FLAGS,
            )
            return True
        except Exception:
            return False
    return _impl.setWindowZOrderAfter(handle, insert_after)


def setWindowInputRegion(
    handle: int,
    rect: tuple[int, int, int, int] | tuple[()] | None = None,
) -> bool:
    """设置窗口静态输入区域（仅 ``static-region`` 模式有效）。

    ``None`` 恢复整窗口可点击，空元组 ``()`` 表示完全点击穿透。
    """
    if not handle or CLICK_THROUGH_MODE != "static-region":
        return False
    return _impl.setWindowInputRegion(handle, rect)


def getWindowInputRegion(handle: int) -> list[tuple[int, int, int, int]] | None:
    """读回窗口当前的输入区域矩形，不支持时返回 None。"""
    if not handle or CLICK_THROUGH_MODE != "static-region":
        return None
    return _impl.getWindowInputRegion(handle)


def setWindowClickThrough(window, enabled: bool) -> bool:
    """开关点击穿透。``window`` 是一个 QWidget（顶层窗口）。"""
    if window is None:
        return False

    if IS_WINDOWS:
        try:
            import ctypes

            hwnd = int(window.winId())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20

            current_style = ctypes.windll.user32.GetWindowLongW(
                hwnd, GWL_EXSTYLE)

            if enabled:
                new_style = current_style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            else:
                new_style = (current_style |
                             WS_EX_LAYERED) & ~WS_EX_TRANSPARENT

            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            return True
        except Exception:
            return False

    if IS_MACOS:
        return _impl.setWindowClickThrough(window, enabled)

    if not IS_LINUX:
        return False

    # X11 / Wayland：交给 Qt 设置空的输入区域
    try:
        from PyQt6.QtCore import Qt

        if bool(getattr(window, "_click_through_applied", False)) == bool(enabled):
            return True

        was_visible = window.isVisible()
        geometry = window.geometry()
        window.setWindowFlag(
            Qt.WindowType.WindowTransparentForInput, bool(enabled))
        window.setGeometry(geometry)
        if was_visible:
            window.show()
        window._click_through_applied = bool(enabled)
        return True
    except Exception:
        return False
