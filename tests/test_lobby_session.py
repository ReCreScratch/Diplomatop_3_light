"""Milestone 4 server logic: lobby settings and random nations, timer and pause, surrender, kick, rejoin (G62)."""
import time

from fastapi.testclient import TestClient

from server.app import create_app
from server.games import Game


def make(tmp_path, maps_dir=None):
    return TestClient(create_app(tmp_path, maps_dir))


class Table:
    """A lobby on the Europa map with helper calls."""

    def __init__(self, tmp_path, rules=None):
        self.c = make(tmp_path)
        r = self.c.post("/api/games", json={"map": "europa", "rules": rules or {}}).json()
        self.gid, self.host_secret = r["game_id"], r["host_token"]
        self.games = self.c.app.state.games

    def url(self, what):
        return f"/api/games/{self.gid}/{what}"

    def join(self, name, nation=None, host=False):
        body = {"name": name, **({"nation": nation} if nation else {}), **({"host_token": self.host_secret} if host else {})}
        r = self.c.post(self.url("join"), json=body)
        return r.json()["token"] if r.status_code == 200 else r

    def post(self, what, token, **body):
        return self.c.post(self.url(what), params={"token": token}, json=body)

    def lobby(self, token=""):
        return self.c.get(self.url("lobby"), params={"token": token}).json()

    def state(self, token):
        return self.c.get(self.url("state"), params={"token": token}).json()

    @property
    def game(self):
        return self.games.games[self.gid]

    def ready(self, token, value=True):
        return self.post("ready", token, ready=value)

    def orders(self, token, orders):
        return self.c.put(self.url("orders"), params={"token": token}, json={"orders": orders})


def running(tmp_path, rules=None, nations=("GB", "FR", "DE")):
    t = Table(tmp_path, rules)
    tokens = [t.join(f"P{i}", n, host=i == 0) for i, n in enumerate(nations)]
    assert t.post("start", tokens[0]).status_code == 200
    return t, tokens


# --- lobby ----------------------------------------------------------------
def test_join_without_nation_then_choose(tmp_path):
    t = Table(tmp_path)
    host, anna = t.join("Felix", host=True), t.join("Anna")
    lob = t.lobby(host)
    assert [(p["name"], p["nation"], p["host"], p["you"]) for p in lob["players"]] == [("Felix", None, True, True), ("Anna", None, False, False)]
    assert lob["is_host"] and lob["me"] is None and lob["joined"] == {} and lob["nation_mode"] == "choose"
    assert t.post("nation", host, nation="GB").status_code == 200
    assert t.post("nation", anna, nation="GB").status_code == 400            # taken
    assert t.post("nation", anna, nation="XX").status_code == 400            # unknown
    assert t.post("nation", anna, nation="FR").status_code == 200
    assert t.post("nation", anna, nation="DE").status_code == 200            # switching frees FR
    lob = t.lobby(anna)
    assert lob["joined"] == {"GB": "Felix", "DE": "Anna"} and lob["me"] == "DE" and lob["host"] == "GB" and not lob["is_host"]
    assert t.post("nation", host, nation=None).status_code == 200            # give back
    assert t.lobby(host)["joined"] == {"DE": "Anna"}
    assert t.post("nation", "bad", nation="GB").status_code == 403


def test_join_checks(tmp_path):
    t = Table(tmp_path)
    assert t.join("  ", None).status_code == 400
    assert t.join("x" * 31, None).status_code == 400
    assert t.join("A", "XX").status_code == 400
    t.join("A", "GB")
    assert t.join("B", "GB").status_code == 400
    for i in range(6):
        t.join(f"P{i}")
    assert t.join("Zu viel").status_code == 400                               # 7 nations on Europa
    assert t.join("Host", host=True).status_code == 400                       # full


def test_only_the_first_joiner_with_the_host_secret_is_host(tmp_path):
    t = Table(tmp_path)
    assert t.join("A") and t.lobby(t.join("A", host=True))["host"] is None   # host member has no nation yet
    assert [p["host"] for p in t.lobby()["players"]] == [False, True]
    t.join("C", host=True)
    assert [p["host"] for p in t.lobby()["players"]] == [False, True, False]


