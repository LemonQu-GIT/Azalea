import asyncio
import pet.pet_api as pet_api
import pet.utils
import random

_active_window = None
config = pet.utils.loadConfig()


def register_active_window(window):
    global _active_window
    _active_window = window


def unregister_active_window():
    global _active_window
    _active_window = None


class Actions:
    def __init__(self, window):
        self._active_window = window

    def get_bounds(self) -> tuple[int, int, int, int]:
        if self._active_window is None:
            return (0, 0, 0, 0)
        try:
            rect = self._active_window.frameGeometry()
            x1 = int(rect.x())
            y1 = int(rect.y())
            x2 = int(rect.x() + rect.width())
            y2 = int(rect.y() + rect.height())
            return (x1, y1, x2, y2)
        except Exception:
            return (0, 0, 0, 0)

    def get_position(self) -> tuple[int, int]:
        if self._active_window is None:
            return (0, 0)
        try:
            rect = self._active_window.frameGeometry()
            x1 = int(rect.x()) + config["window"]['collision_offset']['left']
            y1 = int(rect.y()) + config["window"]['collision_offset']['top']
            x2 = int(rect.x() + rect.width()) - \
                config["window"]['collision_offset']['right']
            y2 = int(rect.y() + rect.height()) - \
                config["window"]['collision_offset']['bottom']
            return ((x1 + x2) // 2, y2)
        except Exception:
            return (0, 0)

    def climb_window(self, hwnd: int):
        if self._active_window is not None:
            self._active_window.enqueue_ai_command(
                "climb_window", hwnd=int(hwnd))

    def jump_on_window(self, hwnd: int):
        if self._active_window is not None:
            self._active_window.enqueue_ai_command(
                "jump_on_window", hwnd=int(hwnd))

    def jump_into_window(self, hwnd: int):
        if self._active_window is not None:
            self._active_window.enqueue_ai_command(
                "jump_into_window", hwnd=int(hwnd))

    def jump(self, height: int = 95, times: int = 1):
        if self._active_window is not None:
            self._active_window.enqueue_ai_command(
                "jump", height=height, times=times)

    def walk(self, distance: int):
        if self._active_window is not None:
            self._active_window.enqueue_ai_command("walk", distance=distance)

    def walk_to(self, x: int):
        if self._active_window is not None:
            self._active_window.enqueue_ai_command("walk_to", x=x)

    async def set_model_scale(self, x: float, y: float, z: float):
        await pet_api.set_model_scale(x, y, z)

    async def set_model_position(self, x: float, y: float, z: float):
        await pet_api.set_model_position(x, y, z)

    async def set_camera_position(self, x: float, y: float, z: float):
        await pet_api.set_camera_position(x, y, z)

    async def play_animation(self, name: str, loop: bool = True):
        await pet_api.play_animation(name, loop=loop)

    async def set_model_transform(
        self,
        scale: tuple[float, float, float] | None = None,
        rotation: tuple[float, float, float] | None = None,
        position: tuple[float, float, float] | None = None,
        rotation_degrees: bool = True,
    ):
        await pet_api.set_model_transform(
            scale=scale,
            rotation=rotation,
            position=position,
            rotation_degrees=rotation_degrees,
        )


async def ai_brain_loop():
    global _active_window
    action = Actions(_active_window)
    await asyncio.sleep(1)

    await action.play_animation("CH0069_Cafe_Idle", loop=True)
    await asyncio.sleep(3)
    while True:
        for _ in range(0, 360, 45):
            print(f"Setting model rotation to {_:03d} degrees")
            await action.set_model_transform(
                rotation=(0, _, 0), rotation_degrees=True)
            await asyncio.sleep(0.75)
