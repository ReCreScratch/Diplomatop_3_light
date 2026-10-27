"""Milestone 5 server side: the turn archive (saves/{gid}.history.jsonl) and the /stats and /history endpoints."""
import json
import time

import engine
from server import storage
from server.games import Games
from test_lobby_session import Table, running

WIN_EARLY = {"victory_share_single": 0.0, "victory_hold_turns": 1}   # anybody with land wins at the first resolution


def rows_of(t):
    path = storage.history_path(t.gid, t.games.save_dir)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def gb_capital(t):
    st = t.game.state
    return st.map["provinces"]["GB1"]["capital"]


def play_turn(t, tokens, orders=None):
    for tok, o in (orders or {}).items():
        assert t.orders(tok, o).status_code == 200
    for tok in tokens:
        t.ready(tok)


def test_every_resolution_appends_one_complete_row(tmp_path):
    t, (a, b) = running(tmp_path, nations=("GB", "FR"))
    cap = gb_capital(t)
    gold = t.game.state.players["GB"]["gold"]
    mine = [{"type": "recruit", "field": cap, "count": 1}]
    play_turn(t, (a, b), {a: mine})
    play_turn(t, (a, b))
    rows = rows_of(t)
    assert [r["turn"] for r in rows] == [1, 2]
    r = rows[0]
    assert set(r) >= {"turn", "player_order", "before", "gold_before", "gold_after", "orders", "events", "alliances",
                      "no_attack", "ai", "timeouts", "ready_at", "started", "resolved"}
    assert set(r["before"]) == {"armies", "owners"} and r["before"]["owners"]["GB1"] == "GB"
    assert r["gold_before"]["GB"] == gold and r["gold_after"]["GB"] != gold
    assert r["orders"] == {"GB": mine, "FR": []}                      # the raw submitted orders of everybody
    assert r["timeouts"] == [] and set(r["ready_at"]) == {"GB", "FR"} and all(v >= 0 for v in r["ready_at"].values())
    assert r["started"] <= r["resolved"] and sorted(r["player_order"]) == ["FR", "GB"]
    assert any(e["kind"] == "recruit" and e["cost"] == 5 for e in r["events"])
    assert all("snap" not in e for e in r["events"])
    # the events shown to the players keep their snaps
    last = t.state(a)["last_turn"]["events"]
    assert any("snap" in e for e in last)
    assert rows[1]["gold_before"]["GB"] == r["gold_after"]["GB"]


def test_ready_times_are_recorded_and_survive_a_restart(tmp_path):
    t, (a, b) = running(tmp_path, nations=("GB", "FR"))
    t.game.turn_started = time.time() - 30
    t.ready(a)
    assert 29 <= t.game.ready_at["GB"] <= 40 and "FR" not in t.game.ready_at
    again = Games(tmp_path)
    game = again.games[t.gid]
    assert game.ready_at == t.game.ready_at and game.turn_started == t.game.turn_started
    t.ready(a, False)
    assert "GB" not in t.game.ready_at
    t.ready(a)
    t.ready(b)
    row = rows_of(t)[0]
    assert row["ready_at"]["GB"] >= 29 and row["ready_at"]["FR"] is not None
    assert t.game.ready_at == {} and t.game.turn_started > row["started"]         # a new turn starts clean


def test_timeouts_are_archived(tmp_path):
    t, (a, b) = running(tmp_path, {"turn_timer_seconds": 60}, nations=("GB", "FR"))
    t.ready(a)
    t.game.deadline = 1
    t.state(b)
    r = rows_of(t)[0]
    assert r["timeouts"] == ["FR"] and r["ready_at"]["FR"] is None and r["ready_at"]["GB"] is not None


def test_stats_and_history_wait_for_the_end(tmp_path):
    t, (a, b) = running(tmp_path, nations=("GB", "FR"))
    for what in ("stats", "history"):
        r = t.c.get(t.url(what), params={"token": a})
        assert r.status_code == 400 and r.json()["detail"] == "Die Statistik gibt es erst am Spielende."
    assert t.c.get(t.url("stats")).status_code == 400


