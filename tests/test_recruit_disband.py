"""Recruiting and disbanding."""
import engine
from conftest import A1_CAP, A1_MID, A2_CAP, B1_CAP, make_game, of_kind, put


def recruit(field, count):
    return {"type": "recruit", "field": field, "count": count}


def test_recruit_on_empty_capital_creates_army():
    state = make_game()
    events = engine.resolve_turn(state, {"AA": [recruit(A1_CAP, 3)]})
    army = state.armies["a1"]
    assert army["owner"] == "AA" and army["field"] == A1_CAP and army["divisions"] == 3
    assert of_kind(events, "recruit")[0]["text"] == "Aland rekrutiert 3 Divisionen in Nordalandstadt."
    # 14 - 9 gold, then income 4 and upkeep 3 x 0.25 + 2 = 2.75 -> 3
    assert state.players["AA"]["gold"] == 14 - 9 + 4 - 3


def test_recruit_joins_army_on_capital():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    engine.resolve_turn(state, {"AA": [recruit(A1_CAP, 1)]})
    assert len(state.armies) == 1 and state.armies["a1"]["divisions"] == 3


def test_recruit_on_own_army_anywhere():
    state = make_game()
    put(state, "AA", A1_MID, 2)
    assert engine.validate_orders(state, "AA", [recruit(A1_MID, 1)]) == [[]]
    engine.resolve_turn(state, {"AA": [recruit(A1_MID, 2)]})
    assert state.armies["a1"]["divisions"] == 4


def test_recruit_invalid_places():
    state = make_game()
    put(state, "BB", A1_MID, 2)
    errors = engine.validate_orders(state, "AA", [
        recruit(A1_MID, 1),     # enemy army there
        recruit([1, 1], 1),     # own field without capital or army
        recruit(B1_CAP, 1),     # foreign capital
        recruit([0, 0], 1),     # sea
        recruit(A1_CAP, 0),     # zero
    ])
    assert all(errors)


def test_recruit_limit_per_province():
    state = make_game(start_gold=100)  # AA owns 2 provinces -> 6 per turn
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 6)]) == [[]]
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 7)])[0]
    split = engine.validate_orders(state, "AA", [recruit(A1_CAP, 4), recruit(A2_CAP, 3), recruit(A2_CAP, 2)])
    assert split[0] == [] and split[1] and split[2] == []


def test_recruit_limit_uses_provinces_at_turn_start():
    state = make_game(start_gold=100, recruit_limit_per_province=2)
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 4)]) == [[]]
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 5)])[0]


def test_recruit_gold_check_at_entry():
    state = make_game()  # 14 gold, cost 3
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 4)]) == [[]]
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 5)])[0]


def test_division_cost_comes_from_rules():
    state = make_game(division_cost=7)
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 2)]) == [[]]
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 3)])[0]


def test_fresh_divisions_cannot_move():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    engine.resolve_turn(state, {"AA": [recruit(A1_CAP, 3),
                                       {"type": "move", "army": "a1", "count": 2, "path": [A1_MID]}]})
    here = state.army_at(A1_CAP)
    moved = state.army_at(A1_MID)
    assert here["divisions"] == 3 and moved["divisions"] == 2


def test_move_order_for_more_than_movable_moves_only_movable():
    state = make_game()
    put(state, "AA", A1_CAP, 5, fresh=2)
    engine.resolve_turn(state, {"AA": [{"type": "move", "army": "a1", "count": 5, "path": [A1_MID]}]})
    assert state.army_at(A1_MID)["divisions"] == 3
    assert state.army_at(A1_CAP)["divisions"] == 2


def test_all_fresh_army_cannot_be_ordered():
    state = make_game()
    put(state, "AA", A1_CAP, 3, fresh=3)
    assert engine.validate_orders(state, "AA", [{"type": "move", "army": "a1", "count": 3, "path": [A1_MID]}])[0]


def test_recruits_can_move_setting():
    state = make_game(recruits_can_move_same_turn=True)
    put(state, "AA", A1_CAP, 5, fresh=2)
    engine.resolve_turn(state, {"AA": [{"type": "move", "army": "a1", "count": 5, "path": [A1_MID]}]})
    assert state.army_at(A1_MID)["divisions"] == 5


def test_fresh_reset_at_turn_start():
    state = make_game()
    engine.resolve_turn(state, {"AA": [recruit(A1_CAP, 3)]})
    assert state.armies["a1"]["fresh"] == 0
    engine.resolve_turn(state, {"AA": [{"type": "move", "army": "a1", "count": 3, "path": [A1_MID]}]})
    assert state.army_at(A1_MID)["divisions"] == 3


# --- disband -------------------------------------------------------
def test_disband_refund_and_events():
    state = make_game()
    put(state, "AA", A1_CAP, 4)
    events = engine.resolve_turn(state, {"AA": [{"type": "disband", "army": "a1", "count": 3}]})
    assert state.armies["a1"]["divisions"] == 1
    assert state.players["AA"]["gold"] == 14 + 6 + 4 - 2  # refund, income, upkeep 0.25 + 2
    assert of_kind(events, "disband")[0]["count"] == 3


def test_disband_all_removes_army():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    engine.resolve_turn(state, {"AA": [{"type": "disband", "army": "a1", "count": 2}]})
    assert not state.armies


def test_disband_refund_not_spendable_in_same_turn():
    state = make_game(start_gold=0)  # 4 gold
    put(state, "AA", A1_CAP, 4)
    orders = [{"type": "disband", "army": "a1", "count": 3}, recruit(A1_CAP, 2)]  # refund 6 would pay 6
    errors = engine.validate_orders(state, "AA", orders)
    assert errors[0] == [] and errors[1]
    engine.resolve_turn(state, {"AA": [orders[0]]})
    assert state.players["AA"]["gold"] >= 6  # spendable next turn
    assert engine.validate_orders(state, "AA", [recruit(A1_CAP, 2)]) == [[]]


def test_disband_validation():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    put(state, "BB", B1_CAP, 2)
    errors = engine.validate_orders(state, "AA", [
        {"type": "disband", "army": "a1", "count": 3},
        {"type": "disband", "army": "a2", "count": 1},
        {"type": "disband", "army": "a9", "count": 1},
        {"type": "disband", "army": "a1", "count": 0}])
    assert all(errors)


def test_disband_does_not_count_against_recruit_limit():
    state = make_game(start_gold=100)
    put(state, "AA", A1_CAP, 2)
    errors = engine.validate_orders(state, "AA", [{"type": "disband", "army": "a1", "count": 2},
                                                  recruit(A1_CAP, 6)])
    assert errors == [[], []]
