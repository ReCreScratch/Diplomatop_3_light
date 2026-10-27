"""Milestone 4: AI ruleset (RULES.md 8.2) for unpicked, surrendered and kicked nations; per-nation start gold; map checks.

Test map: AA owns A1 (cap [0,2], income 3) and A2 (cap [2,2]); N1 (cap [3,2]) is neutral; BB owns B1, B2; CC owns C1."""
import copy
import json

import pytest

import engine
from conftest import A1_CAP, A2_CAP, B1_CAP, N1_CAP, TEST_MAP, make_game, of_kind, put

C1_CAP = [6, 2]


def new(players=("AA", "BB"), ai=("CC",), **overrides):
    map_data = engine.load_map(TEST_MAP)
    rules = engine.load_rules(map_data.get("rules", {}), overrides)
    state = engine.new_game(map_data, {n: "p_" + n for n in players}, rules, 1, ai=ai)
    state.player_order = list(players)
    return state


def move(army, count, *path):
    return {"type": "move", "army": army, "count": count, "path": [list(p) for p in path]}


def test_unpicked_nation_is_ai_and_keeps_its_provinces():
    state = new()
    assert state.owners["C1"] == "CC" and state.owners["N1"] is None     # map-neutral stays neutral
    assert state.ai == {"CC": {"reason": "unpicked", "name": None}}
    assert "CC" not in state.players and "CC" not in state.player_order
    assert state.hostile("AA", "CC") and state.hostile("CC", "AA")


def test_without_ai_argument_unpicked_nations_stay_neutral():
    state = make_game()
    assert state.owners["C1"] is None and state.ai == {}


def test_ai_recruits_in_every_own_city_each_turn_and_never_moves():
    state = new(ai_recruit_per_city=2)
    events = engine.resolve_turn(state, {})
    ai_events = [e for e in of_kind(events, "recruit") if e["player"] == "CC"]
    assert len(ai_events) == 1 and ai_events[0]["count"] == 2 and ai_events[0]["ai"] and "snap" in ai_events[0]
    army = state.army_at(C1_CAP)
    assert army["owner"] == "CC" and army["divisions"] == 2
    engine.resolve_turn(state, {})
    army = state.army_at(C1_CAP)
    assert army["divisions"] == 4 and list(army["field"]) == C1_CAP     # joins the army, stays put


def test_ai_recruit_count_comes_from_the_rules_and_zero_means_none():
    state = new(ai_recruit_per_city=0)
    engine.resolve_turn(state, {})
    assert not state.armies
    assert engine.load_rules({}, {})["ai_recruit_per_city"] == 1


def test_ai_is_free_and_builds_no_ships():
    state = new()
    gold = {p: state.players[p]["gold"] for p in state.players}
    engine.resolve_turn(state, {})
    assert all(not state.is_fleet(a) for a in state.armies.values())
    assert "CC" not in state.players and state.players["AA"]["gold"] - gold["AA"] == 4   # income only, no AI costs


def test_ai_defends_and_can_be_conquered():
    state = new()
    engine.resolve_turn(state, {})                                        # CC has 1 division on C1_CAP
    put(state, "BB", [5, 2], 5)
    events = engine.resolve_turn(state, {"BB": [move("a2", 5, [6, 2])]})
    assert of_kind(events, "fight")                                       # AI armies fight like any enemy
    assert state.owners["C1"] == "BB"                                     # income 2 paid from the 4 survivors


def test_ai_army_attacked_by_ally_of_nobody():
    state = new()
    engine.resolve_turn(state, {})
    state.no_attack["BB"] = ["CC"]
    state.no_attack["CC"] = ["BB"]
    assert state.hostile("BB", "CC")                                      # pacts with the AI do nothing


def test_make_ai_hands_the_nation_over_and_keeps_units():
    state = new()
    army = put(state, "BB", B1_CAP, 3)
    army["route"] = [[5, 2]]
    events = []
    engine.make_ai(state, "BB", "surrender", events)
    assert "BB" not in state.players and "BB" not in state.player_order
    assert state.ai["BB"] == {"reason": "surrender", "name": "p_BB"}
    assert state.armies[army["id"]]["divisions"] == 3 and "route" not in state.armies[army["id"]]
    assert events[-1]["kind"] == "surrender" and "p_BB" in events[-1]["text"]
    assert state.owners["B1"] == "BB" and state.hostile("AA", "BB")
    engine.resolve_turn(state, {"BB": [move(army["id"], 3, [5, 2])]})     # orders of a former player are ignored
    assert list(state.armies[army["id"]]["field"]) == B1_CAP


