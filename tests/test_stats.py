"""Milestone 5: raw event fields for the archive and engine/stats.py (statistics from archive rows)."""
import json

import engine
from conftest import A1_CAP, A1_MID, A2_CAP, B1_CAP, N1_CAP, TEST_MAP, make_game, of_kind, put

S0, S2 = [0, 4], [2, 4]
PORT_A = [0, 3]


def move(army, count, *path):
    return {"type": "move", "army": army, "count": count, "path": [list(p) for p in path]}


def play(state, turns, start_ts=1000):
    """Resolve turns of orders like the server does and return archive rows (plus a final row)."""
    rows = []
    for i, orders in enumerate(turns):
        row = {"turn": state.turn, "player_order": list(state.player_order), "before": engine.orders.snapshot(state),
               "gold_before": {n: p["gold"] for n, p in state.players.items()}, "orders": orders, "timeouts": [],
               "started": start_ts + 10 * i, "ready_at": {n: 1.0 + i for n in state.players}}
        events = engine.resolve_turn(state, orders)
        row.update({"gold_after": {n: p["gold"] for n, p in state.players.items()}, "resolved": start_ts + 10 * i + 5,
                    "events": [{k: v for k, v in e.items() if k != "snap"} for e in events],
                    "alliances": state.alliances, "no_attack": state.no_attack, "ai": state.ai})
        rows.append(json.loads(json.dumps(row)))
    final = {"final": True, "turn": state.turn, "ts": start_ts + 10 * len(turns), "board": engine.orders.snapshot(state),
             "gold": {n: p["gold"] for n, p in state.players.items()}, "winner": None, "ai": state.ai, "players": {}}
    return rows, json.loads(json.dumps(final))


def stats_of(state, rows, final=None, **kw):
    return engine.compute_stats(state.map, state.rules, rows + ([final] if final else []), **kw)


# --- new event fields -----------------------------------------------------------------------
def test_fight_event_has_units_values_and_split_losses():
    state = make_game()
    put(state, "AA", A1_CAP, 3, forced_march=True)
    put(state, "BB", A1_MID, 2)
    ev = of_kind(engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID)]}), "fight")[0]
    a, d = ev["attacker_units"], ev["defender_units"]
    assert ev["sea"] is False
    assert a == [{"army": "a1", "owner": "AA", "unit": "division", "fleet": False, "count": 3, "value": 0.5,
                  "forced_march": True, "transport": False, "lost": ev["attacker_losses"]}]
    assert d[0]["army"] == "a2" and d[0]["count"] == 2 and d[0]["value"] == 1 and d[0]["lost"] == ev["defender_losses"]
    assert ev["attacker_damage"] == 1.5 and ev["defender_damage"] == 2
    assert ev["attacker_divisions_lost"] == ev["attacker_losses"] and ev["attacker_ships_lost"] == 0
    assert ev["defender_divisions_lost"] == ev["defender_losses"] and ev["defender_ships_lost"] == 0


def test_sea_fight_splits_ships_and_divisions_and_marks_transport():
    state = make_game()
    put(state, "AA", [1, 4], 1, unit="ship")
    put(state, "BB", S2, 1, unit="ship")
    put(state, "BB", S2, 3)
    ev = of_kind(engine.resolve_turn(state, {"AA": [move("a1", 1, S2)]}), "fight")[0]
    assert ev["sea"] is True
    ships = [u for u in ev["defender_units"] if u["fleet"]]
    land = [u for u in ev["defender_units"] if not u["fleet"]]
    assert len(ships) == 1 and ships[0]["unit"] == "ship" and ships[0]["value"] == 4 and not ships[0]["transport"]
    assert land[0]["transport"] is True and land[0]["value"] == 0.25
    assert ev["defender_ships_lost"] == ships[0]["lost"] and ev["defender_divisions_lost"] == land[0]["lost"]
    assert ev["defender_ships_lost"] + ev["defender_divisions_lost"] == ev["defender_losses"]


