"""Movement, forced march, combat and conquest."""
import engine
from engine.combat import hp_attrition, strength_formula
from fractions import Fraction

from conftest import (A1_CAP, A1_MID, A2_CAP, B1_CAP, B2_CAP, C1_CAP, N1_CAP, SEA, kinds, make_game, of_kind, put)


def move(army, count, *path):
    return {"type": "move", "army": army, "count": count, "path": [list(p) for p in path]}


def march(army, on=True):
    return {"type": "forced_march", "army": army, "on": on}


def errors_of(state, player, *orders):
    return engine.validate_orders(state, player, list(orders))


# --- paths, range, forced march -----------------------------------------
def test_simple_move_and_text():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID)]})
    assert state.armies["a1"]["field"] == A1_MID
    assert of_kind(events, "move")[0]["text"] == "Aland zieht 3 Divisionen nach Nordaland."
    assert of_kind(events, "move")[0]["to"] == A1_MID


def test_range_is_one_by_default():
    state = make_game(standing_marches=False)
    put(state, "AA", A1_CAP, 3)
    assert errors_of(state, "AA", move("a1", 3, A1_MID, A2_CAP))[0]
    assert errors_of(state, "AA", move("a1", 3, A1_MID)) == [[]]


def test_move_range_setting():
    state = make_game(move_range=2)
    put(state, "AA", A1_CAP, 3)
    assert errors_of(state, "AA", move("a1", 3, A1_MID, A2_CAP)) == [[]]


def test_forced_march_extends_range_even_if_toggle_entered_later():
    state = make_game(standing_marches=False)
    put(state, "AA", A1_CAP, 3)
    path = [A1_MID, A2_CAP, N1_CAP]
    assert errors_of(state, "AA", move("a1", 3, *path))[0]
    assert errors_of(state, "AA", move("a1", 3, *path), march("a1")) == [[], []]
    assert errors_of(state, "AA", move("a1", 3, *path, B1_CAP), march("a1"))[0]


def test_forced_march_toggle_before_movement_and_persists():
    state = make_game()
    put(state, "AA", A1_CAP, 8)
    events = engine.resolve_turn(state, {"AA": [move("a1", 8, A1_MID, A2_CAP), march("a1")]})
    assert kinds(events).index("forced_march") < kinds(events).index("move")
    assert state.armies["a1"]["forced_march"] is True and state.armies["a1"]["field"] == A2_CAP
    engine.resolve_turn(state, {"AA": [march("a1", False)]})
    assert state.armies["a1"]["forced_march"] is False


def test_forced_march_off_restores_range():
    state = make_game(standing_marches=False)
    put(state, "AA", A1_CAP, 3, forced_march=True)
    assert errors_of(state, "AA", move("a1", 3, A1_MID, A2_CAP)) == [[]]
    assert errors_of(state, "AA", move("a1", 3, A1_MID, A2_CAP), march("a1", False))[0]


def test_path_errors():
    state = make_game(move_range=3)
    put(state, "AA", A1_CAP, 3)
    put(state, "AA", [1, 3], 2)
    assert errors_of(state, "AA", move("a1", 3, A2_CAP))[0]                    # not adjacent
    assert errors_of(state, "AA", move("a2", 2, [1, 4]))[0] == ["Ablegen geht nur von einem eigenen Hafen."]
    assert errors_of(state, "AA", move("a1", 3))[0]                            # empty
    assert errors_of(state, "AA", move("a1", 4, A1_MID))[0]                    # too many divisions
    assert errors_of(state, "AA", move("a9", 1, A1_MID))[0]                    # unknown army
    assert errors_of(state, "AA", move("a1", 0, A1_MID))[0]
    assert errors_of(state, "AA", {"type": "move", "army": "a1"})[0]           # malformed
    assert errors_of(state, "AA", {"type": "dance"})[0]


def test_cannot_order_foreign_army_or_move_more_than_movable():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    assert errors_of(state, "BB", move("a1", 3, A1_MID))[0]
    two = errors_of(state, "AA", move("a1", 2, A1_MID), move("a1", 2, A1_MID))
    assert two[0] == [] and two[1]


