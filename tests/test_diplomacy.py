"""Milestone 3: hostility, pass-through, do-not-attack, alliances, selling provinces, victory (RULES.md section 11).

Test map: row 2 is a chain [0..7, 2] (A1 cap, A1, A2 cap, N1 cap, B1 cap, B2 cap, C1 cap, C1); 24 land fields:
A1 6, A2 3, N1 3, B1 3, B2 3, C1 6. Sea in row 4: S0..S2."""
import json

import engine

from conftest import A1_CAP, A1_MID, A2_CAP, B1_CAP, N1_CAP, make_game, of_kind, put

S0, S1, S2 = [[c, 4] for c in range(3)]
THREE = ("AA", "BB", "CC")


def move(army, count, *path):
    return {"type": "move", "army": army, "count": count, "path": [list(p) for p in path]}


def errors_of(state, player, *orders):
    return engine.validate_orders(state, player, list(orders))


def ally(state, *members, since=None):
    """Put the members into a new alliance directly."""
    alliance = {"id": f"b{state.next_alliance_id}", "members": list(members), "since": state.turn if since is None else since}
    state.next_alliance_id += 1
    state.alliances[alliance["id"]] = alliance
    return alliance


def peace(state, a, b):
    """Mutual 'do not attack'."""
    state.no_attack.setdefault(a, []).append(b)
    state.no_attack.setdefault(b, []).append(a)


def no_attack(to, on=True):
    return {"type": "no_attack", "to": to, "on": on}


def idle_turns(state, count):
    events = []
    for _ in range(count):
        events += engine.resolve_turn(state, {})
    return events


def share_of(state, player, key="share_counted"):
    return next(r for r in engine.board(state) if r["player"] == player)[key]


# --- hostility ------------------------------------------------------------
def test_hostile_rules():
    state = make_game(THREE)
    assert state.hostile("AA", "BB") and state.hostile("BB", "AA")
    assert not state.hostile("AA", "AA")
    assert state.hostile("AA", None) and state.hostile(None, "AA")      # neutral / AI provinces
    state.no_attack["AA"] = ["BB"]
    assert state.hostile("AA", "BB") and state.hostile("BB", "AA")      # one-sided is not enough
    state.no_attack["BB"] = ["AA"]
    assert not state.hostile("AA", "BB") and not state.hostile("BB", "AA") and state.hostile("AA", "CC")
    ally(state, "AA", "CC")
    assert not state.hostile("AA", "CC") and not state.hostile("CC", "AA") and state.hostile("BB", "CC")


def test_allies_do_not_fight():
    state = make_game()
    ally(state, "AA", "BB")
    put(state, "AA", A2_CAP, 3)
    put(state, "BB", N1_CAP, 3)
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, N1_CAP)]})
    assert not of_kind(events, "fight")
    assert state.armies["a1"]["field"] == A2_CAP and state.armies["a2"]["divisions"] == 3
    assert of_kind(events, "move_blocked")


def test_mutual_no_attack_means_no_fight_but_one_sided_fights():
    state = make_game()
    put(state, "AA", A2_CAP, 3)
    put(state, "BB", N1_CAP, 3)
    peace(state, "AA", "BB")
    assert not of_kind(engine.resolve_turn(state, {"AA": [move("a1", 3, N1_CAP)]}), "fight")
    state = make_game()
    put(state, "AA", A2_CAP, 3)
    put(state, "BB", N1_CAP, 3)
    state.no_attack["AA"] = ["BB"]                       # only AA promises; BB may still be attacked by AA
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, N1_CAP)]})
    assert of_kind(events, "fight")


def test_no_attack_takes_effect_in_the_same_resolution():
    for toggles, fights in [(True, False), (False, True)]:
        state = make_game()
        put(state, "AA", A2_CAP, 3)
        put(state, "BB", N1_CAP, 4)
        orders = {"AA": [no_attack("BB")] if toggles else [], "BB": [no_attack("AA")] if toggles else []}
        orders["AA"] = orders["AA"] + [move("a1", 3, N1_CAP)]
        events = engine.resolve_turn(state, orders)
        assert bool(of_kind(events, "fight")) == fights
        if toggles:
            assert of_kind(events, "no_attack")[-1]["mutual"] is True
            assert state.no_attack == {"AA": ["BB"], "BB": ["AA"]}