def test_host_settings(tmp_path):
    t = Table(tmp_path)
    host, anna = t.join("Felix", host=True), t.join("Anna")
    ok = t.post("settings", host, rules={"turn_timer_seconds": 5 * 60 + 30, "start_gold": 12.5}, nation_mode="random")
    assert ok.status_code == 200
    lob = t.lobby(host)
    assert lob["rules"]["turn_timer_seconds"] == 330 and lob["rules"]["start_gold"] == 12.5 and lob["nation_mode"] == "random"
    assert "turn_timer_seconds" in lob["editable"]
    assert t.post("settings", anna, rules={"turn_timer_seconds": 1}).status_code == 403
    for bad in ({"division_cost": 1}, {"turn_timer_seconds": -1}, {"turn_timer_seconds": 1.5}, {"turn_timer_seconds": True},
                {"turn_timer_seconds": "9"}):
        assert t.post("settings", host, rules=bad).status_code == 400, bad
    assert t.post("settings", host, nation_mode="weird").status_code == 400
    assert t.lobby(host)["rules"]["turn_timer_seconds"] == 330
    assert t.post("nation", anna, nation="FR").status_code == 400            # random mode: the host draws
    t.post("settings", host, rules={"nation_reveal_pause_seconds": 0})
    t.post("assign_random", host)
    assert t.post("start", host).status_code == 200
    assert t.post("settings", host, rules={"start_gold": 1}).status_code == 400   # running


def test_random_assignment_and_reveal(tmp_path):
    t = Table(tmp_path)
    tokens = [t.join(f"P{i}", host=i == 0) for i in range(4)]
    t.post("settings", tokens[0], rules={"nation_reveal_pause_seconds": 30})
    assert t.post("assign_random", tokens[1]).status_code == 403
    assert t.post("start", tokens[0]).status_code == 400                      # nobody has a nation yet
    assert t.post("assign_random", tokens[0]).status_code == 200
    lob = t.lobby(tokens[2])
    nations = [p["nation"] for p in lob["players"]]
    assert all(nations) and len(set(nations)) == 4
    rv = lob["reveal"]
    assert rv["pause"] == 30 and len(rv["entries"]) == 4 and {e["nation"] for e in rv["entries"]} == set(nations)
    assert {e["name"] for e in rv["entries"]} == {f"P{i}" for i in range(4)} and 0 <= rv["elapsed"] < 5
    r = t.post("start", tokens[0])
    assert r.status_code == 400 and "aufgedeckt" in r.json()["detail"]       # still revealing
    t.game.reveal["started"] -= 30 * 4                                       # animation over
    assert t.post("start", tokens[0]).status_code == 200
    assert t.state(tokens[0])["status"] == "running"


def test_reveal_pause_zero_starts_at_once_and_changes_clear_the_reveal(tmp_path):
    t = Table(tmp_path)
    host = t.join("A", host=True)
    t.join("B")
    t.post("settings", host, rules={"nation_reveal_pause_seconds": 0})
    t.post("assign_random", host)
    assert t.lobby(host)["reveal"]["pause"] == 0
    t.join("C")
    assert t.lobby(host)["reveal"] is None                                    # a new player: draw again
    t.post("assign_random", host)
    assert t.post("start", host).status_code == 200


def test_cannot_draw_more_players_than_nations(tmp_path):
    t = Table(tmp_path)
    host = t.join("A", host=True)
    for i in range(6):
        t.join(f"P{i}")
    t.game.members.append({"id": "x", "token": "tx", "name": "extra", "nation": None, "host": False})   # forced 8th
    r = t.post("assign_random", host)
    assert r.status_code == 400 and "Nationen" in r.json()["detail"]


def test_start_needs_every_player_to_have_a_nation(tmp_path):
    t = Table(tmp_path)
    host = t.join("A", "GB", host=True)
    t.join("B")
    r = t.post("start", host)
    assert r.status_code == 400 and "Nation" in r.json()["detail"]


def test_unpicked_nations_become_ai_and_recruit(tmp_path):
    t, tokens = running(tmp_path, nations=("GB", "FR"))
    v = t.state(tokens[0])
    assert set(v["ai"]) == {"ES", "DE", "AT", "IT", "NA"} and all(a["reason"] == "unpicked" for a in v["ai"].values())
    assert v["owners"]["GB1"] == "GB" and all(o in v["ai"] or o in ("GB", "FR") for o in v["owners"].values())
    t.ready(tokens[0]), t.ready(tokens[1])
    v = t.state(tokens[0])
    ai_units = [a for a in v["armies"].values() if a["owner"] in v["ai"]]
    assert ai_units and all(a["divisions"] == 1 for a in ai_units)
    rows = {r["player"]: r for r in v["board"]}
    assert rows["DE"]["ai"] and rows["DE"]["name"] == "KI" and "ai" not in rows["GB"]


