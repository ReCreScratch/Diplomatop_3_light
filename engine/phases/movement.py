"""Movement phase: forced-march toggles and links first, then moves with combat and conquest."""
from ..combat import fight
from ..conquest import conquer, conquest_target
from ..events import make_event
from ..hexgrid import tup
from ..orders import AutoMove, plural, run_phase_orders

PHASE = "movement"


def run(state, parsed, events):
    """Toggles, links and halts (priority 0), then moves (priority 1), players in player order.
    A player's standing routes continue first in their slot (G58), unless they gave the unit a new move."""
    add_auto_orders(state, parsed)
    run_phase_orders(state, parsed, PHASE, events)


def add_auto_orders(state, parsed):
    """Put an automatic move for every unit with a route in front of its owner's orders."""
    for player in state.player_order:
        ids = [a["id"] for a in state.armies.values() if a["owner"] == player and a.get("route")]
        own = parsed.setdefault(player, [])
        given = {o.data.get("army") for o in own if o.type == "move"}
        parsed[player] = [AutoMove(i) for i in ids if i not in given] + own


def split_off(state, army, count):
    """The moving part: the unit itself if all move, else a new unit of the same type that inherits forced march."""
    if count >= army["divisions"]:
        return army
    state.unlink(army)   # splitting ends a link
    army["divisions"] -= count
    return state.new_army(army["owner"], army["field"], count, forced_march=army["forced_march"],
                          unit=state.unit_of(army))


def walk(state, mover, path):
    """Follow the path until its end or enemy units. Returns (fields walked, field before the last, enemies)."""
    current = tup(mover["field"])
    back_to = current
    walked = []
    for step in path:
        back_to, current = current, tup(step)
        walked.append(list(step))
        enemies = state.enemy_units_at(step, mover["owner"])
        if enemies:
            return walked, back_to, enemies
    return walked, back_to, []


def merge_standing(state, mover, events):
    """If an own unit of the same type already stands on the mover's field, join it (the old one keeps id and flag).
    A link of the mover passes to the merged unit if that one has none. Returns the unit that remains."""
    for other in list(state.armies.values()):
        if (other is not mover and other["owner"] == mover["owner"] and other["field"] == mover["field"]
                and state.unit_of(other) == state.unit_of(mover)):
            partner = state.partner(mover)
            state.unlink(mover)
            other["divisions"] += mover["divisions"]
            other["fresh"] += mover["fresh"]
            state.armies.pop(mover["id"])
            if partner and not state.partner(other):
                state.link(other, partner)
            what = "Flotten" if state.is_fleet(mover) else "Armeen"
            events.append(make_event("merge", mover["owner"],
                                     f"{state.nation_name(mover['owner'])}: {what} bei "
                                     f"{state.place_name(mover['field'])} vereinen sich.",
                                     army=mover["id"], into=other["id"], field=list(mover["field"])))
            return other
    return mover


def move_text(state, mover, count, target, auto, partner):
    """Public text of a move. The destination of a standing march stays secret."""
    name = state.nation_name(mover["owner"])
    amount = plural(count, "Schiff", "Schiffe") if state.is_fleet(mover) else plural(count, "Division", "Divisionen")
    if partner:
        amount += " mit verbundener " + ("Armee" if state.is_fleet(mover) else "Flotte")
    if auto:
        return f"{name} marschiert weiter: {amount} nach {state.place_name(target)}."
    return f"{name} zieht {amount} nach {state.place_name(target)}."


def execute_move(state, army, count, path, events, rest=(), auto=False, group=False):
    """One move: split, walk, fight, conquer, merge. Everything is checked against the current state.
    group: the linked partner moves along (whole units). rest = route fields beyond this turn's path; kept as
    the unit's route unless the march ends (fight, conquest attempt, merge) (G58)."""
    player = army["owner"]
    start = list(army["field"])
    mover = split_off(state, army, count)
    partner = state.partner(mover) if group else None
    movers = [u for u in (partner, mover) if u]
    movers.sort(key=lambda u: not state.is_fleet(u))   # fleet first: it takes damage first
    walked, back_to, enemies = walk(state, mover, path)
    target = walked[-1]
    events.append(make_event("move", player, move_text(state, mover, count, target, auto, partner),
                             army=mover["id"], **{"from": start}, path=walked, to=target, count=count,
                             **({"with": partner["id"]} if partner else {}), **({"auto": True} if auto else {})))
    if enemies:
        at_sea = state.terrain_at(start) == "sea" or state.terrain_at(target) == "sea"
        if fight(state, movers, enemies, target, at_sea, events) != player:
            for unit in movers:   # both sides survived: the attackers stay where they came from (G59)
                if unit["id"] in state.armies:
                    merge_standing(state, unit, events)
            return
    movers = [u for u in movers if u["id"] in state.armies]
    for unit in movers:
        unit["field"] = list(target)
    if mover["id"] in state.armies and not state.is_fleet(mover):
        code = conquest_target(state, target, player)
        if code:
            conquer(state, mover, code, back_to, events)  # on failure the army is sent back to back_to
            rest = ()                                     # a conquest attempt ends the march
    remaining = [merge_standing(state, u, events) for u in movers if u["id"] in state.armies]
    if rest and not enemies and mover in remaining:   # no fight, not merged: the march goes on next turn
        mover["route"] = [list(f) for f in rest]