def test_attacking_army_from_the_sea_is_a_transport():
    state = make_game()
    put(state, "AA", S2, 4)
    put(state, "BB", [2, 3], 2)
    ev = of_kind(engine.resolve_turn(state, {"AA": [move("a1", 4, [2, 3])]}), "fight")[0]
    assert ev["attacker_units"][0]["transport"] is True and ev["attacker_units"][0]["value"] == 0.25 and ev["sea"] is True


def test_recruit_build_and_disband_events_carry_gold():
    state = make_game(start_gold=100)
    put(state, "AA", A1_CAP, 2)
    events = engine.resolve_turn(state, {"AA": [
        {"type": "recruit", "field": list(A1_CAP), "count": 2},
        {"type": "build_ship", "field": S0, "count": 1},
        {"type": "disband", "army": "a1", "count": 1}]})
    assert of_kind(events, "recruit")[0]["cost"] == 10
    assert of_kind(events, "build_ship")[0]["cost"] == 5
    d = of_kind(events, "disband")[0]
    assert d["refund"] == 2 and d["unit"] == "division"


def test_ship_disband_and_ai_recruit_events():
    state = make_game(start_gold=100)
    put(state, "AA", S0, 3, unit="ship")
    d = of_kind(engine.resolve_turn(state, {"AA": [{"type": "disband", "army": "a1", "count": 2}]}), "disband")[0]
    assert d["refund"] == 4 and d["unit"] == "ship"
    state2 = engine.new_game(engine.load_map(TEST_MAP), {"AA": "x"}, engine.load_rules({}, {}), 1, ai=["BB"])
    rec = of_kind(engine.resolve_turn(state2, {}), "recruit")
    assert rec and all(e["cost"] == 0 and e["ai"] for e in rec)


def test_conquest_events_name_the_army_and_the_divisions_lost():
    state = make_game()
    put(state, "AA", A2_CAP, 5)
    put(state, "BB", N1_CAP, 1)
    state.owners["N1"] = "BB"
    events = engine.resolve_turn(state, {"AA": [move("a1", 5, N1_CAP)]})
    fight, c = of_kind(events, "fight")[0], of_kind(events, "conquest")[0]
    assert c["army"] == "a1" and c["lost"] == c["cost"] == 2 and c["divisions"] == 5 - fight["attacker_losses"]
    state = make_game()
    put(state, "AA", A2_CAP, 1)
    f = of_kind(engine.resolve_turn(state, {"AA": [move("a1", 1, N1_CAP)]}), "conquest_failed")[0]
    assert f["army"] == "a1" and f["lost"] == 0 and f["divisions"] == 1


def test_move_event_has_unit_path_count_and_linked_partner():
    state = make_game()
    put(state, "AA", A1_CAP, 3, forced_march=True)
    mv = of_kind(engine.resolve_turn(state, {"AA": [move("a1", 3, A1_MID, A2_CAP)]}), "move")[0]
    assert mv["path"] == [list(A1_MID), list(A2_CAP)] and mv["count"] == 3
    assert mv["unit"] == "division" and mv["fleet"] is False and mv["forced_march"] is True
    state = make_game()
    put(state, "AA", S0, 2, unit="ship")
    put(state, "AA", S0, 4)
    state.link(state.armies["a1"], state.armies["a2"])
    mv = of_kind(engine.resolve_turn(state, {"AA": [move("a1", 2, [1, 4])]}), "move")[0]
    assert mv["fleet"] is True and mv["unit"] == "ship" and mv["with"] == "a2" and mv["with_count"] == 4
    assert mv["with_unit"] == "division"


