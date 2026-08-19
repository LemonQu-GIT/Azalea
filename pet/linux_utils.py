"""Linux (X11 / EWMH) implementations of the desktop window helpers.

This module mirrors the API of :mod:`pet.windows_utils` so that
:mod:`pet.platform_utils` can dispatch to either one at runtime.

Every function degrades gracefully: if ``python-xlib`` is not installed, or the
X connection cannot be established (for example inside a pure Wayland session
without XWayland), all calls return safe empty values instead of raising.
Nothing here raises at import time either.
"""

from __future__ import annotations

import threading

try:  # python-xlib is an optional, linux-only dependency
    from Xlib import X as _X
    from Xlib import display as _xdisplay
    from Xlib.protocol import event as _xevent

    _XLIB_OK = True
except Exception:  # pragma: no cover - depends on the host environment
    _X = None  # type: ignore[assignment]
    _xdisplay = None  # type: ignore[assignment]
    _xevent = None  # type: ignore[assignment]
    _XLIB_OK = False

try:  # SHAPE 扩展：用于设置静态输入区域（点击穿透）
    from Xlib.ext import shape as _xshape

    _SHAPE_OK = _XLIB_OK
except Exception:  # pragma: no cover
    _xshape = None  # type: ignore[assignment]
    _SHAPE_OK = False


# 默认主题色（Windows 蓝），在拿不到 Qt 调色板时使用
DEFAULT_THEME_COLOR = (0x00, 0x78, 0xD4, 0xFF)

_lock = threading.RLock()
_display = None
_display_failed = False
_atom_cache: dict[str, int] = {}

# 不参与窗口跟踪的 EWMH 窗口类型（桌面/任务栏等）
_IGNORED_WINDOW_TYPES = ("_NET_WM_WINDOW_TYPE_DESKTOP", "_NET_WM_WINDOW_TYPE_DOCK")


def is_available() -> bool:
    """X11 后端当前是否可用。"""
    return _get_display() is not None


def _get_display():
    global _display, _display_failed
    if not _XLIB_OK or _display_failed:
        return None
    with _lock:
        if _display is None:
            try:
                _display = _xdisplay.Display()
            except Exception:
                _display = None
                _display_failed = True
        return _display


def _reset_display() -> None:
    """连接断开后丢弃缓存，下次调用重新连接。"""
    global _display
    with _lock:
        _display = None
        _atom_cache.clear()


def _atom(name: str) -> int:
    display = _get_display()
    if display is None:
        return 0
    cached = _atom_cache.get(name)
    if cached is not None:
        return cached
    try:
        value = int(display.get_atom(name))
    except Exception:
        value = 0
    _atom_cache[name] = value
    return value


def _window(handle: int):
    display = _get_display()
    if display is None or not handle:
        return None
    try:
        return display.create_resource_object("window", int(handle))
    except Exception:
        return None


def _root():
    display = _get_display()
    if display is None:
        return None
    try:
        return display.screen().root
    except Exception:
        return None


def _prop(window, name: str):
    if window is None:
        return None
    atom = _atom(name)
    if not atom:
        return None
    try:
        return window.get_full_property(atom, _X.AnyPropertyType)
    except Exception:
        return None


def _frame_extents(window) -> tuple[int, int, int, int]:
    """返回 (left, right, top, bottom) 边框宽度，取不到时全为 0。"""
    prop = _prop(window, "_NET_FRAME_EXTENTS")
    if prop is None or not prop.value or len(prop.value) < 4:
        return (0, 0, 0, 0)
    try:
        values = [int(v) for v in prop.value[:4]]
        return (values[0], values[1], values[2], values[3])
    except Exception:
        return (0, 0, 0, 0)


def get_theme_color(hex: bool = False) -> tuple[int, int, int, int] | str:
    """取系统强调色：优先 Qt 调色板的 Highlight，否则退回默认蓝。"""
    r, g, b, a = DEFAULT_THEME_COLOR
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            color = app.palette().highlight().color()  # type: ignore[attr-defined]
            r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
    except Exception:
        pass

    if hex:
        return f"#{r:02X}{g:02X}{b:02X}{a:02X}"
    return r, g, b, a


# 与 windows_utils 保持同名，方便统一分发
get_windows_theme_color = get_theme_color


def getWindowsInZOrder() -> list[int]:
    """按 z 序返回窗口 id，索引 0 为最顶层（与 Windows 侧语义一致）。"""
    root = _root()
    if root is None:
        return []
    with _lock:
        try:
            prop = _prop(root, "_NET_CLIENT_LIST_STACKING")
            if prop is None or not prop.value:
                prop = _prop(root, "_NET_CLIENT_LIST")
            if prop is None or not prop.value:
                return []
            # EWMH 是自下而上的，反转成自上而下
            return [int(v) for v in reversed(list(prop.value))]
        except Exception:
            _reset_display()
            return []