def test_surrendered_nation_recruits_but_never_moves_and_keeps_old_units():
    state = new()
    put(state, "BB", B1_CAP, 2)
    engine.make_ai(state, "BB", "surrender", [])
    engine.resolve_turn(state, {})
    engine.resolve_turn(state, {})
    on_b1 = state.army_at(B1_CAP)
    assert on_b1["owner"] == "BB" and on_b1["divisions"] == 4              # 2 old + 1 per turn (B2's city also recruits)
    assert state.army_at([5, 2])["divisions"] == 2                         # B2: two recruits
    assert all(list(a["field"]) in (B1_CAP, [5, 2], C1_CAP) for a in state.armies.values())


def test_surrender_leaves_alliance_pacts_invitations_and_offers():
    state = new(("AA", "BB", "CC"), ai=())
    state.alliances["b1"] = {"id": "b1", "members": ["AA", "BB"], "since": 1}
    state.next_alliance_id = 2
    state.no_attack = {"AA": ["CC"], "CC": ["AA"], "BB": ["CC"]}
    state.invitations = [{"from": "CC", "to": "AA", "turn": 1}, {"from": "AA", "to": "BB", "turn": 1}]
    state.offers = [{"province": "A2", "from": "AA", "to": "CC", "price": 2, "turn": 1}]
    events = []
    engine.make_ai(state, "AA", "kick", events)
    assert state.alliances == {} and state.no_attack == {"CC": [], "BB": ["CC"]}
    assert state.invitations == [] and state.offers == []
    assert [e["kind"] for e in events][-1] == "kick" and "alliance_end" in [e["kind"] for e in events]
    assert state.ai["AA"]["reason"] == "kick"


def test_ai_nations_cannot_win_and_do_not_block_victory_of_players():
    state = new(("AA", "BB"), ai=("CC",), victory_hold_turns=1)
    for code in state.owners:
        state.owners[code] = "CC"
    events = engine.resolve_turn(state, {})
    assert state.winner is None and not of_kind(events, "victory")        # 100 % but AI
    rows = {r["player"]: r for r in engine.board(state)}
    assert rows["CC"]["ai"] is True and rows["CC"]["name"] == "KI" and rows["CC"]["share"] == 1
    assert "ai" not in rows["AA"]


def test_ai_state_round_trips_and_old_saves_load():
    state = new()
    engine.make_ai(state, "BB", "surrender", [])
    data = json.loads(json.dumps(state.to_dict()))
    assert engine.GameState.from_dict(data).ai == state.ai
    del data["ai"]
    assert engine.GameState.from_dict(data).ai == {}


def test_board_names_former_players_of_ai_nations():
    state = new()
    engine.make_ai(state, "BB", "surrender", [])
    rows = {r["player"]: r for r in engine.board(state)}
    assert rows["BB"]["name"] == "KI (p_BB)" and rows["CC"]["name"] == "KI"


def test_nation_start_gold_overrides_the_rules():
    map_data = engine.load_map(TEST_MAP)
    map_data["nations"]["AA"]["start_gold"] = 33
    rules = engine.load_rules({}, {"start_gold": 7})
    state = engine.new_game(map_data, {"AA": "a", "BB": "b"}, rules, 1)
    assert state.players["AA"]["gold"] == 33 and state.players["BB"]["gold"] == 7


# --- map checks used by the editor ------------------------------------------
@pytest.mark.parametrize("change", [
    lambda m: m["provinces"]["A1"].update(income=-1),
    lambda m: m["provinces"]["A1"].update(income="viel"),
    lambda m: m["provinces"]["A1"].update(name=" "),
    lambda m: m["nations"]["AA"].update(name=""),
    lambda m: m["nations"]["AA"].update(start_gold=-5),
    lambda m: m.update(rules={"no_such_rule": 1}),
    lambda m: m.update(rules={"max_alliance_size": "zwei"}),
    lambda m: m.update(rules={"max_alliance_size": True}),
    lambda m: m.update(rules={"victory_share_single": -0.5}),
])
def test_map_value_checks(change):
    broken = copy.deepcopy(engine.load_map(TEST_MAP))
    change(broken)
    with pytest.raises(engine.MapError):
        engine.validate_map(broken)


def test_good_map_rules_pass():
    data = copy.deepcopy(engine.load_map(TEST_MAP))
    data["rules"] = {"max_alliance_size": 3, "victory_share_single": 0.5, "ai_recruit_per_city": 2, "alliance_min_turns": 4}
    data["nations"]["AA"]["start_gold"] = 12.5
    engine.validate_map(data)
