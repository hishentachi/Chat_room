import json
import os
from typing import Optional

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Request,
    HTTPException,
    Form          # ← added this
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


app = FastAPI()

templates = Jinja2Templates(directory="templates")


ADMIN_PASSWORD = "mysecret123"  # change to your own password

class ConnectionManager:
    def __init__(self):
        # room_name -> set of WebSocket connections
        self.rooms: dict[str, set[WebSocket]] = {}
        # websocket -> info dict (ip, room, username)
        self.clients: dict[WebSocket, dict] = {}

    async def connect(self, room: str, websocket: WebSocket):
        await websocket.accept()

        # `websocket.client` is usually a tuple (host, port) or None.
        # Access it safely to avoid attribute errors.
        ip = websocket.client[0] if websocket.client else "unknown"

        if room not in self.rooms:
            self.rooms[room] = set()
        self.rooms[room].add(websocket)

        # initial info; username can be updated later
        self.clients[websocket] = {
            "ip": ip,
            "room": room,
            "username": None,
        }

    def disconnect(self, room: str, websocket: WebSocket):
        # remove from room
        if room in self.rooms and websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)
            if not self.rooms[room]:
                del self.rooms[room]

        # remove from clients
        if websocket in self.clients:
            del self.clients[websocket]

    async def broadcast(self, room: str, message: str):
        """Send raw text message to everyone in a room."""
        if room not in self.rooms:
            return
        for connection in list(self.rooms[room]):
            await connection.send_text(message)

    def update_username(self, websocket: WebSocket, username: str):
        if websocket in self.clients:
            self.clients[websocket]["username"] = username

    async def handle_message(self, room: str, websocket: WebSocket, data_str: str):
        """
        Expect JSON like:
          { "type": "join", "username": "Roshan" }
          { "type": "message", "username": "Roshan", "text": "...", "timestamp": "..." }
        Anything else is broadcast as-is.
        """
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            # not JSON -> just broadcast
            await self.broadcast(room, data_str)
            return

        msg_type = data.get("type", "message")

        if msg_type == "join":
            username = (data.get("username") or "Anon").strip()
            if not username:
                username = "Anon"
            self.update_username(websocket, username)
            # we don't broadcast join event as a chat message (you could if you want)
        elif msg_type == "message":
            # just broadcast the same JSON string back to all clients
            await self.broadcast(room, data_str)
        else:
            # unknown type -> ignore or log
            pass

    def get_active_clients(self) -> list[dict]:
        """
        Return a list of dicts:
        [
          {"ip": "x.x.x.x", "room": "lobby", "username": "Roshan"},
          ...
        ]
        """
        return list(self.clients.values())


manager = ConnectionManager()


@app.get("/", include_in_schema=False)
async def root():
    # default room = lobby
    return RedirectResponse(url="/room/lobby")


@app.get("/room/{room_name}", response_class=HTMLResponse)
async def get_room(request: Request, room_name: str):
    # render chat page for a room
    return templates.TemplateResponse(
        "index.html", {"request": request, "room_name": room_name}
    )


@app.websocket("/ws/{room_name}")
async def websocket_endpoint(websocket: WebSocket, room_name: str):
    await manager.connect(room_name, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle_message(room_name, websocket, data)
    except WebSocketDisconnect:
        manager.disconnect(room_name, websocket)


@app.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin", response_class=HTMLResponse)
async def admin_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        active_clients = manager.get_active_clients()
        return templates.TemplateResponse(
            "admin.html",
            {"request": request, "clients": active_clients, "total": len(active_clients)},
        )
    else:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Wrong password!"}
        )
