"""Read-only views: preview_move and the public board."""
from .combat import preview_fight
from .conquest import can_pay, conquest_cost, conquest_target
from .orders import Move, Pending, plural, range_of
from .phases.start_of_turn import income_of, upkeep_of


def empty_preview(errors):
    """Result for an invalid move."""
    return {"valid": False, "errors": errors, "end_field": None, "fight": None, "conquest": None,
            "text": errors[0]}


def first_enemy(state, player, path):
    """(index of the first step with an enemy army, that army) or (None, None)."""
    for index, step in enumerate(path):
        enemy = state.enemy_army_at(step, player)
        if enemy:
            return index, enemy
    return None, None


def preview_move(state, player, army_id, count, path, forced_march=None):
    """What a move would do on the current board (other orders ignored).
    forced_march: the army's setting after this turn's pending toggle (None = current setting)."""
    order = Move({"type": "move", "army": army_id, "count": count, "path": path})
    pending = Pending()
    if forced_march is not None:
        pending.toggles[army_id] = bool(forced_march)
    errors = order.validate(state, player, pending)
    if errors:
        return empty_preview(errors)
    army = state.armies[army_id]
    if forced_march is not None:
        army = {**army, "forced_march": bool(forced_march)}
    count = min(count, state.movable(army))
    path = path[:range_of(state, army)]   # only this turn's part (standing marches, G58)
    index, enemy = first_enemy(state, player, path)
    end = path[index] if enemy else path[-1]
    survivors, fight, texts = count, None, []
    if enemy:
        a_loss, d_loss, winner = preview_fight(state, count, army, enemy)
        survivors = count - a_loss if winner == player else 0
        fight = {"defender": enemy["owner"], "attacker_losses": a_loss, "defender_losses": d_loss, "winner": winner}
        texts.append(f"Kampf gegen {state.nation_name(enemy['owner'])}: du verlierst {a_loss}, "
                     f"sie verlieren {d_loss}.")
    conquest = None
    code = conquest_target(state, end, player)
    if code and survivors > 0:
        cost = conquest_cost(state, code)
        conquest = {"province": code, "cost": cost, "possible": can_pay(state, survivors, cost)}
        texts.append(f"Eroberung kostet {plural(cost, 'Division', 'Divisionen')}.")
    text = " ".join(texts) or f"Zug nach {state.place_name(end)}."
    return {"valid": True, "errors": [], "end_field": list(end), "fight": fight, "conquest": conquest,
            "text": text}


def board(state):
    """One public row per player."""
    total = len(state.owners)
    rows = []
    for player, info in state.players.items():
        armies = [a for a in state.armies.values() if a["owner"] == player]
        count = len(state.provinces_of(player))
        rows.append({"player": player, "name": info["name"], "provinces": count,
                     "share": count / total if total else 0, "income": income_of(state, player),
                     "upkeep": upkeep_of(state, player), "armies": len(armies),
                     "divisions": sum(a["divisions"] for a in armies)})
    return rows