def test_blocked_land_not_passable():
    state = make_game()
    put(state, "AA", [7, 3], 2)
    assert errors_of(state, "AA", move("a1", 2, [7, 4]))[0]  # ?SE


# --- split / merge -------------------------------------------------------
def test_split_inherits_forced_march():
    state = make_game()
    put(state, "AA", A1_CAP, 5, forced_march=True)
    engine.resolve_turn(state, {"AA": [move("a1", 2, A1_MID, A2_CAP)]})
    assert state.armies["a1"]["divisions"] == 3 and state.armies["a1"]["field"] == A1_CAP
    new = state.armies["a2"]
    assert new["divisions"] == 2 and new["field"] == A2_CAP and new["forced_march"] is True


def test_army_splits_in_several_directions():
    """G56: several moves per army, as long as the total stays within its movable divisions."""
    state = make_game()
    put(state, "AA", A1_MID, 5)
    orders = [move("a1", 2, A1_CAP), move("a1", 3, A2_CAP)]
    assert engine.validate_orders(state, "AA", orders) == [[], []]
    engine.resolve_turn(state, {"AA": orders})
    assert state.army_at(A1_CAP)["divisions"] == 2
    assert state.army_at(A2_CAP)["divisions"] == 3 and state.army_at(A2_CAP)["id"] == "a1"
    assert state.army_at(A1_MID) is None


def test_moves_of_one_army_cannot_exceed_its_divisions():
    state = make_game()
    put(state, "AA", A1_MID, 5)
    errors = engine.validate_orders(state, "AA", [move("a1", 3, A1_CAP), move("a1", 3, A2_CAP),
                                                  move("a1", 2, A2_CAP), move("a1", 1, A1_CAP)])
    assert errors[0] == [] and errors[1] == ["Nur noch 2 Divisionen können ziehen."]
    assert errors[2] == [] and errors[3] == ["Alle Divisionen der Armee haben schon einen Zugbefehl."]


def test_split_without_forced_march():
    state = make_game()
    put(state, "AA", A1_CAP, 5)
    engine.resolve_turn(state, {"AA": [move("a1", 2, A1_MID)]})
    assert state.armies["a2"]["forced_march"] is False


def test_merge_keeps_standing_army_id_and_flag():
    state = make_game()
    put(state, "AA", A1_MID, 2)
    put(state, "AA", A1_CAP, 3, forced_march=True)
    events = engine.resolve_turn(state, {"AA": [move("a2", 3, A1_MID)]})
    assert list(state.armies) == ["a1"]
    assert state.armies["a1"]["divisions"] == 5 and state.armies["a1"]["forced_march"] is False
    merge = of_kind(events, "merge")[0]
    assert merge["army"] == "a2" and merge["into"] == "a1" and merge["field"] == A1_MID


def test_pass_over_own_army_without_merging():
    state = make_game()
    put(state, "AA", A1_MID, 2)
    put(state, "AA", A1_CAP, 3, forced_march=True)
    engine.resolve_turn(state, {"AA": [move("a2", 3, A1_MID, A2_CAP)]})
    assert state.armies["a1"]["field"] == A1_MID and state.armies["a2"]["field"] == A2_CAP


def test_moving_whole_army_keeps_id():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID)]})
    assert list(state.armies) == ["a1"]


# --- sequential execution ------------------------------------------------
def test_target_moved_away_means_no_fight():
    state = make_game()
    put(state, "BB", N1_CAP, 3)
    put(state, "AA", A2_CAP, 3)
    state.player_order = ["BB", "AA"]
    events = engine.resolve_turn(state, {"BB": [move("a1", 3, B1_CAP)], "AA": [move("a2", 3, N1_CAP)]})
    assert not of_kind(events, "fight")
    assert state.owners["N1"] == "AA"


def test_target_still_there_means_fight():
    state = make_game()
    put(state, "BB", N1_CAP, 3)
    put(state, "AA", A2_CAP, 3)
    state.player_order = ["AA", "BB"]
    events = engine.resolve_turn(state, {"BB": [move("a1", 3, B1_CAP)], "AA": [move("a2", 3, N1_CAP)]})
    assert len(of_kind(events, "fight")) == 1
    assert not state.armies  # equal strength: both destroyed; BB order was skipped
    assert of_kind(events, "skipped")


