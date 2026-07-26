from pet.websocketm import ws_manager


def request_hit_test(x: int, y: int):
    ws_manager.broadcast_threadsafe(
        {
            "command": "hit_test",
            "x": x,
            "y": y,
        }
    )


async def set_model_scale(x: float, y: float, z: float):
    await ws_manager.broadcast(
        {
            "command": "set_transform",
            "scale": {"x": x, "y": y, "z": z},
        }
    )


async def set_model_position(x: float, y: float, z: float):
    await ws_manager.broadcast(
        {
            "command": "set_transform",
            "position": {"x": x, "y": y, "z": z},
        }
    )


async def set_camera_position(x: float, y: float, z: float):
    await ws_manager.broadcast(
        {
            "command": "set_camera",
            "position": {"x": x, "y": y, "z": z},
        }
    )


async def play_animation(name: str, loop: bool = True):
    await ws_manager.broadcast(
        {
            "command": "play_anim",
            "anim_name": name,
            "loop": loop,
        }
    )


async def set_model_transform(
    scale: tuple[float, float, float] | None = None,
    rotation: tuple[float, float, float] | None = None,
    position: tuple[float, float, float] | None = None,
    rotation_degrees: bool = True,
):
    command: dict = {"command": "set_transform"}

    if scale is not None:
        command["scale"] = {"x": scale[0], "y": scale[1], "z": scale[2]}

    if rotation is not None:
        command["rotation"] = {"x": rotation[0],
                               "y": rotation[1], "z": rotation[2]}
        command["rotation_units"] = "degrees" if rotation_degrees else "radians"

    if position is not None:
        command["position"] = {"x": position[0],
                               "y": position[1], "z": position[2]}

    await ws_manager.broadcast(command)
