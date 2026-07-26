import math
from dataclasses import dataclass

from pet.constants import *


def clamp(value: float, low: float, high: float) -> float:
    if high < low:
        return (low + high) / 2
    return max(low, min(high, value))


def vector_to_speed(dx: float, dy: float, duration: float) -> tuple[float, float]:
    if duration <= 0.001:
        return 0, 0
    vx = dx / duration
    vy = dy / duration
    speed = math.hypot(vx, vy)
    if speed > MAX_THROW_SPEED:
        scale = MAX_THROW_SPEED / speed
        vx *= scale
        vy *= scale
    return vx, vy


def collision_size() -> tuple[float, float]:
    width = max(1, PET_WIDTH - COLLISION_OFFSET_LEFT - COLLISION_OFFSET_RIGHT)
    height = max(1, PET_HEIGHT - COLLISION_OFFSET_TOP -
                 COLLISION_OFFSET_BOTTOM)
    return float(width), float(height)


COLLISION_WIDTH, COLLISION_HEIGHT = collision_size()
COLLISION_CENTER_X = COLLISION_OFFSET_LEFT + COLLISION_WIDTH / 2
COLLISION_CENTER_Y = COLLISION_OFFSET_TOP + COLLISION_HEIGHT / 2


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
        return self.width > COLLISION_WIDTH + 8 and self.height > COLLISION_HEIGHT + 8
