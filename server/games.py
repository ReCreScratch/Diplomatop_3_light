"""Game registry: lobby, players/tokens, orders, ready state, timer, resolution."""
import json
import random
import secrets
import threading
import time
from pathlib import Path

import engine
from . import storage

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / "maps"


# Chat limits (technical safety caps, not gameplay rules)
CHAT_MAX_LEN = 1000
CHAT_MAX_MARKS = 20


class ApiError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail


class Game:
    """One game. All fields are JSON-safe so save/load is trivial."""

    def __init__(self, data):
        self.id = data["id"]
        self.map = data["map"]
        self.overrides = data["overrides"]
        self.status = data["status"]
        self.host_token = data["host_token"]
        self.tokens = data["tokens"]            # token -> nation
        self.joined = data["joined"]            # nation -> player name
        self.host = data["host"]                # nation of the host player or None
        self.orders = data["orders"]            # nation -> [order]
        self.ready = data["ready"]              # nation -> bool
        self.version = data["version"]
        self.last_turn = data["last_turn"]
        self.deadline = data["deadline"]        # epoch seconds or None
        self.chat = data.get("chat", [])        # [{id, from, to, text, marks, turn, ts}]
        self.state = engine.GameState.from_dict(data["state"]) if data["state"] else None

    def to_dict(self):
        return {"id": self.id, "map": self.map, "overrides": self.overrides, "status": self.status,
                "host_token": self.host_token, "tokens": self.tokens, "joined": self.joined,
                "host": self.host, "orders": self.orders, "ready": self.ready, "version": self.version,
                "last_turn": self.last_turn, "deadline": self.deadline, "chat": self.chat,
                "state": self.state.to_dict() if self.state else None}


