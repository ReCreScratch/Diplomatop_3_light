"""Game registry: lobby, players/tokens, orders, ready state, timer, resolution."""
import copy
import json
import random
import secrets
import threading
import time
from pathlib import Path

import engine
from engine.orders import snapshot
from . import maps, storage

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / "maps"


# Technical limits (not gameplay rules)
CHAT_MAX_LEN = 1000
CHAT_MAX_MARKS = 20
NAME_MAX = 30
NOTICE_KEEP = 30                 # public notices kept per game
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # rejoin code: no look-alike characters
CODE_LEN = 6
REJOIN_FAILS = 8                 # wrong rejoin codes allowed per window ...
REJOIN_WINDOW = 60               # ... of this many seconds
REJOIN_TTL = 600                 # an unanswered rejoin request is dropped after this many seconds
SETTING_MAX = 1_000_000
# Rules the host may change in the lobby (key -> int only?). Everything else comes from rules/default.json and the map.
LOBBY_SETTINGS = {"turn_timer_seconds": True, "start_gold": False, "victory_hold_turns": True,
                  "max_alliance_size": True, "alliance_min_turns": True, "idle_warning_seconds": True,
                  "nation_reveal_pause_seconds": True}
NATION_MODES = ("choose", "random")


class ApiError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail


