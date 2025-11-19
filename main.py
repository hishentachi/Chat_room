from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

templates = Jinja2Templates(directory="templates")


class ConnectionManager:
    def __init__(self):
        # room_name -> list of WebSocket connections
        self.rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, room: str, websocket: WebSocket):
        await websocket.accept()
        if room not in self.rooms:
            self.rooms[room] = []
        self.rooms[room].append(websocket)

    def disconnect(self, room: str, websocket: WebSocket):
        if room in self.rooms:
            if websocket in self.rooms[room]:
                self.rooms[room].remove(websocket)
            if not self.rooms[room]:
                # remove empty room
                del self.rooms[room]

    async def broadcast(self, room: str, message: str):
        if room not in self.rooms:
            return
        for connection in self.rooms[room]:
            await connection.send_text(message)


manager = ConnectionManager()


@app.get("/", include_in_schema=False)
async def root():
    # default room = lobby
    return RedirectResponse(url="/room/lobby")


@app.get("/room/{room_name}", response_class=HTMLResponse)
async def get_room(request: Request, room_name: str):
    # render same template with different room name
    return templates.TemplateResponse(
        "index.html", {"request": request, "room_name": room_name}
    )


@app.websocket("/ws/{room_name}")
async def websocket_endpoint(websocket: WebSocket, room_name: str):
    await manager.connect(room_name, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(room_name, data)
    except WebSocketDisconnect:
        manager.disconnect(room_name, websocket)
