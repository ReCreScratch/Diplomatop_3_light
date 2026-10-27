"""Gold phase: income, upkeep, debt, decimals; transfers."""
import engine
from conftest import A1_CAP, A2_CAP, make_game, of_kind, put


def test_no_income_before_first_resolution():
    state = make_game()
    assert state.players["AA"]["gold"] == 10
    assert state.players["BB"]["gold"] == 10
    assert state.players["AA"]["provinces_at_turn_start"] == 2


def test_income_and_upkeep_at_turn_end():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    events = engine.resolve_turn(state, {})
    # income 3 + 1, upkeep 6 x 0.25 = 1.5, no rounding (4.0)
    assert state.players["AA"]["gold"] == 10 + 4 - 1.5
    assert [e["amount"] for e in of_kind(events, "upkeep") if e["player"] == "AA"] == [1.5]
    assert [e["amount"] for e in of_kind(events, "income") if e["player"] == "AA"] == [4]


def test_gold_phase_runs_after_recruitment_before_movement():
    state = make_game(start_gold=100)
    events = engine.resolve_turn(state, {"AA": [{"type": "recruit", "field": A1_CAP, "count": 4}]})
    order = [e["kind"] for e in events]
    assert order.index("recruit") < order.index("income") < order.index("turn_start")
    assert of_kind(events, "upkeep")[0]["amount"] == 1  # the new divisions already pay upkeep
    assert state.players["AA"]["gold"] == 100 - 20 + 4 - 1


def test_upkeep_rounding_modes():
    for mode, expected in (("none", 1.25), ("half_up", 1), ("up", 2), ("down", 1)):
        state = make_game(upkeep_rounding=mode)
        put(state, "AA", A1_CAP, 5)  # 1.25
        assert engine.board(state)[0]["upkeep"] == expected, mode


def test_upkeep_rounded_on_nation_total_not_per_army():
    state = make_game(upkeep_rounding="half_up")
    put(state, "AA", A1_CAP, 1)
    put(state, "AA", A2_CAP, 1)  # 0.5 total -> 1; per army it would round to 0 each
    assert engine.board(state)[0]["upkeep"] == 1


def test_upkeep_per_army_setting():
    state = make_game(upkeep_per_army=2)
    put(state, "AA", A1_CAP, 3)
    put(state, "AA", A2_CAP, 3)  # 1.5 + 2 x 2
    assert engine.board(state)[0]["upkeep"] == 5.5


def test_no_upkeep_per_army_by_default():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    put(state, "AA", A2_CAP, 2)
    assert engine.board(state)[0]["upkeep"] == 1


def test_draft_upkeep_setting():
    state = make_game(upkeep_per_division=0.5)
    put(state, "AA", A1_CAP, 5)
    assert engine.board(state)[0]["upkeep"] == 2.5


def test_gold_keeps_decimals_over_turns():
    state = make_game(start_gold=0)
    put(state, "AA", A1_CAP, 1)
    for _ in range(4):
        engine.resolve_turn(state, {})
    assert state.players["AA"]["gold"] == 4 * (4 - 0.25)
    assert isinstance(engine.GameState.from_dict(state.to_dict()).players["AA"]["gold"], int)


def test_debt_allowed_and_no_penalty():
    state = make_game(start_gold=0)
    put(state, "AA", A1_CAP, 40)  # upkeep 10, income 4
    engine.resolve_turn(state, {})
    assert state.players["AA"]["gold"] == 4 - 10
    engine.resolve_turn(state, {})
    assert state.players["AA"]["gold"] == -6 + 4 - 10


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
    assert state.players["AA"]["gold"] == 10 - 5 + 4
    assert state.players["BB"]["gold"] == 10 + 5 + 3
    assert of_kind(events, "send_gold")[0]["text"] == "Aland sendet 5 Gold an Bland."


def test_send_gold_validation():
    state = make_game()

    def check(order):
        return engine.validate_orders(state, "AA", [order])[0]
    assert check({"type": "send_gold", "to": "AA", "amount": 1})
    assert check({"type": "send_gold", "to": "ZZ", "amount": 1})
    assert check({"type": "send_gold", "to": "BB", "amount": 0})
    assert check({"type": "send_gold", "to": "BB", "amount": -3})
    assert check({"type": "send_gold", "to": "BB", "amount": 11})
    assert not check({"type": "send_gold", "to": "BB", "amount": 10})


def test_received_gold_not_spendable_same_turn():
    state = make_game()  # BB has 10 gold; gold sent to BB this turn does not count when entering orders
    assert engine.validate_orders(state, "BB", [{"type": "recruit", "field": [4, 2], "count": 3}])[0]


def test_gold_check_counts_recruits_and_sent_gold():
    state = make_game()  # AA has 10
    orders = [{"type": "recruit", "field": A1_CAP, "count": 1},          # 5
              {"type": "send_gold", "to": "BB", "amount": 6},             # 11 in total: too much
              {"type": "send_gold", "to": "BB", "amount": 5}]             # 10 in total: fine
    errors = engine.validate_orders(state, "AA", orders)
    assert errors[0] == [] and errors[1] and errors[2] == []


def test_give_province_and_gift_record():
    state = make_game()
    events = engine.resolve_turn(state, {"AA": [{"type": "give_province", "province": "A2", "to": "BB"}]})
    assert state.owners["A2"] == "BB"
    assert state.gifts == [{"province": "A2", "from": "AA", "to": "BB", "turn": 1}]
    assert state.players["BB"]["provinces_at_turn_start"] == 3
    assert of_kind(events, "give_province")[0]["to"] == "BB"
    assert state.players["BB"]["gold"] == 10 + 3  # income was paid before the gift


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


def test_recruitment_runs_before_transfers():
    state = make_game()
    engine.resolve_turn(state, {"AA": [
        {"type": "give_province", "province": "A2", "to": "BB"},
        {"type": "recruit", "field": A2_CAP, "count": 1}]})
    army = state.army_at(A2_CAP)
    assert army["owner"] == "AA"  # recruited before the gift was carried out (4.0 phase order)
    assert state.owners["A2"] == "BB"