class Games:
    def __init__(self, save_dir=None):
        self.save_dir = save_dir
        self.lock = threading.RLock()
        self.games = {}
        for data in storage.load_all(save_dir):
            self.games[data["id"]] = Game(data)

    # --- helpers -----------------------------------------------------
    def _save(self, game):
        game.version += 1
        storage.save(game.id, game.to_dict(), self.save_dir)

    def get(self, gid):
        game = self.games.get(gid)
        if not game:
            raise ApiError(404, "Spiel nicht gefunden.")
        return game

    def _nation(self, game, token):
        nation = game.tokens.get(token)
        if not nation:
            raise ApiError(403, "Ungültiger Token.")
        return nation

    def _theme(self, game):
        path = MAPS / game.map / "theme.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _map_data(self, name):
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
            raise ApiError(400, "Ungültige Karte.")
        try:
            return engine.load_map(MAPS / name)
        except engine.MapError as err:
            raise ApiError(400, str(err))

    def maps(self):
        return sorted(p.name for p in MAPS.iterdir() if (p / "map.json").exists())

    # --- lobby -------------------------------------------------------
    def create(self, map_name, overrides):
        with self.lock:
            self._map_data(map_name)
            gid = secrets.token_urlsafe(6)
            game = Game({"id": gid, "map": map_name, "overrides": overrides or {}, "status": "lobby",
                         "host_token": secrets.token_urlsafe(16), "tokens": {}, "joined": {}, "host": None,
                         "orders": {}, "ready": {}, "version": 0, "last_turn": None, "deadline": None,
                         "chat": [], "state": None})
            self.games[gid] = game
            self._save(game)
            return {"game_id": gid, "host_token": game.host_token}

    def _is_host(self, game, token):
        me = game.tokens.get(token)
        return bool(token) and (token == game.host_token or (me is not None and me == game.host))

    def lobby(self, gid, token):
        with self.lock:
            game = self.get(gid)
            map_data = self._map_data(game.map)
            nations = {c: n["name"] for c, n in map_data["nations"].items()}
            rules = engine.load_rules(map_data.get("rules", {}), game.overrides)
            return {"game_id": gid, "map": game.map, "status": game.status, "nations": nations,
                    "joined": dict(game.joined), "me": game.tokens.get(token),
                    "is_host": self._is_host(game, token), "host": game.host, "rules": rules}

    def join(self, gid, name, nation, host_token):
        with self.lock:
            game = self.get(gid)
            if game.status != "lobby":
                raise ApiError(400, "Das Spiel läuft bereits.")
            name = (name or "").strip() if isinstance(name, str) else ""
            if not name:
                raise ApiError(400, "Name fehlt.")
            if nation not in self._map_data(game.map)["nations"]:
                raise ApiError(400, "Unbekannte Nation.")
            if nation in game.joined:
                raise ApiError(400, "Nation ist schon vergeben.")
            token = secrets.token_urlsafe(16)
            game.tokens[token] = nation
            game.joined[nation] = name
            if host_token and host_token == game.host_token:
                game.host = nation
            self._save(game)
            return {"token": token}

    def start(self, gid, token):
        with self.lock:
            game = self.get(gid)
            if not self._is_host(game, token):
                raise ApiError(403, "Nur der Spielleiter darf starten.")
            if game.status != "lobby":
                raise ApiError(400, "Das Spiel läuft bereits.")
            if not game.joined:
                raise ApiError(400, "Mindestens ein Spieler nötig.")
            map_data = self._map_data(game.map)
            rules = engine.load_rules(map_data.get("rules", {}), game.overrides)
            game.state = engine.new_game(map_data, dict(game.joined), rules, random.randrange(2**31))
            game.status = "running"
            self._begin_turn(game)
            self._save(game)
            return {"ok": True}

    def _begin_turn(self, game):
        game.orders = {n: [] for n in game.joined}
        game.ready = {n: False for n in game.joined}
        secs = game.state.rules.get("turn_timer_seconds", 0)
        game.deadline = time.time() + secs if secs else None

    # --- play --------------------------------------------------------
    def _check_timer(self, game):
        if game.status == "running" and game.deadline and time.time() >= game.deadline:
            self._resolve(game)

    def tick(self):
        """Called every second by the background task."""
        with self.lock:
            for game in self.games.values():
                self._check_timer(game)

    def _resolve(self, game):
        turn = game.state.turn
        events = engine.resolve_turn(game.state, game.orders)
        game.last_turn = {"turn": turn, "events": events}
        self._begin_turn(game)
        self._save(game)

    def _running(self, gid, token):
        game = self.get(gid)
        nation = self._nation(game, token)
        self._check_timer(game)
        if game.status != "running":
            raise ApiError(400, "Das Spiel läuft noch nicht.")
        return game, nation

    def view(self, gid, token, since):
        with self.lock:
            game = self.get(gid)
            if game.status == "lobby":
                if since is not None and since == game.version:
                    return {"changed": False}
                return {"changed": True, "version": game.version, "status": "lobby"}
            nation = self._nation(game, token)
            self._check_timer(game)
            if since is not None and since == game.version:
                return {"changed": False}
            st = game.state
            my_orders = game.orders.get(nation, [])
            limit = st.rules["recruit_limit_per_province"] * st.players[nation]["provinces_at_turn_start"]
            remaining = max(0, round(game.deadline - time.time())) if game.deadline else None
            return {
                "changed": True, "version": game.version, "status": game.status, "me": nation,
                "is_host": self._is_host(game, token), "turn": st.turn, "timer_remaining": remaining,
                "player_order": st.player_order, "ready": dict(game.ready),
                "players": {n: {"name": p["name"]} for n, p in st.players.items()},
                "my_gold": st.players[nation]["gold"], "my_recruit_limit": limit, "rules": st.rules,
                "map": st.map, "theme": self._theme(game), "owners": st.owners, "armies": st.armies,
                "board": engine.board(st), "my_orders": my_orders,
                "order_errors": engine.validate_orders(st, nation, my_orders),
                "incoming": [], "last_turn": game.last_turn,
                "chat": [m for m in game.chat if m["to"] is None or nation in (m["from"], m["to"])],
            }

    def put_orders(self, gid, token, orders):
        with self.lock:
            game, nation = self._running(gid, token)
            if not isinstance(orders, list) or not all(isinstance(o, dict) for o in orders):
                raise ApiError(400, "Befehle ungültig.")
            game.orders[nation] = orders
            self._save(game)
            return {"errors": engine.validate_orders(game.state, nation, orders)}

    def set_ready(self, gid, token, ready):
        with self.lock:
            game, nation = self._running(gid, token)
            game.ready[nation] = bool(ready)
            if all(game.ready.values()):
                self._resolve(game)
            else:
                self._save(game)
            return {"ok": True}

    def preview(self, gid, token, body):
        with self.lock:
            game, nation = self._running(gid, token)
            try:
                return engine.preview_move(game.state, nation, body["army"], body["count"], body["path"],
                                           body.get("forced_march"))
            except (KeyError, TypeError, ValueError):
                raise ApiError(400, "Vorschau ungültig.")

    # --- chat --------------------------------------------------------
    def _clean_marks(self, game, marks):
        if not isinstance(marks, list) or len(marks) > CHAT_MAX_MARKS:
            raise ApiError(400, f"Höchstens {CHAT_MAX_MARKS} Markierungen pro Nachricht.")
        cells = game.state.cells

        def field(f):
            ok = (isinstance(f, (list, tuple)) and len(f) == 2
                  and all(isinstance(v, int) and not isinstance(v, bool) for v in f) and (f[0], f[1]) in cells)
            if not ok:
                raise ApiError(400, "Markierung liegt außerhalb der Karte.")
            return [f[0], f[1]]

        out = []
        for m in marks:
            kind = m.get("kind") if isinstance(m, dict) else None
            if kind == "field":
                out.append({"kind": "field", "f": field(m.get("f"))})
            elif kind == "arrow":
                path = m.get("path")
                if not isinstance(path, list) or not 2 <= len(path) <= 40:
                    raise ApiError(400, "Pfeil ungültig.")
                out.append({"kind": "arrow", "path": [field(f) for f in path]})
            else:
                raise ApiError(400, "Markierung ungültig.")
        return out

    def post_chat(self, gid, token, to, text, marks):
        with self.lock:
            game, nation = self._running(gid, token)
            if to is not None and (not isinstance(to, str) or to == nation or to not in game.joined):
                raise ApiError(400, "Ungültiger Empfänger.")
            text = text.strip() if isinstance(text, str) else ""
            if len(text) > CHAT_MAX_LEN:
                raise ApiError(400, f"Nachricht zu lang (höchstens {CHAT_MAX_LEN} Zeichen).")
            marks = self._clean_marks(game, [] if marks is None else marks)
            if not text and not marks:
                raise ApiError(400, "Nachricht ist leer.")
            msg = {"id": (game.chat[-1]["id"] + 1) if game.chat else 1, "from": nation, "to": to,
                   "text": text, "marks": marks, "turn": game.state.turn, "ts": int(time.time())}
            game.chat.append(msg)
            self._save(game)
            return {"ok": True, "message": msg}
