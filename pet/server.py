import asyncio
import traceback

import uvicorn
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from starlette.websockets import WebSocketDisconnect
from contextlib import asynccontextmanager

from pet.signals import emitter
from pet.websocketm import ws_manager
from pet.ai import ai_brain_loop
import pet.utils

config = pet.utils.loadConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pet.utils.log(f"Server running on http://{config['petServer']['host']}:{config['petServer']['port']}",
                  "INFO", save=False)
    yield
    pet.utils.log("Server closed",
                  "INFO", save=False)


templates = Jinja2Templates(directory="front")
app = FastAPI(lifespan=lifespan)

ai_task: asyncio.Task | None = None


@app.get("/")
async def get_index(request: Request):
    scheme = request.url.scheme.replace("http", "ws")
    host = request.url.netloc
    ws_url = f"{scheme}://{host}/ws"
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "ws_url": ws_url}
    )


@app.get("/three.module.js")
async def get_three_module():
    return FileResponse("front/three.module.js", media_type="application/javascript")


@app.get("/model.glb")
async def get_model():
    return FileResponse("./models/mika.glb", media_type="model/gltf-binary")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global ai_task

    await websocket.accept()
    ws_manager.active_connections.append(websocket)

    if ai_task is None or ai_task.done():
        ai_task = asyncio.create_task(ai_brain_loop())

    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command")

            if command == "set_click_through":
                enabled = data.get("enabled", False)
                emitter.model_hit_tested.emit(
                    not enabled,
                    int(data.get("x", -10_000)),
                    int(data.get("y", -10_000)),
                )

            elif command == "start_drag":
                emitter.drag_started.emit(
                    int(data.get("screen_x", 0)),
                    int(data.get("screen_y", 0)),
                )

            elif command == "drag_move":
                emitter.drag_moved.emit(
                    int(data.get("screen_x", 0)),
                    int(data.get("screen_y", 0)),
                )

            elif command == "end_drag":
                emitter.drag_ended.emit()

    except WebSocketDisconnect:
        pet.utils.log("WebSocket Connection Closed", "INFO", save=False)

    except Exception:
        traceback.print_exc()

    finally:
        if websocket in ws_manager.active_connections:
            ws_manager.active_connections.remove(websocket)


def start_fastapi_server(debug: bool = False):
    fconfig = pet.utils.loadConfig()
    config = uvicorn.Config("pet.server:app", host=fconfig['petServer']['host'], port=fconfig['petServer']['port'], reload=True, log_level="debug") if debug else uvicorn.Config(
        app, host=fconfig['petServer']['host'], port=fconfig['petServer']['port'], log_level="error")
    server = uvicorn.Server(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    ws_manager.loop = loop

    loop.run_until_complete(server.serve())
