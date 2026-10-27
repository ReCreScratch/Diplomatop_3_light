"""AI ruleset (RULES.md 8.2): nations without a player and nations of surrendered or kicked players.
An AI nation recruits ai_recruit_per_city divisions in every own city each turn (free), never moves, is hostile to
everybody and builds no ships. Its units stay where they are. state.ai = {nation: {"reason", "name"}}."""
from .alliances import finish_leaves
from .events import make_event
from .orders import plural, snapshot


def make_ai(state, nation, reason, events):
    """Hand a player's nation to the AI: it leaves player order, alliances, pacts, invitations and offers. Its units
    stay (standing routes end) and its provinces keep their owner. reason: 'surrender' or 'kick'."""
    info = state.players.pop(nation)
    state.ai[nation] = {"reason": reason, "name": info["name"]}
    state.player_order = [p for p in state.player_order if p != nation]
    state.prev_player_order = [p for p in state.prev_player_order if p != nation]
    for army in state.armies.values():
        if army["owner"] == nation:
            army.pop("route", None)
    state.no_attack.pop(nation, None)
    for player, others in list(state.no_attack.items()):
        state.no_attack[player] = [p for p in others if p != nation]
    state.invitations = [i for i in state.invitations if nation not in (i["from"], i["to"])]
    state.offers = [o for o in state.offers if nation not in (o["from"], o["to"])]
    state.leaving = [nation]
    finish_leaves(state, events)   # leaves the alliance now; an alliance of two is dissolved
    name = state.nation_name(nation)
    text = (f"{info['name']} ({name}) hat aufgegeben. Die Nation folgt nun der KI." if reason == "surrender"
            else f"{info['name']} ({name}) wurde vom Spielleiter entfernt. Die Nation folgt nun der KI.")
    events.append(make_event(reason, nation, text))


def recruit(state, events):
    """Recruitment phase: every AI nation recruits in each of its cities, in a fixed order (sorted nations, map order)."""
    count = state.rules["ai_recruit_per_city"]
    if count <= 0:
        return
    for nation in sorted(state.ai):
        for code in state.provinces_of(nation):
            field = state.map["provinces"][code]["capital"]
            if state.hostile_units_at(field, nation):
                continue
            army = state.own_army_at(field, nation)
            if army:
                army["divisions"] += count
                army["fresh"] += count
            else:
                army = state.new_army(nation, field, count, fresh=count)
            events.append(make_event("recruit", nation,
                                     f"{state.nation_name(nation)} (KI) rekrutiert {plural(count, 'Division', 'Divisionen')} "
                                     f"in {state.place_name(field)}.", field=list(field), count=count, army=army["id"],
                                     cost=0, ai=True, snap=snapshot(state)))