# --- compute_stats --------------------------------------------------------------------------
def battle():
    """Turn 1: AA recruits 2 (+1 army), BB sends gold; turn 2: AA attacks BB at A1_MID (BB 2 vs AA 3), then conquers."""
    state = make_game(start_gold=50)
    put(state, "AA", A1_CAP, 3)
    put(state, "BB", A1_MID, 2)
    rows, final = play(state, [
        {"AA": [{"type": "recruit", "field": list(A2_CAP), "count": 2}, {"type": "send_gold", "to": "BB", "amount": 7}],
         "BB": [{"type": "send_gold", "to": "AA", "amount": 2}, {"type": "nonsense"}]},
        {"AA": [move("a1", 3, A1_MID)], "BB": [move("a2", 2, A1_CAP)]},
    ])
    return state, rows, final


def test_series_and_axis():
    state, rows, final = battle()
    st = stats_of(state, rows, final)
    assert st["version"] == engine.STATS_VERSION and st["empty"] is False
    assert st["axis"] == [1, 2, 3] and st["order"] == ["AA", "BB", "CC"]
    s = st["series"]
    assert set(s) >= {"gold", "income", "upkeep", "gold_sent", "gold_received", "provinces", "fields", "share", "cities",
                      "ports", "armies", "divisions", "ships", "divisions_at_sea"}
    assert all(len(s[m][n]) == 3 for m in s for n in s[m])
    assert s["gold"]["AA"][0] == 50 and s["gold"]["CC"] == [None, None, None]   # CC is nobody's
    assert s["provinces"]["AA"][0] == 2 and s["provinces"]["CC"][0] == 0
    assert s["fields"]["AA"][0] == 9 and s["fields"]["BB"][0] == 6
    assert s["share"]["AA"][0] == round(9 / 24, 4)
    assert s["divisions"]["AA"][0] == 3 and s["divisions"]["BB"][0] == 2
    assert s["gold_sent"]["AA"][:2] == [7, 0] and s["gold_sent"]["AA"][2] is None   # flows have no value at the end board
    assert s["gold_received"]["BB"][0] == 7 and s["income"]["AA"][0] == 4 and s["cities"]["AA"][0] == 2
    assert s["ports"]["AA"][0] == 1 and s["ships"]["AA"] == [0, 0, 0] and s["divisions_at_sea"]["AA"] == [0, 0, 0]


def test_series_count_ships_and_armies_at_sea():
    state = make_game()
    put(state, "AA", S0, 2, unit="ship")
    put(state, "AA", S0, 3)
    rows, final = play(state, [{}])
    s = stats_of(state, rows, final)["series"]
    assert s["ships"]["AA"][0] == 2 and s["divisions_at_sea"]["AA"][0] == 3 and s["armies"]["AA"][0] == 1


def test_totals_and_kills():
    state, rows, final = battle()
    t = stats_of(state, rows, final)["totals"]
    aa, bb = t["AA"], t["BB"]
    assert aa["recruited"] == 2 and aa["gold_spent_recruits"] == 10 and aa["gold_sent"] == 7 and bb["gold_received"] == 7
    assert bb["gold_sent"] == 2 and aa["gold_received"] == 2
    assert aa["gold_earned"] == 8 and aa["gold_upkeep"] > 0
    # turn 2: AA moves first or second; whichever way, exactly one fight happens with AA 3 vs BB 2
    assert aa["fights"] == 1 and bb["fights"] == 1
    assert aa["fights_attacker"] + bb["fights_attacker"] == 1 and aa["fights_defender"] + bb["fights_defender"] == 1
    assert aa["fights_won"] + aa["fights_lost"] + aa["fights_both"] == 1
    assert aa["kills_divisions"] == bb["divisions_lost_fights"] and bb["kills_divisions"] == aa["divisions_lost_fights"]
    assert aa["units_lost"] == aa["divisions_lost_fights"] + aa["divisions_lost_conquest"]
    assert aa["orders_given"] == {"recruit": 1, "send_gold": 1, "move": 1}
    assert bb["orders_given"]["nonsense"] == 1 and bb["orders_skipped"]["nonsense"] == 1
    assert aa["moves"] + bb["moves"] >= 1 and aa["avg_ready_seconds"] == 1.5 and aa["timeouts"] == 0
    assert aa["status"] == "player" and t["CC"]["status"] == "player"
    k = stats_of(state, rows, final)["kills"]
    assert k["AA"]["BB"]["divisions"] == aa["kills_divisions"] or aa["kills_divisions"] == 0


