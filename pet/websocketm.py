import asyncio
import json
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def broadcast(self, command_dict: dict):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(command_dict))
            except Exception:
                dead.append(connection)

        for connection in dead:
            if connection in self.active_connections:
                self.active_connections.remove(connection)

    def broadcast_threadsafe(self, command_dict: dict):
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self.broadcast(command_dict),
            self.loop,
        )


ws_manager = WebSocketManager()