def test_lobby_kick_removes_the_player(tmp_path):
    t = Table(tmp_path)
    host, anna = t.join("Felix", "GB", host=True), t.join("Anna")
    lurker = [p for p in t.lobby(host)["players"] if p["name"] == "Anna"][0]
    assert t.post("kick", anna, member=lurker["id"]).status_code == 403
    assert t.post("kick", host, member=lurker["id"]).status_code == 200
    assert [p["name"] for p in t.lobby(host)["players"]] == ["Felix"]
    assert t.lobby(anna)["me_name"] is None                                   # token is gone
    assert t.post("kick", host, nation="GB").status_code == 400               # not himself


# --- timer and pause ------------------------------------------------------
def test_timeout_names_the_slow_players(tmp_path):
    t, (a, b, c) = running(tmp_path, {"turn_timer_seconds": 60})
    t.ready(a)
    t.game.deadline = 1
    v = t.state(b)
    assert v["turn"] == 2 and v["last_turn"]["timeouts"] == ["FR", "DE"]
    note = v["notices"][-1]
    assert note["kind"] == "timeout" and note["turn"] == 2 and "P1 (Frankreich)" in note["text"] and "P2" in note["text"]
    assert "P0" not in note["text"] and 0 < v["timer_remaining"] <= 60


def test_no_timeout_notice_when_everybody_was_ready(tmp_path):
    t, tokens = running(tmp_path, {"turn_timer_seconds": 60})
    for tok in tokens:
        t.ready(tok)
    v = t.state(tokens[0])
    assert v["turn"] == 2 and v["last_turn"]["timeouts"] == [] and v["notices"] == []


class Clock:
    """Moves time.time() forward in the server module (it shares the real time module, so only inside a test)."""

    def __init__(self, monkeypatch):
        self.offset, real = 0, time.time
        monkeypatch.setattr(time, "time", lambda: real() + self.offset)


def test_player_pause_freezes_the_timer_once_and_only_the_host_ends_it(tmp_path, monkeypatch):
    clock = Clock(monkeypatch)
    t, (host, p1, p2) = running(tmp_path, {"turn_timer_seconds": 60})
    v = t.state(p1)
    assert v["pause"] is None and v["pause_available"] is True
    assert t.post("pause", p1, paused=True).status_code == 200
    v = t.state(host)
    assert v["pause"] == {"by": "FR", "host": False, "name": "P1"} and v["pause_available"] is False
    assert "P1 (Frankreich)" in v["notices"][-1]["text"] and v["notices"][-1]["kind"] == "pause"
    r0 = v["timer_remaining"]
    clock.offset += 90                                                        # longer than the whole turn time
    assert t.state(host)["timer_remaining"] == r0                             # frozen at the pause moment
    assert t.state(p2)["turn"] == 1                                           # a pause blocks the timeout
    assert t.post("pause", p2, paused=False).status_code == 403               # only the host ends pauses
    assert t.post("pause", p1, paused=False).status_code == 403
    assert t.post("pause", p2, paused=True).status_code == 400                # already paused
    assert t.post("pause", host, paused=False).status_code == 200
    v = t.state(p1)
    assert v["pause"] is None and r0 - 1 <= v["timer_remaining"] <= r0       # the 90 paused seconds did not count
    clock.offset += 61
    assert t.state(p1)["turn"] == 2                                           # now it runs out
    assert t.post("pause", p1, paused=True).status_code == 400                # one pause per game
    assert t.state(p1)["pause_available"] is False and t.state(p2)["pause_available"] is True


def test_host_pause_is_unlimited_and_does_not_use_up_his_own(tmp_path):
    t, (host, p1, p2) = running(tmp_path, {"turn_timer_seconds": 60})
    for _ in range(3):
        assert t.post("pause", host, paused=True).status_code == 200
        v = t.state(host)
        assert v["pause"]["host"] is True and v["pause"]["by"] == "GB"
        assert t.post("pause", host, paused=False).status_code == 200
    assert t.state(host)["pause_available"] is True
    assert "Spielleiter" in t.state(host)["notices"][0]["text"]
    assert t.post("pause", host, paused=False).status_code == 400            # not paused


