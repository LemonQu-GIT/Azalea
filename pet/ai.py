import asyncio
import pet.pet_api as pet_api
import pet.windows_utils
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

    def get_position(self, type: str = "foot") -> tuple[int, int]:
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
            if type == "foot":
                return ((x1 + x2) // 2, y2)
            else:
                return ((x1 + x2) // 2, (y1 + y2) // 2)
        except Exception:
            return (0, 0)

    async def _run_awaitable_action(
        self,
        command: str,
        *,
        timeout_seconds: float,
        **kwargs,
    ) -> bool:
        if self._active_window is None:
            return False
        try:
            loop = asyncio.get_running_loop()
        except Exception:
            self._active_window.enqueue_ai_command(command, **kwargs)
            return True

        event = asyncio.Event()
        try:
            action_id = self._active_window.register_action_completion(
                loop, event, timeout_seconds + 0.5)
        except Exception:
            self._active_window.enqueue_ai_command(command, **kwargs)
            return True

        kwargs = dict(kwargs)
        kwargs["_action_id"] = int(action_id)
        self._active_window.enqueue_ai_command(command, **kwargs)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _climb_window(self, hwnd: int, timeout_seconds: float = 10.0) -> bool:
        return await self._run_awaitable_action(
            "climb_window",
            timeout_seconds=timeout_seconds,
            hwnd=int(hwnd),
        )

    async def _jump_on_window(self, hwnd: int, timeout_seconds: float = 6.0) -> bool:
        return await self._run_awaitable_action(
            "jump_on_window",
            timeout_seconds=timeout_seconds,
            hwnd=int(hwnd),
        )

    async def _jump_into_window(self, hwnd: int, timeout_seconds: float = 5.0) -> bool:
        return await self._run_awaitable_action(
            "jump_into_window",
            timeout_seconds=timeout_seconds,
            hwnd=int(hwnd),
        )

    async def jump(self, height: int = 95, times: int = 1, timeout_seconds: float | None = None) -> bool:
        height_i = max(1, int(height))
        times_i = max(1, int(times))
        if timeout_seconds is None:
            t_per_jump = 0.9 + (height_i / 420.0)
            timeout_seconds = max(2.5, float(times_i) * t_per_jump + 1.0)
        return await self._run_awaitable_action(
            "jump",
            timeout_seconds=timeout_seconds,
            height=height_i,
            times=times_i,
        )

    async def _walk(self, distance: int, timeout_seconds: float | None = None) -> bool:
        dist_i = int(distance)
        if abs(dist_i) < 1:
            return True
        if timeout_seconds is None:
            timeout_seconds = max(2.0, abs(float(dist_i)) / 260.0 + 1.0)
        return await self._run_awaitable_action(
            "walk",
            timeout_seconds=timeout_seconds,
            distance=dist_i,
        )

    async def _walk_to(self, x: int, timeout_seconds: float | None = None) -> bool:
        x_i = int(x)
        if timeout_seconds is None:
            timeout_seconds = max(2.0, 3840.0 / 260.0 + 1.5)
        return await self._run_awaitable_action(
            "walk_to",
            timeout_seconds=timeout_seconds,
            x=x_i,
        )

    async def climb_window(self, hwnd: int):
        await self._climb_window(hwnd)

    async def jump_on_window(self, hwnd: int):
        position = self.get_position(type="feet")
        win_bounds = pet.windows_utils.getWindowRect(hwnd)
        if win_bounds[0] and win_bounds[1] and win_bounds[2] and win_bounds[3]:
            mid_x = (win_bounds[0] + win_bounds[2]) // 2
            if abs(position[1] - win_bounds[3]) < 10 and win_bounds[0] < position[0] < win_bounds[2]:
                pass
            else:
                angle = 180 if position[0] < mid_x else 0
                await self.set_model_transform(rotation=(0, angle, 0), rotation_degrees=True)
                await self._jump_on_window(hwnd)
                await self.set_model_transform(rotation=(0, 90, 0), rotation_degrees=True)

    async def jump_into_window(self, hwnd: int):
        position = self.get_position(type="main")
        win_bounds = pet.windows_utils.getWindowRect(hwnd)
        if win_bounds[0] and win_bounds[1] and win_bounds[2] and win_bounds[3]:
            mid_x = (win_bounds[0] + win_bounds[2]) // 2
            if win_bounds[1] < position[1] < win_bounds[3] and win_bounds[0] < position[0] < win_bounds[2]:
                pass
            else:
                angle = 180 if position[0] < mid_x else 0
                await self.set_model_transform(rotation=(0, angle, 0), rotation_degrees=True)
                await self._jump_into_window(hwnd)
                await self.set_model_transform(rotation=(0, 90, 0), rotation_degrees=True)

    async def walk(self, distance: int):
        WALK_ROTATION_OFFSET = -19
        if distance == 0:
            return
        if distance < 0:
            await self.play_animation("CH0069_Cafe_Walk", loop=True)
            await self.set_model_transform(rotation=(0, 270+WALK_ROTATION_OFFSET, 0), rotation_degrees=True)
            await self._walk(distance)
            await self.play_animation("CH0069_Cafe_Idle", loop=True)
            await self.set_model_transform(rotation=(0, 90, 0), rotation_degrees=True)
        else:
            await self.play_animation("CH0069_Cafe_Walk", loop=True)
            await self.set_model_transform(rotation=(0, 90+WALK_ROTATION_OFFSET, 0), rotation_degrees=True)
            await self._walk(distance)
            await self.play_animation("CH0069_Cafe_Idle", loop=True)
            await self.set_model_transform(rotation=(0, 90, 0), rotation_degrees=True)

    async def walk_to(self, x: int):
        position = self.get_position(type="feet")
        distance = x - position[0]
        await self.walk(distance)

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
    await asyncio.sleep(3)
    await action.walk_to(1200)
    await action.jump(times=2)
    await asyncio.sleep(3)
    while True:
        await action.jump_into_window(1116608)
        await asyncio.sleep(3)
