"""Milestone 2: ports, ships, armies at sea, linking, sea combat (RULES.md section 10).

Test map: sea in rows 0 and 4. Ports: A1 at [0, 3] (sea neighbours [0, 4], [1, 4]), B1 at [4, 3]."""
import engine
import json

from conftest import A1_CAP, ROOT, make_game, of_kind, put

PORT_A = [0, 3]
PORT_B = [4, 3]
S0, S1, S2, S3 = [[c, 4] for c in range(4)]


def move(army, count, *path):
    return {"type": "move", "army": army, "count": count, "path": [list(p) for p in path]}


def errors(state, player, *orders):
    return engine.validate_orders(state, player, list(orders))


def ship(field, count):
    return {"type": "build_ship", "field": field, "count": count}


# --- map ------------------------------------------------------------------
def test_ports_load_and_are_checked(map_data, tmp_path):
    state = make_game()
    assert state.is_own_port(PORT_A, "AA") and not state.is_own_port(PORT_A, "BB")
    assert state.next_to_own_port(S0, "AA") and not state.next_to_own_port(S2, "AA")
    bad = dict(map_data)
    bad["provinces"] = {**map_data["provinces"], "A2": {**map_data["provinces"]["A2"], "ports": [[2, 2]]}}
    (tmp_path / "map.json").write_text(json.dumps(bad), encoding="utf-8")
    try:
        engine.load_map(tmp_path)
        assert False, "inland port accepted"
    except engine.MapError as err:
        assert "Küste" in str(err)


def test_europa_has_ports():
    europa = engine.load_map(ROOT / "maps" / "europa")
    assert sum(1 for p in europa["provinces"].values() if p.get("ports")) > 30


# --- building and disbanding ships ----------------------------------------
def test_build_ship_next_to_own_port():
    state = make_game()
    events = engine.resolve_turn(state, {"AA": [ship(S0, 2)]})
    fleet = state.armies["a1"]
    assert fleet["unit"] == "ship" and fleet["field"] == S0 and fleet["divisions"] == 2
    assert of_kind(events, "build_ship")[0]["text"] == "Aland baut 2 Schiffe bei Feld 0/4."
    assert state.players["AA"]["gold"] == 10 - 10 + 4 - 0.5   # cost 5 each, upkeep 0.25 each


def test_build_ship_invalid_places_and_limits():
    state = make_game(start_gold=100)
    put(state, "BB", S1, 1, unit="ship")
    assert all(e for e in errors(state, "AA", ship(S2, 1), ship(PORT_A, 1), ship([4, 4], 1), ship(S1, 1),
                                 ship(S0, 0)))
    both = errors(state, "AA", {"type": "recruit", "field": A1_CAP, "count": 4}, ship(S0, 2), ship(S0, 1))
    assert both[0] == [] and both[1] == [] and both[2] == ["Rekrutierungslimit überschritten."]


def test_new_ships_join_fleet_and_cannot_move():
    state = make_game(start_gold=100)
    put(state, "AA", S0, 2, unit="ship")
    engine.resolve_turn(state, {"AA": [ship(S0, 1), move("a1", 3, S1)]})
    assert state.army_at(S0)["divisions"] == 1 and state.army_at(S1)["divisions"] == 2


def test_disband_ships_only_next_to_own_port():
    state = make_game()
    put(state, "AA", S0, 3, unit="ship")
    put(state, "AA", S3, 1, unit="ship")
    assert errors(state, "AA", {"type": "disband", "army": "a2", "count": 1})[0] == \
        ["Schiffe werden nur neben einem eigenen Hafen abgerüstet."]
    engine.resolve_turn(state, {"AA": [{"type": "disband", "army": "a1", "count": 2}]})
    assert state.armies["a1"]["divisions"] == 1
    assert state.players["AA"]["gold"] == 10 + 4 + 4 - 0.5   # refund 2 x 2, income, upkeep 2 ships


def test_ship_upkeep_on_board():
    state = make_game()
    put(state, "AA", S0, 4, unit="ship")
    put(state, "AA", A1_CAP, 2)
    row = engine.board(state)[0]
    assert row["upkeep"] == 1.5 and row["ships"] == 4 and row["divisions"] == 2 and row["armies"] == 1


# --- fleets ---------------------------------------------------------------
def test_fleet_moves_three_fields_at_sea_only():
    state = make_game()
    put(state, "AA", S0, 2, unit="ship")
    assert errors(state, "AA", move("a1", 2, PORT_A))[0] == ["Feld ist nicht begehbar."]
    assert errors(state, "AA", {"type": "forced_march", "army": "a1", "on": True})[0] == \
        ["Flotten haben keinen Gewaltmarsch."]
    engine.resolve_turn(state, {"AA": [move("a1", 2, S1, S2, S3)]})
    assert state.armies["a1"]["field"] == S3


