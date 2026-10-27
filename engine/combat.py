"""Combat: formulas are a registry (rules['combat_formula']); fight() applies one to two sides.

A side is a list of units of one player on one field, fleets first (tank rule, RULES.md 10.5).
A formula gets each side as a list of {divisions, value, hp} and returns the losses per unit."""
import math

from .config import as_number, exact, round_by
from .events import make_event

FORMULAS = {}
BOTH_SURVIVE = "both"   # winner value when neither side is destroyed


def register(name):
    """Decorator: add a combat formula under a name."""
    def wrap(func):
        FORMULAS[name] = func
        return func
    return wrap


def combat_value(state, army, at_sea=None):
    """Combat value per division or ship. An army fighting at sea, or attacking from it, is a transport.
    at_sea: whether the fight involves the sea for this unit (None = the field it stands on)."""
    rules = state.rules
    if state.is_fleet(army):
        return exact(state.unit_type(army)["combat_value"])
    if state.at_sea(army) if at_sea is None else at_sea:
        return exact(rules["transport_combat_value"])
    if army["forced_march"]:
        return exact(rules["forced_march_combat_value"])
    return exact(state.unit_type(army)["combat_value"])


def side(state, units, at_sea=None):
    """Formula input for a list of (unit, count)."""
    return [{"divisions": count, "value": combat_value(state, unit, at_sea),
             "hp": exact(state.unit_type(unit)["hp"])} for unit, count in units]


def damage(units):
    """Total combat value of a side."""
    return sum(u["divisions"] * u["value"] for u in units)


def strength(rules, divisions, value):
    """floor(divisions x value) (rounding by setting), at least min_strength if any division."""
    if divisions <= 0:
        return 0
    return max(round_by(rules["strength_rounding"], divisions * value), rules["min_strength"])


def take_damage(rules, units, dmg):
    """Spread damage over the units in order (fleet first): each loses hit points until the damage is used up."""
    losses = []
    for u in units:
        total = u["divisions"] * u["hp"]
        if dmg >= total:
            losses.append(u["divisions"])
            dmg -= total
            continue
        keep = min(u["divisions"], round_by(rules["survivor_rounding"], (total - dmg) / u["hp"]))
        losses.append(u["divisions"] - keep)
        dmg = 0
    return losses


def spread(units, count):
    """Remove count divisions, first unit first."""
    losses = []
    for u in units:
        lost = min(count, u["divisions"])
        losses.append(lost)
        count -= lost
    return losses


@register("hp_attrition")
def hp_attrition(rules, a, d):
    """4.0: each side loses hit points equal to the other side's total combat value, at the same time.
    At or below 0 hit points a unit is destroyed; else the rest becomes divisions (survivor_rounding).
    Returns (attacker_losses, defender_losses), one entry per unit."""
    return take_damage(rules, a, damage(d)), take_damage(rules, d, damage(a))


@register("strength_3_0")
def strength_formula(rules, a, d):
    """3.0: lower strength is destroyed; the winner loses ceil(loser strength / own value); equal = both die.
    The winner's value is that of its first unit. Returns (attacker_losses, defender_losses)."""
    a_div, d_div = sum(u["divisions"] for u in a), sum(u["divisions"] for u in d)
    a_str = strength(rules, a_div, damage(a) / a_div) if a_div else 0
    d_str = strength(rules, d_div, damage(d) / d_div) if d_div else 0
    if a_str == d_str:
        return spread(a, a_div), spread(d, d_div)
    if a_str > d_str:
        return spread(a, math.ceil(d_str / a[0]["value"])), spread(d, d_div)
    return spread(a, a_div), spread(d, math.ceil(a_str / d[0]["value"]))


