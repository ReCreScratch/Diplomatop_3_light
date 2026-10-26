"""Standing march orders (G58): routes longer than the range keep marching in later turns."""
import engine
from engine.orders import snapshot

from conftest import A1_CAP, A1_MID, A2_CAP, N1_CAP, kinds, make_game, of_kind, put


def move(army, count, *path):
    return {"type": "move", "army": army, "count": count, "path": [list(p) for p in path]}


def turn(state, **orders):
    return engine.resolve_turn(state, {k: v for k, v in orders.items()})


def test_long_route_moves_range_per_turn_and_arrives():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    assert engine.validate_orders(state, "AA", [move("a1", 6, A1_MID, A2_CAP)]) == [[]]
    events = turn(state, AA=[move("a1", 6, A1_MID, A2_CAP)])
    assert state.armies["a1"]["field"] == A1_MID and state.armies["a1"]["route"] == [A2_CAP]
    assert "auto" not in of_kind(events, "move")[0]
    events = turn(state)
    auto = of_kind(events, "move")[0]
    assert auto["auto"] is True and auto["snap"]
    assert auto["text"] == "Aland marschiert weiter: 6 Divisionen nach Südalandstadt."
    assert state.armies["a1"]["field"] == A2_CAP and "route" not in state.armies["a1"]
    assert not of_kind(turn(state), "move")


def test_segment_uses_forced_march_range():
    state = make_game()
    put(state, "AA", A1_CAP, 6, forced_march=True)
    turn(state, AA=[move("a1", 6, A1_MID, A2_CAP, N1_CAP, [4, 2])])
    assert state.armies["a1"]["field"] == N1_CAP and state.owners["N1"] == "AA"   # 3 fields, conquest ends the march
    assert "route" not in state.armies["a1"]


def test_route_ends_on_fight():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    put(state, "BB", A2_CAP, 1)
    turn(state, AA=[move("a1", 6, A1_MID, A2_CAP)])
    events = turn(state)
    assert of_kind(events, "fight")
    assert "route" not in state.armies["a1"]


def test_route_ends_on_conquest_attempt():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    turn(state, AA=[move("a1", 6, A1_MID, A2_CAP, N1_CAP)])
    turn(state)
    assert state.armies["a1"]["route"] == [N1_CAP]
    events = turn(state)
    assert of_kind(events, "conquest") and state.owners["N1"] == "AA"
    assert "route" not in state.armies["a1"]


def test_route_ends_on_failed_conquest():
    state = make_game()
    put(state, "AA", A2_CAP, 1)
    state.armies["a1"]["route"] = [N1_CAP, [4, 2]]
    events = turn(state)
    assert of_kind(events, "conquest_failed")
    assert "route" not in state.armies["a1"] and state.armies["a1"]["field"] == A2_CAP


def test_route_ends_on_merge():
    state = make_game()
    put(state, "AA", A1_CAP, 4)
    put(state, "AA", A2_CAP, 2)
    turn(state, AA=[move("a1", 4, A1_MID, A2_CAP)])
    events = turn(state)
    assert of_kind(events, "merge")
    assert list(state.armies) == ["a2"] and state.armies["a2"]["divisions"] == 6
    assert "route" not in state.armies["a2"]


def test_new_move_replaces_route():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    turn(state, AA=[move("a1", 6, A1_MID, A2_CAP)])
    events = turn(state, AA=[move("a1", 6, A1_CAP)])
    assert [e.get("auto") for e in of_kind(events, "move")] == [None]
    assert state.armies["a1"]["field"] == A1_CAP and "route" not in state.armies["a1"]
    assert not of_kind(turn(state), "move")


def test_halt_clears_route():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    turn(state, AA=[move("a1", 6, A1_MID, A2_CAP)])
    assert engine.validate_orders(state, "AA", [{"type": "halt", "army": "a1"}]) == [[]]
    events = turn(state, AA=[{"type": "halt", "army": "a1"}])
    assert of_kind(events, "halt") and not of_kind(events, "move")
    assert state.armies["a1"]["field"] == A1_MID and "route" not in state.armies["a1"]
    assert engine.validate_orders(state, "AA", [{"type": "halt", "army": "a1"}])[0]   # nothing to halt
    assert engine.validate_orders(state, "BB", [{"type": "halt", "army": "a1"}])[0]   # not his army


def test_split_carries_route_and_rest_stays():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    turn(state, AA=[move("a1", 2, A1_MID, A2_CAP)])
    assert state.armies["a2"]["route"] == [A2_CAP] and "route" not in state.armies["a1"]
    assert state.armies["a1"]["field"] == A1_CAP
    turn(state)
    assert state.armies["a2"]["field"] == A2_CAP and state.armies["a1"]["field"] == A1_CAP


def test_fresh_divisions_stay_behind():
    state = make_game()
    put(state, "AA", A1_CAP, 4)
    turn(state, AA=[move("a1", 4, A1_MID, A2_CAP)])
    state.armies["a1"]["divisions"] += 1
    state.armies["a1"]["fresh"] = 1
    turn(state)
    new = [a for a in state.armies.values() if a["field"] == A2_CAP]
    assert new[0]["divisions"] == 4 and state.armies["a1"]["divisions"] == 1
    assert state.armies["a1"]["field"] == A1_MID and "route" not in state.armies["a1"]


def test_disband_all_removes_route():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    turn(state, AA=[move("a1", 2, A1_MID, A2_CAP)])
    turn(state, AA=[{"type": "disband", "army": "a1", "count": 2}])
    assert not state.armies
    assert engine.GameState.from_dict(state.to_dict()).armies == {}


def test_setting_off_keeps_too_far_error():
    state = make_game(standing_marches=False)
    put(state, "AA", A1_CAP, 6)
    assert engine.validate_orders(state, "AA", [move("a1", 6, A1_MID, A2_CAP)])[0]


def test_auto_move_runs_before_new_orders_in_same_slot():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    put(state, "AA", [0, 3], 2)
    turn(state, AA=[move("a1", 6, A1_MID, A2_CAP)])
    state.player_order = ["AA", "BB"]
    toggle = {"type": "forced_march", "army": "a2", "on": True}
    events = engine.resolve_turn(state, {"AA": [move("a2", 2, [0, 2]), toggle]})
    seq = [(e["kind"], e.get("auto")) for e in events if e["kind"] in ("forced_march", "move")]
    assert seq == [("forced_march", None), ("move", True), ("move", None)]


def test_preview_uses_this_turns_part():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    result = engine.preview_move(state, "AA", "a1", 6, [A1_MID, A2_CAP, N1_CAP])
    assert result["valid"] and result["end_field"] == A1_MID and result["conquest"] is None
    result = engine.preview_move(state, "AA", "a1", 6, [A1_MID, A2_CAP, N1_CAP], forced_march=True)
    assert result["end_field"] == N1_CAP and result["conquest"]


def test_snapshots_hide_routes():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    events = turn(state, AA=[move("a1", 6, A1_MID, A2_CAP)])
    assert "route" in state.armies["a1"]
    assert all("route" not in a for a in snapshot(state)["armies"].values())
    assert all("route" not in a for e in events if "snap" in e for a in e["snap"]["armies"].values())
    assert "move" in kinds(events)