def test_fight_outcome_counts_and_heat():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    put(state, "BB", A1_MID, 2)
    rows, final = play(state, [{"AA": [move("a1", 3, A1_MID)]}])
    st = stats_of(state, rows, final)
    aa, bb = st["totals"]["AA"], st["totals"]["BB"]
    assert (aa["fights_attacker_won"], bb["fights_defender_lost"]) == (1, 1)
    assert (aa["kills_divisions"], bb["kills_divisions"]) == (2, 2) and (aa["divisions_lost_fights"], bb["divisions_lost_fights"]) == (2, 2)
    assert st["kills"] == {"AA": {"BB": {"divisions": 2, "ships": 0}}, "BB": {"AA": {"divisions": 2, "ships": 0}}}
    assert st["heat"]["fights"] == {"1,2": 1} and st["heat"]["divisions_died"] == {"1,2": 4}
    assert st["heat"]["traffic"] == {"1,2": 3} and aa["fields_marched"] == 3
    assert st["game"]["biggest_fight"]["units"] == 5 and st["game"]["biggest_fight"]["field"] == [1, 2]
    assert st["game"]["bloodiest_field"] == {"field": [1, 2], "units": 4}


def test_conquest_gifts_sales_and_contested_province():
    state = make_game(start_gold=50)
    put(state, "AA", N1_CAP, 6)
    state.owners["N1"] = "BB"
    rows, final = play(state, [
        {"AA": [{"type": "give_province", "province": "A2", "to": "BB"}]},
        {"BB": [{"type": "offer_sale", "province": "A2", "to": "AA", "price": 3}]},
        {"AA": [{"type": "buy", "province": "A2"}]},
    ])
    st = stats_of(state, rows, final)
    aa, bb = st["totals"]["AA"], st["totals"]["BB"]
    assert aa["gifts_given_provinces"] == 1 and bb["gifts_received_provinces"] == 1
    assert bb["sales"] == 1 and bb["gold_sales_income"] == 3 and aa["purchases"] == 1 and aa["gold_spent_purchases"] == 3
    assert st["game"]["most_contested_province"] == {"province": "A2", "name": "Südaland", "changes": 2}
    assert bb["gold_traded"] == 3


def test_conquest_totals():
    state = make_game()
    put(state, "AA", A2_CAP, 5)
    state.owners["N1"] = "BB"
    rows, final = play(state, [{"AA": [move("a1", 5, N1_CAP)]}])
    st = stats_of(state, rows, final)
    assert st["totals"]["AA"]["conquests"] == 1 and st["totals"]["AA"]["divisions_lost_conquest"] == 2
    assert st["totals"]["BB"]["provinces_lost"] == 1
    assert st["heat"]["conquests"] == {"3,2": 1} and st["heat"]["divisions_died"] == {"3,2": 2}