def preview_fight(state, attackers, defenders, attack_at_sea=None):
    """(attacker_losses, defender_losses, winner) without changing anything.
    attackers: list of (unit, count); defenders: list of units. Losses are lists per unit.
    winner: a player, None if both sides are destroyed, BOTH_SURVIVE if neither is (G59)."""
    formula = FORMULAS[state.rules["combat_formula"]]
    a_loss, d_loss = formula(state.rules, side(state, attackers, attack_at_sea),
                             side(state, [(u, u["divisions"]) for u in defenders]))
    a_dead = all(lost >= count for lost, (_, count) in zip(a_loss, attackers))
    d_dead = all(lost >= u["divisions"] for lost, u in zip(d_loss, defenders))
    if a_dead == d_dead:
        return a_loss, d_loss, (None if a_dead else BOTH_SURVIVE)
    return a_loss, d_loss, (defenders[0]["owner"] if a_dead else attackers[0][0]["owner"])


def unit_info(state, unit, value, lost, transport):
    """Raw record of one unit in a fight (for the archive and statistics): the state before the fight."""
    return {"army": unit["id"], "owner": unit["owner"], "unit": state.unit_of(unit), "fleet": state.is_fleet(unit),
            "count": unit["divisions"], "value": as_number(value), "forced_march": bool(unit.get("forced_march")),
            "transport": transport, "lost": lost}


def fight(state, attackers, defenders, field, attack_at_sea, events):
    """Resolve a fight on field, update all units, add the event. attackers: units (all of them fight).
    Returns the winner (see preview_fight)."""
    a_loss, d_loss, winner = preview_fight(state, [(u, u["divisions"]) for u in attackers], defenders, attack_at_sea)
    a_owner, d_owner = attackers[0]["owner"], defenders[0]["owner"]
    a_name, d_name = state.nation_name(a_owner), state.nation_name(d_owner)
    result = {None: "beide Seiten sind vernichtet", BOTH_SURVIVE: "beide Seiten überleben",
              a_owner: f"{a_name} siegt", d_owner: f"{d_name} siegt"}[winner]
    text = (f"Kampf bei {state.place_name(field)}: {a_name} verliert {losses_text(state, attackers, a_loss)}, "
            f"{d_name} verliert {losses_text(state, defenders, d_loss)}; {result}.")
    a_side, d_side = side(state, [(u, u["divisions"]) for u in attackers], attack_at_sea), side(state, [(u, u["divisions"]) for u in defenders])
    a_units = [unit_info(state, u, s["value"], n, not state.is_fleet(u) and bool(attack_at_sea))
               for u, s, n in zip(attackers, a_side, a_loss)]
    d_units = [unit_info(state, u, s["value"], n, not state.is_fleet(u) and state.at_sea(u))
               for u, s, n in zip(defenders, d_side, d_loss)]
    ships = lambda infos: sum(i["lost"] for i in infos if i["fleet"])          # noqa: E731
    divisions = lambda infos: sum(i["lost"] for i in infos if not i["fleet"])  # noqa: E731
    events.append(make_event("fight", a_owner, text, field=list(field), attacker=a_owner, defender=d_owner,
                             attacker_losses=sum(a_loss), defender_losses=sum(d_loss), winner=winner,
                             losses={u["id"]: n for u, n in zip(attackers + defenders, a_loss + d_loss)},
                             sea=bool(attack_at_sea or state.terrain_at(field) == "sea"),
                             attacker_units=a_units, defender_units=d_units,
                             attacker_damage=as_number(damage(a_side)), defender_damage=as_number(damage(d_side)),
                             attacker_divisions_lost=divisions(a_units), attacker_ships_lost=ships(a_units),
                             defender_divisions_lost=divisions(d_units), defender_ships_lost=ships(d_units)))
    for unit, lost in zip(attackers + defenders, a_loss + d_loss):
        unit.pop("route", None)  # a fight ends a standing march (G58)
        state.lose_divisions(unit, lost)
    return winner


def losses_text(state, units, losses):
    """'3 Divisionen', '1 Schiff und 2 Divisionen'."""
    parts = []
    for unit, lost in zip(units, losses):
        if state.is_fleet(unit):
            parts.append(f"{lost} {'Schiff' if lost == 1 else 'Schiffe'}")
        else:
            parts.append(f"{lost} {'Division' if lost == 1 else 'Divisionen'}")
    return " und ".join(parts)
