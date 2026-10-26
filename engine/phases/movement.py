"""Movement phase: forced-march toggles first, then moves with combat and conquest."""
from ..combat import fight
from ..conquest import conquer, conquest_target
from ..events import make_event
from ..hexgrid import tup
from ..orders import plural, run_phase_orders

PHASE = "movement"


def run(state, parsed, events):
    """Toggles (priority 0) then moves (priority 1), players in player order."""
    run_phase_orders(state, parsed, PHASE, events)


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


def execute_move(state, army, count, path, events):
    """One move: split, walk, fight, conquer, merge. Everything is checked against the current state."""
    player = army["owner"]
    start = list(army["field"])
    mover = split_off(state, army, count)
    walked, back_to, enemy = walk(state, mover, path)
    target = walked[-1]
    events.append(make_event(
        "move", player,
        f"{state.nation_name(player)} zieht {plural(count, 'Division', 'Divisionen')} nach {state.place_name(target)}.",
        army=mover["id"], **{"from": start}, path=walked, to=target, count=count))
    if enemy and fight(state, mover, enemy, events) != player:
        return
    mover["field"] = list(target)
    code = conquest_target(state, target, player)
    if code:
        conquer(state, mover, code, back_to, events)  # on failure the army is sent back to back_to
    if mover["id"] in state.armies:
        merge_standing(state, mover, events)