def test_own_fleets_merge_fleet_and_army_share_a_field():
    state = make_game()
    put(state, "AA", S0, 2, unit="ship")
    put(state, "AA", S1, 1, unit="ship")
    put(state, "AA", S1, 3)
    engine.resolve_turn(state, {"AA": [move("a1", 2, S1)]})
    units = sorted((a["unit"], a["divisions"]) for a in state.armies.values())
    assert units == [("division", 3), ("ship", 3)]


def test_fleet_split_keeps_ship_type():
    state = make_game()
    put(state, "AA", S0, 3, unit="ship")
    engine.resolve_turn(state, {"AA": [move("a1", 1, S1)]})
    assert state.army_at(S1)["unit"] == "ship" and state.army_at(S0)["divisions"] == 2


# --- armies at sea --------------------------------------------------------
def test_army_puts_to_sea_from_own_port_and_stops_there():
    state = make_game(move_range=3)
    put(state, "AA", PORT_A, 3)
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, S0, S1)]})
    army = state.armies["a1"]
    assert army["field"] == S0 and army["route"] == [S1]   # putting to sea ends the move (G34)
    assert of_kind(events, "move")[0]["to"] == S0


def test_no_putting_to_sea_from_foreign_port():
    state = make_game()
    put(state, "AA", PORT_B, 2)
    assert errors(state, "AA", move("a1", 2, [4, 4]))[0] == ["Ablegen geht nur von einem eigenen Hafen."]


def test_army_at_sea_moves_one_field_and_lands_anywhere():
    state = make_game(forced_march_range=3)
    put(state, "AA", S1, 2, forced_march=True)
    engine.resolve_turn(state, {"AA": [move("a1", 2, S2, S3)]})
    assert state.armies["a1"]["field"] == S2   # forced march has no effect at sea
    engine.resolve_turn(state, {"AA": [move("a1", 2, [2, 3])]})
    assert state.armies["a1"]["field"] == [2, 3]


def test_army_at_sea_cannot_recruit_or_disband():
    state = make_game()
    put(state, "AA", S0, 2)
    assert all(e for e in errors(state, "AA", {"type": "recruit", "field": S0, "count": 1},
                                 {"type": "disband", "army": "a1", "count": 1}))


def test_landing_fights_with_transport_value():
    state = make_game()
    put(state, "AA", S2, 4)
    put(state, "BB", [2, 3], 2)
    events = engine.resolve_turn(state, {"AA": [move("a1", 4, [2, 3])]})
    fight = of_kind(events, "fight")[0]
    # AA deals 4 x 0.25 = 1 to 2 hit points (1 left), takes 2: both survive, AA stays at sea
    assert (fight["attacker_losses"], fight["defender_losses"], fight["winner"]) == (2, 1, "both")
    assert state.armies["a1"]["field"] == S2 and state.armies["a1"]["divisions"] == 2


def test_landing_on_enemy_city_conquers():
    state = make_game()
    state.map["provinces"]["B2"]["capital"] = [5, 3]   # a coastal city for this test
    put(state, "AA", [5, 4], 3)
    engine.resolve_turn(state, {"AA": [move("a1", 3, [5, 3])]})
    assert state.owners["B2"] == "AA" and state.armies["a1"]["divisions"] == 2


def test_putting_to_sea_onto_enemy_fleet_fights_at_sea():
    state = make_game()
    put(state, "AA", PORT_A, 8)
    put(state, "BB", S0, 1, unit="ship")
    events = engine.resolve_turn(state, {"AA": [move("a1", 8, S0)]})
    fight = of_kind(events, "fight")[0]
    # AA deals 8 x 0.25 = 2 to 4 hit points; the ship deals 4: both survive
    assert fight["winner"] == "both" and fight["attacker_losses"] == 4 and fight["defender_losses"] == 0
    assert state.armies["a1"]["field"] == PORT_A and state.armies["a1"]["divisions"] == 4


# --- tank rule -------------------------------------------------------------
def test_fleet_takes_damage_before_the_army():
    state = make_game()
    put(state, "AA", S1, 1, unit="ship")
    put(state, "BB", S2, 2, unit="ship")
    put(state, "BB", S2, 2)
    events = engine.resolve_turn(state, {"AA": [move("a1", 1, S2)]})
    fight = of_kind(events, "fight")[0]
    assert fight["losses"] == {"a1": 1, "a2": 1, "a3": 0}   # the 4 damage hit the fleet, not the army
    assert state.armies["a3"]["divisions"] == 2 and "a1" not in state.armies