def test_no_attack_can_be_switched_off_again():
    state = make_game()
    engine.resolve_turn(state, {"AA": [no_attack("BB")]})
    assert state.no_attack == {"AA": ["BB"]}
    events = engine.resolve_turn(state, {"AA": [no_attack("BB", False)]})
    assert state.no_attack == {} and of_kind(events, "no_attack")[0]["on"] is False


# --- pass-through and blocked end fields -----------------------------------
def test_pass_through_friendly_units():
    state = make_game(move_range=2)
    ally(state, "AA", "BB")
    put(state, "AA", A1_MID, 4)
    put(state, "BB", A2_CAP, 2)
    engine.resolve_turn(state, {"AA": [move("a1", 4, A2_CAP, N1_CAP)]})
    assert state.armies["a1"]["field"] == N1_CAP and state.armies["a1"]["divisions"] == 2   # conquered N1 (cost 2)
    assert state.armies["a2"]["field"] == A2_CAP and state.owners["N1"] == "AA"


def test_move_stops_on_last_free_field_and_keeps_the_rest_of_the_route():
    state = make_game(move_range=2)
    peace(state, "AA", "BB")
    put(state, "AA", A1_MID, 3)
    put(state, "BB", N1_CAP, 2)
    events = engine.resolve_turn(state, {"AA": [move("a1", 3, A2_CAP, N1_CAP)]})
    army = state.armies["a1"]
    assert army["field"] == A2_CAP and army["route"] == [N1_CAP]
    assert of_kind(events, "move")[0]["to"] == A2_CAP
    # the march goes on and waits as long as the field is taken
    assert not of_kind(engine.resolve_turn(state, {}), "fight")
    assert state.armies["a1"]["field"] == A2_CAP and state.armies["a1"]["route"] == [N1_CAP]
    del state.armies["a2"]
    engine.resolve_turn(state, {})
    assert state.armies["a1"]["field"] == N1_CAP and "route" not in state.armies["a1"]


def test_blocked_from_the_start_keeps_whole_route_but_not_a_split_part():
    state = make_game()
    peace(state, "AA", "BB")
    put(state, "AA", A1_MID, 4)
    put(state, "BB", A2_CAP, 1)
    engine.resolve_turn(state, {"AA": [move("a1", 4, A2_CAP, N1_CAP)]})
    assert state.armies["a1"]["field"] == A1_MID and state.armies["a1"]["route"] == [A2_CAP, N1_CAP]
    state.armies["a1"].pop("route")
    engine.resolve_turn(state, {"AA": [move("a1", 2, A2_CAP)]})
    assert len(state.armies) == 2 and "route" not in state.armies["a1"]   # nothing split off


def test_blocked_end_without_standing_marches_drops_the_rest():
    state = make_game(standing_marches=False, move_range=2)
    peace(state, "AA", "BB")
    put(state, "AA", A1_MID, 3)
    put(state, "BB", N1_CAP, 2)
    engine.resolve_turn(state, {"AA": [move("a1", 3, A2_CAP, N1_CAP)]})
    assert state.armies["a1"]["field"] == A2_CAP and "route" not in state.armies["a1"]


def test_preview_shows_the_blocked_end():
    state = make_game(move_range=2)
    peace(state, "AA", "BB")
    put(state, "AA", A1_MID, 3)
    put(state, "BB", N1_CAP, 2)
    pv = engine.preview_move(state, "AA", "a1", 3, [A2_CAP, N1_CAP])
    assert pv["valid"] and pv["end_field"] == A2_CAP and pv["fight"] is None and pv["conquest"] is None
    pv = engine.preview_move(state, "AA", "a1", 3, [A2_CAP])
    assert pv["end_field"] == A2_CAP
    put(state, "BB", A2_CAP, 1)
    pv = engine.preview_move(state, "AA", "a1", 3, [A2_CAP])
    assert pv["end_field"] == A1_MID and "besetzt" in pv["text"]