def getWindowTitle(handle: int) -> str:
    window = _window(handle)
    if window is None:
        return ""
    with _lock:
        try:
            prop = _prop(window, "_NET_WM_NAME")
            if prop is not None and prop.value:
                value = prop.value
                if isinstance(value, bytes):
                    return value.decode("utf-8", errors="replace")
                return str(value)
            name = window.get_wm_name()
            if not name:
                return ""
            if isinstance(name, bytes):
                return name.decode("utf-8", errors="replace")
            return str(name)
        except Exception:
            return ""


def isWindowVisible(handle: int) -> bool:
    window = _window(handle)
    if window is None:
        return False
    with _lock:
        try:
            attributes = window.get_attributes()
            if attributes is None or attributes.map_state != _X.IsViewable:
                return False

            state = _prop(window, "_NET_WM_STATE")
            if state is not None and state.value:
                hidden = _atom("_NET_WM_STATE_HIDDEN")
                if hidden and hidden in [int(v) for v in state.value]:
                    return False

            win_type = _prop(window, "_NET_WM_WINDOW_TYPE")
            if win_type is not None and win_type.value:
                ignored = {_atom(name) for name in _IGNORED_WINDOW_TYPES}
                ignored.discard(0)
                if ignored & {int(v) for v in win_type.value}:
                    return False

            geometry = window.get_geometry()
            return geometry is not None and geometry.width > 0 and geometry.height > 0
        except Exception:
            return False


def getWindowLogicalRect(
    handle: int,
) -> tuple[int | None, int | None, int | None, int | None]:
    window = _window(handle)
    root = _root()
    if window is None or root is None:
        return (None, None, None, None)
    with _lock:
        try:
            geometry = window.get_geometry()
            translated = root.translate_coords(int(handle), 0, 0)
            left = int(translated.x)
            top = int(translated.y)
            width = int(geometry.width)
            height = int(geometry.height)
        except Exception:
            return (None, None, None, None)

        frame_left, frame_right, frame_top, frame_bottom = _frame_extents(window)
        return (
            left - frame_left,
            top - frame_top,
            left + width + frame_right,
            top + height + frame_bottom,
        )


def getWindowRect(
    handle: int,
) -> tuple[int | None, int | None, int | None, int | None]:
    return getWindowLogicalRect(handle)


def getAllWindowsRects() -> list[tuple[str, int, int, int, int, int]]:
    rects: list[tuple[str, int, int, int, int, int]] = []
    for handle in getWindowsInZOrder():
        title = getWindowTitle(handle)
        if not title:
            continue
        if not isWindowVisible(handle):
            continue

        x, y, right, bottom = getWindowRect(handle)
        if x is None or y is None or right is None or bottom is None:
            continue
        if right - x > 0 and bottom - y > 0:
            rects.append((title, handle, x, y, right - x, bottom - y))
    return rects


