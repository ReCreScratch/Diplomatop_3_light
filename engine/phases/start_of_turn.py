"""Start of a turn: fresh divisions become normal, new player order. Income is paid in the gold phase."""
from ..events import make_event
from ..turn_order import draw_order


def start_turn(state, events):
    """Reset fresh divisions, draw the order, note the province count for the recruit limit."""
    for army in state.armies.values():
        army["fresh"] = 0
    state.prev_player_order = state.player_order
    state.player_order = draw_order(state)
    names = ", ".join(state.nation_name(p) for p in state.player_order)
    events.append(make_event("turn_start", None, f"Runde {state.turn} beginnt. Reihenfolge: {names}.",
                             player_order=list(state.player_order)))
    for player in state.player_order:
        state.players[player]["provinces_at_turn_start"] = len(state.provinces_of(player))
