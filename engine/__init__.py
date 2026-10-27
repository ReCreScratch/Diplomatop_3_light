"""Diplomatio rules engine: pure Python. Public API (see API.md section 2)."""
from .ai import make_ai
from .config import MapError, load_map, load_rules, validate_map
from .orders import ORDER_TYPES, Pending, parse_order
from .phases.start_of_turn import start_turn
from .preview import board, preview_move
from .resolve import resolve_turn
from .state import GameState
from .stats import STATS_VERSION, compute_stats

__all__ = ["MapError", "load_map", "load_rules", "validate_map", "new_game", "validate_orders", "resolve_turn",
           "preview_move", "board", "make_ai", "GameState", "compute_stats", "STATS_VERSION"]


def new_game(map_data, players, rules, seed, ai=()):
    """Create a game and run the start of turn 1. players: {nation: player_name}. ai: nations run by the AI ruleset
    (RULES.md 8.2); other nations without a player stay neutral (owner None). A nation's start_gold in the map
    overrides the rules' start_gold."""
    ai = {nation: {"reason": "unpicked", "name": None} for nation in ai if nation not in players}
    owners = {code: (p["owner"] if p["owner"] in players or p["owner"] in ai else None)
              for code, p in map_data["provinces"].items()}
    nations = map_data["nations"]
    infos = {nation: {"name": name, "gold": nations.get(nation, {}).get("start_gold", rules["start_gold"]),
                      "provinces_at_turn_start": 0} for nation, name in players.items()}
    state = GameState(1, seed, rules, map_data, infos, owners, {}, 1, [], [], [])
    state.ai = ai
    for army in map_data.get("start_armies", []):
        if army["owner"] in players or army["owner"] in ai:
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