def test_destroyed_army_order_is_skipped():
    state = make_game()
    put(state, "BB", N1_CAP, 2)
    put(state, "AA", A2_CAP, 5)
    state.player_order = ["AA", "BB"]
    events = engine.resolve_turn(state, {"AA": [move("a2", 5, N1_CAP)], "BB": [move("a1", 2, B1_CAP)]})
    skipped = of_kind(events, "skipped")
    assert len(skipped) == 1 and skipped[0]["player"] == "BB"
    assert skipped[0]["order"]["type"] == "move"


def test_fewer_divisions_than_ordered_all_remaining_move():
    state = make_game()
    put(state, "BB", N1_CAP, 5)
    put(state, "AA", A2_CAP, 3)
    state.player_order = ["AA", "BB"]
    engine.resolve_turn(state, {"AA": [move("a2", 3, N1_CAP)], "BB": [move("a1", 5, B1_CAP)]})
    # AA 3 attacks BB 5: AA destroyed, BB loses 3 -> 2 left, which all move
    assert state.armies["a1"]["divisions"] == 2 and state.armies["a1"]["field"] == B1_CAP


def test_player_order_decides_who_moves_first():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    put(state, "BB", B1_CAP, 2)
    state.player_order = ["BB", "AA"]
    events = engine.resolve_turn(state, {"AA": [move("a1", 2, A1_MID)], "BB": [move("a2", 2, N1_CAP)]})
    moves = of_kind(events, "move")
    assert [m["player"] for m in moves] == ["BB", "AA"]


def test_entry_order_within_player():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    put(state, "AA", A2_CAP, 2)
    events = engine.resolve_turn(state, {"AA": [move("a2", 2, N1_CAP), move("a1", 2, A1_MID)]})
    assert [m["army"] for m in of_kind(events, "move")] == ["a2", "a1"]


# --- combat ---------------------------------------------------------------
def test_rules_example_10_forced_march_vs_4():
    state = make_game()
    put(state, "AA", A1_CAP, 10, forced_march=True)   # deals 5, has 10 hit points
    put(state, "BB", A1_MID, 4)
    events = engine.resolve_turn(state, {"AA": [move("a1", 10, A1_MID)]})
    fight = of_kind(events, "fight")[0]
    assert (fight["attacker_losses"], fight["defender_losses"], fight["winner"]) == (4, 4, "AA")
    assert state.armies["a1"]["divisions"] == 6 and state.armies["a1"]["field"] == A1_MID
    assert fight["field"] == A1_MID and fight["attacker"] == "AA" and fight["defender"] == "BB"
    assert fight["text"].startswith("Kampf bei Nordaland:")


def test_equal_strength_both_die():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    put(state, "BB", A1_MID, 3)
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID)]})
    assert not state.armies and of_kind(events, "fight")[0]["winner"] is None


def test_single_forced_march_division_loses():
    state = make_game()
    put(state, "AA", A1_CAP, 1, forced_march=True)  # deals 0.5: the defender keeps 0.5 hit points -> 1 division
    put(state, "BB", A1_MID, 1)
    engine.resolve_turn(state, {"AA": [move("a1", 1, A1_MID)]})
    assert list(state.armies) == ["a2"] and state.armies["a2"]["divisions"] == 1


def test_survivor_rounding_setting():
    state = make_game(survivor_rounding="down")
    put(state, "AA", A1_CAP, 1, forced_march=True)
    put(state, "BB", A1_MID, 1)
    engine.resolve_turn(state, {"AA": [move("a1", 1, A1_MID)]})
    assert not state.armies


def test_defender_wins_attacker_gone():
    state = make_game()
    put(state, "AA", A1_CAP, 2)
    put(state, "BB", A1_MID, 5)
    engine.resolve_turn(state, {"AA": [move("a1", 2, A1_MID)]})
    assert list(state.armies) == ["a2"] and state.armies["a2"]["divisions"] == 3


