"""Turn resolution: run the phase pipeline from rules['phases'], then start the next turn."""
from .orders import parse_order, skipped
from .phases import PHASES
from .phases.start_of_turn import start_turn


def parse_all(state, orders, events):
    """{player: [Order objects]}; unknown order types become 'skipped' events."""
    parsed = {}
    for player, items in orders.items():
        if player not in state.players:
            continue
        parsed[player] = []
        for data in items:
            order = parse_order(data)
            if order:
                parsed[player].append(order)
            else:
                events.append(skipped(state, player, data, "Unbekannter Befehl."))
    return parsed


def resolve_turn(state, orders):
    """Resolve one turn in place and return the events."""
    events = []
    parsed = parse_all(state, orders, events)
    for name in state.rules["phases"]:
        PHASES[name](state, parsed, events)
    state.turn += 1
    start_turn(state, events)
    return events
