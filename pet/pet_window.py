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
        self._pynput_listener = None

        emitter.click_through_changed.connect(self.set_click_through)
        emitter.model_hit_tested.connect(self.handle_model_hit_tested)

        emitter.drag_started.connect(self.handle_global_mouse_press)
        emitter.drag_moved.connect(self.handle_global_mouse_move)
        emitter.drag_ended.connect(
            self.handle_global_mouse_release_without_pos)

        emitter.global_mouse_press.connect(self.handle_global_mouse_press)
        emitter.global_mouse_move.connect(self.handle_global_mouse_move)
        emitter.global_mouse_release.connect(self.handle_global_mouse_release)

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

    def eventFilter(self, watched, event):  # type: ignore
        if isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    pos = event.globalPosition().toPoint()
                    self.handle_global_mouse_press(pos.x(), pos.y())
                    event.accept()
                    return True

            elif event.type() == QEvent.Type.MouseMove:
                if self.window_drag_active:
                    pos = event.globalPosition().toPoint()
                    self.handle_global_mouse_move(pos.x(), pos.y())
                    event.accept()
                    return True

            elif event.type() == QEvent.Type.MouseButtonRelease:
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and self.window_drag_active
                ):
                    pos = event.globalPosition().toPoint()
                    self.handle_global_mouse_release(pos.x(), pos.y())
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

    def _play_drag_anim(self, anim_name: str):
        _send_command_threadsafe(
            {
                "command": "play_anim",
                "anim_name": anim_name,
                "loop": True,
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

        # self._play_drag_anim("CH0069_Formation_Pickup")

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
        # self._play_drag_anim("CH0069_Cafe_Idle")

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

    def _on_global_mouse_move(self, x, y):
        emitter.global_mouse_move.emit(int(x), int(y))

    def cleanup(self):
        if getattr(self, "_cleanup_done", False):
            return

        self._cleanup_done = True

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
