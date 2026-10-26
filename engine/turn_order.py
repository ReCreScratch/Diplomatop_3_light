"""Turn-order rules: registry name -> function(state, rng) -> list of player ids."""
import random

TURN_ORDER_RULES = {}


def register(name):
    """Decorator: add a rule under a name."""
    def wrap(func):
        TURN_ORDER_RULES[name] = func
        return func
    return wrap


def rng_for_turn(state):
    """Random generator derived only from seed and turn."""
    return random.Random(f"{state.seed}:{state.turn}")


def shuffled(players, rng):
    """Random order of a sorted copy (sorting keeps it independent of dict order)."""
    order = sorted(players)
    rng.shuffle(order)
    return order


@register("no_repeat_first_last")
def no_repeat_first_last(state, rng):
    """Random; nobody first or last twice in a row. If impossible, no restriction."""
    prev = state.prev_player_order
    prev_first = prev[0] if prev else None
    prev_last = prev[-1] if prev else None
    for first in shuffled([p for p in state.players if p != prev_first], rng):
        rest = [p for p in state.players if p != first]
        lasts = [p for p in rest if p != prev_last]
        if lasts:
            last = rng.choice(sorted(lasts))
            middle = shuffled([p for p in rest if p != last], rng)
            return [first] + middle + [last]
    return shuffled(state.players, rng)


def draw_order(state):
    """Player order for the current turn by the configured rule."""
    rule = TURN_ORDER_RULES[state.rules["turn_order_rule"]]
    return rule(state, rng_for_turn(state))
