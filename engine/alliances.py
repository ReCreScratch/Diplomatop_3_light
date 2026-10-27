"""Alliance records: forming, joining, leaving. Rules in RULES.md 11.3; orders live in diplomacy_orders.py."""
from .events import make_event


def names(state, players):
    """'Aland', 'Aland und Bland', 'Aland, Bland und Cland'."""
    texts = [state.nation_name(p) for p in players]
    return texts[0] if len(texts) == 1 else ", ".join(texts[:-1]) + " und " + texts[-1]


def has_room(state, player):
    """The player may take one more member into their alliance (or found one)."""
    alliance = state.alliance_of(player)
    return len(alliance["members"]) < state.rules["max_alliance_size"] if alliance else state.rules["max_alliance_size"] >= 2


def accept_invitation(state, inviter, player, events):
    """player joins the inviter's alliance, or both found a new one. Their other open invitations are void."""
    alliance = state.alliance_of(inviter)
    if alliance:
        old = list(alliance["members"])
        alliance["members"].append(player)
        alliance["since"] = state.turn
        text = f"{state.nation_name(player)} tritt dem Bündnis von {names(state, old)} bei."
    else:
        alliance = {"id": f"b{state.next_alliance_id}", "members": [inviter, player], "since": state.turn}
        state.next_alliance_id += 1
        state.alliances[alliance["id"]] = alliance
        text = f"{state.nation_name(inviter)} und {state.nation_name(player)} schließen ein Bündnis."
    state.invitations = [i for i in state.invitations if i["to"] != player]
    events.append(make_event("alliance", player, text, alliance=alliance["id"], members=list(alliance["members"])))


def finish_leaves(state, events):
    """End of the resolution: members who left are out now; an alliance with one member left is dissolved."""
    for player in state.leaving:
        alliance = state.alliance_of(player)
        if not alliance:
            continue
        alliance["members"].remove(player)
        alliance["since"] = state.turn
        if len(alliance["members"]) < 2:
            state.alliances.pop(alliance["id"])
            events.append(make_event("alliance_end", None, f"Das Bündnis von {names(state, alliance['members'] + [player])} "
                                                           f"ist aufgelöst.", alliance=alliance["id"]))
        else:
            events.append(make_event("alliance", player, f"Das Bündnis besteht nun aus {names(state, alliance['members'])}.",
                                     alliance=alliance["id"], members=list(alliance["members"])))
    state.leaving = []
