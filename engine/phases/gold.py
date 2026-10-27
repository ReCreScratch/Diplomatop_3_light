"""Gold phase: income and upkeep for every player, then gold transfers and province gifts."""
from ..config import as_number, exact, round_by
from ..events import make_event
from ..orders import run_phase_orders

PHASE = "gold"


def income_of(state, player):
    """Sum of the income values of the player's provinces."""
    return sum(state.map["provinces"][code]["income"] for code in state.provinces_of(player))


def upkeep_of(state, player):
    """Upkeep for the player's divisions, armies and ships, rounded (or not) on the nation total."""
    rules = state.rules
    units = [a for a in state.armies.values() if a["owner"] == player]
    armies = [a for a in units if not state.is_fleet(a)]
    ships = sum(a["divisions"] for a in units if state.is_fleet(a))
    total = (exact(rules["upkeep_per_division"]) * sum(a["divisions"] for a in armies)
             + exact(rules["upkeep_per_army"]) * len(armies) + exact(rules["upkeep_per_ship"]) * ships)
    return as_number(round_by(rules["upkeep_rounding"], total))


def pay(state, events):
    """Income minus upkeep for every player in player order (gold may go negative)."""
    for player in state.player_order:
        info = state.players[player]
        income, upkeep = income_of(state, player), upkeep_of(state, player)
        info["gold"] = as_number(exact(info["gold"]) + income - exact(upkeep))
        name = state.nation_name(player)
        events.append(make_event("income", player, f"{name} erhält {income} Gold Einkommen.", amount=income))
        events.append(make_event("upkeep", player, f"{name} zahlt {upkeep} Gold Unterhalt.", amount=upkeep))


def run(state, parsed, events):
    """Pay income and upkeep, then run all send_gold / give_province orders."""
    pay(state, events)
    run_phase_orders(state, parsed, PHASE, events)
