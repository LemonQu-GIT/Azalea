from __future__ import annotations

import sys
import time
import queue
import ctypes
import traceback
from typing import Callable

from PyQt6.QtCore import QEvent, QPoint, QTimer, QUrl, Qt
from PyQt6.QtGui import QColor, QCursor, QMouseEvent
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from pyglet import event
from pynput import mouse as pynput_mouse
from pynput.mouse import Button

from pet.constants import (
    WINDOW_TITLE,
    PET_WIDTH,
    PET_HEIGHT,
    STEP_SECONDS,
)
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
import os

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
ctypes.windll.user32.SetProcessDPIAware()

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


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()

        register_active_window(self)

        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFixedSize(PET_WIDTH, PET_HEIGHT)

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
        self.webView.load(QUrl("http://127.0.0.1:8000"))

        self.screen_width, self.screen_height = pet.windows_utils.getScreenSize()

        self.physics = PetPhysics(self.screen_width, self.screen_height)
        self.tracker = WindowTracker(self.screen_width, self.screen_height)

        self.previous_bottom = 0.0
        self.command_queue: queue.Queue[tuple[str,
                                              dict[str, int]]] = queue.Queue()
        self.ai_follow: dict[str, int | str | float] | None = None

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

    def _move_qt_window_to_body(self):
        gx, gy = self.physics.body.position
        x = round(gx - COLLISION_CENTER_X)
        y = round(gy - COLLISION_CENTER_Y)

        if self.x() != x or self.y() != y:
            self.move(x, y)

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

    def enqueue_ai_command(self, command: str, **kwargs: int):
        self.command_queue.put((command, kwargs))

    def _consume_ai_commands(self):
        while True:
            try:
                command, kwargs = self.command_queue.get_nowait()
            except queue.Empty:
                return

            hwnd = kwargs.get("hwnd")
            if hwnd is None:
                continue

            if command == "climb_window":
                self._start_climbing(hwnd)
            elif command == "jump_on_window":
                self._jump_on_window(hwnd)
            elif command == "jump_into_window":
                self._jump_into_window(hwnd)

    def _start_climbing(self, hwnd: int):
        target = self.tracker.get_window(hwnd)
        if target is None:
            return

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

        self.tracker.ignored_container_hwnd = hwnd
        self.tracker.active_container_hwnd = None
        self.physics.rebuild_bounds(
            (0, 0, self.screen_width, self.screen_height))

    def _jump_on_window(self, hwnd: int):
        target = self.tracker.get_window(hwnd)
        if target is None:
            return

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

    def _jump_into_window(self, hwnd: int):
        target = self.tracker.get_window(hwnd)
        if target is None or not target.can_contain_pet_window():
            return

        self.ai_follow = None
        self.tracker.ignored_container_hwnd = None

        target_x = target.x + target.width / 2
        target_y = target.y + min(
            target.height * 0.45,
            COLLISION_HEIGHT * 0.8,
        )

        self.physics.launch_towards(target_x, target_y, arc_strength=650)

    def _apply_ai_follow(self):
        if self.ai_follow is None:
            return

        hwnd = int(self.ai_follow["hwnd"])
        target = self.tracker.get_window(hwnd)

        if target is None:
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
        """动态设置窗口鼠标穿透 (仅限 Windows)"""
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

        self.ai_follow = None
        self.tracker.reset_to_fullscreen(self.physics)

        self.physics.start_drag(x, y)

        self.window_drag_active = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.grabMouse()

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
        self._play_drag_anim("CH0069_Cafe_Idle")

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
            traceback.print_exc()

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
