from __future__ import annotations

import math
import sys
import time
import queue
import ctypes
import traceback
from typing import Callable

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, QTimer, QUrl, Qt, QRectF
from PyQt6.QtGui import QBrush, QColor, QCursor, QMouseEvent, QPainter, QPen, QFont, QPainterPath, QFontMetrics
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QLabel

from pyglet import event
from pynput import mouse as pynput_mouse
from pynput.mouse import Button

from pet.constants import (
    WINDOW_TITLE,
    PET_WIDTH,
    PET_HEIGHT,
    STEP_SECONDS,
    GRAVITY,
)
import pet.utils
import pet.windows_utils

from pet.signals import emitter
from pet.physics import (
    PetPhysics,
    COLLISION_WIDTH,
    COLLISION_HEIGHT,
    COLLISION_CENTER_X,
    COLLISION_CENTER_Y,
    clamp,
)
from pet.ai import register_active_window
from pet.webview import PetWebView
from pet.window_tracker import WindowTracker
from pet.utils import loadConfig
import os

# os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=3"
# ctypes.windll.user32.SetProcessDPIAware()

_request_hit_test_func: Callable[[int, int], None] | None = None
_send_command_threadsafe_func: Callable[[dict], None] | None = None


def register_request_hit_test(func: Callable[[int, int], None]) -> None:
    global _request_hit_test_func
    _request_hit_test_func = func


def register_send_command_threadsafe(func: Callable[[dict], None]) -> None:
    global _send_command_threadsafe_func
    _send_command_threadsafe_func = func


def _request_hit_test(x: int, y: int) -> None:
    if _request_hit_test_func is not None:
        _request_hit_test_func(x, y)


def _send_command_threadsafe(command_dict: dict) -> None:
    if _send_command_threadsafe_func is not None:
        _send_command_threadsafe_func(command_dict)


