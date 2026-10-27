"""Combat: formulas are a registry (rules['combat_formula']); fight() applies one to two armies."""
import math

from .config import exact, round_by
from .events import make_event

FORMULAS = {}
BOTH_SURVIVE = "both"   # winner value when neither army is destroyed


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


def side(state, divisions, army):
    """What a formula needs about one side: divisions, combat value and hit points per division."""
    return {"divisions": divisions, "value": combat_value(state, army), "hp": exact(state.unit_type(army)["hp"])}


def strength(rules, divisions, value):
    """floor(divisions x value) (rounding by setting), at least min_strength if any division."""
    if divisions <= 0:
        return 0
    return max(round_by(rules["strength_rounding"], divisions * value), rules["min_strength"])


@register("hp_attrition")
def hp_attrition(rules, a, d):
    """4.0: each side loses hit points equal to the other side's total combat value, at the same time.
    At or below 0 hit points the army is destroyed; else the rest becomes divisions (survivor_rounding).
    Returns (attacker_losses, defender_losses)."""
    def losses(own, other):
        left = own["divisions"] * own["hp"] - other["divisions"] * other["value"]
        if left <= 0:
            return own["divisions"]
        return own["divisions"] - min(own["divisions"], round_by(rules["survivor_rounding"], left / own["hp"]))
    return losses(a, d), losses(d, a)


@register("strength_3_0")
def strength_formula(rules, a, d):
    """3.0: lower strength is destroyed; the winner loses ceil(loser strength / own value); equal = both die.
    Returns (attacker_losses, defender_losses)."""
    a_div, a_value, d_div, d_value = a["divisions"], a["value"], d["divisions"], d["value"]
    a_str = strength(rules, a_div, a_value)
    d_str = strength(rules, d_div, d_value)
    if a_str == d_str:
        return a_div, d_div
    if a_str > d_str:
        return min(a_div, math.ceil(d_str / a_value)), d_div
    return a_div, min(d_div, math.ceil(a_str / d_value))


def preview_fight(state, attacker_div, attacker, defender):
    """(attacker_losses, defender_losses, winner) without changing anything.
    winner: a player, None if both are destroyed, BOTH_SURVIVE if neither is (G59)."""
    formula = FORMULAS[state.rules["combat_formula"]]
    a_loss, d_loss = formula(state.rules, side(state, attacker_div, attacker),
                             side(state, defender["divisions"], defender))
    a_dead = a_loss >= attacker_div
    d_dead = d_loss >= defender["divisions"]
    if a_dead == d_dead:
        return a_loss, d_loss, (None if a_dead else BOTH_SURVIVE)
    return a_loss, d_loss, (defender["owner"] if a_dead else attacker["owner"])


def fight(state, attacker, defender, events):
    """Resolve a fight on the defender's field, update both armies, add the event. Returns the winner (see preview_fight)."""
    field = list(defender["field"])
    a_loss, d_loss, winner = preview_fight(state, attacker["divisions"], attacker, defender)
    a_name = state.nation_name(attacker["owner"])
    d_name = state.nation_name(defender["owner"])
    result = {None: "beide Armeen sind vernichtet", BOTH_SURVIVE: "beide Armeen überleben",
              attacker["owner"]: f"{a_name} siegt",
              defender["owner"]: f"{d_name} siegt"}[winner]
    text = (f"Kampf bei {state.place_name(field)}: {a_name} verliert {a_loss}, "
            f"{d_name} verliert {d_loss} Divisionen; {result}.")
    events.append(make_event("fight", attacker["owner"], text, field=field,
                             attacker=attacker["owner"], defender=defender["owner"],
                             attacker_losses=a_loss, defender_losses=d_loss, winner=winner))
    state.lose_divisions(attacker, a_loss)
    state.lose_divisions(defender, d_loss)
    for army in (attacker, defender):
        army.pop("route", None)  # a fight ends a standing march (G58)
    return winner
