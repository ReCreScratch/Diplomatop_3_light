"""Diplomatio rules engine: pure Python. Public API (see API.md section 2)."""
from .config import MapError, load_map, load_rules
from .orders import ORDER_TYPES, Pending, parse_order
from .phases.start_of_turn import start_turn
from .preview import board, preview_move
from .resolve import resolve_turn
from .state import GameState

__all__ = ["MapError", "load_map", "load_rules", "new_game", "validate_orders", "resolve_turn",
           "preview_move", "board", "GameState"]


def new_game(map_data, players, rules, seed):
    """Create a game and run the start of turn 1. players: {nation: player_name}."""
    owners = {code: (p["owner"] if p["owner"] in players else None) for code, p in map_data["provinces"].items()}
    infos = {nation: {"name": name, "gold": rules["start_gold"], "provinces_at_turn_start": 0}
             for nation, name in players.items()}
    state = GameState(1, seed, rules, map_data, infos, owners, {}, 1, [], [], [])
    for army in map_data.get("start_armies", []):
        if army["owner"] in players:
            state.new_army(army["owner"], army["field"], army["divisions"])
    start_turn(state, [])
    return state


def validate_orders(state, player_id, orders):
    """One list of German error strings per order (empty = valid), checked in entry order."""
    if player_id not in state.players:
        return [["Unbekannter Spieler."] for _ in orders]
    pending = Pending()
    parsed = [parse_order(data) for data in orders]
    for order in parsed:
        if order:
            order.prepare(state, player_id, pending)
    results = []
    for order in parsed:
        if order is None:
            results.append(["Unbekannter Befehl."])
            continue
        errors = order.validate(state, player_id, pending)
        if not errors:
            order.reserve(state, pending)
        results.append(errors)
    return results