def test_victory_writes_the_final_row_and_opens_stats(tmp_path):
    t, (a, b) = running(tmp_path, WIN_EARLY, nations=("GB", "FR"))
    play_turn(t, (a, b), {a: [{"type": "recruit", "field": gb_capital(t), "count": 1}]})
    v = t.state(a)
    assert v["status"] == "finished" and v["winner"]
    rows = rows_of(t)
    assert len(rows) == 2 and rows[1]["final"] is True
    f = rows[1]
    assert f["turn"] == v["turn"] and f["board"]["owners"] == v["owners"] and set(f["gold"]) == {"GB", "FR"}
    assert f["winner"] == v["winner"] and f["players"] == {"GB": "P0", "FR": "P1"} and "ai" in f and "ts" in f

    hist = t.c.get(t.url("history"), params={"token": b})
    assert hist.status_code == 200 and hist.json() == rows
    for token in (a, b, ""):                                         # members and anonymous visitors
        assert t.c.get(t.url("stats"), params={"token": token}).status_code == 200
    assert t.c.get(t.url("stats"), params={"token": "nope"}).status_code == 403
    s = t.c.get(t.url("stats"), params={"token": a}).json()
    assert s["version"] == engine.STATS_VERSION and s["empty"] is False and s["axis"] == [1, 2]
    assert s["nations"]["GB"] == {"name": "Großbritannien", "player": "P0"} and s["map"]
    assert s["video_seconds_per_turn"] == 1 and s["game"]["turns"] == 1 and s["game"]["winner"] == f["winner"]
    assert s["totals"]["GB"]["recruited"] == 1 and s["totals"]["GB"]["gold_spent_recruits"] == 5
    json.dumps(s)


def test_stats_cache_is_keyed_by_version_archive_and_chat(tmp_path, monkeypatch):
    t, (a, b) = running(tmp_path, WIN_EARLY, nations=("GB", "FR"))
    play_turn(t, (a, b))
    calls = []
    real = engine.compute_stats
    monkeypatch.setattr(engine, "compute_stats", lambda *args, **kw: calls.append(1) or real(*args, **kw))
    first = t.c.get(t.url("stats")).json()
    cache = storage.stats_cache_path(t.gid, tmp_path)
    assert cache.exists() and json.loads(cache.read_text(encoding="utf-8"))["key"]["version"] == engine.STATS_VERSION
    assert t.c.get(t.url("stats")).json() == first and len(calls) == 1          # second call: from the cache
    monkeypatch.setattr(engine, "STATS_VERSION", engine.STATS_VERSION + 1)
    t.c.get(t.url("stats"))
    assert len(calls) == 2                                                      # version change: recomputed
    storage.append_history(t.gid, {"turn": 99, "events": [], "before": {"armies": {}, "owners": {}}}, tmp_path)
    t.c.get(t.url("stats"))
    assert len(calls) == 3                                                      # longer archive: recomputed
    t.post("chat", a, to=None, text="Gut gespielt")                             # chat is allowed after the end
    s = t.c.get(t.url("stats")).json()
    assert len(calls) == 4 and s["totals"]["GB"]["chat_public"] == 1 and s["chat_matrix"] == {"GB": {"all": 1}}
    assert "Gut gespielt" not in json.dumps(s)                                  # never the text


def test_stats_cache_file_is_not_loaded_as_a_game(tmp_path):
    t, (a, b) = running(tmp_path, WIN_EARLY, nations=("GB", "FR"))
    play_turn(t, (a, b))
    t.c.get(t.url("stats"))
    again = Games(tmp_path)
    assert list(again.games) == [t.gid]


def test_game_ended_by_everybody_leaving_has_a_final_row(tmp_path):
    t, (host, p1) = running(tmp_path, nations=("GB", "FR"))
    t.post("surrender", p1)
    t.post("surrender", host)
    rows = rows_of(t)
    assert len(rows) == 1 and rows[0]["final"] and rows[0]["winner"] is None
    assert set(rows[0]["ai"]) >= {"GB", "FR"} and rows[0]["players"] == {"GB": "P0", "FR": "P1"}
    s = t.c.get(t.url("stats")).json()
    assert s["empty"] is True and s["totals"]["FR"]["status"] == "surrender" and s["players"]["FR"] == "P1"


def test_old_finished_game_without_archive_still_has_stats(tmp_path):
    t, (a, b) = running(tmp_path, WIN_EARLY, nations=("GB", "FR"))
    play_turn(t, (a, b))
    storage.history_path(t.gid, tmp_path).unlink()
    s = t.c.get(t.url("stats")).json()
    assert s["empty"] is True and s["axis"] == [] and s["totals"]["GB"]["recruited"] == 0
    assert t.c.get(t.url("history")).json() == []


def test_broken_and_duplicate_archive_lines_are_tolerated(tmp_path):
    folder = tmp_path
    storage.append_history("g", {"turn": 1, "x": 1}, folder)
    with storage.history_path("g", folder).open("a", encoding="utf-8") as f:
        f.write('{"turn": 2, "x"\n')                                            # crash while writing
    storage.append_history("g", {"turn": 1, "x": 2}, folder)                    # replayed turn
    storage.append_history("g", {"final": True, "turn": 2}, folder)
    rows = storage.load_history("g", folder)
    assert rows == [{"turn": 1, "x": 2}, {"final": True, "turn": 2}]
    assert storage.load_history("nothing", folder) == []
