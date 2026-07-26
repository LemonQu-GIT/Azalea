import ctypes
import ctypes.wintypes
import win32gui
import time
import cv2
import numpy as np


ctypes.windll.user32.SetProcessDPIAware()


def isWindowVisible(hwnd: int) -> bool:
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi

    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    DWMWA_CLOAKED = 14
    GA_ROOTOWNER = 4

    if not user32.IsWindowVisible(hwnd):
        return False

    cloaked = ctypes.wintypes.DWORD()
    result = dwmapi.DwmGetWindowAttribute(
        ctypes.wintypes.HWND(hwnd),
        DWMWA_CLOAKED,
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked)
    )
    if result == 0 and cloaked.value == 0x02:
        return False

    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    is_tool = ex_style & WS_EX_TOOLWINDOW
    is_app = ex_style & WS_EX_APPWINDOW
    if is_tool and not is_app:
        return False

    title_length = user32.GetWindowTextLengthW(hwnd)
    if title_length == 0 and not is_app:
        return False

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(ctypes.wintypes.HWND(hwnd), ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False

    owner = user32.GetWindow(hwnd, GA_ROOTOWNER)
    if owner != 0 and owner != hwnd:
        if title_length == 0:
            return False

    return True


def getWindowRect(hwnd: int) -> tuple[int | None, int | None, int | None, int | None]:
    """
    【修复根因】使用 Win32 GetWindowRect 替代 DwmGetWindowAttribute。
    确保返回的矩形大小与 win32gui.MoveWindow 使用的矩形坐标系完全一致，
    从根本上解决窗口每次移动都被扣掉阴影边框导致不断缩小的 bug。
    """
    user32 = ctypes.windll.user32
    rect = ctypes.wintypes.RECT()
    if user32.GetWindowRect(ctypes.wintypes.HWND(hwnd), ctypes.byref(rect)):
        return rect.left, rect.top, rect.right, rect.bottom
    return None, None, None, None


def getWindowsInZOrder() -> list[int]:
    user32 = ctypes.windll.user32
    GW_HWNDNEXT = 2

    hwnds: list[int] = []
    hwnd = user32.GetTopWindow(None)
    while hwnd != 0:
        hwnds.append(hwnd)
        hwnd = user32.GetWindow(ctypes.wintypes.HWND(hwnd), GW_HWNDNEXT)

    return hwnds


def getWindowTitle(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def getAllWindowsRects() -> list[tuple[str, int, int, int, int, int]]:
    z_order_hwnds = getWindowsInZOrder()

    rects: list[tuple[str, int, int, int, int, int]] = []

    for hwnd in z_order_hwnds:
        title = getWindowTitle(hwnd)
        if not title:
            continue
        if not isWindowVisible(hwnd):
            continue

        x, y, z, b = getWindowRect(hwnd)
        if x is not None and y is not None and z is not None and b is not None:
            if x >= 0 and y >= 0 and z >= 0 and b >= 0:
                rects.append((title, hwnd, x, y, z - x, b - y))

    return rects


def transformWindow(hwnd: int, x: int | None = None, y: int | None = None, width: int | None = None, height: int | None = None):
    winrect = getWindowRect(hwnd)
    if winrect[0] is not None and winrect[1] is not None and winrect[2] is not None and winrect[3] is not None:
        if x is None:
            x = winrect[0]
        if y is None:
            y = winrect[1]
        if width is None:
            width = winrect[2] - winrect[0]
        if height is None:
            height = winrect[3] - winrect[1]
        win32gui.MoveWindow(hwnd, x, y, width, height, True)
        return
    raise ValueError("Failed to get window rect for hwnd: {}".format(hwnd))


def debugDrawWindows():
    if cv2 is None or np is None:
        raise RuntimeError(
            "debugDrawWindows() requires opencv-python and numpy")

    all_rects = getAllWindowsRects()
    for i, (title, hwnd, x, y, w, h) in enumerate(all_rects):
        print(f"[{i}] {title}  @ ({x},{y}) {w}x{h} (hwnd: {hwnd})")

    img = np.zeros((1080, 1920, 3), np.uint8)

    for i, (title, hwnd, x, y, w, h) in enumerate(all_rects):
        green = max(50, 255 - i * 30)
        color = (0, green, 0)
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        cv2.putText(img, f"[{i}] {title}", (x + 10, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    cv2.imwrite('window_rects.png', img)


def getScreenSize() -> tuple[int, int]:
    return (
        int(ctypes.windll.user32.GetSystemMetrics(0)),
        int(ctypes.windll.user32.GetSystemMetrics(1)),
    )


if __name__ == "__main__":
    debugDrawWindows()
    # transformWindow(264370, 100, 100)
