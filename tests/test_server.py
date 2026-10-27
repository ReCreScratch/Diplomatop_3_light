"""HTTP server tests (FastAPI TestClient) on a temp save folder."""
from fastapi.testclient import TestClient

from server.app import create_app


def make(tmp_path):
    return TestClient(create_app(tmp_path))


def setup_game(c):
    r = c.post("/api/games", json={"map": "europa"}).json()
    gid, host = r["game_id"], r["host_token"]
    t1 = c.post(f"/api/games/{gid}/join", json={"name": "Felix", "nation": "GB", "host_token": host}).json()["token"]
    t2 = c.post(f"/api/games/{gid}/join", json={"name": "Anna", "nation": "FR"}).json()["token"]
    return gid, t1, t2


def test_flow(tmp_path):
    c = make(tmp_path)
    assert "europa" in c.get("/api/maps").json()
    gid, t1, t2 = setup_game(c)
    lob = c.get(f"/api/games/{gid}/lobby", params={"token": t1}).json()
    assert lob["status"] == "lobby" and lob["me"] == "GB" and lob["is_host"]
    assert lob["rules"]["start_gold"] == 10 and "division_cost" in lob["rules"]
    assert lob["joined"] == {"GB": "Felix", "FR": "Anna"}
    assert not c.get(f"/api/games/{gid}/lobby", params={"token": t2}).json()["is_host"]
    assert c.get(f"/api/games/{gid}/state", params={"token": t1}).json()["status"] == "lobby"
    assert c.post(f"/api/games/{gid}/start", params={"token": t2}).status_code == 403
    assert c.post(f"/api/games/{gid}/start", params={"token": t1}).json() == {"ok": True}

    v = c.get(f"/api/games/{gid}/state", params={"token": t1}).json()
    for key in ("version", "me", "turn", "ready", "players", "my_gold", "my_recruit_limit", "rules", "map",
                "theme", "owners", "armies", "board", "my_orders", "order_errors", "incoming", "last_turn",
                "player_order", "timer_remaining", "is_host"):
        assert key in v
    assert v["me"] == "GB" and v["turn"] == 1 and v["last_turn"] is None
    assert v["ready"] == {"GB": False, "FR": False}

    # orders: stored even if invalid, errors returned
    bad = [{"type": "recruit", "field": [0, 0], "count": 1}, {"type": "nonsense"}]
    r = c.put(f"/api/games/{gid}/orders", params={"token": t1}, json={"orders": bad}).json()
    assert len(r["errors"]) == 2 and all(r["errors"])
    v2 = c.get(f"/api/games/{gid}/state", params={"token": t1}).json()
    assert v2["my_orders"] == bad and v2["version"] > v["version"]
    same = c.get(f"/api/games/{gid}/state", params={"token": t1, "since": v2["version"]}).json()
    assert same == {"changed": False}

    c.put(f"/api/games/{gid}/orders", params={"token": t1}, json={"orders": []})
    c.post(f"/api/games/{gid}/ready", params={"token": t1}, json={"ready": True})
    mid = c.get(f"/api/games/{gid}/state", params={"token": t2}).json()
    assert mid["turn"] == 1 and mid["ready"]["GB"] is True
    c.post(f"/api/games/{gid}/ready", params={"token": t2}, json={"ready": True})
    after = c.get(f"/api/games/{gid}/state", params={"token": t1}).json()
    assert after["turn"] == 2 and after["version"] > mid["version"]
    assert after["last_turn"]["turn"] == 1 and after["last_turn"]["events"]
    before = after["last_turn"]["before"]
    assert set(before) == {"armies", "owners"} and before["owners"]
    assert after["ready"] == {"GB": False, "FR": False} and after["my_orders"] == []


def test_auth_and_errors(tmp_path):
    c = make(tmp_path)
    gid, t1, t2 = setup_game(c)
    c.post(f"/api/games/{gid}/start", params={"token": t1})
    assert c.get(f"/api/games/{gid}/state", params={"token": "bad"}).status_code == 403
    assert c.put(f"/api/games/{gid}/orders", params={"token": "bad"}, json={"orders": []}).status_code == 403
    assert c.get("/api/games/nope/lobby").status_code == 404
    r = c.post(f"/api/games/{gid}/join", json={"name": "X", "nation": "DE"})
    assert r.status_code == 400 and "detail" in r.json()
    assert c.post("/api/games", json={"map": "../x"}).status_code == 400


def test_save_load(tmp_path):
    c = make(tmp_path)
    gid, t1, t2 = setup_game(c)
    c.post(f"/api/games/{gid}/start", params={"token": t1})
    orders = [{"type": "forced_march", "army": "a1", "on": True}]
    c.put(f"/api/games/{gid}/orders", params={"token": t1}, json={"orders": orders})
    before = c.get(f"/api/games/{gid}/state", params={"token": t1}).json()
    after = make(tmp_path).get(f"/api/games/{gid}/state", params={"token": t1}).json()
    assert after == before


