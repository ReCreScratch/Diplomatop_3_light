"""Shared helpers for the scenario tests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine  # noqa: E402

TEST_MAP = ROOT / "tests" / "maps" / "test"

# Fields of the test map: a chain along row 2, every step is one move.
A1_CAP, A1_MID, A2_CAP, N1_CAP, B1_CAP, B2_CAP, C1_CAP, C1_END = [[c, 2] for c in range(8)]
SEA = [0, 4]


@pytest.fixture
def map_data():
    return engine.load_map(TEST_MAP)


def make_game(players=("AA", "BB"), seed=1, **rule_overrides):
    """New game on the test map; players get the names 'p_<nation>'."""
    map_data = engine.load_map(TEST_MAP)
    rules = engine.load_rules(map_data.get("rules", {}), rule_overrides)
    state = engine.new_game(map_data, {n: "p_" + n for n in players}, rules, seed)
    state.player_order = list(players)
    return state


@pytest.fixture
def game():
    return make_game()


def put(state, owner, field, divisions, fresh=0, forced_march=False, unit=None):
    """Place an army (or with unit='ship' a fleet) directly."""
    return state.new_army(owner, field, divisions, fresh=fresh, forced_march=forced_march, unit=unit)


def kinds(events):
    return [e["kind"] for e in events]


def of_kind(events, kind):
    return [e for e in events if e["kind"] == kind]