def test_allied_fleets_share_a_sea_field_but_peaceful_ones_do_not():
    state = make_game()
    ally(state, "AA", "BB")
    put(state, "AA", S0, 2, unit="ship")
    put(state, "BB", S1, 1, unit="ship")
    engine.resolve_turn(state, {"AA": [move("a1", 2, S1)]})
    assert state.armies["a1"]["field"] == S1 and state.armies["a2"]["field"] == S1
    state = make_game()
    peace(state, "AA", "BB")
    put(state, "AA", S0, 2, unit="ship")
    put(state, "BB", S1, 1, unit="ship")
    engine.resolve_turn(state, {"AA": [move("a1", 2, S1)]})
    assert state.armies["a1"]["field"] == S0


def test_fleets_pass_through_peaceful_fleets():
    state = make_game()
    peace(state, "AA", "BB")
    put(state, "AA", S0, 2, unit="ship")
    put(state, "BB", S1, 1, unit="ship")
    engine.resolve_turn(state, {"AA": [move("a1", 2, S1, S2)]})
    assert state.armies["a1"]["field"] == S2


def test_attack_on_two_allied_fleets_fights_both_as_one_side():
    state = make_game(THREE)
    ally(state, "BB", "CC")
    put(state, "AA", S0, 4, unit="ship")
    put(state, "BB", S1, 1, unit="ship")
    put(state, "CC", S1, 1, unit="ship")
    events = engine.resolve_turn(state, {"AA": [move("a1", 4, S1)]})
    assert of_kind(events, "fight")[0]["defender_losses"] == 2
    assert [a["owner"] for a in state.armies.values()] == ["AA"]


def test_won_fight_does_not_end_on_a_field_still_held_by_peaceful_units():
    state = make_game(THREE)
    peace(state, "AA", "CC")
    put(state, "AA", S0, 4, unit="ship")
    put(state, "BB", S1, 1, unit="ship")
    put(state, "CC", S1, 1, unit="ship")
    events = engine.resolve_turn(state, {"AA": [move("a1", 4, S1)]})
    assert of_kind(events, "fight")[0]["defender_losses"] == 1
    assert state.armies["a1"]["field"] == S0 and "a2" not in state.armies and state.armies["a3"]["field"] == S1


def test_no_conquest_of_allied_or_peaceful_cities():
    for link in (ally, peace):
        state = make_game(move_range=2)
        link(state, "AA", "BB")
        put(state, "AA", N1_CAP, 6)
        engine.resolve_turn(state, {"AA": [move("a1", 6, B1_CAP)]})
        assert state.armies["a1"]["field"] == B1_CAP and state.owners["B1"] == "BB" and state.armies["a1"]["divisions"] == 6
    state = make_game()
    put(state, "AA", N1_CAP, 6)
    engine.resolve_turn(state, {"AA": [move("a1", 6, B1_CAP)]})
    assert state.owners["B1"] == "AA"


def test_cannot_recruit_on_a_city_held_by_allied_units():
    state = make_game()
    ally(state, "AA", "BB")
    put(state, "BB", A1_CAP, 1)
    assert errors_of(state, "AA", {"type": "recruit", "field": A1_CAP, "count": 1}) == [["Feld ist von fremden Truppen besetzt."]]
    state = make_game()
    put(state, "BB", A1_CAP, 1)
    assert errors_of(state, "AA", {"type": "recruit", "field": A1_CAP, "count": 1}) == [["Feld ist vom Feind besetzt."]]


