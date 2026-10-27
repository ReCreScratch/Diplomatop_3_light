"""Read-only views: preview_move and the public board."""
from .combat import preview_fight
from .conquest import can_pay, conquest_cost, conquest_target
from .orders import Move, Pending, moves_as_group, plural, this_turn
from .phases.gold import income_of, upkeep_of
from .victory import fields_of


def empty_preview(errors):
    """Result for an invalid move."""
    return {"valid": False, "errors": errors, "end_field": None, "fight": None, "conquest": None,
            "text": errors[0]}


def first_enemy(state, player, path):
    """(index of the first step with hostile units, those units) or (None, [])."""
    for index, step in enumerate(path):
        enemies = state.hostile_units_at(step, player)
        if enemies:
            return index, enemies
    return None, []


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
    partner = state.partner(army)
    group = moves_as_group(state, army, path, partner)
    count = army["divisions"] if group else min(count, state.movable(army))
    path = path[:this_turn(state, army, path, group=group)]   # only this turn's part (standing marches, G58)
    index, enemies = first_enemy(state, player, path)
    if not enemies:   # the move may not end on a field held by non-hostile foreign units (RULES.md 11.1)
        free = state.free_steps(player, path)
        if not free:
            return {"valid": True, "errors": [], "end_field": list(army["field"]), "fight": None, "conquest": None,
                    "text": "Das Ziel ist von fremden Truppen besetzt, die Armee bleibt stehen."}
        path = path[:free]
    end = path[index] if enemies else path[-1]
    survivors, fight, texts = count, None, []
    if enemies:
        attackers = [(army, count)] + ([(partner, partner["divisions"])] if group else [])
        attackers.sort(key=lambda pair: not state.is_fleet(pair[0]))
        at_sea = state.at_sea(army) or state.terrain_at(end) == "sea"
        a_loss, d_loss, winner = preview_fight(state, attackers, enemies, at_sea)
        mine = [i for i, (unit, _) in enumerate(attackers) if unit is army][0]
        survivors = count - a_loss[mine] if winner == player else 0
        fight = {"defender": enemies[0]["owner"], "attacker_losses": sum(a_loss), "defender_losses": sum(d_loss),
                 "winner": winner}
        texts.append(f"Kampf gegen {state.nation_name(enemies[0]['owner'])}: du verlierst {sum(a_loss)}, "
                     f"sie verlieren {sum(d_loss)}.")
    conquest = None
    code = None if state.is_fleet(army) else conquest_target(state, end, player)
    if code and survivors > 0:
        cost = conquest_cost(state, code)
        conquest = {"province": code, "cost": cost, "possible": can_pay(state, survivors, cost)}
        texts.append(f"Eroberung kostet {plural(cost, 'Division', 'Divisionen')}.")
    text = " ".join(texts) or f"Zug nach {state.place_name(end)}."
    return {"valid": True, "errors": [], "end_field": list(end), "fight": fight, "conquest": conquest,
            "text": text}


def board(state):
    """One public row per player. share = share of all land fields; share_counted = the part that counts for victory
    (gifted and sold provinces only after gift_delay_turns, RULES.md 11.5)."""
    fields, total = fields_of(state, state.turn - 1)
    rows = []
    for player, info in state.players.items():
        units = [a for a in state.armies.values() if a["owner"] == player]
        armies = [a for a in units if not state.is_fleet(a)]
        real, counted = fields[player]
        alliance = state.alliance_of(player)
        rows.append({"player": player, "name": info["name"], "provinces": len(state.provinces_of(player)), "fields": real,
                     "share": real / total if total else 0, "share_counted": counted / total if total else 0,
                     "alliance": alliance["id"] if alliance else None, "income": income_of(state, player),
                     "upkeep": upkeep_of(state, player), "armies": len(armies),
                     "divisions": sum(a["divisions"] for a in armies),
                     "ships": sum(a["divisions"] for a in units if state.is_fleet(a))})
    return rows