def test_pause_needs_a_timer_and_survives_turn_change_and_restart(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    r = t.post("pause", host, paused=True)
    assert r.status_code == 400 and "timer" in r.json()["detail"]
    t2, (h, a, b) = running(tmp_path / "b", {"turn_timer_seconds": 60})
    t2.post("pause", a, paused=True)
    for tok in (h, a, b):
        t2.ready(tok)                                                         # everybody ready during a pause: resolves
    v = t2.state(h)
    assert v["turn"] == 2 and v["pause"]["by"] == "FR" and 59 <= v["timer_remaining"] <= 60
    again = make(tmp_path / "b").get(t2.url("state"), params={"token": h}).json()
    assert again["pause"]["by"] == "FR"
    t2.game.deadline = 1
    assert t2.state(h)["turn"] == 2                                           # still paused after the turn change


def test_view_of_pause_is_public(tmp_path):
    t, (host, p1, p2) = running(tmp_path, {"turn_timer_seconds": 60})
    t.post("pause", p2, paused=True)
    assert t.state(p1)["pause"]["by"] == "DE" and t.state(p1)["pause"]["name"] == "P2"


# --- surrender ------------------------------------------------------------
def test_surrender_makes_a_spectator_and_the_nation_ai(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.orders(p1, [{"type": "recruit", "field": [0, 0], "count": 1}])
    assert t.post("surrender", p1).status_code == 200
    v = t.state(p1)
    assert v["me"] is None and v["spectator"] is True and v["my_nation"] == "FR" and v["my_gold"] is None
    assert v["my_orders"] == [] and v["order_errors"] == [] and "FR" not in v["players"] and v["ai"]["FR"]["reason"] == "surrender"
    assert "FR" not in v["ready"] and v["invitations"] == {"incoming": [], "outgoing": []}
    pub = t.state(host)
    assert pub["notices"][-1]["kind"] == "surrender" and "P1" in pub["notices"][-1]["text"] and "aufgegeben" in pub["notices"][-1]["text"]
    assert [r["name"] for r in pub["board"] if r["player"] == "FR"] == ["KI (P1)"]
    # read-only
    assert t.orders(p1, []).status_code == 400
    assert t.ready(p1).status_code == 400
    assert t.post("preview", p1, army="a1", count=1, path=[[1, 1]]).status_code == 400
    assert t.post("surrender", p1).status_code == 400
    assert t.post("chat", p1, to=None, text="hi").status_code == 400
    assert t.post("chat", host, to="FR", text="hi").status_code == 400        # no longer a player to talk to
    assert t.state(p1)["status"] == "running" and t.state(p1)["chat"] == []


def test_surrendered_players_do_not_count_for_all_ready_and_the_ai_recruits(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.post("surrender", p1)
    t.ready(host)
    assert t.state(host)["turn"] == 1
    t.ready(p2)                                                               # the rest is ready: resolves
    v = t.state(host)
    assert v["turn"] == 2 and set(v["ready"]) == {"GB", "DE"}
    fr_cities = [p["capital"] for p in v["map"]["provinces"].values() if p["owner"] == "FR"]
    fr_units = [a for a in v["armies"].values() if a["owner"] == "FR"]
    assert len(fr_units) == len(fr_cities) and all(a["divisions"] == 1 for a in fr_units)


def test_surrender_resolves_a_turn_when_the_rest_is_ready(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.ready(host), t.ready(p2)
    t.post("surrender", p1)
    assert t.state(host)["turn"] == 2


def test_last_player_surrendering_ends_the_game(tmp_path):
    t, (host, p1) = running(tmp_path, {"turn_timer_seconds": 60}, nations=("GB", "FR"))
    t.post("surrender", p1)
    assert t.state(host)["status"] == "running"
    t.post("surrender", host)
    v = t.state(host)
    assert v["status"] == "finished" and v["timer_remaining"] is None and v["spectator"]
    assert t.state(host)["notices"][-1]["kind"] == "end"


def test_spectators_keep_the_public_chat_readable(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.post("chat", host, to=None, text="Hallo")
    t.post("chat", host, to="FR", text="geheim")
    t.post("surrender", p1)
    assert [m["text"] for m in t.state(p1)["chat"]] == ["Hallo", "geheim"]     # he still reads what he took part in
    assert [m["text"] for m in t.state(p2)["chat"]] == ["Hallo"]


# --- kick -----------------------------------------------------------------
def test_kick_invalidates_the_token_and_hands_the_nation_to_the_ai(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.orders(p1, [])
    assert t.post("kick", p1, nation="DE").status_code == 403                 # not the host
    assert t.post("kick", host, nation="GB").status_code == 400               # not himself
    assert t.post("kick", host, nation="ES").status_code == 400               # nobody plays ES
    assert t.post("kick", host, nation="FR").status_code == 200
    assert t.c.get(t.url("state"), params={"token": p1}).status_code == 403
    assert t.orders(p1, []).status_code == 403
    v = t.state(host)
    assert v["ai"]["FR"]["reason"] == "kick" and "FR" not in v["players"] and "FR" not in v["ready"]
    assert v["notices"][-1]["kind"] == "kick" and "entfernt" in v["notices"][-1]["text"]
    t.ready(host), t.ready(p2)
    assert t.state(host)["turn"] == 2


def test_kicked_nations_cannot_be_rejoined(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.post("kick", host, nation="FR")
    r = t.c.post(t.url("rejoin"), json={"nation": "FR"})
    assert r.status_code == 400
    r = t.c.post(t.url("rejoin"), json={"nation": "FR", "code": "ABCDEF"})
    assert r.status_code == 400


def test_kicking_a_spectator_removes_him(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.post("surrender", p1)
    assert t.post("kick", host, nation="FR").status_code == 200
    assert t.c.get(t.url("state"), params={"token": p1}).status_code == 403
    assert t.state(host)["ai"]["FR"]["reason"] == "surrender"                  # stays AI as before


# --- rejoin ---------------------------------------------------------------
def test_rejoin_with_host_confirmation_keeps_orders_and_ready(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    orders = [{"type": "forced_march", "army": "a999", "on": True}]
    t.orders(p1, orders)
    t.ready(p1)
    rid = t.c.post(t.url("rejoin"), json={"nation": "FR"}).json()["request_id"]
    assert t.c.get(t.url(f"rejoin/{rid}")).json() == {"status": "pending"}
    v = t.state(host)
    assert v["rejoin_requests"] == [{"id": rid, "nation": "FR", "name": "P1", "ts": v["rejoin_requests"][0]["ts"]}]
    assert t.state(p1)["rejoin_requests"] == []                               # only the host sees requests
    assert t.post(f"rejoin/{rid}/answer", p1, accept=True).status_code == 403
    assert t.post(f"rejoin/{rid}/answer", host, accept=True).status_code == 200
    # old token dead at once, new token delivered once
    assert t.c.get(t.url("state"), params={"token": p1}).status_code == 403
    got = t.c.get(t.url(f"rejoin/{rid}")).json()
    assert got["status"] == "approved"
    new = got["token"]
    assert t.c.get(t.url(f"rejoin/{rid}")).status_code == 404
    v = t.state(new)
    assert v["me"] == "FR" and v["my_orders"] == orders and v["ready"]["FR"] is True
    assert t.state(host)["rejoin_requests"] == [] and "wieder da" in t.state(host)["notices"][-1]["text"]
    assert make(tmp_path).get(t.url("state"), params={"token": new}).json()["me"] == "FR"   # survives a restart


def test_rejoin_can_be_declined(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    rid = t.c.post(t.url("rejoin"), json={"nation": "DE"}).json()["request_id"]
    assert t.post(f"rejoin/{rid}/answer", host, accept=False).status_code == 200
    assert t.c.get(t.url(f"rejoin/{rid}")).json() == {"status": "declined"}
    assert t.c.get(t.url(f"rejoin/{rid}")).status_code == 404
    assert t.state(p2)["me"] == "DE"                                          # the old token still works
    assert t.post(f"rejoin/{rid}/answer", host, accept=True).status_code == 404


def test_rejoin_checks(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    assert t.c.post(t.url("rejoin"), json={"nation": "XX"}).status_code == 400
    assert t.c.post(t.url("rejoin"), json={"nation": "ES"}).status_code == 400   # AI nation
    assert t.c.post(t.url("rejoin"), json={}).status_code == 400
    t.post("surrender", p1)
    assert t.c.post(t.url("rejoin"), json={"nation": "FR"}).status_code == 400   # surrendered
    lobby_game = Table(tmp_path / "x")
    lobby_game.join("A", "GB", host=True)
    assert lobby_game.c.post(lobby_game.url("rejoin"), json={"nation": "GB"}).status_code == 400   # not running
    assert t.c.get(t.url("rejoin/none")).status_code == 404


def test_a_second_request_replaces_the_first_and_a_new_token_voids_requests(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    r1 = t.c.post(t.url("rejoin"), json={"nation": "FR"}).json()["request_id"]
    r2 = t.c.post(t.url("rejoin"), json={"nation": "FR"}).json()["request_id"]
    assert t.c.get(t.url(f"rejoin/{r1}")).status_code == 404 and len(t.state(host)["rejoin_requests"]) == 1
    t.post(f"rejoin/{r2}/answer", host, accept=True)
    assert t.c.get(t.url(f"rejoin/{r2}")).json()["status"] == "approved"


def test_rejoin_with_code_works_for_the_host_too(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    code = t.state(host)["my_rejoin_code"]
    assert len(code) == 6 and t.state(p1)["my_rejoin_code"] != code
    t.orders(host, [{"type": "forced_march", "army": "a999", "on": True}])
    t.ready(host)
    bad = t.c.post(t.url("rejoin"), json={"nation": "GB", "code": "WRONG1"})
    assert bad.status_code == 403
    r = t.c.post(t.url("rejoin"), json={"nation": "GB", "code": " " + code.lower() + " "})
    assert r.status_code == 200
    new = r.json()["token"]
    assert t.c.get(t.url("state"), params={"token": host}).status_code == 403
    v = t.state(new)
    assert v["is_host"] is True and v["me"] == "GB" and v["ready"]["GB"] is True and v["my_orders"]   # still host, orders kept
    assert v["my_rejoin_code"] != code                                        # a used code is void
    assert t.c.post(t.url("rejoin"), json={"nation": "GB", "code": code}).status_code == 403
    assert t.post("kick", new, nation="FR").status_code == 200                # host powers work with the new token


def test_rejoin_code_attempts_are_limited(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    code = t.state(p1)["my_rejoin_code"]
    for _ in range(8):
        assert t.c.post(t.url("rejoin"), json={"nation": "FR", "code": "NOPE00"}).status_code == 403
    r = t.c.post(t.url("rejoin"), json={"nation": "FR", "code": code})
    assert r.status_code == 400 and "viele" in r.json()["detail"]             # even the right code waits
    t.game.rejoin_fails = [time.time() - 61] * 8
    assert t.c.post(t.url("rejoin"), json={"nation": "FR", "code": code}).status_code == 200


def test_spectators_get_no_rejoin_code_and_codes_exist_for_old_saves(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    t.post("surrender", p1)
    assert t.state(p1)["my_rejoin_code"] is None
    t.game.codes.clear()
    reloaded = make(tmp_path)                                                  # _ensure_codes on load
    code = reloaded.get(t.url("state"), params={"token": host}).json()["my_rejoin_code"]
    assert code and len(code) == 6


# --- persistence ----------------------------------------------------------
def test_old_saves_with_tokens_and_joined_load_as_members(tmp_path):
    t, (host, p1, p2) = running(tmp_path)
    data = t.game.to_dict()
    members = data.pop("members")
    data["tokens"] = {m["token"]: m["nation"] for m in members}
    data["joined"] = {m["nation"]: m["name"] for m in members}
    data["host"] = "GB"
    old = Game(data)
    assert [(m["token"], m["nation"], m["name"], m["host"]) for m in old.members] == [(m["token"], m["nation"], m["name"], m["host"]) for m in members]
    assert old.tokens == data["tokens"] and old.joined == data["joined"] and old.host == "GB"


def test_save_load_keeps_pause_notices_and_members(tmp_path):
    t, (host, p1, p2) = running(tmp_path, {"turn_timer_seconds": 60})
    t.post("pause", p1, paused=True)
    t.post("surrender", p2)
    before = t.state(host)
    after = make(tmp_path).get(t.url("state"), params={"token": host}).json()
    assert after["pause"] == before["pause"] and after["notices"] == before["notices"]
    assert after["ai"] == before["ai"] and after["members"] == before["members"]
    assert make(tmp_path).get(t.url("state"), params={"token": p2}).json()["spectator"] is True
