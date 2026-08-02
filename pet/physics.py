from __future__ import annotations

import math
import time
from collections import deque
import pymunk

from pet.constants import (
    GRAVITY,
    STEP_SECONDS,
    WALL_BOUNCE,
    MAX_THROW_SPEED,
)
from pet.geometry import clamp, vector_to_speed, COLLISION_WIDTH, COLLISION_HEIGHT, COLLISION_CENTER_Y, COLLISION_CENTER_X


class PetPhysics:
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.space = pymunk.Space()
        self.space.gravity = (0, GRAVITY)
        self.space.damping = 0.92
        self.space.iterations = 24

        mass = 14
        moment = pymunk.moment_for_box(
            mass, (COLLISION_WIDTH, COLLISION_HEIGHT))

        self.body = pymunk.Body(mass, moment)
        self.body.position = (
            self.screen_width * 0.5,
            COLLISION_CENTER_Y + 20,
        )
        self.body.angular_velocity = 0

        self.shape = pymunk.Poly.create_box(
            self.body,
            (COLLISION_WIDTH, COLLISION_HEIGHT),
        )
        self.shape.elasticity = 0.2
        self.shape.friction = 1.5

        self.space.add(self.body, self.shape)

        self.mouse_body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.border_shapes: list[pymunk.Segment] = []
        self.mouse_joint: pymunk.PivotJoint | None = None  # type: ignore
        self.bounds = (
            0.0,
            0.0,
            float(self.screen_width),
            float(self.screen_height),
        )
        self.drag_points: deque[tuple[float, float, float]] = deque(maxlen=8)

        self.rebuild_bounds((0, 0, self.screen_width, self.screen_height))

    @property
    def is_dragging(self) -> bool:
        return self.mouse_joint is not None

    def rebuild_bounds(self, bounds: tuple[float, float, float, float]) -> None:
        for shape in self.border_shapes:
            self.space.remove(shape)
        self.border_shapes.clear()

        left, top, right, bottom = bounds
        self.bounds = (float(left), float(top), float(right), float(bottom))

        static_body = self.space.static_body
        segments = [
            pymunk.Segment(static_body, (left, top), (right, top), 1),
            pymunk.Segment(static_body, (left, bottom), (right, bottom), 1),
            pymunk.Segment(static_body, (left, top), (left, bottom), 1),
            pymunk.Segment(static_body, (right, top), (right, bottom), 1),
        ]

        for segment in segments:
            segment.elasticity = 0.25
            segment.friction = 1.5

        self.space.add(*segments)
        self.border_shapes.extend(segments)
        self.clamp_body_inside_bounds()

    def clamp_body_inside_bounds(self) -> None:
        left, top, right, bottom = self.bounds

        min_x = left + COLLISION_WIDTH / 2
        max_x = right - COLLISION_WIDTH / 2
        min_y = top + COLLISION_HEIGHT / 2
        max_y = bottom - COLLISION_HEIGHT / 2

        x, y = self.body.position
        vx, vy = self.body.velocity

        clamped_x = clamp(x, min_x, max_x)
        clamped_y = clamp(y, min_y, max_y)

        if clamped_x != x:
            vx = -vx * WALL_BOUNCE

        if clamped_y != y:
            vy = -vy * WALL_BOUNCE if y < min_y else min(0, -vy * WALL_BOUNCE)

        self.body.position = (clamped_x, clamped_y)
        self.body.velocity = (vx, vy)
        self.body.angle = 0
        self.body.angular_velocity = 0

    def start_drag(self, x: int, y: int) -> None:
        if self.is_dragging:
            return

        self.mouse_body.position = (x, y)
        local_anchor = self.body.world_to_local(self.mouse_body.position)

        self.mouse_joint = pymunk.PivotJoint(  # type: ignore
            self.mouse_body,
            self.body,
            (0, 0),
            local_anchor,
        )
        self.mouse_joint.max_force = 10_000_000
        self.mouse_joint.error_bias = pow(1.0 - 0.18, 60.0)

        self.space.add(self.mouse_joint)

        self.drag_points.clear()
        self.drag_points.append((time.monotonic(), float(x), float(y)))
        self.body.activate()

    def move_drag(self, x: int, y: int) -> None:
        if not self.is_dragging:
            return

        self.mouse_body.position = (x, y)
        self.drag_points.append((time.monotonic(), float(x), float(y)))
        self.body.activate()

    def end_drag(self, x: int | None = None, y: int | None = None) -> None:
        if not self.is_dragging:
            return

        if self.mouse_joint is not None:
            self.space.remove(self.mouse_joint)
            self.mouse_joint = None

        if x is not None and y is not None:
            self.drag_points.append((time.monotonic(), float(x), float(y)))

        if len(self.drag_points) >= 2:
            start_t, start_x, start_y = self.drag_points[0]
            end_t, end_x, end_y = self.drag_points[-1]
            vx, vy = vector_to_speed(
                end_x - start_x,
                end_y - start_y,
                end_t - start_t,
            )
            self.body.velocity = (vx, vy)
            self.body.activate()

    def launch_towards(
        self,
        target_x: float,
        target_y: float,
        arc_strength: float,
    ) -> None:
        gx, gy = self.body.position
        dx = target_x - gx
        dy = target_y - gy

        travel_time = clamp(
            math.sqrt(abs(dx) / 900 + abs(dy) / 900),
            0.35,
            1.0,
        )

        vx = dx / travel_time
        vy = dy / travel_time - arc_strength

        speed = math.hypot(vx, vy)
        if speed > MAX_THROW_SPEED:
            scale = MAX_THROW_SPEED / speed
            vx *= scale
            vy *= scale

        self.body.velocity = (vx, vy)
        self.body.activate()

    def step(self, dt: float | None = None) -> None:
        self.space.step(STEP_SECONDS if dt is None else dt)


