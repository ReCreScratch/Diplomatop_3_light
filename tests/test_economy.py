"""Turn start: income, upkeep, debt; transfers."""
import engine
from conftest import A1_CAP, A2_CAP, make_game, of_kind, put


def test_income_in_turn_one():
    state = make_game()
    assert state.players["AA"]["gold"] == 10 + 3 + 1
    assert state.players["BB"]["gold"] == 10 + 2 + 1
    assert state.players["AA"]["provinces_at_turn_start"] == 2


def test_income_and_upkeep_next_turn():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    before = state.players["AA"]["gold"]
    events = engine.resolve_turn(state, {})
    # 6 x 0.25 + 2 = 3.5 -> half up 4
    assert state.players["AA"]["gold"] == before + 4 - 4
    assert [e["amount"] for e in of_kind(events, "upkeep") if e["player"] == "AA"] == [4]
    assert [e["amount"] for e in of_kind(events, "income") if e["player"] == "AA"] == [4]


def test_upkeep_rounding_modes():
    for mode, expected in (("half_up", 4), ("up", 4), ("down", 3)):
        state = make_game(upkeep_rounding=mode)
        put(state, "AA", A1_CAP, 6)  # 3.5
        assert engine.board(state)[0]["upkeep"] == expected, mode
    for mode, expected in (("half_up", 3), ("up", 4), ("down", 3)):
        state = make_game(upkeep_rounding=mode)
        put(state, "AA", A1_CAP, 5)  # 3.25
        assert engine.board(state)[0]["upkeep"] == expected, mode


def test_upkeep_rounded_on_nation_total_not_per_army():
    state = make_game(upkeep_per_army=0)
    put(state, "AA", A1_CAP, 1)
    put(state, "AA", A2_CAP, 1)  # 0.5 total -> 1; per army it would round to 0 each
    assert engine.board(state)[0]["upkeep"] == 1


def test_upkeep_per_army_and_division():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    put(state, "AA", A2_CAP, 3)  # 1.5 + 2 x 2 = 5.5 -> 6
    assert engine.board(state)[0]["upkeep"] == 6


def test_draft_upkeep_setting():
    state = make_game(upkeep_per_division=0.5, upkeep_per_army=0)
    put(state, "AA", A1_CAP, 5)
    assert engine.board(state)[0]["upkeep"] == 3  # 2.5 half up


def test_debt_allowed_and_no_penalty():
    state = make_game(start_gold=0)
    put(state, "AA", A1_CAP, 40)  # upkeep 12, income 4
    engine.resolve_turn(state, {})
    assert state.players["AA"]["gold"] == 4 + 4 - 12
    engine.resolve_turn(state, {})
    assert state.players["AA"]["gold"] == -4 + 4 - 12


def test_cannot_recruit_in_debt():
    state = make_game(start_gold=0)
    state.players["AA"]["gold"] = -1
    assert engine.validate_orders(state, "AA", [{"type": "recruit", "field": A1_CAP, "count": 1}])[0]


def test_spending_into_debt_setting():
    state = make_game(start_gold=0, allow_spending_into_debt=True)
    assert engine.validate_orders(state, "AA", [{"type": "recruit", "field": A1_CAP, "count": 2}]) == [[]]


# --- transfers -------------------------------------------------------
def test_send_gold():
    state = make_game()
    events = engine.resolve_turn(state, {"AA": [{"type": "send_gold", "to": "BB", "amount": 5}]})
    assert state.players["AA"]["gold"] == 14 - 5 + 4
    assert state.players["BB"]["gold"] == 13 + 5 + 3
    assert of_kind(events, "send_gold")[0]["text"] == "Aland sendet 5 Gold an Bland."


def test_send_gold_validation():
    state = make_game()

    def check(order):
        return engine.validate_orders(state, "AA", [order])[0]
    assert check({"type": "send_gold", "to": "AA", "amount": 1})
    assert check({"type": "send_gold", "to": "ZZ", "amount": 1})
    assert check({"type": "send_gold", "to": "BB", "amount": 0})
    assert check({"type": "send_gold", "to": "BB", "amount": -3})
    assert check({"type": "send_gold", "to": "BB", "amount": 15})
    assert not check({"type": "send_gold", "to": "BB", "amount": 14})


def test_received_gold_not_spendable_same_turn():
    state = make_game()  # BB has 13 gold; gold sent to BB this turn does not count when entering orders
    assert engine.validate_orders(state, "BB", [{"type": "recruit", "field": [4, 2], "count": 5}])[0]


def test_gold_check_counts_recruits_and_sent_gold():
    state = make_game()  # AA has 14
    orders = [{"type": "recruit", "field": A1_CAP, "count": 3},          # 9
              {"type": "send_gold", "to": "BB", "amount": 6},             # 15 in total: too much
              {"type": "send_gold", "to": "BB", "amount": 5}]             # 14 in total: fine
    errors = engine.validate_orders(state, "AA", orders)
    assert errors[0] == [] and errors[1] and errors[2] == []


def test_give_province_and_gift_record():
    state = make_game()
    events = engine.resolve_turn(state, {"AA": [{"type": "give_province", "province": "A2", "to": "BB"}]})
    assert state.owners["A2"] == "BB"
    assert state.gifts == [{"province": "A2", "from": "AA", "to": "BB", "turn": 1}]
    assert state.players["BB"]["provinces_at_turn_start"] == 3
    assert of_kind(events, "give_province")[0]["to"] == "BB"
    assert state.players["BB"]["gold"] == 13 + 4  # income 2 + 1 + 1


def test_give_province_validation():
    state = make_game()

    def check(order):
        return engine.validate_orders(state, "AA", [order])[0]
    assert check({"type": "give_province", "province": "B1", "to": "BB"})
    assert check({"type": "give_province", "province": "A2", "to": "AA"})
    assert check({"type": "give_province", "province": "N1", "to": "BB"})
    assert not check({"type": "give_province", "province": "A2", "to": "BB"})
    two = engine.validate_orders(state, "AA", [{"type": "give_province", "province": "A2", "to": "BB"}] * 2)
    assert two[0] == [] and two[1]


def test_transfers_run_before_recruitment():
    state = make_game()
    events = engine.resolve_turn(state, {"AA": [
        {"type": "recruit", "field": A2_CAP, "count": 1},
        {"type": "give_province", "province": "A2", "to": "BB"}]})
    assert not state.armies  # the gift came first, so recruiting on the now foreign capital was skipped
    assert of_kind(events, "skipped")