def transformWindow(
    handle: int,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    window = _window(handle)
    display = _get_display()
    if window is None or display is None:
        return

    current = getWindowLogicalRect(handle)
    if current[0] is None:
        return
    left, top, right, bottom = current  # type: ignore[misc]

    if x is None:
        x = left
    if y is None:
        y = top
    if width is None:
        width = right - left
    if height is None:
        height = bottom - top

    with _lock:
        frame_left, frame_right, frame_top, frame_bottom = _frame_extents(window)
        try:
            window.configure(
                x=int(x) + frame_left,
                y=int(y) + frame_top,
                width=max(1, int(width) - frame_left - frame_right),
                height=max(1, int(height) - frame_top - frame_bottom),
            )
            display.flush()
        except Exception:
            _reset_display()


def _send_wm_state(handle: int, action: int, state_name: str) -> bool:
    window = _window(handle)
    root = _root()
    display = _get_display()
    if window is None or root is None or display is None:
        return False

    state_atom = _atom(state_name)
    message_atom = _atom("_NET_WM_STATE")
    if not state_atom or not message_atom:
        return False

    with _lock:
        try:
            message = _xevent.ClientMessage(
                window=window,
                client_type=message_atom,
                data=(32, [action, state_atom, 0, 1, 0]),
            )
            root.send_event(
                message,
                event_mask=_X.SubstructureRedirectMask | _X.SubstructureNotifyMask,
            )
            display.flush()
            return True
        except Exception:
            _reset_display()
            return False


def setWindowTopmost(handle: int, topmost: bool) -> bool:
    # _NET_WM_STATE_ADD = 1, _NET_WM_STATE_REMOVE = 0
    return _send_wm_state(handle, 1 if topmost else 0, "_NET_WM_STATE_ABOVE")


def raiseWindowToTop(handle: int) -> bool:
    window = _window(handle)
    display = _get_display()
    if window is None or display is None:
        return False
    with _lock:
        try:
            window.configure(stack_mode=_X.Above)
            display.flush()
            return True
        except Exception:
            _reset_display()
            return False


def has_input_shape() -> bool:
    """SHAPE 扩展是否可用（静态输入区域点击穿透的前提）。"""
    if not _SHAPE_OK:
        return False
    display = _get_display()
    if display is None:
        return False
    with _lock:
        try:
            return display.query_extension(_xshape.extname) is not None
        except Exception:
            return False


def setWindowInputRegion(
    handle: int,
    rect: tuple[int, int, int, int] | tuple[()] | None = None,
) -> bool:
    """设置窗口的 X11 输入区域（SHAPE Input）。

    ``rect`` 的三种取值：

    - ``None``：恢复整窗口可点击。
    - 空序列 ``()``：输入区域为空，整个窗口完全点击穿透（气泡这类纯展示
      窗口用这个）。
    - ``(x, y, width, height)``：相对窗口左上角的矩形，只有矩形内的点击
      会落到本窗口，其余区域穿透到下层窗口。

    宽或高 <= 0 的矩形一律视为参数错误返回 False，而不是当成"空区域"——
    免得某个算错的区域把窗口静默变成完全点不到。要空区域请显式传 ``()``。

    这是 Wayland/XWayland 会话下唯一可靠的点击穿透方式：它是静态的，
    不依赖全局指针位置（XQueryPointer 在 Wayland 下会是陈旧值）。
    """
    if not _SHAPE_OK:
        return False
    window = _window(handle)
    display = _get_display()
    if window is None or display is None:
        return False

    with _lock:
        try:
            # 先做一次同步往返验证 handle：shape 请求本身是异步的，句柄无效时
            # 不会返回错误，只会在之后由 Xlib 默认错误处理器打一堆 BadWindow。
            # （比如 Qt 跑在 wayland 插件下，winId() 根本不是 X 窗口 id。）
            geometry = window.get_geometry()

            if rect is None:
                rectangles = [{
                    "x": 0,
                    "y": 0,
                    "width": int(geometry.width),
                    "height": int(geometry.height),
                }]
            elif len(rect) == 0:
                # SHAPE Set + 零个矩形 = 空输入区域
                rectangles = []
            else:
                x, y, width, height = (int(v) for v in rect)
                if width <= 0 or height <= 0:
                    return False
                rectangles = [{
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                }]

            window.shape_rectangles(
                _xshape.SO.Set,
                _xshape.SK.Input,
                _X.Unsorted,
                0,
                0,
                rectangles,
            )
            display.flush()
            return True
        except Exception:
            _reset_display()
            return False


def getWindowInputRegion(handle: int) -> list[tuple[int, int, int, int]] | None:
    """读回窗口当前的 SHAPE Input 矩形列表，失败返回 None。"""
    if not _SHAPE_OK:
        return None
    window = _window(handle)
    if window is None:
        return None
    with _lock:
        try:
            reply = window.shape_get_rectangles(_xshape.SK.Input)
            return [
                (int(r.x), int(r.y), int(r.width), int(r.height))
                for r in reply.rectangles
            ]
        except Exception:
            return None


def setWindowZOrderAfter(handle: int, insert_after: int) -> bool:
    """X11 下没有"插入到某窗口之后"的通用做法，直接放弃（安全空操作）。"""
    return False


def getScreenSize() -> tuple[int, int]:
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()  # type: ignore[attr-defined]
            if screen is not None:
                # 用虚拟桌面（所有显示器的并集）而不是主屏，
                # 否则物理边界会把桌宠困在主显示器里，无法拖到其他屏幕
                geometry = screen.virtualGeometry()
                if geometry.width() > 0 and geometry.height() > 0:
                    return (int(geometry.width()), int(geometry.height()))
    except Exception:
        pass

    display = _get_display()
    if display is not None:
        with _lock:
            try:
                screen = display.screen()
                return (
                    int(screen.width_in_pixels),
                    int(screen.height_in_pixels),
                )
            except Exception:
                _reset_display()

    return (1920, 1080)
