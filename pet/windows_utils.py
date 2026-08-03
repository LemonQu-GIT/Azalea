from ctypes import wintypes
import ctypes
import ctypes.wintypes
import win32gui
import time
import numpy as np

DWMWA_EXTENDED_FRAME_BOUNDS = 9
ctypes.windll.user32.SetProcessDPIAware()
dwmapi = ctypes.WinDLL("dwmapi")

DwmGetColorizationColor = dwmapi.DwmGetColorizationColor
DwmGetColorizationColor.argtypes = [
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.BOOL)
]
DwmGetColorizationColor.restype = ctypes.c_long


def get_windows_theme_color(hex: bool = False) -> tuple[int, int, int, int] | str:
    color = wintypes.DWORD()
    opaque = wintypes.BOOL()

    hr = DwmGetColorizationColor(
        ctypes.byref(color),
        ctypes.byref(opaque)
    )

    if hr != 0:
        raise OSError(f"DwmGetColorizationColor failed: {hr}")

    value = color.value

    a = (value >> 24) & 0xFF
    r = (value >> 16) & 0xFF
    g = (value >> 8) & 0xFF
    b = value & 0xFF
    if hex:
        return f"#{r:02X}{g:02X}{b:02X}{a:02X}"
    return r, g, b, a


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
    return getWindowLogicalRect(hwnd)
    '''rect = wintypes.RECT()

    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect),
        ctypes.sizeof(rect)
    )

    return (
        rect.left,
        rect.top,
        rect.right,
        rect.bottom
    )'''


def getWindowLogicalRect(hwnd: int) -> tuple[int | None, int | None, int | None, int | None]:
    rect = wintypes.RECT()
    ok = ctypes.windll.user32.GetWindowRect(
        ctypes.wintypes.HWND(hwnd), ctypes.byref(rect))
    if not ok:
        return (None, None, None, None)
    return (rect.left, rect.top, rect.right, rect.bottom)


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
            if z - x > 0 and b - y > 0:
                rects.append((title, hwnd, x, y, z - x, b - y))
    return rects


def transformWindow(hwnd: int, x: int | None = None, y: int | None = None, width: int | None = None, height: int | None = None):
    rect = wintypes.RECT()
    ok = ctypes.windll.user32.GetWindowRect(
        ctypes.wintypes.HWND(hwnd), ctypes.byref(rect))
    if ok:
        if x is None:
            x = rect.left
        if y is None:
            y = rect.top
        if width is None:
            width = rect.right - rect.left
        if height is None:
            height = rect.bottom - rect.top
        win32gui.MoveWindow(hwnd, x, y, width, height, True)
        return
    raise ValueError("Failed to get window rect for hwnd: {}".format(hwnd))


def debugDrawWindows():
    import cv2
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
    print(get_windows_theme_color(hex=True)[0:7])
    # debugDrawWindows()
    # transformWindow(264370, 100, 100)
