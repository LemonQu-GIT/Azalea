import asyncio
import json
import traceback

import uvicorn
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from contextlib import asynccontextmanager

from pet.signals import emitter
from pet.websocketm import ws_manager
from pet.ai import ai_brain_loop
import pet.utils

config = pet.utils.loadConfig()


# 全局用户消息队列：对话框 -> ai_brain_core
# 每一项是用户消息文本字符串
user_message_queue: asyncio.Queue[str] = asyncio.Queue()

# 全局摸头事件队列：窗口手势检测 -> ai_brain_core
# 每一项是 True（表示一次"摸了头"事件），内容字符串由 ai 侧拼 assembled_content
head_pat_queue: asyncio.Queue[bool] = asyncio.Queue()

# 全局 AI 回复队列：ai_brain_core -> 对话框前端
# 每一项是回复内容字符串
ai_reply_queue: asyncio.Queue[str] = asyncio.Queue()

chat_ws_connections: list[WebSocket] = []


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


def _on_ai_task_done(task: asyncio.Task):
    try:
        task.result()
    except asyncio.CancelledError:
        msg = f"任务已被取消 (done_callback 确认)"
        pet.utils.log(msg, "INFO", save=False)
    except Exception as exc:
        header = f"任务以异常结束 (未被 ai_brain_loop 捕获到): {type(exc).__name__}: {exc}"
        pet.utils.log(header, "FATAL")


@app.get("/")
async def get_index(request: Request):
    scheme = request.url.scheme.replace("http", "ws")
    host = request.url.netloc
    ws_url = f"{scheme}://{host}/ws"
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "ws_url": ws_url}
    )


@app.get("/chat")
async def get_chat(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/three.module.js")
async def get_three_module():
    return FileResponse("front/three.module.js", media_type="application/javascript")


@app.get("/three.core.js")
async def get_three_core():
    return FileResponse("front/three.core.js", media_type="application/javascript")


@app.get("/model.glb")
async def get_model():
    return FileResponse("./models/mika.glb", media_type="model/gltf-binary")


class ChatSendRequest(BaseModel):
    content: str


@app.post("/chat_send")
async def chat_send_post(req: ChatSendRequest):
    """HTTP fallback 接口：接收用户发送的对话消息。"""
    content = (req.content or "").strip()
    if not content:
        return JSONResponse({"success": False, "error": "消息不能为空"}, status_code=400)
    try:
        await user_message_queue.put(content)
        return JSONResponse({"success": True, "reply": None})
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/chat_close")
async def chat_close_post():
    """前端请求关闭对话框窗口（ESC / 发送成功后调用）。"""
    try:
        emitter.request_close_chat.emit()
    except Exception:
        pet.utils.log(
            "emit request_close_chat 异常:\n" + traceback.format_exc(),
            "ERROR",
        )
    return JSONResponse({"ok": True})


async def _broadcast_chat_ws(payload: dict):
    """向所有已连接的对话框 WebSocket 广播 JSON 消息。"""
    dead = []
    for conn in chat_ws_connections:
        try:
            await conn.send_text(json.dumps(payload))
        except Exception:
            dead.append(conn)
    for conn in dead:
        if conn in chat_ws_connections:
            chat_ws_connections.remove(conn)


async def _ai_reply_forwarder_task():
    """后台任务：把 ai_reply_queue 中的回复推送给所有对话框前端。"""
    while True:
        try:
            reply = await ai_reply_queue.get()
            await _broadcast_chat_ws({
                "type": "assistant_reply",
                "content": reply,
            })
        except Exception:
            pet.utils.log(
                "异常:\n" + traceback.format_exc(),
                "ERROR",
            )
            await asyncio.sleep(0.5)


_reply_forwarder_task: asyncio.Task | None = None


@app.websocket("/chat_ws")
async def chat_websocket_endpoint(websocket: WebSocket):
    global _reply_forwarder_task

    await websocket.accept()
    chat_ws_connections.append(websocket)

    # 启动 AI 回复转发器（只启动一次）
    if _reply_forwarder_task is None or _reply_forwarder_task.done():
        _reply_forwarder_task = asyncio.create_task(_ai_reply_forwarder_task())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            msg_type = data.get("type")
            if msg_type == "user_message":
                content = (data.get("content") or "").strip()
                if content:
                    await user_message_queue.put(content)
            elif msg_type == "close_window":
                # 前端（ESC 或发送完成后）请求关闭对话框窗口
                try:
                    emitter.request_close_chat.emit()
                except Exception:
                    pet.utils.log(
                        "emit request_close_chat 异常:\n"
                        + traceback.format_exc(),
                        "ERROR",
                    )
    except WebSocketDisconnect:
        pet.utils.log("Chat WebSocket Connection Closed", "INFO", save=False)
    except Exception:
        pet.utils.log(
            "Chat WebSocket 异常:\n" + traceback.format_exc(), "ERROR"
        )
    finally:
        if websocket in chat_ws_connections:
            chat_ws_connections.remove(websocket)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global ai_task

    await websocket.accept()
    ws_manager.active_connections.append(websocket)

    if ai_task is None or ai_task.done():
        if ai_task is not None and ai_task.done() and not ai_task.cancelled():
            try:
                ai_task.result()
            except Exception:
                pass
        ai_task = asyncio.create_task(ai_brain_loop())
        ai_task.add_done_callback(_on_ai_task_done)
        pet.utils.log("决策任务已启动", "INFO", save=False)

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

            elif command == "right_click_model":
                emitter.model_right_clicked.emit(
                    int(data.get("screen_x", 0)),
                    int(data.get("screen_y", 0)),
                )

    except WebSocketDisconnect:
        pet.utils.log("WebSocket Connection Closed", "INFO", save=False)

    except Exception:
        pet.utils.log("WebSocket 异常:\n" + traceback.format_exc(), "ERROR")

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
    # 把 user_message_queue / head_pat_queue / ai_reply_queue 绑定到这个 event loop
    import pet.server as _self
    _self.user_message_queue = asyncio.Queue()
    _self.head_pat_queue = asyncio.Queue()
    _self.ai_reply_queue = asyncio.Queue()

    # 注意：emitter.pet_head_patted -> head_pat_queue 的桥接**必须在 Qt 主线程执行 connect**，
    # 因为 Qt signal/slot 的线程亲和性在创建线程。本函数运行在 api_thread（非 Qt 线程），
    # 在这里执行 connect 会导致 signal 永远不会被投递到本线程。
    # 因此：桥接逻辑移到 main.py 的 Qt 主线程（在 PetWindow 创建之后）注册。

    loop.run_until_complete(server.serve())
