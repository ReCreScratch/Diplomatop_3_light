"""FastAPI app: JSON API (API.md section 8) plus static client and maps."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .games import ApiError, Games

ROOT = Path(__file__).resolve().parent.parent


def create_app(save_dir=None, maps_dir=None):
    games = Games(save_dir, maps_dir)

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

    @app.get("/api/rules")
    def default_rules():
        return games.default_rules()

    @app.put("/api/maps/{name}")
    def save_map(name: str, body: dict = Body(...)):
        return games.save_map(name, body.get("map"), body.get("theme"), body.get("theme_from"))

    @app.post("/api/games")
    def create(body: dict = Body(...)):
        return games.create(body.get("map"), body.get("rules") or {})

    @app.get("/api/games/{gid}/lobby")
    def lobby(gid: str, token: str = ""):
        return games.lobby(gid, token)

    @app.post("/api/games/{gid}/join")
    def join(gid: str, body: dict = Body(...)):
        return games.join(gid, body.get("name"), body.get("nation"), body.get("host_token"))

    @app.post("/api/games/{gid}/nation")
    def nation(gid: str, token: str = "", body: dict = Body(...)):
        return games.choose_nation(gid, token, body.get("nation"))

    @app.post("/api/games/{gid}/settings")
    def settings(gid: str, token: str = "", body: dict = Body(...)):
        return games.settings(gid, token, body.get("rules"), body.get("nation_mode"))

    @app.post("/api/games/{gid}/assign_random")
    def assign_random(gid: str, token: str = ""):
        return games.assign_random(gid, token)

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

    @app.post("/api/games/{gid}/chat")
    def chat(gid: str, token: str = "", body: dict = Body(...)):
        return games.post_chat(gid, token, body.get("to"), body.get("text"), body.get("marks"))

    @app.post("/api/games/{gid}/pause")
    def pause(gid: str, token: str = "", body: dict = Body(...)):
        return games.set_pause(gid, token, bool(body.get("paused")))

    @app.post("/api/games/{gid}/surrender")
    def surrender(gid: str, token: str = ""):
        return games.surrender(gid, token)

    @app.post("/api/games/{gid}/kick")
    def kick(gid: str, token: str = "", body: dict = Body(...)):
        return games.kick(gid, token, body.get("nation"), body.get("member"))

    @app.post("/api/games/{gid}/rejoin")
    def rejoin(gid: str, body: dict = Body(...)):
        return games.rejoin_request(gid, body.get("nation"), body.get("code"))

    @app.get("/api/games/{gid}/rejoin/{rid}")
    def rejoin_status(gid: str, rid: str):
        return games.rejoin_status(gid, rid)

    @app.post("/api/games/{gid}/rejoin/{rid}/answer")
    def rejoin_answer(gid: str, rid: str, token: str = "", body: dict = Body(...)):
        return games.rejoin_answer(gid, token, rid, bool(body.get("accept")))

    @app.get("/")
    def index():
        return FileResponse(ROOT / "client" / "index.html")

    @app.get("/editor")
    def editor():
        return FileResponse(ROOT / "client" / "editor.html")

    app.mount("/client", StaticFiles(directory=ROOT / "client"), name="client")
    app.mount("/maps", StaticFiles(directory=games.maps_dir), name="maps")
    return app


app = create_app()
