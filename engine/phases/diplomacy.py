"""Diplomacy phase (first): do-not-attack toggles, alliances, sale offers. They take effect for the rest of this
resolution (G61). finish() runs after the last phase."""
from ..alliances import finish_leaves
from ..orders import run_phase_orders
from ..victory import check_victory

PHASE = "diplomacy"


def run(state, parsed, events):
    """Run all diplomacy orders: toggles, leaves, invitations, acceptances, offers (by priority, then player order)."""
    run_phase_orders(state, parsed, PHASE, events)


def finish(state, events):
    """End of the resolution, before the next turn starts: members who left are out, invitations and offers of
    earlier turns expire (they were valid for one turn only), then the victory check."""
    finish_leaves(state, events)
    state.invitations = [i for i in state.invitations if i["turn"] >= state.turn]
    state.offers = [o for o in state.offers if o["turn"] >= state.turn]
    check_victory(state, events)
