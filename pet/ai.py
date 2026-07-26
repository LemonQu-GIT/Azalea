import asyncio
import pet.pet_api as pet_api

_active_window = None


def register_active_window(window):
    global _active_window
    _active_window = window


def unregister_active_window():
    global _active_window
    _active_window = None


def climb_window(hwnd: int):
    if _active_window is not None:
        _active_window.enqueue_ai_command("climb_window", hwnd=int(hwnd))


def jump_on_window(hwnd: int):
    if _active_window is not None:
        _active_window.enqueue_ai_command("jump_on_window", hwnd=int(hwnd))


def jump_into_window(hwnd: int):
    if _active_window is not None:
        _active_window.enqueue_ai_command("jump_into_window", hwnd=int(hwnd))


async def ai_brain_loop():
    await asyncio.sleep(1)
    await pet_api.play_animation("CH0069_Cafe_Idle", loop=True)
    while True:
        # await do_something()
        break
