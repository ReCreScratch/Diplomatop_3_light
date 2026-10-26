"""Transfer phase: gold and province gifts."""
from ..orders import run_phase_orders

PHASE = "transfers"


def run(state, parsed, events):
    """Run all send_gold / give_province orders."""
    run_phase_orders(state, parsed, PHASE, events)
