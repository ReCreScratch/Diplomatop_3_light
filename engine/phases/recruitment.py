"""Recruitment phase: recruiting and disbanding, then the AI nations recruit (RULES.md 8.2)."""
from ..ai import recruit
from ..orders import run_phase_orders

PHASE = "recruitment"


def run(state, parsed, events):
    """Run all recruit / disband orders, then the AI recruitment."""
    run_phase_orders(state, parsed, PHASE, events)
    recruit(state, events)
