from __future__ import annotations

import time
import traceback
from dataclasses import dataclass

import win32con
import win32gui
import ctypes

from pet.constants import WINDOW_TITLE
import pet.windows_utils
from pet.physics import PetPhysics, COLLISION_WIDTH, COLLISION_HEIGHT


ctypes.windll.user32.SetProcessDPIAware()


@dataclass
class DesktopWindow:
    title: str
    hwnd: int
    x: int
    y: int
    width: int
    height: int
    z_index: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains_point(self, x: float, y: float) -> bool:
        return self.x <= x <= self.right and self.y <= y <= self.bottom

    def can_contain_pet_window(self) -> bool:
        return (
            self.width > COLLISION_WIDTH + 8
            and self.height > COLLISION_HEIGHT + 8
        )


class WindowTracker:
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.self_hwnd: int | None = None

        self.desktop_windows: list[DesktopWindow] = []
        self.windows_by_hwnd: dict[int, DesktopWindow] = {}

        self.active_container_hwnd: int | None = None
        self.active_platform_hwnd: int | None = None
        self.ignored_container_hwnd: int | None = None

        self.temporary_topmost_until = 0.0
        self.is_temporarily_topmost = False

    def get_window(self, hwnd: int | None) -> DesktopWindow | None:
        if hwnd is None:
            return None
        return self.windows_by_hwnd.get(hwnd)

    def scan_desktop_windows(
        self,
        self_hwnd: int | None,
        physics: PetPhysics | None = None,
    ) -> None:
        self.self_hwnd = self_hwnd
        rects = pet.windows_utils.getAllWindowsRects()
        windows: list[DesktopWindow] = []

        for z_index, (title, hwnd, x, y, width, height) in enumerate(rects):
            if self_hwnd is not None and hwnd == self_hwnd:
                continue
            if WINDOW_TITLE in title:
                continue
            if width <= 0 or height <= 0:
                continue

            windows.append(
                DesktopWindow(
                    title,
                    hwnd,
                    x,
                    y,
                    width,
                    height,
                    z_index,
                )
            )

        self.desktop_windows = windows
        self.windows_by_hwnd = {window.hwnd: window for window in windows}

        if physics is not None:
            self.refresh_container_from_position(physics)

    def refresh_container_from_position(self, physics: PetPhysics) -> None:
        if physics.is_dragging:
            return

        x, y = physics.body.position
        container = None

        if self.active_container_hwnd is not None:
            active_window = self.windows_by_hwnd.get(
                self.active_container_hwnd)
            if (
                active_window is not None
                and active_window.can_contain_pet_window()
                and active_window.hwnd != self.ignored_container_hwnd
            ):
                container = active_window

        if container is None:
            containing_windows = [
                window
                for window in self.desktop_windows
                if (
                    window.can_contain_pet_window()
                    and window.hwnd != self.ignored_container_hwnd
                    and window.contains_point(x, y)
                )
            ]
            container = containing_windows[0] if containing_windows else None

        new_hwnd = container.hwnd if container else None

        if new_hwnd != self.active_container_hwnd:
            self.active_container_hwnd = new_hwnd
            self.active_platform_hwnd = None

            if container is None:
                physics.rebuild_bounds(
                    (0, 0, self.screen_width, self.screen_height)
                )
            else:
                physics.rebuild_bounds(
                    (
                        container.x,
                        container.y,
                        container.right,
                        container.bottom,
                    )
                )
                self.sync_z_order_to_container(container.hwnd)

        elif container is not None:
            new_bounds = (
                container.x,
                container.y,
                container.right,
                container.bottom,
            )
            old_left, old_top, old_right, old_bottom = physics.bounds

            if (
                abs(new_bounds[0] - old_left) > 1
                or abs(new_bounds[1] - old_top) > 1
                or abs(new_bounds[2] - old_right) > 1
                or abs(new_bounds[3] - old_bottom) > 1
            ):
                dx = new_bounds[0] - old_left
                dy = new_bounds[1] - old_top
                physics.body.position = (
                    physics.body.position.x + dx,
                    physics.body.position.y + dy,
                )
                physics.rebuild_bounds(new_bounds)
                self.activate_temporary_topmost()

            self.sync_z_order_to_container(container.hwnd)

    def handle_window_top_landing(
        self,
        physics: PetPhysics,
        previous_bottom: float,
    ) -> None:
        if self.active_container_hwnd is not None:
            return

        gx, gy = physics.body.position
        pet_left = gx - COLLISION_WIDTH / 2
        pet_right = gx + COLLISION_WIDTH / 2
        pet_bottom = gy + COLLISION_HEIGHT / 2

        vx, vy = physics.body.velocity
        if vy < 0:
            return

        candidates = []
        for window in self.desktop_windows:
            horizontal_overlap = (
                pet_right > window.x + 8
                and pet_left < window.right - 8
            )
            crossed_top = previous_bottom <= window.y <= pet_bottom

            if horizontal_overlap and crossed_top:
                candidates.append(window)

        if not candidates:
            return

        landed = candidates[0]
        target_y = max(
            COLLISION_HEIGHT / 2,
            landed.y - COLLISION_HEIGHT / 2,
        )

        physics.body.position = (gx, target_y)
        physics.body.velocity = (vx * 0.78, 0)

        self.active_platform_hwnd = landed.hwnd
        self.ignored_container_hwnd = landed.hwnd
        self.sync_z_order_to_container(landed.hwnd)

    def follow_active_platform(self, physics: PetPhysics) -> None:
        if (
            self.active_platform_hwnd is None
            or self.active_container_hwnd is not None
        ):
            return

        platform = self.windows_by_hwnd.get(self.active_platform_hwnd)
        if platform is None:
            self.active_platform_hwnd = None
            if self.ignored_container_hwnd is not None:
                self.ignored_container_hwnd = None
            return

        gx, gy = physics.body.position
        pet_left = gx - COLLISION_WIDTH / 2
        pet_right = gx + COLLISION_WIDTH / 2

        if pet_right < platform.x or pet_left > platform.right:
            self.active_platform_hwnd = None
            if self.ignored_container_hwnd == platform.hwnd:
                self.ignored_container_hwnd = None
            return

        if (
            abs((gy + COLLISION_HEIGHT / 2) - platform.y) < 6
            and physics.body.velocity.y >= 0
        ):
            platform_y = max(
                COLLISION_HEIGHT / 2,
                platform.y - COLLISION_HEIGHT / 2,
            )
            physics.body.position = (gx, platform_y)
            physics.body.velocity = (physics.body.velocity.x * 0.96, 0)
            self.sync_z_order_to_container(platform.hwnd)

    def sync_z_order_to_container(self, container_hwnd: int) -> None:
        if self.self_hwnd is None:
            return

        try:
            hwnds = [
                hwnd
                for hwnd in pet.windows_utils.getWindowsInZOrder()
                if hwnd != self.self_hwnd
            ]
            container_index = hwnds.index(container_hwnd)
        except ValueError:
            return

        insert_after = (
            win32con.HWND_TOP
            if container_index == 0
            else hwnds[container_index - 1]
        )
        self.set_z_order_after(insert_after)

    def set_z_order_after(self, insert_after: int) -> None:
        if self.self_hwnd is None:
            return

        try:
            win32gui.SetWindowPos(
                self.self_hwnd,
                insert_after,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE,
            )
        except Exception:
            # traceback.print_exc()
            pass

    def activate_temporary_topmost(self) -> None:
        self.temporary_topmost_until = time.monotonic() + 0.45

    def update_temporary_topmost(self) -> None:
        if self.self_hwnd is None:
            return

        should_be_topmost = (
            self.active_container_hwnd is not None
            and time.monotonic() < self.temporary_topmost_until
        )

        if should_be_topmost:
            win32gui.SetWindowPos(
                self.self_hwnd,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE,
            )
            self.is_temporarily_topmost = True
            return

        if self.is_temporarily_topmost:
            win32gui.SetWindowPos(
                self.self_hwnd,
                win32con.HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE,
            )
            self.is_temporarily_topmost = False

            if self.active_container_hwnd is not None:
                self.sync_z_order_to_container(self.active_container_hwnd)

    def cleanup_topmost(self) -> None:
        if self.self_hwnd is not None and self.is_temporarily_topmost:
            win32gui.SetWindowPos(
                self.self_hwnd,
                win32con.HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE,
            )
            self.is_temporarily_topmost = False

    def reset_to_fullscreen(self, physics: PetPhysics) -> None:
        self.active_container_hwnd = None
        self.active_platform_hwnd = None
        self.ignored_container_hwnd = None
        physics.rebuild_bounds((0, 0, self.screen_width, self.screen_height))
