from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass

from pet.constants import WINDOW_TITLE
import pet.platform_utils
from pet.constants import STEP_SECONDS
from pet.physics import PetPhysics, WindowBouncePhysics, COLLISION_WIDTH, COLLISION_HEIGHT


if sys.platform == "win32":
    import ctypes

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

        # 跳跃进入窗口期间抑制自动容器检测，防止被路径上/原窗口错误接住
        self.suppress_auto_container_until = 0.0

        self.temporary_topmost_until = 0.0
        self.is_temporarily_topmost = False
        self.is_drag_topmost = False

        self.window_bounce: WindowBouncePhysics | None = None
        self.window_bounce_pending_hwnd: int | None = None
        self.window_bounce_pending_impact_speed: float = 0.0

    def _log(self, message: str) -> None:
        return

    def _trace(self, message: str) -> None:
        return

    def _arm_window_bounce_pending(self, hwnd: int, impact_speed: float) -> None:
        self.window_bounce_pending_hwnd = int(hwnd)
        self.window_bounce_pending_impact_speed = max(
            self.window_bounce_pending_impact_speed,
            float(impact_speed),
        )
        self._log(
            f"window bounce pending hwnd={hwnd} impact_speed={self.window_bounce_pending_impact_speed:.1f}"
        )

    def _maybe_start_window_bounce_pending(self, physics: PetPhysics) -> None:
        if self.window_bounce is not None:
            return

        pending_hwnd = self.window_bounce_pending_hwnd
        if pending_hwnd is None:
            return

        if self.active_container_hwnd != pending_hwnd and self.active_platform_hwnd != pending_hwnd:
            return

        vy = abs(float(physics.body.velocity.y))
        vx = abs(float(physics.body.velocity.x))
        if vy > 18.0 or vx > 260.0:
            return

        impact_speed = self.window_bounce_pending_impact_speed
        self.window_bounce_pending_hwnd = None
        self.window_bounce_pending_impact_speed = 0.0
        self._log(
            f"window bounce start confirmed hwnd={pending_hwnd} impact_speed={impact_speed:.1f} vx={vx:.1f} vy={vy:.1f}"
        )
        self.start_window_bounce(pending_hwnd, impact_speed=impact_speed)

    def suppress_auto_container(self, duration_seconds: float) -> None:
        """在一段时间内禁止refresh_container_from_position自动检测容器。

        用于jump_into_window期间，防止桌宠尚未飞离原窗口时又被检测回去，
        或者路径上的中间窗口错误地成为容器。enter模式在结束时（成功或超时）
        必须调用suppress_auto_container(0)解除抑制。
        """
        self.suppress_auto_container_until = (
            time.monotonic() + max(0.0, duration_seconds)
        )

    def get_window(self, hwnd: int | None) -> DesktopWindow | None:
        if hwnd is None:
            return None
        return self.windows_by_hwnd.get(hwnd)

    def scan_desktop_windows(
        self,
        self_hwnd: int | None,
        physics: PetPhysics | None = None,
        previous_bottom: float | None = None,
    ) -> None:
        self.self_hwnd = self_hwnd
        rects = pet.platform_utils.getAllWindowsRects()
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
            self.refresh_container_from_position(
                physics, previous_bottom=previous_bottom)

    def refresh_container_from_position(
        self,
        physics: PetPhysics,
        previous_bottom: float | None = None,
    ) -> None:
        if physics.is_dragging:
            self._trace(
                "refresh_container_from_position skipped: physics is dragging")
            return

        if (
            self.window_bounce is not None
            and self.active_container_hwnd == self.window_bounce.hwnd
        ):
            self._trace(
                f"refresh_container_from_position skipped: bounce active hwnd={self.window_bounce.hwnd}"
            )
            return

        x, y = physics.body.position
        container = None
        self._trace(
            f"refresh_container_from_position body=({x:.1f}, {y:.1f}) active_container={self.active_container_hwnd} ignored={self.ignored_container_hwnd} previous_bottom={previous_bottom}"
        )

        # 跳跃进入窗口期间的抑制逻辑：
        # - 如果已经有active_container（enter模式已成功附着），继续维护它的bounds同步
        # - 如果没有active_container，禁止自动扫描新容器（防止原窗口/路径窗口干扰）
        suppression_active = time.monotonic() < self.suppress_auto_container_until
        auto_detect_blocked = suppression_active and self.active_container_hwnd is None

        if self.active_container_hwnd is not None:
            active_window = self.windows_by_hwnd.get(
                self.active_container_hwnd)
            if (
                active_window is not None
                and active_window.can_contain_pet_window()
                and active_window.hwnd != self.ignored_container_hwnd
            ):
                container = active_window

        if container is None and not auto_detect_blocked:
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
            self._log(
                f"container changed {self.active_container_hwnd} -> {new_hwnd}")
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
                if previous_bottom is not None:
                    pet_bottom = y + COLLISION_HEIGHT / 2
                    crossed_top = previous_bottom <= container.y <= pet_bottom
                    horizontal_overlap = (
                        x + COLLISION_WIDTH / 2 > container.x + 8
                        and x - COLLISION_WIDTH / 2 < container.right - 8
                    )
                    impact_speed = abs(float(physics.body.velocity.y))
                    self._log(
                        f"container acquired hwnd={container.hwnd} crossed_top={crossed_top} horizontal_overlap={horizontal_overlap} impact_speed={impact_speed:.1f}"
                    )
                    if horizontal_overlap:
                        self._arm_window_bounce_pending(
                            container.hwnd, impact_speed)
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

            if (
                previous_bottom is not None
                and self.active_platform_hwnd is None
                and self.window_bounce is None
            ):
                pet_bottom = y + COLLISION_HEIGHT / 2
                crossed_top = previous_bottom <= container.y <= pet_bottom
                horizontal_overlap = (
                    x + COLLISION_WIDTH / 2 > container.x + 8
                    and x - COLLISION_WIDTH / 2 < container.right - 8
                )
                if crossed_top and horizontal_overlap:
                    self._log(
                        f"container acquired hwnd={container.hwnd} crossed_top={crossed_top} horizontal_overlap={horizontal_overlap} source=active_container"
                    )
                    self.active_platform_hwnd = container.hwnd
                    self.ignored_container_hwnd = container.hwnd
                    self._arm_window_bounce_pending(
                        container.hwnd,
                        max(abs(float(physics.body.velocity.y)), 60.0),
                    )

            self._trace(
                f"container bounds refreshed hwnd={container.hwnd} bounds={new_bounds}")

            self.sync_z_order_to_container(container.hwnd)

    def handle_window_top_landing(
        self,
        physics: PetPhysics,
        previous_bottom: float,
    ) -> None:
        self._trace(
            f"handle_window_top_landing enter previous_bottom={previous_bottom:.1f} active_container={self.active_container_hwnd} active_platform={self.active_platform_hwnd}"
        )
        if self.active_container_hwnd is not None:
            self._trace(
                "handle_window_top_landing skipped: already inside a container")
            return

        # 跳跃进入窗口期间：抑制期内且没有active_container的情况下，
        # 暂停所有顶部着陆检测，防止路径上的第三个窗口把桌宠截停在半空
        if time.monotonic() < self.suppress_auto_container_until:
            self._trace(
                "handle_window_top_landing skipped: suppression active")
            return

        gx, gy = physics.body.position
        pet_left = gx - COLLISION_WIDTH / 2
        pet_right = gx + COLLISION_WIDTH / 2
        pet_bottom = gy + COLLISION_HEIGHT / 2

        vx, vy = physics.body.velocity
        if vy < 0:
            self._trace(f"handle_window_top_landing skipped: vy={vy:.1f} < 0")
            return

        candidates = []
        for window in self.desktop_windows:
            # 跳过被忽略的容器（例如jump_on_window的目标窗口等场景）
            if window.hwnd == self.ignored_container_hwnd:
                continue
            horizontal_overlap = (
                pet_right > window.x + 8
                and pet_left < window.right - 8
            )
            crossed_top = previous_bottom <= window.y <= pet_bottom

            if horizontal_overlap and crossed_top:
                candidates.append(window)

        if not candidates:
            self._trace("handle_window_top_landing no candidate windows")
            return

        landed = candidates[0]
        self._log(
            f"handle_window_top_landing landed hwnd={landed.hwnd} title={landed.title!r} rect=({landed.x}, {landed.y}, {landed.right}, {landed.bottom})"
        )
        target_y = max(
            COLLISION_HEIGHT / 2,
            landed.y - COLLISION_HEIGHT / 2,
        )

        physics.body.position = (gx, target_y)
        physics.body.velocity = (vx * 0.78, 0)

        self.active_platform_hwnd = landed.hwnd
        self.ignored_container_hwnd = landed.hwnd
        self.sync_z_order_to_container(landed.hwnd)
        self._arm_window_bounce_pending(landed.hwnd, abs(float(vy)))

    def start_window_bounce(self, hwnd: int, impact_speed: float | None = None) -> None:
        rect = pet.platform_utils.getWindowRect(hwnd)
        if rect[0] is None or rect[1] is None or rect[2] is None or rect[3] is None:
            return
        self._log(f"start_window_bounce hwnd={hwnd} rect={rect}")

        self.window_bounce = WindowBouncePhysics(
            hwnd,
            (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])),
        )
        self.window_bounce.kick(
            impact_speed=240.0 if impact_speed is None else impact_speed)
        self._log(
            f"window bounce started hwnd={hwnd} mass={self.window_bounce.mass:.2f}")

    def update_window_bounce(self, physics: PetPhysics) -> None:
        self._maybe_start_window_bounce_pending(physics)

        if self.window_bounce is None:
            return

        bounce = self.window_bounce
        if bounce.finished:
            self._trace(f"window bounce already finished hwnd={bounce.hwnd}")
            self.window_bounce = None
            return

        offset_y, finished = bounce.step(STEP_SECONDS)
        self._trace(
            f"window bounce step hwnd={bounce.hwnd} offset_y={offset_y:.2f} finished={finished} origin_top={bounce.origin_top}"
        )
        if offset_y != 0.0:
            pet.platform_utils.transformWindow(
                bounce.hwnd,
                y=bounce.origin_top + round(offset_y),
            )
            self._trace(
                f"window moved hwnd={bounce.hwnd} y={bounce.origin_top + round(offset_y)}"
            )

            if self.active_container_hwnd == bounce.hwnd or self.active_platform_hwnd == bounce.hwnd:
                physics.body.position = (
                    physics.body.position.x,
                    physics.body.position.y + offset_y,
                )
                self._trace(
                    f"pet synced with bounced window hwnd={bounce.hwnd} body_y={physics.body.position.y:.2f}"
                )

        if finished:
            try:
                pet.platform_utils.transformWindow(
                    bounce.hwnd,
                    x=bounce.origin_left,
                    y=bounce.origin_top,
                    width=bounce.width,
                    height=bounce.height,
                )
                self._log(
                    f"window bounce restored hwnd={bounce.hwnd} to origin=({bounce.origin_left}, {bounce.origin_top}) size=({bounce.width}, {bounce.height})"
                )
            finally:
                self.window_bounce = None

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
            self._log(
                f"follow_active_platform hwnd={platform.hwnd} platform_y={platform_y} body=({gx:.1f}, {physics.body.position.y:.1f})"
            )
            self.sync_z_order_to_container(platform.hwnd)

    def sync_z_order_to_container(self, container_hwnd: int) -> None:
        if self.self_hwnd is None:
            return

        try:
            hwnds = [
                hwnd
                for hwnd in pet.platform_utils.getWindowsInZOrder()
                if hwnd != self.self_hwnd
            ]
            container_index = hwnds.index(container_hwnd)
        except ValueError:
            return

        insert_after = (
            pet.platform_utils.WINDOW_Z_TOP
            if container_index == 0
            else hwnds[container_index - 1]
        )
        self.set_z_order_after(insert_after)

    def set_z_order_after(self, insert_after: int) -> None:
        if self.self_hwnd is None:
            return

        pet.platform_utils.setWindowZOrderAfter(self.self_hwnd, insert_after)

    def activate_temporary_topmost(self) -> None:
        self.temporary_topmost_until = time.monotonic() + 0.45

    def set_drag_topmost(self, enable: bool) -> None:
        if self.self_hwnd is None:
            return

        try:
            pet.platform_utils.setWindowTopmost(self.self_hwnd, enable)
            self.is_drag_topmost = enable
        except Exception:
            pass

    def update_temporary_topmost(self) -> None:
        if self.self_hwnd is None:
            return

        # 拖拽期间始终置顶
        if self.is_drag_topmost:
            if not self.is_temporarily_topmost:
                pet.platform_utils.setWindowTopmost(self.self_hwnd, True)
                self.is_temporarily_topmost = True
            return

        should_be_topmost = (
            self.active_container_hwnd is not None
            and time.monotonic() < self.temporary_topmost_until
        )

        if should_be_topmost:
            pet.platform_utils.setWindowTopmost(self.self_hwnd, True)
            self.is_temporarily_topmost = True
            return

        if self.is_temporarily_topmost:
            pet.platform_utils.setWindowTopmost(self.self_hwnd, False)
            self.is_temporarily_topmost = False

            if self.active_container_hwnd is not None:
                self.sync_z_order_to_container(self.active_container_hwnd)

    def cleanup_topmost(self) -> None:
        if self.self_hwnd is not None and (self.is_temporarily_topmost or self.is_drag_topmost):
            pet.platform_utils.setWindowTopmost(self.self_hwnd, False)
            self.is_temporarily_topmost = False
            self.is_drag_topmost = False

    def reset_to_fullscreen(self, physics: PetPhysics) -> None:
        self.active_container_hwnd = None
        self.active_platform_hwnd = None
        self.ignored_container_hwnd = None
        self.window_bounce = None
        self.window_bounce_pending_hwnd = None
        self.window_bounce_pending_impact_speed = 0.0
        physics.rebuild_bounds((0, 0, self.screen_width, self.screen_height))