class ChatBubble(QWidget):
    PADDING_X = 16
    PADDING_Y = 12
    TAIL_WIDTH = 16
    TAIL_HEIGHT = 10
    MAX_WIDTH = 360
    BORDER_RADIUS = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._message = ""
        self._text_size = QSize(0, 0)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_bubble)

        self._update_font()

    def _update_font(self):
        candidates = [
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "PingFang SC",
            "Source Han Sans CN",
            "SimHei",
            "Segoe UI",
        ]
        chosen = ""
        for name in candidates:
            f = QFont(name)
            if f.exactMatch() or name == "Segoe UI":
                chosen = name
                break
        if not chosen:
            chosen = candidates[-1]
        self._font = QFont(chosen, 10)
        self._font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(self._font)

    def set_message(self, message: str, duration: float = 3.0):
        self._message = message if message else ""
        if not self._message:
            self.hide_bubble()
            return

        self._calc_text_size()
        self._resize_and_update()
        self._cached_bubble_w, self._cached_bubble_h = self._bubble_size()

        if duration > 0:
            self._hide_timer.start(max(1, int(duration * 1000)))
        else:
            self._hide_timer.stop()
        if not self.winId():
            self.winId()
        self.show()
        self.raise_()
        if sys.platform == "win32":
            try:
                HWND_TOPMOST = -1
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                ctypes.windll.user32.SetWindowPos(
                    int(self.winId()),
                    HWND_TOPMOST,
                    0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
            except Exception:
                pass

    def hide_bubble(self):
        self._hide_timer.stop()
        self.hide()
        self._cached_bubble_w = 0
        self._cached_bubble_h = 0

    def update_position(self, pet_window_x: int, pet_window_y: int,
                        pet_window_width: int, pet_window_height: int,
                        pet_collision_top_offset: int = 0):
        if not self._message:
            return
        bw = getattr(self, "_cached_bubble_w", 0)
        bh = getattr(self, "_cached_bubble_h", 0)
        if bw <= 0 or bh <= 0:
            bw, bh = self._bubble_size()
            self._cached_bubble_w, self._cached_bubble_h = bw, bh

        x = pet_window_x + (pet_window_width - bw) // 2
        y = (pet_window_y)
        if y < 2:
            y = pet_window_y + pet_window_height + 6
        self.move(max(2, x), max(2, y))

    def _calc_text_size(self):
        if not self._message:
            self._text_size = QSize(0, 0)
            return
        fm = QFontMetrics(self._font)
        max_text_w = max(20, self.MAX_WIDTH - self.PADDING_X * 2)
        text_rect = fm.boundingRect(
            QRect(0, 0, max_text_w, 100000),
            Qt.TextFlag.TextWordWrap
            | Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop,
            self._message,
        )
        self._text_size = QSize(
            max(10, text_rect.width() + 2),
            max(fm.height(), text_rect.height() + 2),
        )

    def _bubble_size(self) -> tuple[int, int]:
        w = self._text_size.width() + self.PADDING_X * 2
        h = self._text_size.height() + self.PADDING_Y * 2 + self.TAIL_HEIGHT
        return (max(40, w), max(30, h))

    def _resize_and_update(self):
        w, h = self._bubble_size()
        self.resize(w, h)
        self.update()

    def paintEvent(self, event):  # type: ignore
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0 or not self._message:
            return

        bubble_body_h = h - self.TAIL_HEIGHT
        body_rect = QRectF(0, 0, w, bubble_body_h)
        path = QPainterPath()
        path.addRoundedRect(body_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

        tail_cx = w // 2
        tail_top_y = bubble_body_h
        tail_bottom_y = h
        tail_left = tail_cx - self.TAIL_WIDTH // 2
        tail_right = tail_cx + self.TAIL_WIDTH // 2

        tail_path = QPainterPath()
        tail_path.moveTo(tail_left, tail_top_y)
        tail_path.lineTo(tail_cx, tail_bottom_y)
        tail_path.lineTo(tail_right, tail_top_y)
        tail_path.closeSubpath()

        bubble_path = path.united(tail_path)

        bg_color = QColor(255, 255, 255, 242)
        painter.setBrush(QBrush(bg_color))
        border_color = QColor(220, 224, 232, 200)
        painter.setPen(QPen(border_color, 1))
        painter.drawPath(bubble_path)

        painter.setPen(QColor(32, 33, 36, 255))
        painter.setFont(self._font)
        text_rect = QRect(
            self.PADDING_X,
            self.PADDING_Y,
            self._text_size.width(),
            self._text_size.height(),
        )
        painter.drawText(
            text_rect,
            Qt.TextFlag.TextWordWrap
            | Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop,
            self._message,
        )


CHAT_WINDOW_WIDTH = 360
CHAT_WINDOW_HEIGHT = 160


class ChatWindow(QWidget):
    """桌宠对话框窗口：整个窗口用 QWebEngineView 渲染 /chat 页面，没有别的内容。

    特性：
      - 无边框（视觉风格由 chat.html 的圆角卡片提供）
      - 始终置顶
      - 不能被用户拖动
      - 用定时器跟随桌宠位置，始终保持在桌宠左/右侧
      - 用户发完消息或按 ESC 后：前端通过信号 request_close_chat 通知后端 hide()
    """

    def __init__(self, pet_window: "PetWindow"):
        super().__init__()
        self._pet = pet_window
        fconfig = pet.utils.loadConfig()

        # 无边框 + 工具窗 + 始终置顶
        self.setWindowTitle("与桌宠对话")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(CHAT_WINDOW_WIDTH, CHAT_WINDOW_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.webView = QWebEngineView(self)
        # 让 QWebEngineView 的页面也透明，露出 chat.html 的圆角卡片
        page = self.webView.page()
        page.setBackgroundColor(QColor(0, 0, 0, 0))  # type: ignore
        self.webView.setStyleSheet("background: transparent;")
        self.webView.setMouseTracking(True)
        layout.addWidget(self.webView)

        self.webView.load(
            QUrl(
                f"http://{fconfig['petServer']['host']}:{fconfig['petServer']['port']}/chat")
        )

        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(1000 // 60)
        self._follow_timer.timeout.connect(self._refresh_position)

        emitter.request_close_chat.connect(self.hide)

    def event(self, a0: QEvent | None):
        if a0 is None:
            return super().event(a0)
        if a0.type() in (QEvent.Type.WindowBlocked,):
            return super().event(a0)
        return super().event(a0)

    def show(self):  # type: ignore
        # 先定位，再显示，避免瞬间出现在 (0,0)
        self._refresh_position()
        self._follow_timer.start()
        super().show()
        self.raise_()
        self.activateWindow()
        # 让输入框聚焦
        try:
            self.webView.setFocus()
        except Exception:
            pass

    def hide(self):
        try:
            self._follow_timer.stop()
        except Exception:
            pass
        super().hide()

    def closeEvent(self, event):  # type: ignore
        try:
            self._follow_timer.stop()
        except Exception:
            pass
        event.accept()

    # ---- 始终贴桌宠左/右侧 ----
    def _refresh_position(self):
        try:
            pet_rect = self._pet.frameGeometry()
        except Exception:
            return
        screen = self.screen()
        if screen is not None:
            screen_geom = screen.availableGeometry()
        else:
            screen_geom = QRect(0, 0, self._pet.screen_width,
                                self._pet.screen_height)

        space_left = pet_rect.x() - screen_geom.left()
        space_right = screen_geom.right() - (pet_rect.x() + pet_rect.width())

        if space_right >= CHAT_WINDOW_WIDTH or space_right >= space_left:
            x = pet_rect.right() - 50
            if x + CHAT_WINDOW_WIDTH > screen_geom.right():
                x = pet_rect.left() - CHAT_WINDOW_WIDTH + 50
        else:
            x = pet_rect.left() - CHAT_WINDOW_WIDTH + 50
            if x < screen_geom.left():
                x = pet_rect.right() - 50

        # 垂直对齐：对话框顶部和桌宠顶部对齐，不越界
        y = pet_rect.top()+pet_rect.height()//2-CHAT_WINDOW_HEIGHT//2 - 30
        if y + CHAT_WINDOW_HEIGHT > screen_geom.bottom():
            y = screen_geom.bottom() - CHAT_WINDOW_HEIGHT - 4
        if y < screen_geom.top():
            y = screen_geom.top() + 4

        target = QPoint(
            max(screen_geom.left() + 2, int(x)),
            max(screen_geom.top() + 2, int(y)),
        )
        if self.pos() != target:
            self.move(target)


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()

        fconfig = pet.utils.loadConfig()
        register_active_window(self)

        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFixedSize(PET_WIDTH, PET_HEIGHT)

        self._collision_offset = fconfig["window"]["collision_offset"]
        self.chat_bubble = ChatBubble()
        self.chat_window: ChatWindow | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.webView = PetWebView(self)
        self.webView.page().setBackgroundColor(QColor(0, 0, 0, 0))  # type: ignore
        self.webView.setStyleSheet("background: transparent;")
        self.webView.setMouseTracking(True)
        self.webView.installEventFilter(self)

        if self.webView.focusProxy() is not None:
            self.webView.focusProxy().installEventFilter(self)  # type: ignore

        layout.addWidget(self.webView)
        self.webView.load(
            QUrl(f"http://{fconfig['petServer']['host']}:{fconfig['petServer']['port']}"))

        self.screen_width, self.screen_height = pet.windows_utils.getScreenSize()

        self.physics = PetPhysics(self.screen_width, self.screen_height)
        self.tracker = WindowTracker(self.screen_width, self.screen_height)

        self.previous_bottom = 0.0
        self.command_queue: queue.Queue[tuple[str,
                                              dict[str, int]]] = queue.Queue()
        self.ai_follow: dict[str, int | str | float] | None = None

        self._pending_actions: dict[int, dict] = {}
        self._next_action_id: int = 1

        self.click_through_enabled = False
        self.pointer_over_model = False
        self.last_model_hit_at = 0.0
        self.window_drag_active = False
        self._last_left_pressed = False
        self._last_right_pressed = False
        self._right_press_over_model = False
        self._pynput_listener = None

        self._head_pat_active: bool = False
        self._head_pat_anchor_x: int | None = None
        self._head_pat_accum_x: int = 0
        self._head_pat_last_sample_x: int | None = None
        self._HEAD_PAT_THRESHOLD_X: int = 110
        self._HEAD_PAT_COOLDOWN_MS: int = 5000
        self._last_head_pat_at: float = 0.0
        self._HEAD_PAT_MAX_HOLD_MS: int = 6000
        self._head_pat_started_at: float = 0.0

        emitter.click_through_changed.connect(self.set_click_through)
        emitter.model_hit_tested.connect(self.handle_model_hit_tested)

        emitter.drag_started.connect(self.handle_global_mouse_press)
        emitter.drag_moved.connect(self.handle_global_mouse_move)
        emitter.drag_ended.connect(
            self.handle_global_mouse_release_without_pos)

        emitter.global_mouse_press.connect(self.handle_global_mouse_press)
        emitter.global_mouse_move.connect(self.handle_global_mouse_move)
        emitter.global_mouse_release.connect(self.handle_global_mouse_release)

        emitter.model_right_clicked.connect(self.handle_model_right_clicked)
        emitter.request_open_chat.connect(self.open_chat_window)

        # 摸头手势（来源是 pynput 全局右键事件，主线程 queued 到这里）
        emitter.global_right_press.connect(self._handle_global_right_press)
        emitter.global_right_move.connect(self._handle_global_right_move)
        emitter.global_right_release.connect(self._handle_global_right_release)

        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_desktop_windows)
        self.scan_timer.start(1000 // 60)

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self.update_physics)
        self.physics_timer.start(round(STEP_SECONDS * 1000))

        self.click_through_timer = QTimer(self)
        self.click_through_timer.setInterval(30)
        self.click_through_timer.timeout.connect(self.sync_click_through_state)
        self.click_through_timer.start()

        self._start_global_mouse_listener()

    def showEvent(self, event):  # type: ignore
        super().showEvent(event)
        self.tracker.self_hwnd = int(self.winId())
        self.scan_desktop_windows()

    def closeEvent(self, a0):
        self.cleanup()
        super().closeEvent(a0)

    def show_message_bubble(self, message: str, duration: float = 3.0):
        self.enqueue_ai_command(
            "show_message",
            message=str(message),
            duration=float(duration),
        )

    def _show_message_bubble_impl(self, message: str, duration: float):
        try:
            self.chat_bubble.set_message(message, duration=duration)
            self.chat_bubble.update_position(
                pet_window_x=self.x(),
                pet_window_y=self.y(),
                pet_window_width=self.width(),
                pet_window_height=self.height(),
                pet_collision_top_offset=int(self._collision_offset["top"]),
            )
            self.repaint()
            if sys.platform == "win32":
                try:
                    ctypes.windll.user32.RedrawWindow(
                        int(self.winId()),
                        None,
                        None,
                        0x0400 | 0x0001 | 0x0080,  # RDW_FRAME | RDW_INVALIDATE | RDW_UPDATENOW
                    )
                except Exception:
                    pass
        except Exception:
            pet.utils.log(
                traceback.format_exc(),
                "ERROR",
            )

    def scan_desktop_windows(self):
        self.tracker.scan_desktop_windows(int(self.winId()), self.physics)

    def update_physics(self):
        gx, gy = self.physics.body.position
        self.previous_bottom = gy + COLLISION_HEIGHT / 2

        self._consume_ai_commands()
        self._apply_ai_follow()

        self.physics.step(STEP_SECONDS)

        if not self.physics.is_dragging:
            self.tracker.refresh_container_from_position(self.physics)
            self.tracker.handle_window_top_landing(
                self.physics,
                self.previous_bottom,
            )
            self.tracker.follow_active_platform(self.physics)
        elif self.tracker.active_container_hwnd is not None:
            self.tracker.reset_to_fullscreen(self.physics)

        self.physics.clamp_body_inside_bounds()
        self._move_qt_window_to_body()
        self.tracker.update_temporary_topmost()
        self._cleanup_timed_out_actions()

    def _move_qt_window_to_body(self):
        gx, gy = self.physics.body.position
        x = round(gx - COLLISION_CENTER_X)
        y = round(gy - COLLISION_CENTER_Y)

        moved = self.x() != x or self.y() != y
        if moved:
            self.move(x, y)

        if moved:
            try:
                self.chat_bubble.update_position(
                    pet_window_x=x,
                    pet_window_y=y,
                    pet_window_width=self.width(),
                    pet_window_height=self.height(),
                    pet_collision_top_offset=int(
                        self._collision_offset["top"]),
                )
            except Exception:
                pass

    def open_chat_window(self):
        """打开或激活对话框窗口（放在桌宠左/右侧）。
        注意：本函数会创建 QWebEngineView，只允许在 Qt 主线程调用。"""
        try:
            if self.chat_window is None:
                self.chat_window = ChatWindow(self)
            # ChatWindow.show() 内部会：定位 → 启动跟随定时器 → 显示
            self.chat_window.show()
        except Exception:
            pet.utils.log(
                f"[open_chat_window] 异常:\n{traceback.format_exc()}",
                "ERROR",
            )

    def handle_model_right_clicked(self, screen_x: int, screen_y: int):
        """**主线程执行的**右键点击处理器（由信号 queued 到主线程）。
        - eventFilter 本地右键和 pynput 全局右键最终都走这里，统一防抖。
        - 负责：范围判定 → 关闭穿透 → 打开对话框。
        - **注意：当右键被用于摸头手势（达到摸头累计移动阈值）时，本函数不应该再打开对话框，
          靠摸头手势触发时已经调用过 _head_pat_mark_used 来吃掉后续右键点击打开窗口。"""
        if getattr(self, "_head_pat_suppress_click", False):
            self._head_pat_suppress_click = False
            return
        # 防抖 300ms，避免 eventFilter 源 + pynput 源触发两次打开
        now_ts = time.monotonic()
        last_ts = getattr(self, "_last_right_click_open_at", 0.0)
        if now_ts - last_ts < 0.3:
            return
        # 判定：屏幕坐标是否落在桌宠窗口范围内（宽松）
        window_rect = self.frameGeometry()
        pt = QPoint(int(screen_x), int(screen_y))
        in_window = window_rect.contains(pt)
        on_model = self._is_recently_over_model()
        if not (in_window or on_model):
            return
        self._last_right_click_open_at = now_ts
        # 如果窗口正处于穿透状态，先解除——这样后续用户点击对话框标题栏/桌宠时不会漏掉
        if self.click_through_enabled:
            self.set_click_through(False)
        self.open_chat_window()

    def eventFilter(self, watched, event):  # type: ignore
        if isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                pos = event.globalPosition().toPoint()
                if event.button() == Qt.MouseButton.LeftButton:
                    self.handle_global_mouse_press(pos.x(), pos.y())
                    event.accept()
                    return True
                elif event.button() == Qt.MouseButton.RightButton:
                    # 主线程安全的操作可以直接做：记录按下状态便于释放判定
                    self._last_right_pressed = True
                    self._right_press_over_model = self._is_recently_over_model()
                    if self.click_through_enabled:
                        self.set_click_through(False)
                    # 摸头手势：按下开始（只有在模型上的按下才开始）
                    self._head_pat_begin(pos.x())
                    event.accept()
                    return True

            elif event.type() == QEvent.Type.MouseMove:
                pos = event.globalPosition().toPoint()
                if self.window_drag_active:
                    self.handle_global_mouse_move(pos.x(), pos.y())
                    event.accept()
                    return True
                # 摸头手势：按住右键时的水平移动累计
                self._head_pat_update(pos.x())

            elif event.type() == QEvent.Type.MouseButtonRelease:
                pos = event.globalPosition().toPoint()
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and self.window_drag_active
                ):
                    self.handle_global_mouse_release(pos.x(), pos.y())
                    event.accept()
                    return True
                elif event.button() == Qt.MouseButton.RightButton:
                    # 如果这次按住右键过程中触发过摸头，就不要再打开对话框（否则一松开就弹对话框，体验差）
                    triggered_pat = False
                    if self._head_pat_active:
                        cooldown_s = self._HEAD_PAT_COOLDOWN_MS / 1000.0
                        # 触发判断：要么触发时刻就在最近 2*cool 内，要么累计量超过阈值（松开前恰好到）
                        if time.monotonic() - self._last_head_pat_at < cooldown_s * 2:
                            triggered_pat = True
                        elif self._head_pat_accum_x >= self._HEAD_PAT_THRESHOLD_X:
                            triggered_pat = True
                    self._head_pat_reset()

                    # Qt 本地事件的右键释放：通过信号走统一的主线程 handler（含防抖）
                    was_over = self._last_right_pressed and self._right_press_over_model
                    still_over = self._is_recently_over_model()
                    self._last_right_pressed = False
                    self._right_press_over_model = False

                    if triggered_pat:
                        # 吃掉本次右键点击打开对话框的动作（置位，让 handler 里跳过）
                        self._head_pat_suppress_click = True
                    else:
                        self._head_pat_suppress_click = False

                    if was_over or still_over:
                        emitter.model_right_clicked.emit(pos.x(), pos.y())
                    event.accept()
                    return True

            elif event.type() == QEvent.Type.ContextMenu:
                # 阻止系统右键菜单
                event.accept()
                return True

        return super().eventFilter(watched, event)

    def register_action_completion(
        self,
        asyncio_loop,
        asyncio_event,
        timeout_seconds: float,
    ) -> int:
        """给排队中的命令登记一个完成事件，返回 action_id。

        调用方（ai_brain_loop的异步线程）应把这个action_id通过command_queue的kwargs
        以 _action_id=N 形式送入；当对应ai_follow自然完成/被替换/超时时，会通过
        loop.call_soon_threadsafe(event.set) 通知异步线程。
        """
        action_id = self._next_action_id
        self._next_action_id += 1
        self._pending_actions[action_id] = {
            "loop": asyncio_loop,
            "event": asyncio_event,
            "deadline": time.monotonic() + max(0.1, float(timeout_seconds)),
        }
        return action_id

    def _signal_action_completion(self, action_id: int):
        """当某 action 完成（自然结束/取消/覆盖/超时）时唤醒异步等待者。"""
        info = self._pending_actions.pop(int(action_id), None)
        if info is None:
            return
        try:
            loop = info["loop"]
            event = info["event"]
            if loop is not None and event is not None:
                loop.call_soon_threadsafe(event.set)
        except Exception:
            pass

    def _cleanup_timed_out_actions(self):
        """每帧检查：超过deadline的pending action直接超时回调。"""
        now = time.monotonic()
        expired = [
            aid for aid, info in self._pending_actions.items()
            if info.get("deadline", 0.0) < now
        ]
        for aid in expired:
            self._signal_action_completion(aid)

    def _signal_current_ai_follow_completion(self):
        """若当前ai_follow里带了_action_id，则触发其完成事件并从ai_follow中剥离。"""
        if self.ai_follow is None:
            return
        aid = self.ai_follow.get("_action_id")
        if aid is None:
            return
        self.ai_follow["_action_id"] = None  # type:ignore
        self._signal_action_completion(int(aid))

    def enqueue_ai_command(self, command: str, **kwargs):
        self.command_queue.put((command, kwargs))

    def _consume_ai_commands(self):
        while True:
            try:
                command, kwargs = self.command_queue.get_nowait()
            except queue.Empty:
                return

            action_id = kwargs.pop("_action_id", None)

            if command == "jump":
                height = int(kwargs.get("height", 95))
                times = int(kwargs.get("times", 1))
                self._jump(height, times, action_id=action_id)
                continue
            elif command == "walk":
                distance = int(kwargs.get("distance", 0))
                if distance != 0:
                    self._walk(distance, action_id=action_id)
                else:
                    if action_id is not None:
                        self._signal_action_completion(int(action_id))
                continue
            elif command == "walk_to":
                target_x = int(kwargs.get("x", -1))
                if target_x >= 0:
                    self._walk_to(target_x, action_id=action_id)
                else:
                    if action_id is not None:
                        self._signal_action_completion(int(action_id))
                continue
            elif command == "show_message":
                message = str(kwargs.get("message", ""))
                duration = float(kwargs.get("duration", 3.0))
                self._show_message_bubble_impl(message, duration)
                if action_id is not None:
                    self._signal_action_completion(int(action_id))
                continue

            hwnd = kwargs.get("hwnd")
            if hwnd is None:
                if action_id is not None:
                    self._signal_action_completion(int(action_id))
                continue

            if command == "climb_window":
                self._start_climbing(int(hwnd), action_id=action_id)
            elif command == "jump_on_window":
                self._jump_on_window(int(hwnd), action_id=action_id)
            elif command == "jump_into_window":
                self._jump_into_window(int(hwnd), action_id=action_id)
            else:
                # 未知命令，避免action_id永久悬挂
                if action_id is not None:
                    self._signal_action_completion(int(action_id))

    def _start_climbing(self, hwnd: int, action_id: int | None = None):
        target = self.tracker.get_window(hwnd)
        if target is None:
            if action_id is not None:
                self._signal_action_completion(int(action_id))
            return

        self._signal_current_ai_follow_completion()

        gx, gy = self.physics.body.position

        left_distance = abs(gx - target.x)
        right_distance = abs(gx - target.right)

        left_has_space = target.x >= COLLISION_WIDTH
        right_has_space = self.screen_width - target.right >= COLLISION_WIDTH

        if left_has_space and not right_has_space:
            side = "left"
        elif right_has_space and not left_has_space:
            side = "right"
        else:
            side = "left" if left_distance <= right_distance else "right"

        offset_y = clamp(
            gy - target.y,
            COLLISION_HEIGHT / 2,
            target.height - COLLISION_HEIGHT / 2,
        )

        self.ai_follow = {
            "mode": "climb",
            "hwnd": hwnd,
            "side": side,
            "offset_y": offset_y,
        }
        if action_id is not None:
            self.ai_follow["_action_id"] = int(action_id)

        self.tracker.ignored_container_hwnd = hwnd
        self.tracker.active_container_hwnd = None
        self.physics.rebuild_bounds(
            (0, 0, self.screen_width, self.screen_height))

    def _jump(self, height: int, times: int, action_id: int | None = None):
        height = max(1, int(height))
        times = max(1, int(times)) + 1

        if (
            self.ai_follow is not None
            and self.ai_follow.get("mode") == "jump"
        ):
            self._signal_current_ai_follow_completion()
            self.ai_follow["remaining"] = int(
                self.ai_follow.get("remaining", 0)) + times
            if action_id is not None:
                self.ai_follow["_action_id"] = int(action_id)
            return

        self._signal_current_ai_follow_completion()

        v_up = -(2.0 * GRAVITY * float(height)) ** 0.5 * 1.08
        self.tracker.activate_temporary_topmost()
        vx, vy = self.physics.body.velocity
        _, gy = self.physics.body.position
        _, top, _, bottom = self.physics.bounds
        floor_y = bottom - COLLISION_HEIGHT / 2
        near_floor = abs(gy - floor_y) < 8.0 and vy >= -20.0

        if near_floor:
            self.physics.body.velocity = (vx, v_up)
            self.physics.body.activate()
            remaining = times - 1
        else:
            remaining = times

        if remaining > 0 or not near_floor:
            self.ai_follow = {
                "mode": "jump",
                "v_up": v_up,
                "remaining": remaining,
                "in_air": not near_floor,
            }
            if action_id is not None:
                self.ai_follow["_action_id"] = int(action_id)
        elif action_id is not None:
            self._signal_action_completion(int(action_id))

    def _walk(self, distance: int, action_id: int | None = None):
        distance = int(distance)
        if distance == 0:
            if action_id is not None:
                self._signal_action_completion(int(action_id))
            return
        walk_speed_mag = 260.0
        if (
            self.ai_follow is not None
            and self.ai_follow.get("mode") == "walk"
        ):
            self._signal_current_ai_follow_completion()
            current_remaining = float(self.ai_follow.get("remaining", 0.0))
            new_remaining = current_remaining + float(distance)
            if abs(new_remaining) < 1.0:
                self.ai_follow = None
                if action_id is not None:
                    self._signal_action_completion(int(action_id))
            else:
                self.ai_follow["remaining"] = new_remaining
                self.ai_follow["speed"] = (
                    walk_speed_mag if new_remaining > 0 else -walk_speed_mag
                )
                if action_id is not None:
                    self.ai_follow["_action_id"] = int(action_id)
            return

        self._signal_current_ai_follow_completion()

        self.tracker.activate_temporary_topmost()

        self.ai_follow = {
            "mode": "walk",
            "remaining": float(distance),
            "speed": walk_speed_mag if distance > 0 else -walk_speed_mag,
        }
        if action_id is not None:
            self.ai_follow["_action_id"] = int(action_id)

    def _walk_to(self, target_x: int, action_id: int | None = None):
        target_x = int(target_x)

        left, top, right, bottom = self.physics.bounds
        min_x = int(left + COLLISION_WIDTH / 2)
        max_x = int(right - COLLISION_WIDTH / 2)
        target_x_clamped = max(min_x, min(max_x, target_x))

        gx, _ = self.physics.body.position
        current_x = int(gx)
        distance = target_x_clamped - current_x

        # 覆盖任何正在进行的其他ai_follow
        self._signal_current_ai_follow_completion()

        if abs(distance) < 2:
            # 已经在目标位置
            if action_id is not None:
                self._signal_action_completion(int(action_id))
            return

        walk_speed_mag = 260.0
        if (
            self.ai_follow is not None
            and self.ai_follow.get("mode") in ("walk", "walk_to")
        ):
            self.ai_follow = None
        self.tracker.activate_temporary_topmost()

        self.ai_follow = {
            "mode": "walk_to",
            "target_x": float(target_x_clamped),
            "distance": float(distance),
            "speed": walk_speed_mag if distance > 0 else -walk_speed_mag,
        }
        if action_id is not None:
            self.ai_follow["_action_id"] = int(action_id)

    def _jump_on_window(self, hwnd: int, action_id: int | None = None):
        target = self.tracker.get_window(hwnd)
        if target is None:
            if action_id is not None:
                self._signal_action_completion(int(action_id))
            return

        # 覆盖其他ai_follow模式（带action_id的先signal）
        self._signal_current_ai_follow_completion()

        self.ai_follow = None
        self.tracker.active_container_hwnd = None
        self.tracker.ignored_container_hwnd = hwnd
        self.physics.rebuild_bounds(
            (0, 0, self.screen_width, self.screen_height))

        target_x = clamp(
            target.x + target.width / 2,
            COLLISION_WIDTH / 2,
            self.screen_width - COLLISION_WIDTH / 2,
        )
        target_y = max(
            COLLISION_HEIGHT / 2,
            target.y - COLLISION_HEIGHT / 2 - 4,
        )

        self.physics.launch_towards(target_x, target_y, arc_strength=900)

        # 新增 ai_follow jump_on 模式：等待落到目标窗口顶部
        self.ai_follow = {
            "mode": "jump_on",
            "hwnd": hwnd,
            "target_x": float(target_x),
            "target_y": float(target_y),
            "start_time": time.monotonic(),
        }
        if action_id is not None:
            self.ai_follow["_action_id"] = int(action_id)

    def _jump_into_window(self, hwnd: int, action_id: int | None = None):
        target = self.tracker.get_window(hwnd)
        if target is None or not target.can_contain_pet_window():
            if action_id is not None:
                self._signal_action_completion(int(action_id))
            return

        # 覆盖其他ai_follow模式（带action_id的先signal）
        self._signal_current_ai_follow_completion()

        self.ai_follow = None
        self.tracker.active_container_hwnd = None
        self.tracker.active_platform_hwnd = None
        self.tracker.ignored_container_hwnd = hwnd
        self.tracker.suppress_auto_container(2.5)
        self.physics.rebuild_bounds(
            (0, 0, self.screen_width, self.screen_height))
        self.tracker.sync_z_order_to_container(hwnd)
        self.tracker.activate_temporary_topmost()

        target_x = target.x + target.width / 2
        target_y = target.y + min(
            target.height * 0.45,
            COLLISION_HEIGHT * 0.8,
        )

        self.physics.launch_towards(target_x, target_y, arc_strength=650)
        self.ai_follow = {
            "mode": "enter",
            "hwnd": hwnd,
        }
        if action_id is not None:
            self.ai_follow["_action_id"] = int(action_id)

    def _apply_ai_follow(self):
        if self.ai_follow is None:
            return

        mode = self.ai_follow.get("mode")

        # ----- jump 模式：不需要 hwnd，先单独处理 -----
        if mode == "jump":
            v_up = float(self.ai_follow.get("v_up", 0.0))
            remaining = int(self.ai_follow.get("remaining", 0))
            in_air = bool(self.ai_follow.get("in_air", False))

            if remaining <= 0:
                # 已无剩余跳跃，退出
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

            _, gy = self.physics.body.position
            vx, vy = self.physics.body.velocity
            _, top, _, bottom = self.physics.bounds
            floor_y = bottom - COLLISION_HEIGHT / 2

            # 判断是否已落地（贴近底部且垂直速度下降或微小向上，并且没有继续上升）
            touching_ground = abs(gy - floor_y) < 4.0
            # 刚落地的标志：上一帧在空中，这一帧贴近地面，且 vy 不是大的向上速度
            just_landed = in_air and touching_ground and vy >= -15.0
            # 始终在地面：初始就在地面的边缘情况（remaining 还在但 near_floor 判断过）
            standing = not in_air and touching_ground

            if just_landed or standing:
                # 执行下一次跳跃
                self.physics.body.velocity = (vx, v_up)
                self.physics.body.activate()
                self.tracker.activate_temporary_topmost()
                remaining -= 1
                self.ai_follow["remaining"] = remaining
                self.ai_follow["in_air"] = True  # 现在已腾空
                if remaining <= 0:
                    self._signal_current_ai_follow_completion()
                    self.ai_follow = None
                    return
                return

            # 在空中：更新 in_air 状态
            if touching_ground and vy >= -15.0:
                self.ai_follow["in_air"] = False
            elif vy < -5.0 or not touching_ground:
                self.ai_follow["in_air"] = True
            return

        # ----- walk 模式：不需要 hwnd -----
        if mode == "walk":
            remaining = float(self.ai_follow.get("remaining", 0.0))
            speed = float(self.ai_follow.get("speed", 0.0))

            if abs(remaining) < 0.5 or abs(speed) < 1.0:
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

            # 计算本帧应移动的距离
            step = speed * STEP_SECONDS

            # 剩余距离不足一步：只走剩余的量，然后停下
            if abs(step) > abs(remaining):
                step = remaining
                speed_dir = 1.0 if remaining > 0 else -1.0
                # 到达终点：把速度置为一个较短的步进值，避免冲过头
                overshoot_fix = remaining / max(STEP_SECONDS, 1e-6)
                vx_cur, vy_cur = self.physics.body.velocity
                self.physics.body.velocity = (overshoot_fix, vy_cur)
                self.physics.body.activate()

                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

            # 正常推进：直接设置水平速度（保持原有竖直速度，让重力/地面碰撞正常）
            vx_cur, vy_cur = self.physics.body.velocity
            self.physics.body.velocity = (speed, vy_cur)
            self.physics.body.activate()

            remaining -= step
            self.ai_follow["remaining"] = remaining

            # 偶尔激活临时置顶，保持在前面
            if abs(remaining) % 80 < abs(step) * 1.1:
                self.tracker.activate_temporary_topmost()

            if abs(remaining) < 0.5:
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
            return

        # ----- walk_to 模式：不需要 hwnd -----
        if mode == "walk_to":
            target_x = float(self.ai_follow.get("target_x", 0.0))
            speed_mag = abs(float(self.ai_follow.get("speed", 260.0)))

            # 动态重算目标的可达范围（bounds 可能在容器切换中变化）
            left, top, right, bottom = self.physics.bounds
            min_x = left + COLLISION_WIDTH / 2
            max_x = right - COLLISION_WIDTH / 2
            effective_target = max(min_x, min(max_x, target_x))

            gx, _ = self.physics.body.position
            diff = effective_target - gx

            if abs(diff) < 1.0:
                # 已到达目标
                vx_cur, vy_cur = self.physics.body.velocity
                self.physics.body.velocity = (0.0, vy_cur)
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

            # 距离小于一步时，精确停下不冲过
            max_step = speed_mag * STEP_SECONDS
            if abs(diff) <= max_step:
                step = diff
                vx_fix = step / max(STEP_SECONDS, 1e-6)
                vx_cur, vy_cur = self.physics.body.velocity
                self.physics.body.velocity = (vx_fix, vy_cur)
                self.physics.body.activate()
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

            # 正常推进：按 diff 符号设置速度
            desired_speed = speed_mag if diff > 0 else -speed_mag
            vx_cur, vy_cur = self.physics.body.velocity
            self.physics.body.velocity = (desired_speed, vy_cur)
            self.physics.body.activate()

            # 偶尔激活临时置顶
            if abs(diff) % 80 < max_step * 1.1:
                self.tracker.activate_temporary_topmost()
            return

        # ----- jump_on 模式：跳到窗口顶部的落地追踪（不需要 hwnd 键，已提前读入） -----
        if mode == "jump_on":
            hwnd = int(self.ai_follow.get("hwnd", 0))
            start_time = float(self.ai_follow.get("start_time", 0.0))
            target = self.tracker.get_window(hwnd)
            if target is None:
                # 目标窗口消失 → 认为完成
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

            gx, gy = self.physics.body.position
            vx, vy = self.physics.body.velocity
            speed_sq = vx * vx + vy * vy
            _, _, _, bottom = self.physics.bounds
            floor_y = bottom - COLLISION_HEIGHT / 2

            # 判定已"落到窗口顶部"：要么tracker已经把active_platform设置为目标hwnd，
            # 要么桌宠垂直位置已经在窗口顶部附近且速度很小（落地）
            tracker_landed = (
                self.tracker.active_platform_hwnd == hwnd
                or self.tracker.active_container_hwnd == hwnd
            )

            on_platform = abs(gy - (target.y - COLLISION_HEIGHT / 2)) < 8.0
            low_speed = speed_sq < 220.0 * 220.0   # 落地后速度通常很小
            touched_floor = abs(gy - floor_y) < 4.0  # 没跳到平台上，掉地上了

            landed = tracker_landed or (
                on_platform and low_speed) or touched_floor
            timeout = time.monotonic() - start_time > 4.0

            if landed or timeout:
                self.tracker.ignored_container_hwnd = None
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return
            return

        # ----- 其余模式（climb / enter）需要 hwnd -----
        hwnd = int(self.ai_follow["hwnd"])
        target = self.tracker.get_window(hwnd)

        if target is None:
            self._signal_current_ai_follow_completion()
            self.ai_follow = None
            return

        if self.ai_follow.get("mode") == "climb":
            side = str(self.ai_follow["side"])
            offset_y = float(self.ai_follow["offset_y"])

            target_x = (
                target.x - COLLISION_WIDTH / 2
                if side == "left"
                else target.right + COLLISION_WIDTH / 2
            )
            target_y = target.y + clamp(
                offset_y,
                COLLISION_HEIGHT / 2,
                target.height - COLLISION_HEIGHT / 2,
            )

            target_x = clamp(
                target_x,
                COLLISION_WIDTH / 2,
                self.screen_width - COLLISION_WIDTH / 2,
            )
            target_y = clamp(
                target_y,
                COLLISION_HEIGHT / 2,
                self.screen_height - COLLISION_HEIGHT / 2,
            )

            gx, gy = self.physics.body.position
            dx = target_x - gx
            dy = target_y - gy

            if abs(dx) < 2 and abs(dy) < 2:
                self.physics.body.position = (target_x, target_y)
                self.physics.body.velocity = (0, 0)
            else:
                self.physics.body.velocity = (
                    clamp(dx * 12, -1800, 1800),
                    clamp(dy * 12, -1800, 1800),
                )

            self.tracker.sync_z_order_to_container(hwnd)

            # climb模式是吸附式移动；速度设置后每帧追。这里没有显式"到达"判定，
            # 所以加一个到达后稳定0.1秒作为climb完成：
            if abs(dx) < 3 and abs(dy) < 3:
                if "stuck_since" not in self.ai_follow:
                    self.ai_follow["stuck_since"] = time.monotonic()
                elif time.monotonic() - float(self.ai_follow["stuck_since"]) > 0.12:
                    self.tracker.ignored_container_hwnd = None
                    self._signal_current_ai_follow_completion()
                    self.ai_follow = None
                    return
            else:
                self.ai_follow.pop("stuck_since", None)

            # climb 超时保护（防止窗口关闭但target依然存在异常）
            if "start_time" not in self.ai_follow:
                self.ai_follow["start_time"] = time.monotonic()
            elif time.monotonic() - float(self.ai_follow["start_time"]) > 8.0:
                self.tracker.ignored_container_hwnd = None
                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

        elif self.ai_follow.get("mode") == "enter":
            gx, gy = self.physics.body.position
            vx, vy = self.physics.body.velocity
            speed = (vx * vx + vy * vy) ** 0.5
            self.tracker.sync_z_order_to_container(hwnd)
            margin = 4
            inside_window = (
                target.x + margin <= gx <= target.right - margin
                and target.y + margin <= gy <= target.bottom - margin
            )
            near_target = (
                abs(gx - (target.x + target.width / 2)) < COLLISION_WIDTH
                and abs(gy - (target.y + min(
                    target.height * 0.45, COLLISION_HEIGHT * 0.8))) < COLLISION_HEIGHT
            )
            can_attach = False
            if inside_window:
                if speed < 180 or near_target:
                    can_attach = True
                else:
                    if "inside_since" not in self.ai_follow:
                        self.ai_follow["inside_since"] = time.monotonic()

                    elif time.monotonic() - float(self.ai_follow["inside_since"]) > 0.15:
                        can_attach = True
            else:
                self.ai_follow.pop("inside_since", None)

            if can_attach:
                self.tracker.ignored_container_hwnd = None
                self.tracker.suppress_auto_container(0)
                self.tracker.active_container_hwnd = hwnd
                self.tracker.active_platform_hwnd = None
                self.physics.rebuild_bounds(
                    (target.x, target.y, target.right, target.bottom))

                self.physics.clamp_body_inside_bounds()

                self.tracker.sync_z_order_to_container(hwnd)
                self.tracker.activate_temporary_topmost()

                self._signal_current_ai_follow_completion()
                self.ai_follow = None
                return

            if "start_time" not in self.ai_follow:
                self.ai_follow["start_time"] = time.monotonic()
            elif time.monotonic() - float(self.ai_follow["start_time"]) > 2.5:
                self.tracker.ignored_container_hwnd = None
                self.tracker.suppress_auto_container(0)
                self._signal_current_ai_follow_completion()
                self.ai_follow = None

    def handle_model_hit_tested(self, hovering_model: bool, x: int, y: int):
        cursor_pos = QCursor.pos()
        local_pos = cursor_pos - self.frameGeometry().topLeft()

        if abs(local_pos.x() - x) > 16 or abs(local_pos.y() - y) > 16:
            return

        self.pointer_over_model = hovering_model
        self.last_model_hit_at = time.monotonic()

        if not self.window_drag_active:
            self.set_click_through(not hovering_model)

    def _is_recently_over_model(self) -> bool:
        return (
            self.pointer_over_model
            and time.monotonic() - self.last_model_hit_at < 0.25
        )

    # ==================================================================
    # 摸头手势检测
    # 触发条件：
    #   1. 鼠标右键按下时指针在模型命中区域（_is_recently_over_model 真）
    #   2. 按住不松的同时，指针在水平方向上左右来回累计移动绝对值
    #      >= _HEAD_PAT_THRESHOLD_X（约摸一次头的左右幅度）
    #   3. 两次触发间隔 >= _HEAD_PAT_COOLDOWN_MS 冷却时间
    #   4. 按住的总时长不超过 _HEAD_PAT_MAX_HOLD_MS（超过则重置手势）
    # 触发后 emit emitter.pet_head_patted()，随后由 server.py 转成
    # head_pat_queue 事件，再由 ai_brain_core 拼 assembled_content。
    # 摸头期间：把鼠标样式设置为"手"形，松开/超时/重置时恢复正常。
    # ==================================================================
    def _head_pat_begin(self, screen_x: int):
        if self._head_pat_active:
            return
        if not self._is_recently_over_model():
            return
        now = time.monotonic()
        # 先把冷却的判断去掉：这里是"开始"，冷却只在"触发了一次摸头"之后判断
        self._head_pat_active = True
        self._head_pat_anchor_x = int(screen_x)
        self._head_pat_last_sample_x = int(screen_x)
        self._head_pat_accum_x = 0
        self._head_pat_started_at = now
        # —— 设置鼠标样式：摸头时变成"手"形（PointerHand，指的是点击/拖拽那种手指张开指向前的手）
        # 使用 QApplication.setOverrideCursor，保证在本进程所有窗口（主要是桌宠窗口）生效
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.setOverrideCursor(
                QCursor(Qt.CursorShape.PointingHandCursor))
        except Exception:
            pass

    def _head_pat_update(self, screen_x: int):
        if not self._head_pat_active:
            return
        x = int(screen_x)
        last = self._head_pat_last_sample_x
        if last is None:
            self._head_pat_last_sample_x = x
            return
        dx = abs(x - last)
        self._head_pat_accum_x += dx
        self._head_pat_last_sample_x = x
        now = time.monotonic()

        # 按住太久也不让它一直触发：重置手势
        hold_ms = (now - self._head_pat_started_at) * 1000.0
        if hold_ms > self._HEAD_PAT_MAX_HOLD_MS:
            self._head_pat_reset()
            return

        if self._head_pat_accum_x >= self._HEAD_PAT_THRESHOLD_X:
            cooldown_s = self._HEAD_PAT_COOLDOWN_MS / 1000.0
            if now - self._last_head_pat_at >= cooldown_s:
                self._last_head_pat_at = now
                emitter.pet_head_patted.emit()
            self._head_pat_accum_x = 0
            self._head_pat_last_sample_x = x

    def _head_pat_reset(self):
        was_active = bool(self._head_pat_active)
        self._head_pat_active = False
        self._head_pat_anchor_x = None
        self._head_pat_last_sample_x = None
        self._head_pat_accum_x = 0
        self._head_pat_started_at = 0.0
        if was_active:
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

    def _handle_global_right_press(self, x: int, y: int):
        try:
            self._head_pat_begin(int(x))
        except Exception:
            pass

    def _handle_global_right_move(self, x: int, y: int):
        try:
            self._head_pat_update(int(x))
        except Exception:
            pass

    def _handle_global_right_release(self, x: int, y: int):
        triggered_pat = False
        try:
            if self._head_pat_active:
                cooldown_s = self._HEAD_PAT_COOLDOWN_MS / 1000.0
                if (time.monotonic() - self._last_head_pat_at
                        < cooldown_s * 2) or self._head_pat_accum_x >= self._HEAD_PAT_THRESHOLD_X:
                    triggered_pat = True
                self._head_pat_reset()
            if triggered_pat:
                self._head_pat_suppress_click = True
            else:
                pass
        except Exception:
            pass

    def sync_click_through_state(self):
        if sys.platform != "win32":
            return

        if self.window_drag_active:
            if self.click_through_enabled:
                self.set_click_through(False)
            return

        cursor_pos = QCursor.pos()
        inside_window = self.frameGeometry().contains(cursor_pos)

        if not inside_window:
            self.pointer_over_model = False
            if not self.click_through_enabled:
                self.set_click_through(True)
            return

        local_pos = cursor_pos - self.frameGeometry().topLeft()
        _request_hit_test(local_pos.x(), local_pos.y())

    def set_click_through(self, enabled: bool):
        if sys.platform != "win32":
            return

        if enabled == self.click_through_enabled:
            return

        self.click_through_enabled = enabled
        hwnd = int(self.winId())

        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x80000
        WS_EX_TRANSPARENT = 0x20

        current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        if enabled:
            new_style = current_style | WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            new_style = (current_style | WS_EX_LAYERED) & ~WS_EX_TRANSPARENT

        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)

    def play_end_drag_anim(self):
        _send_command_threadsafe(
            {
                "command": "set_transform",
                "position": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 90, "z": 0},
                "rotation_units": "degrees",
                "rotation_orientation": "global"
            }
        )
        _send_command_threadsafe(
            {
                "command": "play_anim",
                "anim_name": "CH0069_Cafe_Idle",
                "loop": True,
                "fade_duration": 0
            }
        )

    def play_drag_anim(self):
        _send_command_threadsafe(
            {
                "command": "play_anim",
                "anim_name": "CH0069_Formation_Pickup",
                "loop": True,
                "fade_duration": 0
            }
        )
        _send_command_threadsafe(
            {
                "command": "set_transform",
                "position": {
                    "x": 0.5, "y": 0.1, "z": -0.5
                },
                "rotation": {
                    "x": -62.980, "y": 64.900, "z": 77.045
                },
                "rotation_units": "degrees",
            }
        )

    def _start_physics_drag(self, x: int, y: int):
        if self.window_drag_active:
            return

        if self.click_through_enabled:
            self.set_click_through(False)

        self._signal_current_ai_follow_completion()
        self.ai_follow = None
        self.tracker.reset_to_fullscreen(self.physics)

        self.physics.start_drag(x, y)

        self.window_drag_active = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.grabMouse()
        self.tracker.set_drag_topmost(True)

        self.play_drag_anim()

    def _move_physics_drag(self, x: int, y: int):
        if not self.window_drag_active or not self.physics.is_dragging:
            return

        if self.click_through_enabled:
            self.set_click_through(False)

        self.physics.move_drag(x, y)

    def _end_physics_drag(self, x: int | None = None, y: int | None = None):
        if not self.window_drag_active:
            return

        self.physics.end_drag(x, y)

        try:
            self.releaseMouse()
        except Exception:
            pass

        self.window_drag_active = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.tracker.set_drag_topmost(False)
        self.play_end_drag_anim()

    def handle_global_mouse_press(self, x, y):
        window_rect = self.frameGeometry()
        if not window_rect.contains(QPoint(x, y)):
            return

        if not self._is_recently_over_model():
            return

        self._last_left_pressed = True
        self._start_physics_drag(x, y)

    def handle_global_mouse_move(self, x, y):
        self._move_physics_drag(x, y)

    def handle_global_mouse_release(self, x, y):
        self._last_left_pressed = False
        self._end_physics_drag(x, y)

    def handle_global_mouse_release_without_pos(self):
        self._last_left_pressed = False
        self._end_physics_drag()

    def _start_global_mouse_listener(self):
        try:
            self._pynput_listener = pynput_mouse.Listener(
                on_click=self._on_global_mouse_click,
                on_move=self._on_global_mouse_move,
            )
            self._pynput_listener.start()
        except Exception:
            pet.utils.log(
                f"Failed to start global mouse listener. {traceback.format_exc()}", "ERROR")

    def _on_global_mouse_click(self, x, y, button, pressed):
        if button == Button.left:
            if pressed:
                emitter.global_mouse_press.emit(int(x), int(y))
            else:
                emitter.global_mouse_release.emit(int(x), int(y))
        elif button == Button.right:
            # ⚠️ pynput 回调运行在独立线程，绝对不能调用 self.frameGeometry /
            # self.set_click_through / self.open_chat_window / QWebEngineView 等
            # 任何 Qt GUI/WebEngine 对象的方法。只能 emit 信号，由主线程 handler 处理。
            if pressed:
                # 全局右键按下：信号给主线程用于摸头手势 begin
                try:
                    emitter.global_right_press.emit(int(x), int(y))
                except Exception:
                    pass
            else:
                # 全局右键释放：摸头手势 reset；同时保留 model_right_clicked 给打开对话框
                try:
                    emitter.global_right_release.emit(int(x), int(y))
                except Exception:
                    pass
                emitter.model_right_clicked.emit(int(x), int(y))

    def _on_global_mouse_move(self, x, y):
        emitter.global_mouse_move.emit(int(x), int(y))
        # 全局鼠标移动：若正在摸头手势状态中，也触发 update（穿透态下 Qt 自己拿不到 move）
        try:
            emitter.global_right_move.emit(int(x), int(y))
        except Exception:
            pass

    def cleanup(self):
        if getattr(self, "_cleanup_done", False):
            return

        self._cleanup_done = True

        # 兜底：如果清理时还处于摸头态，强制重置（也会恢复鼠标样式）
        try:
            if getattr(self, "_head_pat_active", False):
                self._head_pat_reset()
        except Exception:
            pass
        # 再兜底一次：摸头 reset 失败了就手动清掉 override cursor，确保不会卡手形
        try:
            from PyQt6.QtWidgets import QApplication
            # 把所有 override cursor 清空到默认（最多清 16 层防嵌套残余）
            for _ in range(16):
                if QApplication.overrideCursor() is None:
                    break
                QApplication.restoreOverrideCursor()
        except Exception:
            pass

        # 清理对话框窗口
        try:
            if self.chat_window is not None:
                self.chat_window.hide()
                self.chat_window.close()
                self.chat_window = None
        except Exception:
            pass

        # 清理对话气泡窗口
        try:
            self.chat_bubble.hide_bubble()
            self.chat_bubble.close()
        except Exception:
            pass

        if self._pynput_listener is not None:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
            self._pynput_listener = None

        try:
            self.tracker.cleanup_topmost()
        except Exception:
            pass

        try:
            if self.click_through_enabled:
                self.set_click_through(False)
        except Exception:
            pass

        try:
            self.webView.hide()
            self.webView.page().setUrl(QUrl("about:blank"))  # type:ignore
        except Exception:
            pass