def new_code():
    """Short secret for rejoining without the personal link."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


class Game:
    """One game. All fields are JSON-safe so save/load is trivial."""

    def __init__(self, data):
        self.id = data["id"]
        self.map = data["map"]
        self.overrides = data["overrides"]
        self.status = data["status"]
        self.host_token = data["host_token"]
        if "members" in data:
            self.members = data["members"]      # [{id, token, name, nation|None, host}] in join order
        else:                                   # save from before milestone 4: tokens + joined + host
            self.members = [{"id": secrets.token_urlsafe(4), "token": t, "name": data["joined"].get(n, n), "nation": n,
                             "host": n == data.get("host")} for t, n in data["tokens"].items()]
        self.nation_mode = data.get("nation_mode", "choose")
        self.reveal = data.get("reveal")        # {started, pause, order: [{nation, name}]} of the last random draw
        self.orders = data["orders"]            # nation -> [order]
        self.ready = data["ready"]              # nation -> bool
        self.version = data["version"]
        self.last_turn = data["last_turn"]
        self.deadline = data["deadline"]        # epoch seconds or None (while paused: the deadline if it ran on)
        self.pause = data.get("pause")          # {by: nation|None, host: bool, at: epoch} or None
        self.pause_used = data.get("pause_used", [])   # nations that used their one pause
        self.notices = data.get("notices", [])  # public: [{id, turn, kind, text}]
        self.codes = data.get("codes", {})      # nation -> rejoin code
        self.rejoin = data.get("rejoin", {})    # request id -> {nation, ts, status, token}
        self.rejoin_fails = []                  # epoch seconds of wrong rejoin codes (not saved)
        self.chat = data.get("chat", [])        # [{id, from, to, text, marks, turn, ts}]
        self.state = engine.GameState.from_dict(data["state"]) if data["state"] else None

    # --- players: derived from members -------------------------------
    @property
    def tokens(self):
        return {m["token"]: m["nation"] for m in self.members if m["nation"]}

    @property
    def joined(self):
        return {m["nation"]: m["name"] for m in self.members if m["nation"]}

    @property
    def host(self):
        return next((m["nation"] for m in self.members if m["host"]), None)

    def member(self, token):
        return next((m for m in self.members if token and m["token"] == token), None)

    def member_of(self, nation):
        return next((m for m in self.members if m["nation"] == nation), None)

    def to_dict(self):
        return {"id": self.id, "map": self.map, "overrides": self.overrides, "status": self.status,
                "host_token": self.host_token, "members": self.members, "nation_mode": self.nation_mode,
                "reveal": self.reveal, "orders": self.orders, "ready": self.ready, "version": self.version,
                "last_turn": self.last_turn, "deadline": self.deadline, "pause": self.pause,
                "pause_used": self.pause_used, "notices": self.notices, "codes": self.codes, "rejoin": self.rejoin,
                "chat": self.chat, "state": self.state.to_dict() if self.state else None}


class Games:
    def __init__(self, save_dir=None, maps_dir=None):
        self.save_dir = save_dir
        self.maps_dir = Path(maps_dir) if maps_dir else MAPS
        self.lock = threading.RLock()
        self.games = {}
        for data in storage.load_all(save_dir):
            game = Game(data)
            self.games[data["id"]] = game
            if game.status != "lobby" and game.state:
                self._ensure_codes(game)

    # --- helpers -----------------------------------------------------
    def _save(self, game):
        game.version += 1
        storage.save(game.id, game.to_dict(), self.save_dir)

    def get(self, gid):
        game = self.games.get(gid)
        if not game:
            raise ApiError(404, "Spiel nicht gefunden.")
        return game

    def _member(self, game, token):
        member = game.member(token)
        if not member:
            raise ApiError(403, "Ungültiger Token.")
        return member

    def _nation(self, game, token):
        nation = self._member(game, token)["nation"]
        if not nation:
            raise ApiError(403, "Du hast noch keine Nation.")
        return nation

    def _theme(self, game):
        path = self.maps_dir / game.map / "theme.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _map_data(self, name):
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
            raise ApiError(400, "Ungültige Karte.")
        try:
            return engine.load_map(self.maps_dir / name)
        except engine.MapError as err:
            raise ApiError(400, str(err))

    def maps(self):
        return sorted(p.name for p in self.maps_dir.iterdir() if (p / "map.json").exists())

    def default_rules(self):
        """rules/default.json (the editor shows these as placeholders for map rule overrides)."""
        return engine.load_rules({}, {})

    def save_map(self, name, map_data, theme, theme_from):
        """Editor: validate and store a map (server/maps.py)."""
        with self.lock:
            error = maps.save_map(self.maps_dir, name, map_data, theme, theme_from)
            if error:
                raise ApiError(400, error)
            return {"ok": True, "name": name}

    def _rules(self, game, map_data=None):
        map_data = map_data or self._map_data(game.map)
        return engine.load_rules(map_data.get("rules", {}), game.overrides)

    def _notice(self, game, kind, text):
        """A public message for everybody (surrender, kick, pause, timeouts)."""
        turn = game.state.turn if game.state else 0
        game.notices.append({"id": (game.notices[-1]["id"] + 1) if game.notices else 1, "turn": turn,
                             "kind": kind, "text": text})
        del game.notices[:-NOTICE_KEEP]

    def _label(self, game, nation):
        """'Felix (Frankreich)' for notices."""
        name = (game.member_of(nation) or {}).get("name") or nation
        return f"{name} ({game.state.nation_name(nation)})"

    def _ensure_codes(self, game):
        """Every member of a running game has a rejoin code (older saves get theirs here)."""
        changed = False
        for m in game.members:
            if m["nation"] and m["nation"] not in game.codes:
                game.codes[m["nation"]] = new_code()
                changed = True
        if changed:
            storage.save(game.id, game.to_dict(), self.save_dir)

    # --- lobby -------------------------------------------------------
    def create(self, map_name, overrides):
        with self.lock:
            self._map_data(map_name)
            gid = secrets.token_urlsafe(6)
            game = Game({"id": gid, "map": map_name, "overrides": overrides or {}, "status": "lobby",
                         "host_token": secrets.token_urlsafe(16), "members": [],
                         "orders": {}, "ready": {}, "version": 0, "last_turn": None, "deadline": None,
                         "chat": [], "state": None})
            self.games[gid] = game
            self._save(game)
            return {"game_id": gid, "host_token": game.host_token}

    def _is_host(self, game, token):
        me = game.member(token)
        return bool(token) and (token == game.host_token or bool(me and me["host"]))

    def _need_host(self, game, token, what):
        if not self._is_host(game, token):
            raise ApiError(403, f"Nur der Spielleiter darf das {what}.")

    def _need_lobby(self, game):
        if game.status != "lobby":
            raise ApiError(400, "Das Spiel läuft bereits.")

    def _reveal_view(self, game):
        """The last random draw as the clients animate it: entries appear one by one, `pause` seconds apart
        (the first after one pause); elapsed = seconds since the draw."""
        rv = game.reveal
        if not rv:
            return None
        return {"elapsed": round(time.time() - rv["started"], 2), "pause": rv["pause"], "entries": rv["order"]}

    def _reveal_done(self, game):
        rv = game.reveal
        return not rv or time.time() - rv["started"] >= rv["pause"] * len(rv["order"])

    def lobby(self, gid, token):
        with self.lock:
            game = self.get(gid)
            map_data = self._map_data(game.map)
            nations = {c: n["name"] for c, n in map_data["nations"].items()}
            me = game.member(token)
            state = game.state
            return {"game_id": gid, "map": game.map, "status": game.status, "nations": nations,
                    "joined": dict(game.joined), "me": me["nation"] if me else None,
                    "me_name": me["name"] if me else None, "is_host": self._is_host(game, token), "host": game.host,
                    "players": [{"id": m["id"], "name": m["name"], "nation": m["nation"], "host": m["host"],
                                 "you": m is me} for m in game.members],
                    "ai": sorted(state.ai) if state else [], "nation_mode": game.nation_mode,
                    "reveal": self._reveal_view(game), "editable": list(LOBBY_SETTINGS),
                    "rules": self._rules(game, map_data)}

    def join(self, gid, name, nation, host_token):
        """Join the lobby. The nation is optional here: it can be chosen later or handed out at random."""
        with self.lock:
            game = self.get(gid)
            self._need_lobby(game)
            name = (name or "").strip() if isinstance(name, str) else ""
            if not name:
                raise ApiError(400, "Name fehlt.")
            if len(name) > NAME_MAX:
                raise ApiError(400, f"Name zu lang (höchstens {NAME_MAX} Zeichen).")
            nations = self._map_data(game.map)["nations"]
            if nation is not None and nation not in nations:
                raise ApiError(400, "Unbekannte Nation.")
            if nation is not None and nation in game.joined:
                raise ApiError(400, "Nation ist schon vergeben.")
            if len(game.members) >= len(nations):
                raise ApiError(400, "Das Spiel ist voll.")
            is_host = bool(host_token) and host_token == game.host_token and not any(m["host"] for m in game.members)
            member = {"id": secrets.token_urlsafe(4), "token": secrets.token_urlsafe(16), "name": name,
                      "nation": nation, "host": is_host}
            game.members.append(member)
            game.reveal = None
            self._save(game)
            return {"token": member["token"]}

    def choose_nation(self, gid, token, nation):
        """Lobby: pick a free nation (None = give it back). Not in random mode (the host draws them)."""
        with self.lock:
            game = self.get(gid)
            self._need_lobby(game)
            member = self._member(game, token)
            if game.nation_mode == "random":
                raise ApiError(400, "Der Spielleiter verteilt die Nationen zufällig.")
            if nation is not None:
                if nation not in self._map_data(game.map)["nations"]:
                    raise ApiError(400, "Unbekannte Nation.")
                if game.member_of(nation) and game.member_of(nation) is not member:
                    raise ApiError(400, "Nation ist schon vergeben.")
            member["nation"] = nation
            game.reveal = None
            self._save(game)
            return {"ok": True}

    def settings(self, gid, token, rules, nation_mode):
        """Lobby: the host changes the allowed rule settings and how nations are handed out."""
        with self.lock:
            game = self.get(gid)
            self._need_host(game, token, "einstellen")
            self._need_lobby(game)
            changes = {}
            for key, value in (rules or {}).items():
                if key not in LOBBY_SETTINGS:
                    raise ApiError(400, f"Einstellung nicht änderbar: {key}")
                ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= SETTING_MAX
                if ok and LOBBY_SETTINGS[key]:
                    ok = value == int(value)
                if not ok:
                    raise ApiError(400, f"Ungültiger Wert für {key}.")
                changes[key] = int(value) if LOBBY_SETTINGS[key] else value
            if nation_mode is not None and nation_mode not in NATION_MODES:
                raise ApiError(400, "Ungültiger Modus.")
            game.overrides.update(changes)
            if nation_mode is not None:
                game.nation_mode = nation_mode
            self._save(game)
            return {"ok": True}

    def assign_random(self, gid, token):
        """Lobby: the host hands out all nations at random; the draw is revealed one by one (clients animate it)."""
        with self.lock:
            game = self.get(gid)
            self._need_host(game, token, "auslosen")
            self._need_lobby(game)
            map_data = self._map_data(game.map)
            if not game.members:
                raise ApiError(400, "Noch keine Spieler.")
            nations = list(map_data["nations"])
            if len(game.members) > len(nations):
                raise ApiError(400, "Mehr Spieler als Nationen.")
            rng = random.SystemRandom()
            rng.shuffle(nations)
            for member, nation in zip(game.members, nations):
                member["nation"] = nation
            order = [{"nation": m["nation"], "name": m["name"]} for m in game.members]
            rng.shuffle(order)
            game.reveal = {"started": time.time(), "pause": self._rules(game, map_data)["nation_reveal_pause_seconds"],
                           "order": order}
            self._save(game)
            return {"ok": True}

    def start(self, gid, token):
        with self.lock:
            game = self.get(gid)
            self._need_host(game, token, "starten")
            self._need_lobby(game)
            if not game.members:
                raise ApiError(400, "Mindestens ein Spieler nötig.")
            if any(not m["nation"] for m in game.members):
                raise ApiError(400, "Alle Spieler brauchen eine Nation.")
            if not self._reveal_done(game):
                raise ApiError(400, "Die Nationen werden noch aufgedeckt.")
            map_data = self._map_data(game.map)
            rules = self._rules(game, map_data)
            unpicked = [c for c in map_data["nations"] if c not in game.joined]   # nobody plays them: AI ruleset (8.2)
            game.state = engine.new_game(map_data, dict(game.joined), rules, random.randrange(2**31), ai=unpicked)
            game.status = "running"
            game.codes = {n: new_code() for n in game.joined}
            self._begin_turn(game)
            self._save(game)
            return {"ok": True}

    def _begin_turn(self, game):
        game.orders = {n: [] for n in game.state.players}
        game.ready = {n: False for n in game.state.players}
        secs = game.state.rules.get("turn_timer_seconds", 0)
        now = time.time()
        game.deadline = now + secs if secs else None
        if game.pause:   # the new turn's timer starts frozen
            game.pause["at"] = now

    # --- timer and pause ---------------------------------------------
    def _remaining(self, game):
        """Seconds left on the turn timer (frozen while paused) or None without a timer."""
        if not game.deadline:
            return None
        return max(0, game.deadline - (game.pause["at"] if game.pause else time.time()))

    def _check_timer(self, game):
        if game.status == "running" and game.deadline and not game.pause and time.time() >= game.deadline:
            self._resolve(game, [n for n, r in game.ready.items() if not r])

    def tick(self):
        """Called every second by the background task."""
        with self.lock:
            for game in self.games.values():
                self._check_timer(game)

    def set_pause(self, gid, token, paused):
        """Pause or resume the turn timer. The host may pause any time and is the only one who ends a pause; every
        player has one pause per game."""
        with self.lock:
            game, member = self._running(gid, token, active=False)
            nation, host = member["nation"], self._is_host(game, token)
            if paused:
                if game.pause:
                    raise ApiError(400, "Es ist schon pausiert.")
                if not game.deadline:
                    raise ApiError(400, "Es läuft kein Zugtimer.")
                if not host:
                    if nation not in game.state.players:
                        raise ApiError(400, "Du schaust nur noch zu.")
                    if nation in game.pause_used:
                        raise ApiError(400, "Du hast deine Pause schon benutzt.")
                    game.pause_used.append(nation)
                game.pause = {"by": nation, "host": host, "at": time.time()}
                who = f"Der Spielleiter ({self._label(game, nation)})" if host else self._label(game, nation)
                self._notice(game, "pause", f"{who} hat die Pause gestartet.")
            else:
                if not host:
                    raise ApiError(403, "Nur der Spielleiter beendet die Pause.")
                if not game.pause:
                    raise ApiError(400, "Es ist nicht pausiert.")
                game.deadline += time.time() - game.pause["at"]   # the paused time does not count
                game.pause = None
                self._notice(game, "pause", "Die Pause ist beendet.")
            self._save(game)
            return {"ok": True}

    def _resolve(self, game, timed_out=()):
        turn = game.state.turn
        before = snapshot(game.state)
        order = list(game.state.player_order)
        events = engine.resolve_turn(game.state, game.orders)
        game.last_turn = {"turn": turn, "events": events, "before": before, "player_order": order,
                          "timeouts": list(timed_out)}
        self._begin_turn(game)
        if game.state.winner:   # victory: nothing is resolved any more
            game.status, game.deadline, game.pause = "finished", None, None
        elif timed_out:
            self._notice(game, "timeout",
                         "Zeit überschritten: " + ", ".join(self._label(game, n) for n in timed_out) + ".")
        self._save(game)

    def _running(self, gid, token, finished_ok=False, active=True):
        """(game, member) of a running game. active: the caller must still play (not surrendered)."""
        game = self.get(gid)
        member = self._member(game, token)
        if not member["nation"]:
            raise ApiError(403, "Du hast noch keine Nation.")
        self._check_timer(game)
        if game.status == "finished" and finished_ok:
            return game, member
        if game.status == "finished":
            raise ApiError(400, "Das Spiel ist beendet.")
        if game.status != "running":
            raise ApiError(400, "Das Spiel läuft noch nicht.")
        if active and member["nation"] not in game.state.players:
            raise ApiError(400, "Du schaust nur noch zu.")
        return game, member

    def _diplomacy_view(self, st, nation):
        """Public alliances / do-not-attack marks and the caller's own invitations and sale offers
        (nation None = spectator: nothing of his own)."""
        offers = [o for o in st.offers if st.owners.get(o["province"]) == o["from"]]   # seller still owns it
        return {
            "alliances": st.alliances, "no_attack": st.no_attack,
            "invitations": {"incoming": [i for i in st.invitations if i["to"] == nation],
                            "outgoing": [i for i in st.invitations if i["from"] == nation]},
            "offers": {"incoming": [o for o in offers if o["to"] == nation],
                       "outgoing": [o for o in offers if o["from"] == nation]},
            "victory": {"leader": st.victory, "need": st.rules["victory_hold_turns"]}, "winner": st.winner,
        }

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
            playing = nation in st.players
            my_orders = game.orders.get(nation, []) if playing else []
            limit = st.rules["recruit_limit_per_province"] * st.players[nation]["provinces_at_turn_start"] if playing else 0
            remaining = self._remaining(game)
            host = self._is_host(game, token)
            pause = game.pause and {"by": game.pause["by"], "host": game.pause["host"],
                                    "name": (game.member_of(game.pause["by"]) or {}).get("name")}
            return {
                "changed": True, "version": game.version, "status": game.status,
                "me": nation if playing else None, "spectator": not playing, "my_nation": nation,
                "is_host": host, "turn": st.turn, "timer_remaining": None if remaining is None else round(remaining),
                "pause": pause, "pause_available": bool(playing and game.deadline and nation not in game.pause_used
                                                        and not game.pause),
                "player_order": st.player_order, "ready": dict(game.ready),
                "players": {n: {"name": p["name"]} for n, p in st.players.items()},
                "ai": {n: {"reason": a["reason"], "name": a["name"]} for n, a in st.ai.items()},
                "my_gold": st.players[nation]["gold"] if playing else None, "my_recruit_limit": limit,
                "rules": st.rules,
                "map": st.map, "theme": self._theme(game), "owners": st.owners,
                "armies": {i: a if a["owner"] == nation else {k: v for k, v in a.items() if k != "route"}
                           for i, a in st.armies.items()},   # foreign routes are secret
                "board": engine.board(st), "my_orders": my_orders,
                "order_errors": engine.validate_orders(st, nation, my_orders) if playing else [],
                "incoming": [], "last_turn": game.last_turn, **self._diplomacy_view(st, nation if playing else None),
                "chat": [m for m in game.chat if m["to"] is None or nation in (m["from"], m["to"])],
                "notices": game.notices, "my_rejoin_code": game.codes.get(nation) if playing else None,
                "rejoin_requests": self._rejoin_list(game) if host else [],
                "members": {m["nation"]: m["name"] for m in game.members if m["nation"]},
            }

    def put_orders(self, gid, token, orders):
        with self.lock:
            game, member = self._running(gid, token)
            nation = member["nation"]
            if not isinstance(orders, list) or not all(isinstance(o, dict) for o in orders):
                raise ApiError(400, "Befehle ungültig.")
            game.orders[nation] = orders
            self._save(game)
            return {"errors": engine.validate_orders(game.state, nation, orders)}

    def set_ready(self, gid, token, ready):
        with self.lock:
            game, member = self._running(gid, token)
            game.ready[member["nation"]] = bool(ready)
            if all(game.ready.values()):
                self._resolve(game)
            else:
                self._save(game)
            return {"ok": True}

    def preview(self, gid, token, body):
        with self.lock:
            game, member = self._running(gid, token)
            try:
                return engine.preview_move(game.state, member["nation"], body["army"], body["count"], body["path"],
                                           body.get("forced_march"))
            except (KeyError, TypeError, ValueError):
                raise ApiError(400, "Vorschau ungültig.")

    # --- surrender, kick ---------------------------------------------
    def _hand_to_ai(self, game, nation, reason):
        """The nation follows the AI ruleset from now on; its orders are gone. If everybody left, the game ends;
        if all remaining players are ready, the turn resolves."""
        events = []
        engine.make_ai(game.state, nation, reason, events)
        self._notice(game, reason, events[-1]["text"])
        game.orders.pop(nation, None)
        game.ready.pop(nation, None)
        if not game.state.players:
            game.status, game.deadline, game.pause = "finished", None, None
            self._notice(game, "end", "Alle Spieler haben das Spiel verlassen.")
            self._save(game)
        elif all(game.ready.values()):
            self._resolve(game)
        else:
            self._save(game)

    def surrender(self, gid, token):
        """A player gives up and keeps watching; the nation follows the AI ruleset (RULES.md 8.1)."""
        with self.lock:
            game, member = self._running(gid, token)
            self._hand_to_ai(game, member["nation"], "surrender")
            return {"ok": True}

    def kick(self, gid, token, nation=None, member_id=None):
        """The host removes a player. In the lobby the player is simply gone; in a running game the token becomes
        invalid and the nation follows the AI ruleset."""
        with self.lock:
            game = self.get(gid)
            self._need_host(game, token, "entfernen")
            target = next((m for m in game.members
                           if (nation and m["nation"] == nation) or (member_id and m["id"] == member_id)), None)
            if not target:
                raise ApiError(400, "Spieler nicht gefunden.")
            if target["host"] or target["token"] == token:
                raise ApiError(400, "Der Spielleiter kann sich nicht selbst entfernen.")
            if game.status == "finished":
                raise ApiError(400, "Das Spiel ist beendet.")
            game.members.remove(target)
            game.reveal = None
            nation = target["nation"]
            game.rejoin = {r: q for r, q in game.rejoin.items() if q["nation"] != nation}
            if game.status == "running" and nation in game.state.players:
                self._hand_to_ai(game, nation, "kick")
            else:
                if game.status == "running":   # a spectator: the nation already is AI
                    self._notice(game, "kick", f"{target['name']} wurde vom Spielleiter entfernt.")
                self._save(game)
            return {"ok": True}

    # --- rejoin without the personal link (G62) ---------------------
    def _reissue(self, game, member):
        """New token for a member; the old one stops working at once. Orders and ready state stay (keyed by nation)."""
        member["token"] = secrets.token_urlsafe(16)
        game.rejoin = {r: q for r, q in game.rejoin.items() if q["nation"] != member["nation"]}
        return member["token"]

    def _rejoinable(self, game, nation):
        member = game.member_of(nation) if isinstance(nation, str) else None
        if game.status != "running" or not member or nation not in game.state.players:
            raise ApiError(400, "Diese Nation kann nicht neu betreten werden.")
        return member

    def rejoin_request(self, gid, nation, code):
        """With a rejoin code: get a new token at once. Without: ask the host (answer via rejoin_status)."""
        with self.lock:
            game = self.get(gid)
            member = self._rejoinable(game, nation)
            now = time.time()
            if code is not None:
                game.rejoin_fails = [t for t in game.rejoin_fails if now - t < REJOIN_WINDOW]
                if len(game.rejoin_fails) >= REJOIN_FAILS:
                    raise ApiError(400, "Zu viele falsche Codes. Bitte kurz warten.")
                if not isinstance(code, str) or code.strip().upper() != game.codes.get(nation):
                    game.rejoin_fails.append(now)
                    raise ApiError(403, "Falscher Code.")
                token = self._reissue(game, member)
                game.codes[nation] = new_code()   # a used code is void
                self._save(game)
                return {"token": token}
            game.rejoin = {r: q for r, q in game.rejoin.items()
                           if q["nation"] != nation and now - q["ts"] < REJOIN_TTL}
            rid = secrets.token_urlsafe(9)
            game.rejoin[rid] = {"nation": nation, "ts": now, "status": "pending", "token": None}
            self._save(game)
            return {"request_id": rid}

    def rejoin_status(self, gid, rid):
        """The requester asks: pending / declined / approved (with the new token, delivered once)."""
        with self.lock:
            game = self.get(gid)
            req = game.rejoin.get(rid)
            if not req:
                raise ApiError(404, "Anfrage nicht gefunden.")
            if req["status"] == "pending":
                return {"status": "pending"}
            del game.rejoin[rid]
            self._save(game)
            return {"status": req["status"], **({"token": req["token"]} if req["status"] == "approved" else {})}

    def _rejoin_list(self, game):
        return [{"id": r, "nation": q["nation"], "name": (game.member_of(q["nation"]) or {}).get("name"),
                 "ts": int(q["ts"])} for r, q in game.rejoin.items() if q["status"] == "pending"]

    def rejoin_answer(self, gid, token, rid, accept):
        """The host confirms or declines a rejoin request."""
        with self.lock:
            game = self.get(gid)
            self._need_host(game, token, "bestätigen")
            req = game.rejoin.get(rid)
            if not req or req["status"] != "pending":
                raise ApiError(404, "Anfrage nicht gefunden.")
            if accept:
                member = self._rejoinable(game, req["nation"])
                new = self._reissue(game, member)   # also drops the nation's requests, so store the answer after
                game.rejoin[rid] = {**req, "status": "approved", "token": new}
                self._notice(game, "rejoin", f"{self._label(game, req['nation'])} ist wieder da.")
            else:
                req["status"] = "declined"
            self._save(game)
            return {"ok": True}

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
            game, member = self._running(gid, token, finished_ok=True)
            nation = member["nation"]
            if nation not in game.state.players:
                raise ApiError(400, "Du schaust nur noch zu.")
            if to is not None and (not isinstance(to, str) or to == nation or to not in game.state.players):
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
