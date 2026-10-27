"""Movement phase: forced-march toggles first, then moves with combat and conquest."""
from ..combat import fight
from ..conquest import conquer, conquest_target
from ..events import make_event
from ..hexgrid import tup
from ..orders import AutoMove, plural, run_phase_orders

PHASE = "movement"


def run(state, parsed, events):
    """Toggles and halts (priority 0), then moves (priority 1), players in player order.
    A player's standing routes continue first in their slot (G58), unless they gave the army a new move."""
    add_auto_orders(state, parsed)
    run_phase_orders(state, parsed, PHASE, events)


def add_auto_orders(state, parsed):
    """Put an automatic move for every army with a route in front of its owner's orders."""
    for player in state.player_order:
        ids = [a["id"] for a in state.armies.values() if a["owner"] == player and a.get("route")]
        own = parsed.setdefault(player, [])
        given = {o.data.get("army") for o in own if o.type == "move"}
        parsed[player] = [AutoMove(i) for i in ids if i not in given] + own


def split_off(state, army, count):
    """The moving part: the army itself if all move, else a new army that inherits forced march."""
    if count >= army["divisions"]:
        return army
    army["divisions"] -= count
    return state.new_army(army["owner"], army["field"], count, forced_march=army["forced_march"])


def walk(state, mover, path):
    """Follow the path until its end or an enemy army. Returns (fields walked, field before the last, enemy)."""
    current = tup(mover["field"])
    back_to = current
    walked = []
    for step in path:
        back_to, current = current, tup(step)
        walked.append(list(step))
        enemy = state.enemy_army_at(step, mover["owner"])
        if enemy:
            return walked, back_to, enemy
    return walked, back_to, None


def merge_standing(state, mover, events):
    """If an own army already stands on the mover's field, join it (the old one keeps id and flag)."""
    for other in list(state.armies.values()):
        if other is not mover and other["owner"] == mover["owner"] and other["field"] == mover["field"]:
            other["divisions"] += mover["divisions"]
            state.armies.pop(mover["id"])
            events.append(make_event("merge", mover["owner"],
                                     f"{state.nation_name(mover['owner'])}: Armeen bei "
                                     f"{state.place_name(mover['field'])} vereinen sich.",
                                     army=mover["id"], into=other["id"], field=list(mover["field"])))
            return


def execute_move(state, army, count, path, events, rest=(), goal=None, auto=False):
    """One move: split, walk, fight, conquer, merge. Everything is checked against the current state.
    rest = route fields beyond this turn's path; kept as army['route'] unless the march ends
    (fight, conquest attempt, merge) (G58)."""
    player = army["owner"]
    start = list(army["field"])
    mover = split_off(state, army, count)
    walked, back_to, enemy = walk(state, mover, path)
    target = walked[-1]
    name, amount = state.nation_name(player), plural(count, "Division", "Divisionen")
    if auto:
        # events are public: the destination of a standing march stays secret
        text = f"{name} marschiert weiter: {amount} nach {state.place_name(target)}."
    else:
        text = f"{name} zieht {amount} nach {state.place_name(target)}."
    events.append(make_event("move", player, text, army=mover["id"], **{"from": start}, path=walked,
                             to=target, count=count, **({"auto": True} if auto else {})))
    if enemy and fight(state, mover, enemy, events) != player:
        if mover["id"] in state.armies:   # both survived: the attacker stays where it came from (G59)
            merge_standing(state, mover, events)
        return
    mover["field"] = list(target)
    code = conquest_target(state, target, player)
    if code:
        conquer(state, mover, code, back_to, events)  # on failure the army is sent back to back_to
        rest = ()                                     # a conquest attempt ends the march
    merge_standing(state, mover, events)
    if rest and not enemy and mover["id"] in state.armies:  # no fight, not merged: the march goes on next turn
        mover["route"] = [list(f) for f in rest]