def test_both_survive_attacker_stays_back():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    put(state, "BB", A1_MID, 4, forced_march=True)  # deals 2
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID)]})
    assert of_kind(events, "fight")[0]["winner"] == "both"
    assert state.armies["a1"]["divisions"] == 1 and state.armies["a1"]["field"] == A1_CAP   # G59
    assert state.armies["a2"]["divisions"] == 1 and state.armies["a2"]["field"] == A1_MID


def test_split_part_that_survives_merges_back():
    state = make_game()
    put(state, "AA", A1_CAP, 5)
    put(state, "BB", A1_MID, 4, forced_march=True)
    engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID)]})
    assert [(a["field"], a["divisions"]) for a in state.armies.values() if a["owner"] == "AA"] == [(A1_CAP, 3)]


def test_fight_stops_movement():
    state = make_game()
    put(state, "AA", A1_CAP, 10, forced_march=True)
    put(state, "BB", A2_CAP, 2)
    events = engine.resolve_turn(state, {"AA": [move("a1", 10, A1_MID, A2_CAP, N1_CAP)]})
    army = state.armies["a1"]
    assert army["field"] == A2_CAP and army["divisions"] == 8
    assert state.owners["N1"] is None
    assert of_kind(events, "move")[0]["to"] == A2_CAP


def side(divisions, value=1):
    return [{"divisions": divisions, "value": Fraction(value), "hp": Fraction(1)}]


def test_formula_functions_directly():
    rules = engine.load_rules({}, {})
    assert hp_attrition(rules, side(10, Fraction(1, 2)), side(4)) == ([4], [4])
    assert hp_attrition(rules, side(3), side(3)) == ([3], [3])
    assert hp_attrition(rules, side(3), side(5)) == ([3], [3])
    assert strength_formula(rules, side(10, Fraction(1, 2)), side(4)) == ([8], [4])
    assert strength_formula(rules, side(3), side(3)) == ([3], [3])


def test_old_3_0_formula_still_selectable():
    state = make_game(combat_formula="strength_3_0")
    put(state, "AA", A1_CAP, 10, forced_march=True)
    put(state, "BB", A1_MID, 4)
    engine.resolve_turn(state, {"AA": [move("a1", 10, A1_MID)]})
    assert state.armies["a1"]["divisions"] == 2


def test_strength_rounding_setting():
    state = make_game(combat_formula="strength_3_0", strength_rounding="up")
    put(state, "AA", A1_CAP, 3, forced_march=True)  # ceil(1.5) = 2
    put(state, "BB", A1_MID, 2)
    engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID)]})
    assert not state.armies  # 2 vs 2


def test_combat_formula_registry():
    from engine.combat import FORMULAS
    assert {"hp_attrition", "strength_3_0"} <= set(FORMULAS)


# --- conquest -------------------------------------------------------------
def test_conquer_empty_neutral_capital():
    state = make_game()
    put(state, "AA", A2_CAP, 5)
    events = engine.resolve_turn(state, {"AA": [move("a1", 5, N1_CAP)]})
    conquest = of_kind(events, "conquest")[0]
    assert (conquest["province"], conquest["cost"], conquest["old_owner"]) == ("N1", 2, None)
    assert state.owners["N1"] == "AA"
    assert state.armies["a1"]["divisions"] == 3 and state.armies["a1"]["field"] == N1_CAP


def test_conquered_province_gives_income_next_turn():
    state = make_game(upkeep_per_division=0)
    put(state, "AA", A2_CAP, 5)
    gold = state.players["AA"]["gold"]
    engine.resolve_turn(state, {"AA": [move("a1", 5, N1_CAP)]})
    assert state.players["AA"]["gold"] == gold + 3 + 1   # gold phase ran before the conquest
    engine.resolve_turn(state, {})
    assert state.players["AA"]["gold"] == gold + 4 + 3 + 1 + 2


def test_conquest_exactly_enough_army_used_up():
    state = make_game()
    put(state, "AA", A2_CAP, 2)
    engine.resolve_turn(state, {"AA": [move("a1", 2, N1_CAP)]})
    assert state.owners["N1"] == "AA" and not state.armies