class WindowBouncePhysics:
    def __init__(self, hwnd: int, rect: tuple[int, int, int, int]):
        left, top, right, bottom = rect

        self.hwnd = int(hwnd)
        self.origin_left = int(left)
        self.origin_top = int(top)
        self.width = max(1, int(right - left))
        self.height = max(1, int(bottom - top))

        self.mass = max(4.0, (self.width * self.height) / 140000.0)

        self.space = pymunk.Space()
        self.space.gravity = (0, 0)
        self.space.damping = 0.96

        moment = pymunk.moment_for_box(self.mass, (self.width, self.height))
        self.body = pymunk.Body(self.mass, moment)
        self.body.position = (0.0, 0.0)
        self.body.velocity = (0.0, 0.0)

        stiffness = 180.0 * self.mass
        damping = 16.0 * self.mass
        self.spring = pymunk.DampedSpring(  # type: ignore[attr-defined]
            self.space.static_body,
            self.body,
            (0, 0),
            (0, 0),
            0.0,
            stiffness,
            damping,
        )
        self.space.add(self.body, self.spring)

        self._settle_started_at: float | None = None
        self._finished = False

    @property
    def finished(self) -> bool:
        return self._finished

    def kick(self, impact_speed: float) -> None:
        if self._finished:
            return

        impulse = clamp(abs(impact_speed) * 36.0, 320.0, 6800.0)
        self.body.apply_impulse_at_local_point((0.0, impulse))
        self._settle_started_at = None

    def step(self, dt: float) -> tuple[float, bool]:
        if self._finished:
            return 0.0, True

        self.space.step(dt)
        offset_y = float(self.body.position.y)
        velocity_y = float(self.body.velocity.y)

        if abs(offset_y) < 0.4 and abs(velocity_y) < 16.0:
            if self._settle_started_at is None:
                self._settle_started_at = time.monotonic()
            elif time.monotonic() - self._settle_started_at > 0.08:
                self._finished = True
                return 0.0, True
        else:
            self._settle_started_at = None

        return offset_y, False