def test_rest_damage_passes_to_the_army():
    state = make_game()
    put(state, "AA", S1, 2, unit="ship")
    put(state, "BB", S2, 1, unit="ship")
    put(state, "BB", S2, 3)
    events = engine.resolve_turn(state, {"AA": [move("a1", 2, S2)]})
    fight = of_kind(events, "fight")[0]
    # AA deals 8: fleet (4 hp) and army (3 hp) die; BB deals 4 + 0.75 to 8 hp -> 3.25 left = 1 ship
    assert fight["winner"] == "AA" and fight["losses"] == {"a1": 1, "a2": 1, "a3": 3}
    assert state.armies["a1"]["field"] == S2 and state.armies["a1"]["divisions"] == 1


# --- linking -----------------------------------------------------------------
def test_link_and_move_together_with_range_one():
    state = make_game()
    put(state, "AA", S0, 2, unit="ship")
    put(state, "AA", S0, 3)
    orders = [{"type": "link", "fleet": "a1", "army": "a2"}, move("a1", 2, S1, S2)]
    assert errors(state, "AA", *orders) == [[], []]
    events = engine.resolve_turn(state, {"AA": orders})
    assert state.armies["a1"]["field"] == S1 and state.armies["a2"]["field"] == S1
    assert state.armies["a1"]["linked"] == "a2" and state.armies["a1"]["route"] == [S2]
    assert of_kind(events, "move")[0]["with"] == "a2"
    engine.resolve_turn(state, {})
    assert state.armies["a2"]["field"] == S2   # the standing route takes the army along


def test_link_validation():
    state = make_game()
    put(state, "AA", S0, 2, unit="ship")
    put(state, "AA", S1, 3)
    put(state, "AA", S1, 1, unit="ship")
    put(state, "BB", S0, 1)
    assert errors(state, "AA", {"type": "link", "fleet": "a1", "army": "a2"})[0]   # different fields
    assert errors(state, "AA", {"type": "link", "fleet": "a2", "army": "a3"})[0]   # army as fleet
    assert errors(state, "AA", {"type": "link", "fleet": "a1", "army": "a4"})[0]   # foreign army
    assert errors(state, "AA", {"type": "link", "fleet": "a3", "army": "a2"}) == [[]]


def test_linked_units_move_only_whole():
    state = make_game()
    fleet = put(state, "AA", S0, 2, unit="ship")
    army = put(state, "AA", S0, 3)
    state.link(fleet, army)
    assert errors(state, "AA", move("a2", 2, S1))[0] == ["Verbundene Einheiten ziehen nur vollständig – erst trennen."]
    assert errors(state, "AA", {"type": "unlink", "army": "a2"}, move("a2", 2, S1)) == [[], []]


def test_landing_ends_the_link():
    state = make_game()
    fleet = put(state, "AA", S0, 2, unit="ship")
    army = put(state, "AA", S0, 3)
    state.link(fleet, army)
    engine.resolve_turn(state, {"AA": [move("a2", 3, PORT_A)]})
    assert state.armies["a2"]["field"] == PORT_A and "linked" not in state.armies["a1"]
    assert state.armies["a1"]["field"] == S0


def test_linked_pair_fights_as_one_side():
    state = make_game()
    fleet = put(state, "AA", S1, 1, unit="ship")
    army = put(state, "AA", S1, 4)
    state.link(fleet, army)
    put(state, "BB", S2, 1, unit="ship")
    events = engine.resolve_turn(state, {"AA": [move("a1", 1, S2)]})
    fight = of_kind(events, "fight")[0]
    # AA deals 4 + 1 = 5 > 4: BB destroyed; BB deals 4 to the AA ship first: it sinks, the army is untouched
    assert fight["winner"] == "AA" and fight["losses"] == {"a1": 1, "a2": 0, "a3": 1}
    assert state.armies["a2"]["field"] == S2 and "linked" not in state.armies["a2"]


def test_links_survive_save_and_load():
    state = make_game()
    fleet = put(state, "AA", S0, 2, unit="ship")
    army = put(state, "AA", S0, 3)
    state.link(fleet, army)
    clone = engine.GameState.from_dict(state.to_dict())
    assert clone.partner(clone.armies["a1"]) is clone.armies["a2"]


def test_preview_of_fleet_attack():
    state = make_game()
    put(state, "AA", S1, 2, unit="ship")
    put(state, "BB", S2, 1, unit="ship")
    result = engine.preview_move(state, "AA", "a1", 2, [S2])
    assert result["fight"] == {"defender": "BB", "attacker_losses": 1, "defender_losses": 1, "winner": "AA"}
    assert result["conquest"] is None
