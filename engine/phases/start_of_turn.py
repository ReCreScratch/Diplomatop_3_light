"""Start of a turn: new player order, income, upkeep."""
from ..config import exact, round_by
from ..events import make_event
from ..turn_order import draw_order


def income_of(state, player):
    """Sum of the income values of the player's provinces."""
    return sum(state.map["provinces"][code]["income"] for code in state.provinces_of(player))


def upkeep_of(state, player):
    """Upkeep for the player's armies, rounded on the nation total."""
    rules = state.rules
    armies = [a for a in state.armies.values() if a["owner"] == player]
    total = (exact(rules["upkeep_per_division"]) * sum(a["divisions"] for a in armies)
             + exact(rules["upkeep_per_army"]) * len(armies))
    return round_by(rules["upkeep_rounding"], total)


def start_turn(state, events):
    """Reset fresh divisions, draw the order, pay income and upkeep (gold may go negative)."""
    for army in state.armies.values():
        army["fresh"] = 0
    state.prev_player_order = state.player_order
    state.player_order = draw_order(state)
    names = ", ".join(state.nation_name(p) for p in state.player_order)
    events.append(make_event("turn_start", None, f"Runde {state.turn} beginnt. Reihenfolge: {names}.",
                             player_order=list(state.player_order)))
    for player in state.player_order:
        info = state.players[player]
        info["provinces_at_turn_start"] = len(state.provinces_of(player))
        income, upkeep = income_of(state, player), upkeep_of(state, player)
        info["gold"] += income - upkeep
        name = state.nation_name(player)
        events.append(make_event("income", player, f"{name} erhält {income} Gold Einkommen.", amount=income))
        events.append(make_event("upkeep", player, f"{name} zahlt {upkeep} Gold Unterhalt.", amount=upkeep))
