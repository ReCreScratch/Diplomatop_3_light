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
