"""Conquest of a province by standing on its capital."""
import math

from .config import exact
from .events import make_event


def conquest_target(state, field, player):
    """Province code if field is the capital of a province with a hostile or neutral owner, else None."""
    code = state.is_capital(field)
    if code and state.hostile(player, state.owners[code]):
        return code
    return None


def conquest_cost(state, code):
    """Divisions needed: income x conquest_cost_factor, rounded up."""
    income = state.map["provinces"][code]["income"]
    return math.ceil(income * exact(state.rules["conquest_cost_factor"]))


def can_pay(state, divisions, cost):
    """Enough divisions? Exactly enough counts if conquest_allow_army_used_up."""
    if divisions > cost:
        return True
    return divisions == cost and state.rules["conquest_allow_army_used_up"]


def conquer(state, army, code, back_to, events):
    """Try to take the province with the army standing on its capital. On failure the army goes to back_to.
    Returns True if conquered."""
    cost = conquest_cost(state, code)
    field = list(army["field"])
    name = state.nation_name(army["owner"])
    prov = state.map["provinces"][code]["name"]
    if not can_pay(state, army["divisions"], cost):
        army["field"] = list(back_to)
        events.append(make_event("conquest_failed", army["owner"],
                                 f"{name} kann {prov} nicht erobern ({cost} Divisionen nötig) und weicht zurück.",
                                 province=code, field=field, cost=cost, back_to=list(back_to)))
        return False
    old_owner = state.owners[code]
    state.owners[code] = army["owner"]
    state.gifts = [g for g in state.gifts if g["province"] != code]   # conquered provinces count at once (11.5)
    state.lose_divisions(army, cost)
    events.append(make_event("conquest", army["owner"],
                             (f"{name} erobert {prov} von {state.nation_name(old_owner)} (Kosten: {cost} Divisionen)." if old_owner
                              else f"{name} erobert das neutrale {prov} (Kosten: {cost} Divisionen)."),
                             province=code, field=field, cost=cost, old_owner=old_owner))
    return True