def test_conquest_exactly_enough_not_allowed_by_setting():
    state = make_game(conquest_allow_army_used_up=False)
    put(state, "AA", A2_CAP, 2)
    engine.resolve_turn(state, {"AA": [move("a1", 2, N1_CAP)]})
    assert state.owners["N1"] is None and state.armies["a1"]["field"] == A2_CAP


def test_conquest_not_enough_goes_back():
    state = make_game()
    put(state, "AA", A2_CAP, 1)
    events = engine.resolve_turn(state, {"AA": [move("a1", 1, N1_CAP)]})
    failed = of_kind(events, "conquest_failed")[0]
    assert failed["province"] == "N1" and failed["cost"] == 2 and failed["back_to"] == A2_CAP
    assert state.owners["N1"] is None and state.armies["a1"]["field"] == A2_CAP


def test_failed_conquest_returns_to_field_before_capital():
    state = make_game()
    put(state, "AA", A1_CAP, 1, forced_march=True)
    events = engine.resolve_turn(state, {"AA": [move("a1", 1, A1_MID, A2_CAP, N1_CAP)]})
    assert state.armies["a1"]["field"] == A2_CAP
    assert of_kind(events, "conquest_failed")[0]["back_to"] == A2_CAP


def test_failed_conquest_single_step_returns_to_start_and_merges():
    state = make_game()
    put(state, "AA", A2_CAP, 3)
    put(state, "AA", [2, 1], 1)  # another own army in the same province, not on the start field
    engine.resolve_turn(state, {"AA": [move("a1", 1, N1_CAP)]})  # split 1 of 3: cost 2 -> fails
    assert state.armies["a1"]["divisions"] == 3 and state.armies["a1"]["field"] == A2_CAP
    assert len(state.armies) == 2


def test_capitals_passed_midway_are_not_conquered():
    state = make_game()
    put(state, "AA", A2_CAP, 6, forced_march=True)
    engine.resolve_turn(state, {"AA": [move("a1", 6, N1_CAP, B1_CAP)]})
    assert state.owners["N1"] is None and state.owners["B1"] == "AA"
    assert state.armies["a1"]["divisions"] == 4


def test_old_owner_armies_stay_after_conquest():
    state = make_game()
    put(state, "AA", B1_CAP, 3)
    put(state, "BB", [5, 3], 2)
    engine.resolve_turn(state, {"AA": [move("a1", 3, B2_CAP)]})
    assert state.owners["B2"] == "AA"
    assert state.armies["a2"]["owner"] == "BB" and state.armies["a2"]["field"] == [5, 3]
    assert state.armies["a1"]["divisions"] == 2


def test_fight_on_capital_then_conquest():
    state = make_game()
    put(state, "AA", N1_CAP, 5)
    put(state, "BB", B1_CAP, 2)
    events = engine.resolve_turn(state, {"AA": [move("a1", 5, B1_CAP)]})
    assert kinds([e for e in events if e["kind"] in ("fight", "conquest")]) == ["fight", "conquest"]
    assert state.owners["B1"] == "AA" and state.armies["a1"]["divisions"] == 3 - 2


def test_conquest_cost_factor():
    state = make_game(conquest_cost_factor=2)
    put(state, "AA", A2_CAP, 5)
    engine.resolve_turn(state, {"AA": [move("a1", 5, N1_CAP)]})
    assert state.armies["a1"]["divisions"] == 1


def test_attacker_losing_at_capital_does_not_conquer():
    state = make_game()
    put(state, "AA", N1_CAP, 2)
    put(state, "BB", B1_CAP, 5)
    engine.resolve_turn(state, {"AA": [move("a1", 2, B1_CAP)]})
    assert state.owners["B1"] == "BB"


def test_moving_onto_own_province_capital_is_not_conquest():
    state = make_game()
    put(state, "AA", A1_MID, 2)
    events = engine.resolve_turn(state, {"AA": [move("a1", 2, A1_CAP)]})
    assert not of_kind(events, "conquest")