def test_timer_expiry(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/games", json={"map": "europa", "rules": {"turn_timer_seconds": 60}}).json()
    gid = r["game_id"]
    t = c.post(f"/api/games/{gid}/join",
               json={"name": "A", "nation": "GB", "host_token": r["host_token"]}).json()["token"]
    c.post(f"/api/games/{gid}/start", params={"token": t})
    v = c.get(f"/api/games/{gid}/state", params={"token": t}).json()
    assert 0 < v["timer_remaining"] <= 60
    c.app.state.games.games[gid].deadline = 1
    assert c.get(f"/api/games/{gid}/state", params={"token": t}).json()["turn"] == 2


def test_chat(tmp_path):
    c = make(tmp_path)
    gid, t1, t2 = setup_game(c)
    t3 = c.post(f"/api/games/{gid}/join", json={"name": "Otto", "nation": "DE"}).json()["token"]
    url = f"/api/games/{gid}/chat"
    assert c.post(url, params={"token": t1}, json={"to": None, "text": "hi"}).status_code == 400  # not running
    c.post(f"/api/games/{gid}/start", params={"token": t1})
    st = lambda t: c.get(f"/api/games/{gid}/state", params={"token": t}).json()
    assert st(t1)["chat"] == []
    pub = c.post(url, params={"token": t1}, json={"to": None, "text": " Hallo "}).json()
    assert pub["ok"] and pub["message"]["text"] == "Hallo" and pub["message"]["from"] == "GB"
    mark = {"kind": "field", "f": [1, 1]}
    arrow = {"kind": "arrow", "path": [[1, 1], [1, 2]]}
    priv = c.post(url, params={"token": t1}, json={"to": "FR", "text": "geheim", "marks": [mark, arrow]}).json()
    assert priv["message"]["id"] > pub["message"]["id"] and priv["message"]["marks"] == [mark, arrow]
    assert [m["text"] for m in st(t1)["chat"]] == ["Hallo", "geheim"]
    assert [m["text"] for m in st(t2)["chat"]] == ["Hallo", "geheim"]
    assert [m["text"] for m in st(t3)["chat"]] == ["Hallo"]           # private stays secret
    assert "geheim" not in c.get(f"/api/games/{gid}/state", params={"token": t3}).text
    only_marks = c.post(url, params={"token": t2}, json={"to": "GB", "text": "  ", "marks": [mark]})
    assert only_marks.status_code == 200
    # validation
    bad = [{"to": None, "text": " "}, {"to": "GB", "text": "x"}, {"to": "XX", "text": "x"},
           {"to": None, "text": "x" * 1001}, {"to": None, "text": "x", "marks": [{"kind": "field", "f": [999, 1]}]},
           {"to": None, "text": "x", "marks": [mark] * 21}, {"to": None, "text": "x", "marks": [{"kind": "zzz"}]},
           {"to": None, "text": "x", "marks": [{"kind": "arrow", "path": [[1, 1]]}]}]
    for body in bad:
        r = c.post(url, params={"token": t1}, json=body)
        assert r.status_code == 400 and r.json()["detail"], body
    assert c.post(url, params={"token": "bad"}, json={"to": None, "text": "x"}).status_code == 403
    # save/load keeps chat
    before = st(t1)["chat"]
    assert len(before) == 3 and make(tmp_path).get(f"/api/games/{gid}/state", params={"token": t1}).json()["chat"] == before


def test_diplomacy_view_and_finished_game(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/games", json={"map": "europa", "rules": {"victory_hold_turns": 1}}).json()
    gid = r["game_id"]
    t1 = c.post(f"/api/games/{gid}/join", json={"name": "Felix", "nation": "GB", "host_token": r["host_token"]}).json()["token"]
    t2 = c.post(f"/api/games/{gid}/join", json={"name": "Anna", "nation": "FR"}).json()["token"]
    c.post(f"/api/games/{gid}/start", params={"token": t1})
    url = lambda what: f"/api/games/{gid}/{what}"
    st = lambda t: c.get(url("state"), params={"token": t}).json()
    play = lambda t, orders: c.put(url("orders"), params={"token": t}, json={"orders": orders}).json()
    ready = lambda t: c.post(url("ready"), params={"token": t}, json={"ready": True})

    v = st(t1)
    assert v["alliances"] == {} and v["no_attack"] == {} and v["winner"] is None
    assert v["invitations"] == {"incoming": [], "outgoing": []} and v["offers"] == {"incoming": [], "outgoing": []}
    assert v["victory"] == {"leader": None, "need": 1}
    assert all("alliance" in row and "share_counted" in row for row in v["board"])

    prov = next(code for code, o in v["owners"].items() if o == "GB")
    assert play(t1, [{"type": "invite", "to": "FR"}, {"type": "no_attack", "to": "FR", "on": True},
                     {"type": "offer_sale", "province": prov, "to": "FR", "price": 2}])["errors"] == [[], [], []]
    ready(t1), ready(t2)
    v1, v2 = st(t1), st(t2)
    assert v1["no_attack"] == {"GB": ["FR"]}
    assert v1["invitations"]["outgoing"] == [{"from": "GB", "to": "FR", "turn": 1}] and v1["invitations"]["incoming"] == []
    assert v2["invitations"]["incoming"] == v1["invitations"]["outgoing"] and v2["offers"]["incoming"][0]["price"] == 2
    assert play(t2, [{"type": "accept", "from": "GB"}, {"type": "buy", "province": prov}])["errors"] == [[], []]
    # GB gets more than 40 % of the land: the game ends after this resolution (victory_hold_turns = 1)
    game = c.app.state.games.games[gid]
    for code, owner in game.state.owners.items():
        if owner is None or owner == "FR":
            game.state.owners[code] = "GB"
    game.state.owners[prov] = "GB"
    ready(t1), ready(t2)
    done = st(t1)
    assert done["status"] == "finished" and done["winner"]["players"] == ["GB"] and done["alliances"]
    assert done["timer_remaining"] is None
    assert c.put(url("orders"), params={"token": t1}, json={"orders": []}).json() == {"detail": "Das Spiel ist beendet."}
    assert ready(t1).status_code == 400
    assert c.get(url("lobby"), params={"token": t1}).json()["status"] == "finished"
    assert c.post(url("chat"), params={"token": t1}, json={"to": None, "text": "gg"}).status_code == 200
    assert make(tmp_path).get(url("state"), params={"token": t1}).json()["winner"] == done["winner"]   # survives a restart