# --- alliances ------------------------------------------------------------
def test_invite_then_accept_next_turn_forms_alliance():
    state = make_game()
    assert errors_of(state, "BB", {"type": "accept", "from": "AA"}) == [["Keine Einladung von diesem Spieler."]]
    events = engine.resolve_turn(state, {"AA": [{"type": "invite", "to": "BB"}]})
    assert state.invitations == [{"from": "AA", "to": "BB", "turn": 1}] and not state.alliances
    assert not of_kind(events, "alliance")
    assert errors_of(state, "BB", {"type": "accept", "from": "AA"}) == [[]]
    events = engine.resolve_turn(state, {"BB": [{"type": "accept", "from": "AA"}]})
    alliance = next(iter(state.alliances.values()))
    assert alliance["members"] == ["AA", "BB"] and alliance["since"] == 2 and not state.invitations
    assert of_kind(events, "alliance")[0]["text"] == "Aland und Bland schließen ein Bündnis."
    assert not state.hostile("AA", "BB")


def test_invitation_expires_after_one_turn():
    state = make_game()
    engine.resolve_turn(state, {"AA": [{"type": "invite", "to": "BB"}]})
    engine.resolve_turn(state, {})
    assert state.invitations == []
    assert errors_of(state, "BB", {"type": "accept", "from": "AA"}) == [["Keine Einladung von diesem Spieler."]]


def test_accept_in_the_same_turn_as_the_invite_does_nothing():
    state = make_game()
    events = engine.resolve_turn(state, {"AA": [{"type": "invite", "to": "BB"}], "BB": [{"type": "accept", "from": "AA"}]})
    assert not state.alliances and of_kind(events, "skipped")


def test_alliance_size_is_limited():
    state = make_game(THREE)
    ally(state, "AA", "BB")
    assert errors_of(state, "AA", {"type": "invite", "to": "CC"}) == [["Dein Bündnis ist voll."]]
    state = make_game(THREE, max_alliance_size=3)
    ally(state, "AA", "BB")
    assert errors_of(state, "AA", {"type": "invite", "to": "CC"}) == [[]]
    engine.resolve_turn(state, {"AA": [{"type": "invite", "to": "CC"}]})
    engine.resolve_turn(state, {"CC": [{"type": "accept", "from": "AA"}]})
    assert state.alliance_of("CC")["members"] == ["AA", "BB", "CC"]
    assert state.alliance_of("CC")["since"] == 2
    state = make_game(THREE, max_alliance_size=1)
    assert errors_of(state, "AA", {"type": "invite", "to": "BB"})[0]


def test_full_alliance_at_resolution_skips_the_accept():
    state = make_game(THREE)
    engine.resolve_turn(state, {"AA": [{"type": "invite", "to": "BB"}, {"type": "invite", "to": "CC"}]})
    events = engine.resolve_turn(state, {"BB": [{"type": "accept", "from": "AA"}], "CC": [{"type": "accept", "from": "AA"}]})
    assert [len(a["members"]) for a in state.alliances.values()] == [2]          # whoever comes first in the order
    assert [e["reason"] for e in of_kind(events, "skipped")] == ["Das Bündnis ist voll."]


def test_one_alliance_per_player():
    state = make_game(THREE, max_alliance_size=3)
    engine.resolve_turn(state, {"AA": [{"type": "invite", "to": "BB"}], "CC": [{"type": "invite", "to": "BB"}]})
    both = [{"type": "accept", "from": "AA"}, {"type": "accept", "from": "CC"}]
    assert errors_of(state, "BB", *both) == [[], ["Du kannst nur eine Einladung annehmen."]]
    engine.resolve_turn(state, {"BB": both})                   # the second accept is skipped at resolution
    assert len(state.alliances) == 1 and state.alliance_of("BB")["members"] == ["AA", "BB"]
    assert errors_of(state, "CC", {"type": "invite", "to": "BB"}) == [["Bland ist schon in einem Bündnis."]]
    assert errors_of(state, "BB", {"type": "accept", "from": "CC"})[0]


