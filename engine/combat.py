"""Combat: formulas are a registry (rules['combat_formula']); fight() applies one to two armies."""
import math

from .config import exact, round_by
from .events import make_event

FORMULAS = {}


def register(name):
    """Decorator: add a combat formula under a name."""
    def wrap(func):
        FORMULAS[name] = func
        return func
    return wrap


def combat_value(state, army):
    """Combat value per division: unit value, or the forced-march value."""
    if army["forced_march"]:
        return exact(state.rules["forced_march_combat_value"])
    return exact(state.unit_type(army)["combat_value"])


def strength(rules, divisions, value):
    """floor(divisions x value) (rounding by setting), at least min_strength if any division."""
    if divisions <= 0:
        return 0
    return max(round_by(rules["strength_rounding"], divisions * value), rules["min_strength"])


@register("default")
def default_formula(rules, a_div, a_value, d_div, d_value):
    """Lower strength is destroyed; the winner loses ceil(loser strength / own value); equal = both die.
    Returns (attacker_losses, defender_losses)."""
    a_str = strength(rules, a_div, a_value)
    d_str = strength(rules, d_div, d_value)
    if a_str == d_str:
        return a_div, d_div
    if a_str > d_str:
        return min(a_div, math.ceil(d_str / a_value)), d_div
    return a_div, min(d_div, math.ceil(a_str / d_value))


def preview_fight(state, attacker_div, attacker, defender):
    """(attacker_losses, defender_losses, winner player or None) without changing anything."""
    formula = FORMULAS[state.rules["combat_formula"]]
    a_loss, d_loss = formula(state.rules, attacker_div, combat_value(state, attacker),
                             defender["divisions"], combat_value(state, defender))
    a_dead = a_loss >= attacker_div
    d_dead = d_loss >= defender["divisions"]
    winner = None
    if d_dead and not a_dead:
        winner = attacker["owner"]
    elif a_dead and not d_dead:
        winner = defender["owner"]
    return a_loss, d_loss, winner


def fight(state, attacker, defender, events):
    """Resolve a fight on the defender's field, update both armies, add the event. Returns the winner or None."""
    field = list(defender["field"])
    a_loss, d_loss, winner = preview_fight(state, attacker["divisions"], attacker, defender)
    a_name = state.nation_name(attacker["owner"])
    d_name = state.nation_name(defender["owner"])
    result = {None: "beide Armeen sind vernichtet", attacker["owner"]: f"{a_name} siegt",
              defender["owner"]: f"{d_name} siegt"}[winner]
    text = (f"Kampf bei {state.place_name(field)}: {a_name} verliert {a_loss}, "
            f"{d_name} verliert {d_loss} Divisionen; {result}.")
    events.append(make_event("fight", attacker["owner"], text, field=field,
                             attacker=attacker["owner"], defender=defender["owner"],
                             attacker_losses=a_loss, defender_losses=d_loss, winner=winner))
    state.lose_divisions(attacker, a_loss)
    state.lose_divisions(defender, d_loss)
    return winner
