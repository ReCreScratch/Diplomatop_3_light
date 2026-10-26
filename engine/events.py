"""Tiny helper to build event dicts."""


def make_event(kind, player, text, **extra):
    """{'kind', 'player', 'text', ...extra}"""
    return {"kind": kind, "player": player, "text": text, **extra}