def test_leave_is_effective_after_the_resolution():
    state = make_game()
    ally(state, "AA", "BB")
    put(state, "AA", A2_CAP, 3)
    put(state, "BB", N1_CAP, 3)
    events = engine.resolve_turn(state, {"AA": [{"type": "leave"}, move("a1", 3, N1_CAP)]})
    assert not of_kind(events, "fight")                   # still allied during this resolution
    assert state.alliances == {} and state.hostile("AA", "BB")
    assert of_kind(events, "alliance_end")


def test_alliance_with_one_member_left_is_dissolved():
    state = make_game(THREE, max_alliance_size=3)
    alliance = ally(state, "AA", "BB", "CC", since=1)
    engine.resolve_turn(state, {"CC": [{"type": "leave"}]})
    assert alliance["members"] == ["AA", "BB"] and alliance["since"] == 1
    assert state.alliance_of("CC") is None
    assert errors_of(state, "CC", {"type": "leave"}) == [["Du bist in keinem Bündnis."]]
    engine.resolve_turn(state, {"AA": [{"type": "leave"}]})
    assert state.alliances == {}


def test_diplomacy_order_validation():
    state = make_game()
    result = errors_of(state, "AA", no_attack("AA"), no_attack("XX"), {"type": "invite", "to": "AA"},
                       {"type": "offer_sale", "province": "B1", "to": "BB", "price": 3},
                       {"type": "offer_sale", "province": "A1", "to": "BB", "price": 0},
                       {"type": "offer_sale", "province": "A1", "to": "AA", "price": 3},
                       {"type": "invite", "to": "BB"}, {"type": "invite", "to": "BB"}, {"type": "no_attack", "to": "BB"})
    assert [bool(e) for e in result] == [True, True, True, True, True, True, False, True, True]


# --- selling provinces ----------------------------------------------------
def sell(province="A2", to="BB", price=3):
    return {"type": "offer_sale", "province": province, "to": to, "price": price}


def buy(province="A2"):
    return {"type": "buy", "province": province}


def test_offer_then_buy_swaps_province_and_gold():
    state = make_game()
    engine.resolve_turn(state, {"AA": [sell()]})
    assert state.offers == [{"province": "A2", "from": "AA", "to": "BB", "price": 3, "turn": 1}]
    assert state.owners["A2"] == "AA"
    state.players["AA"]["gold"], state.players["BB"]["gold"] = 10, 10
    events = engine.resolve_turn(state, {"BB": [buy()]})
    assert state.owners["A2"] == "BB" and not state.offers
    assert state.players["AA"]["gold"] == 10 + 4 + 3          # income of A1 + A2 comes first, then the price
    assert state.players["BB"]["gold"] == 10 + 3 - 3
    assert of_kind(events, "buy")[0]["text"] == "Bland kauft Südaland von Aland für 3 Gold."
    assert state.gifts[-1] == {"province": "A2", "from": "AA", "to": "BB", "turn": 2, "price": 3}


def test_buy_needs_an_offer_and_enough_gold():
    state = make_game(THREE)
    assert errors_of(state, "BB", buy()) == [["Kein Angebot für diese Provinz."]]
    engine.resolve_turn(state, {"AA": [sell(price=30)]})
    assert errors_of(state, "BB", buy()) == [["Nicht genug Gold."]]
    state.players["BB"]["gold"] = 30
    assert errors_of(state, "BB", buy()) == [[]]
    assert errors_of(state, "BB", buy(), buy()) == [[], ["Provinz wird schon gekauft."]]
    assert errors_of(state, "BB", {"type": "send_gold", "to": "AA", "amount": 1}, buy()) == [[], ["Nicht genug Gold."]]
    assert errors_of(state, "CC", buy()) == [["Kein Angebot für diese Provinz."]]     # not the named buyer


def test_offer_expires_after_one_turn():
    state = make_game()
    engine.resolve_turn(state, {"AA": [sell()]})
    engine.resolve_turn(state, {})
    assert state.offers == []
    state.players["BB"]["gold"] = 50
    assert errors_of(state, "BB", buy()) == [["Kein Angebot für diese Provinz."]]


