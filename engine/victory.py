"""Victory (RULES.md 11.5): shares of land fields, gift delay, alliance age, holding the lead for some resolutions."""
from fractions import Fraction

from .alliances import names
from .config import exact
from .events import make_event


def province_fields(state):
    """{province code: number of land fields}."""
    sizes = {}
    for token in state.cells.values():
        if token in state.owners:
            sizes[token] = sizes.get(token, 0) + 1
    return sizes


def counted(state, code, now):
    """The province counts towards its owner's share: not given or sold to that owner less than gift_delay_turns ago.
    now = number of the last resolved turn."""
    owner = state.owners[code]
    gifts = [g for g in state.gifts if g["province"] == code]
    return not (gifts and gifts[-1]["to"] == owner and now - gifts[-1]["turn"] < state.rules["gift_delay_turns"])


def fields_of(state, now):
    """{player: (real fields, counted fields)} and the total of all land fields."""
    sizes = province_fields(state)
    result = {p: [0, 0] for p in list(state.players) + list(state.ai)}   # AI nations hold land but cannot win
    for code, owner in state.owners.items():
        if owner in result:
            result[owner][0] += sizes.get(code, 0)
            if counted(state, code, now):
                result[owner][1] += sizes.get(code, 0)
    return result, sum(sizes.values())


def candidates(state, now):
    """Everybody who meets a victory condition right now: [(share, kind, id, players)], best first.
    An alliance meets it with the sum of its members' counted fields and when old enough (alliance_min_turns)."""
    fields, total = fields_of(state, now)
    found = []
    if not total:
        return found
    rules = state.rules
    for alliance in state.alliances.values():
        share = Fraction(sum(fields[p][1] for p in alliance["members"] if p in fields), total)
        if share > exact(rules["victory_share_alliance"]) and now - alliance["since"] >= rules["alliance_min_turns"]:
            found.append((share, "alliance", alliance["id"], list(alliance["members"])))
    for player, (_, own) in fields.items():
        if player in state.players and Fraction(own, total) > exact(rules["victory_share_single"]):   # also when in an alliance
            found.append((Fraction(own, total), "player", player, [player]))
    return sorted(found, key=lambda c: -c[0])   # stable: an alliance comes before its own member on equal share


def check_victory(state, events):
    """End of every resolution: count how long the same leader keeps meeting a condition; at victory_hold_turns the
    game is won (state.winner). Run before the turn counter moves on."""
    if state.winner:
        return
    now = state.turn
    found = candidates(state, now)
    if not found:
        state.victory = None
        return
    _, kind, ident, players = found[0]
    old = state.victory
    same = old and (old["kind"], old["id"], old["players"]) == (kind, ident, players)
    state.victory = {"kind": kind, "id": ident, "players": players, "turns": old["turns"] + 1 if same else 1}
    need = state.rules["victory_hold_turns"]
    who = names(state, players) if kind == "player" else f"Das Bündnis von {names(state, players)}"
    if state.victory["turns"] >= need:
        state.winner = {"players": players, "alliance": ident if kind == "alliance" else None, "turn": now}
        events.append(make_event("victory", None, f"{who} gewinnt das Spiel!", players=players, alliance=state.winner["alliance"]))
    else:
        events.append(make_event("victory_progress", None,
                                 f"{who} erfüllt die Siegbedingung: Runde {state.victory['turns']} von {need}.",
                                 players=players, turns=state.victory["turns"], need=need))
