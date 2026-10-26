"""Map loading, rules merge, state round trip, determinism, turn order."""
import copy
import json

import pytest

import engine
from conftest import ROOT, make_game, map_data  # noqa: F401
from engine import MapError


def test_europa_loads():
    data = engine.load_map(ROOT / "maps" / "europa")
    assert data["name"] == "Europa" and len(data["provinces"]) > 40


def test_test_map_loads(map_data):
    assert set(map_data["nations"]) == {"AA", "BB", "CC"}


@pytest.mark.parametrize("change", [
    lambda m: m["provinces"]["A1"].update(capital=[5, 2]),          # capital outside the province
    lambda m: m["provinces"]["A1"].update(owner="XX"),              # owner does not exist
    lambda m: m["provinces"].update(Z9=copy.deepcopy(m["provinces"]["A1"])),  # province without fields
    lambda m: m["grid"].__setitem__(0, "QQ ~~ ~~ ~~ ~~ ~~ ~~ ~~"),  # unknown token
    lambda m: m.pop("grid"),
    lambda m: m.update(start_armies=[{"owner": "AA", "field": [0, 0], "divisions": 1}]),  # on sea
])
def test_broken_maps_are_rejected(map_data, change, tmp_path):
    broken = copy.deepcopy(map_data)
    change(broken)
    (tmp_path / "map.json").write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(MapError):
        engine.load_map(tmp_path)


def test_missing_map_file(tmp_path):
    with pytest.raises(MapError):
        engine.load_map(tmp_path)


def test_rules_merge_order():
    rules = engine.load_rules({"start_gold": 20, "division_cost": 4}, {"division_cost": 5})
    assert rules["start_gold"] == 20 and rules["division_cost"] == 5
    assert rules["phases"] == ["transfers", "recruitment", "movement"]
    assert engine.load_rules({}, {})["start_gold"] == 10


def test_rules_have_all_section_13_settings():
    rules = engine.load_rules({}, {})
    for key in ("division_cost", "disband_refund", "upkeep_per_division", "upkeep_per_army", "upkeep_rounding",
                "allow_spending_into_debt", "recruit_limit_per_province", "recruits_can_move_same_turn",
                "move_range", "forced_march_range", "forced_march_combat_value", "strength_rounding",
                "combat_formula", "conquest_cost_factor", "conquest_allow_army_used_up", "turn_order_rule",
                "turn_timer_seconds", "start_gold", "show_other_players_gold", "gift_delay_turns",
                "victory_share_single", "victory_share_alliance", "transport_combat_value",
                "fleet_move_range", "fleet_forced_march_range"):
        assert key in rules


def test_new_game_neutral_owners_and_players():
    state = make_game(players=("AA", "BB"))
    assert state.owners["C1"] is None and state.owners["A1"] == "AA"
    assert set(state.players) == {"AA", "BB"}
    assert state.turn == 1


def test_round_trip_exact():
    state = make_game()
    engine.resolve_turn(state, {"AA": [{"type": "recruit", "field": [0, 2], "count": 2}]})
    data = state.to_dict()
    clone = engine.GameState.from_dict(json.loads(json.dumps(data)))
    assert clone.to_dict() == data
    orders = {"AA": [{"type": "move", "army": "a1", "count": 2, "path": [[1, 2]]}]}
    assert engine.resolve_turn(state, orders) == engine.resolve_turn(clone, orders)
    assert state.to_dict() == clone.to_dict()


def run_turns(seed, players, turns):
    state = make_game(players=players, seed=seed)
    orders = []
    for _ in range(turns):
        orders.append(list(state.player_order))
        engine.resolve_turn(state, {})
    return orders, state


def test_determinism_same_seed():
    a, state_a = run_turns(7, ("AA", "BB", "CC"), 8)
    b, state_b = run_turns(7, ("AA", "BB", "CC"), 8)
    assert a == b and state_a.to_dict() == state_b.to_dict()


def test_different_seeds_differ():
    results = {tuple(map(tuple, run_turns(seed, ("AA", "BB", "CC"), 6)[0])) for seed in range(5)}
    assert len(results) > 1


def test_turn_order_no_repeat_first_last():
    for seed in range(5):
        state = make_game(players=("AA", "BB", "CC"), seed=seed)
        previous = list(state.player_order)
        for _ in range(25):
            engine.resolve_turn(state, {})
            now = state.player_order
            assert sorted(now) == ["AA", "BB", "CC"]
            assert now[0] != previous[0] and now[-1] != previous[-1]
            assert state.prev_player_order == previous
            previous = list(now)


def test_turn_order_fallback_single_player():
    state = make_game(players=("AA",))
    for _ in range(3):
        engine.resolve_turn(state, {})
        assert state.player_order == ["AA"]


def test_turn_order_two_players_alternate():
    state = make_game(players=("AA", "BB"))
    first = state.player_order[0]
    engine.resolve_turn(state, {})
    assert state.player_order[0] != first


def test_turn_order_registry():
    from engine.turn_order import TURN_ORDER_RULES
    assert "no_repeat_first_last" in TURN_ORDER_RULES