# --- preview and board ------------------------------------------------------
def test_preview_move_with_fight_and_conquest():
    state = make_game()
    put(state, "AA", N1_CAP, 6)
    put(state, "BB", B1_CAP, 2)
    result = engine.preview_move(state, "AA", "a1", 6, [B1_CAP])
    assert result["valid"] and result["end_field"] == B1_CAP
    assert result["fight"] == {"defender": "BB", "attacker_losses": 2, "defender_losses": 2, "winner": "AA"}
    assert result["conquest"] == {"province": "B1", "cost": 2, "possible": True}
    assert "Kampf gegen Bland" in result["text"] and "Eroberung kostet 2 Divisionen" in result["text"]
    assert state.armies["a1"]["divisions"] == 6  # nothing changed


def test_preview_uses_pending_forced_march():
    state = make_game()
    put(state, "AA", N1_CAP, 6)
    put(state, "BB", B1_CAP, 2)
    result = engine.preview_move(state, "AA", "a1", 6, [B1_CAP], forced_march=True)
    # deals 6 x 0.5 = 3 against 2 hit points; loses the 2 the defender deals
    assert result["fight"] == {"defender": "BB", "attacker_losses": 2, "defender_losses": 2, "winner": "AA"}
    assert state.armies["a1"]["forced_march"] is False  # nothing changed


def test_preview_move_invalid_and_plain():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    bad = engine.preview_move(state, "AA", "a1", 6, [N1_CAP])
    assert bad["valid"] is False and bad["errors"] and bad["fight"] is None and bad["end_field"] is None
    ok = engine.preview_move(state, "AA", "a1", 6, [A1_MID])
    assert ok["valid"] and ok["fight"] is None and ok["conquest"] is None


def test_preview_conquest_not_possible():
    state = make_game()
    put(state, "AA", A2_CAP, 1)
    assert engine.preview_move(state, "AA", "a1", 1, [N1_CAP])["conquest"]["possible"] is False


def test_board_rows():
    state = make_game()
    put(state, "AA", A1_CAP, 6)
    row = engine.board(state)[0]
    assert row == {"player": "AA", "name": "p_AA", "provinces": 2, "fields": 9, "share": 9 / 24, "share_counted": 9 / 24,
                   "alliance": None, "income": 4,
                   "upkeep": 1.5, "armies": 1, "divisions": 6, "ships": 0}


def test_player_without_provinces_stays():
    state = make_game()
    engine.resolve_turn(state, {"BB": [{"type": "give_province", "province": "B1", "to": "AA"},
                                       {"type": "give_province", "province": "B2", "to": "AA"}]})
    assert "BB" in state.players and engine.board(state)[1]["provinces"] == 0
    engine.resolve_turn(state, {})


def test_conquer_province_of_nation_without_player():
    state = make_game()
    put(state, "AA", B2_CAP, 4)
    engine.resolve_turn(state, {"AA": [move("a1", 4, C1_CAP)]})
    assert state.owners["C1"] == "AA"  # neutral province, cost 2


# --- replay snapshots ------------------------------------------------------
def test_snap_on_last_event_of_each_order():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    put(state, "BB", B1_CAP, 2)
    events = engine.resolve_turn(state, {"AA": [move("a1", 2, A1_MID), move("a1", 1, A1_MID)], "BB": []})
    snapped = [e for e in events if "snap" in e]
    assert [e["kind"] for e in snapped] == ["move", "merge"]
    first = snapped[0]["snap"]
    assert first["armies"]["a1"]["divisions"] == 1 and first["armies"]["a3"]["field"] == A1_MID
    assert not any("snap" in e for e in events if e["kind"] in ("turn_start", "income", "upkeep"))
    last = snapped[-1]["snap"]
    strip = lambda armies: {i: {k: v for k, v in a.items() if k != "fresh"} for i, a in armies.items()}
    assert strip(last["armies"]) == strip(state.armies) and last["owners"] == state.owners


def test_snap_is_a_copy_and_skipped_has_one():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID), move("zz", 1, A1_MID)]})
    snap = of_kind(events, "move")[0]["snap"]
    assert snap["armies"]["a1"]["field"] == A1_MID
    state.armies["a1"]["field"] = [9, 9]
    assert snap["armies"]["a1"]["field"] == A1_MID
    assert "snap" in of_kind(events, "skipped")[0]
