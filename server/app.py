"""FastAPI app: JSON API (API.md section 8) plus static client and maps."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .games import ApiError, Games

ROOT = Path(__file__).resolve().parent.parent


def create_app(save_dir=None):
    games = Games(save_dir)

    async def ticker():
        while True:
            await asyncio.sleep(1)
            games.tick()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(ticker())
        yield
        task.cancel()

    app = FastAPI(lifespan=lifespan)
    app.state.games = games

    @app.exception_handler(ApiError)
    async def api_error(request: Request, err: ApiError):
        return JSONResponse({"detail": err.detail}, status_code=err.status)

    @app.get("/api/maps")
    def maps():
        return games.maps()

    @app.post("/api/games")
    def create(body: dict = Body(...)):
        return games.create(body.get("map"), body.get("rules") or {})

    @app.get("/api/games/{gid}/lobby")
    def lobby(gid: str, token: str = ""):
        return games.lobby(gid, token)

    @app.post("/api/games/{gid}/join")
    def join(gid: str, body: dict = Body(...)):
        return games.join(gid, body.get("name"), body.get("nation"), body.get("host_token"))

    @app.post("/api/games/{gid}/start")
    def start(gid: str, token: str = ""):
        return games.start(gid, token)

    @app.get("/api/games/{gid}/state")
    def state(gid: str, token: str = "", since: int | None = None):
        return games.view(gid, token, since)

    @app.put("/api/games/{gid}/orders")
    def orders(gid: str, token: str = "", body: dict = Body(...)):
        return games.put_orders(gid, token, body.get("orders"))

    @app.post("/api/games/{gid}/ready")
    def ready(gid: str, token: str = "", body: dict = Body(...)):
        return games.set_ready(gid, token, body.get("ready"))

    @app.post("/api/games/{gid}/preview")
    def preview(gid: str, token: str = "", body: dict = Body(...)):
        return games.preview(gid, token, body)

    @app.get("/")
    def index():
        return FileResponse(ROOT / "client" / "index.html")

    app.mount("/client", StaticFiles(directory=ROOT / "client"), name="client")
    app.mount("/maps", StaticFiles(directory=ROOT / "maps"), name="maps")
    return app


app = create_app()