def test_knocked_out_turn_peak_share_and_titles():
    state = make_game()
    put(state, "AA", A1_CAP, 3)
    put(state, "BB", A1_MID, 1)
    for code in ("B1", "B2"):
        state.owners[code] = "AA"          # BB owns nothing but its one army, which dies in turn 1
    rows, final = play(state, [{"AA": [move("a1", 3, A1_MID)]}, {}])
    st = stats_of(state, rows, final, chat=[{"from": "AA", "to": None, "turn": 1}, {"from": "AA", "to": "BB", "turn": 2},
                                           {"from": "BB", "to": None, "turn": 2}])
    t = st["totals"]
    assert t["BB"]["knocked_out_turn"] == 2 and t["AA"]["knocked_out_turn"] is None and t["CC"]["knocked_out_turn"] is None
    assert t["BB"]["peak_share"] == 0 and t["BB"]["peak_share_turn"] is None
    assert t["AA"]["peak_share"] == round(15 / 24, 4) and t["AA"]["peak_share_turn"] == 1
    assert (t["AA"]["chat_public"], t["AA"]["chat_private"], t["BB"]["chat_public"]) == (1, 1, 1)
    assert st["chat_matrix"] == {"AA": {"all": 1, "BB": 1}, "BB": {"all": 1}}
    titles = {x["title"]: x for x in st["titles"]}
    assert titles["Schlächter"]["nation"] == "AA" and titles["Schlächter"]["metric"] == "kills" and titles["Schlächter"]["value"] == 1
    assert titles["Plaudertasche"]["nation"] == "AA" and titles["Plaudertasche"]["value"] == 2
    assert titles["Pechvogel"]["value"] == 1 and titles["Pechvogel"]["tied"] == ["BB"]   # one division each
    assert titles["Blitzmerker"]["tied"] == ["BB"]              # both were ready after the same time
    assert "Eroberer" not in titles and "Kaufmann" not in titles   # nobody has a value > 0


def test_status_timeouts_alliances_and_game_facts():
    state = make_game()
    rows, final = play(state, [{}, {}, {}])
    rows[0]["timeouts"] = ["BB"]
    rows[1]["alliances"] = {"b1": {"id": "b1", "members": ["AA", "BB"], "since": 2}}
    rows[2]["alliances"] = {}
    rows[2]["ai"] = {"BB": {"reason": "surrender", "name": "Bea"}, "CC": {"reason": "unpicked", "name": None}}
    final["ai"] = {**rows[2]["ai"], "AA": {"reason": "kick", "name": "Anna"}}   # kicked after the last resolution
    final["winner"] = {"players": ["AA"], "alliance": None, "turn": 3}
    final["players"] = {"AA": "Anna", "BB": "Bea"}
    st = stats_of(state, rows, final)
    t = st["totals"]
    assert t["BB"]["timeouts"] == 1 and t["BB"]["avg_ready_seconds"] == 2.5     # the timed-out turn is not averaged
    assert (t["AA"]["alliances_joined"], t["AA"]["alliances_left"]) == (1, 1)
    assert t["BB"]["status"] == "surrender" and t["BB"]["ai_since_turn"] == 3
    assert t["CC"]["status"] == "unpicked" and t["CC"]["ai_since_turn"] == 1
    assert t["AA"]["status"] == "kick" and t["AA"]["ai_since_turn"] == 4         # only the final row knows
    assert st["players"] == {"AA": "Anna", "BB": "Bea", "CC": None}
    g = st["game"]
    assert (g["turns"], g["final_turn"], g["started"], g["ended"], g["duration_seconds"]) == (3, 4, 1000, 1030, 30)
    assert g["winner"] == final["winner"] and g["biggest_fight"] is None and g["most_contested_province"] is None
    json.dumps(st)


def test_empty_history_still_has_the_full_shape():
    state = make_game()
    for history in ([], None):
        st = engine.compute_stats(state.map, state.rules, history)
        assert st["empty"] is True and st["axis"] == [] and st["titles"] == [] and st["kills"] == {}
        assert st["series"]["gold"] == {"AA": [], "BB": [], "CC": []}
        assert st["totals"]["AA"]["recruited"] == 0 and st["totals"]["AA"]["knocked_out_turn"] is None
        assert st["game"]["turns"] == 0 and st["game"]["duration_seconds"] is None
        json.dumps(st)


def test_history_without_a_final_row_and_a_registry_entry():
    state, rows, _ = battle()
    st = stats_of(state, rows)
    assert st["axis"] == [1, 2] and len(st["series"]["gold"]["AA"]) == 2 and st["series"]["income"]["AA"][1] is not None

    @engine.stats.series("test_two")
    def two(ctx):
        return {n: [2] * len(ctx.axis) for n in ctx.nations}
    try:
        assert stats_of(state, rows)["series"]["test_two"]["AA"] == [2, 2]
    finally:
        del engine.stats.SERIES["test_two"]