def test_buy_is_skipped_if_the_seller_lost_the_province():
    state = make_game(THREE)
    engine.resolve_turn(state, {"AA": [sell()]})
    state.players["BB"]["gold"] = 20
    assert errors_of(state, "BB", buy()) == [[]]
    state.owners["A2"] = "CC"                                                # conquered meanwhile
    assert errors_of(state, "BB", buy()) == [["Der Verkäufer besitzt die Provinz nicht mehr."]]
    state.owners["A2"] = "AA"
    gold = state.players["BB"]["gold"]
    state.player_order = ["AA", "BB", "CC"]
    events = engine.resolve_turn(state, {"AA": [{"type": "give_province", "province": "A2", "to": "CC"}],
                                         "BB": [buy()]})                   # AA's gift runs first in the gold phase
    assert state.owners["A2"] == "CC" and of_kind(events, "skipped")
    assert state.players["BB"]["gold"] == gold + 3                           # only income, nothing paid


# --- victory --------------------------------------------------------------
def test_counted_share_excludes_young_gifts_and_sales():
    state = make_game(gift_delay_turns=2, victory_hold_turns=9)
    engine.resolve_turn(state, {"AA": [{"type": "give_province", "province": "A1", "to": "BB"}]})
    assert share_of(state, "BB", "share") == 12 / 24 and share_of(state, "BB") == 6 / 24
    assert share_of(state, "AA") == 3 / 24
    engine.resolve_turn(state, {})
    assert share_of(state, "BB") == 6 / 24
    engine.resolve_turn(state, {})
    assert share_of(state, "BB") == 12 / 24


def test_bought_provinces_wait_for_the_delay_too():
    state = make_game(gift_delay_turns=3, victory_hold_turns=9)
    engine.resolve_turn(state, {"AA": [sell("A1", "BB", 1)]})
    state.players["BB"]["gold"] = 5
    engine.resolve_turn(state, {"BB": [buy("A1")]})
    assert share_of(state, "BB", "share") == 12 / 24 and share_of(state, "BB") == 6 / 24


def test_conquered_provinces_count_at_once():
    state = make_game(gift_delay_turns=5, victory_hold_turns=9)
    state.gifts.append({"province": "B1", "from": "BB", "to": "BB", "turn": 1})   # B1 was once gifted to BB ...
    put(state, "AA", N1_CAP, 6)
    engine.resolve_turn(state, {"AA": [move("a1", 6, B1_CAP)]})                   # ... and is conquered by AA
    assert state.owners["B1"] == "AA" and state.gifts == []
    assert share_of(state, "AA") == 12 / 24


def test_board_shows_alliance_id():
    state = make_game()
    alliance = ally(state, "AA", "BB")
    assert [r["alliance"] for r in engine.board(state)] == [alliance["id"]] * 2


def win_setup(**rules):
    state = make_game(**rules)
    state.owners["N1"] = "AA"                                                      # AA: 12 of 24 land fields
    return state


def test_single_player_wins_after_holding_three_resolutions():
    state = win_setup()
    events = engine.resolve_turn(state, {})
    assert state.victory["turns"] == 1 and not state.winner and of_kind(events, "victory_progress")
    engine.resolve_turn(state, {})
    assert state.victory["turns"] == 2 and not state.winner
    events = engine.resolve_turn(state, {})
    assert state.winner == {"players": ["AA"], "alliance": None, "turn": 3}
    assert of_kind(events, "victory")[0]["text"] == "Aland gewinnt das Spiel!"
    assert engine.resolve_turn(state, {}) == [] and state.turn == 4              # the game is over


def test_forty_percent_is_not_enough():
    state = make_game()                                                           # AA has 9 of 24 = 37.5 %
    idle_turns(state, 4)
    assert state.victory is None and state.winner is None
    state.owners["N1"] = "AA"
    state.rules["victory_share_single"] = 0.5                                     # exactly 50 %: "more than" fails
    idle_turns(state, 4)
    assert state.victory is None


