"""Recruitment phase: recruiting and disbanding."""
from ..orders import run_phase_orders

PHASE = "recruitment"


def run(state, parsed, events):
    """Run all recruit / disband orders."""
    run_phase_orders(state, parsed, PHASE, events)