def test_counter_resets_when_the_condition_breaks_or_the_leader_changes():
    state = win_setup()
    idle_turns(state, 2)
    assert state.victory["turns"] == 2
    state.owners["N1"] = "BB"
    idle_turns(state, 1)
    assert state.victory is None
    state.owners["N1"] = "AA"
    idle_turns(state, 2)
    assert state.victory["turns"] == 2 and not state.winner
    state.owners.update({"N1": "BB", "A2": "BB", "B1": "BB", "B2": "BB"})         # now BB leads instead
    idle_turns(state, 1)
    assert state.victory["players"] == ["BB"] and state.victory["turns"] == 1


def test_alliance_victory_needs_its_age_and_the_share_of_the_sum():
    state = make_game(alliance_min_turns=2)
    state.owners["N1"] = "BB"                                                     # AA 9, BB 9: no single winner, together 75 %
    alliance = ally(state, "AA", "BB", since=1)
    idle_turns(state, 2)                                                          # resolutions of turns 1 and 2: age 0 and 1
    assert state.victory is None
    idle_turns(state, 1)                                                          # turn 3: age 2
    assert state.victory["kind"] == "alliance" and state.victory["turns"] == 1
    idle_turns(state, 2)
    assert state.winner == {"players": ["AA", "BB"], "alliance": alliance["id"], "turn": 5}


def test_alliance_needs_more_than_55_percent_and_a_member_change_restarts_its_age():
    state = make_game(THREE, max_alliance_size=3, alliance_min_turns=2, victory_share_single=0.9)
    state.owners.update({"N1": "BB", "C1": "BB"})                                 # AA 9, BB 15, CC 0 (of 24)
    ally(state, "AA", "CC", since=1)                                              # 9 fields: 37 %, not enough
    idle_turns(state, 4)
    assert state.victory is None
    state.alliances.clear()
    alliance = ally(state, "AA", "BB", since=1)
    idle_turns(state, 1)
    assert state.victory["kind"] == "alliance"
    alliance["since"] = state.turn                                                # membership changed: age starts again
    idle_turns(state, 1)
    assert state.victory is None


def test_single_player_in_an_alliance_wins_alone_with_forty_percent():
    state = win_setup()
    ally(state, "AA", "BB")
    idle_turns(state, 3)
    assert state.winner["players"] == ["AA"] and state.winner["alliance"] is None


def test_victory_hold_turns_is_a_setting():
    state = win_setup(victory_hold_turns=1)
    idle_turns(state, 1)
    assert state.winner


# --- save / load ----------------------------------------------------------
def test_new_state_round_trips_through_json():
    state = win_setup()
    ally(state, "AA", "BB")
    state.no_attack = {"AA": ["BB"]}
    idle_turns(state, 3)
    state.offers.append({"province": "A2", "from": "AA", "to": "BB", "price": 3, "turn": 3})
    state.invitations.append({"from": "AA", "to": "BB", "turn": 3})
    assert state.winner and state.alliances
    data = json.loads(json.dumps(state.to_dict()))
    clone = engine.GameState.from_dict(data)
    assert clone.to_dict() == state.to_dict()
    for key in ("alliances", "no_attack", "invitations", "offers", "victory", "winner", "next_alliance_id"):
        assert key in data
    assert clone.hostile("AA", "BB") is False and clone.winner == state.winner


def test_old_saves_without_diplomacy_keys_still_load():
    state = make_game()
    data = state.to_dict()
    for key in ("alliances", "next_alliance_id", "no_attack", "invitations", "offers", "victory", "winner"):
        del data[key]
    for key in ("victory_hold_turns", "max_alliance_size", "alliance_min_turns"):
        del data["rules"][key]
    data["rules"]["phases"] = ["recruitment", "gold", "movement"]
    old = engine.GameState.from_dict(data)
    assert old.rules["phases"][0] == "diplomacy" and old.rules["victory_hold_turns"] == 3
    assert old.alliances == {} and old.winner is None
    engine.resolve_turn(old, {"AA": [no_attack("BB")]})
    assert old.no_attack == {"AA": ["BB"]}
