"""Order types. Each is a small class with validate / reserve / apply, registered by its type name.

validate(state, player, pending) -> list of German error strings (empty = ok).
reserve(state, pending) notes a valid order's effect so later orders in the same list see it.
apply(state, player, events) executes the order during resolution.
"""
import copy

from .events import make_event
from .hexgrid import is_adjacent

ORDER_TYPES = {}


def register(cls):
    """Class decorator: add an order class under cls.type."""
    ORDER_TYPES[cls.type] = cls
    return cls


class Pending:
    """What the orders entered so far (in one list) already use up."""

    def __init__(self):
        self.spent = 0          # gold for recruits and sent gold
        self.recruited = 0      # divisions ordered
        self.moved = {}         # army id -> divisions already ordered to move
        self.toggles = {}       # army id -> forced march after this turn's toggle orders
        self.given = set()      # provinces already offered as gift
        self.links = {}         # unit id -> linked unit id (or None) after this turn's link / unlink orders
        self.invited = set()    # players already invited in this list
        self.accepted = False   # an invitation is already accepted in this list
        self.bought = set()     # provinces already bought in this list


def is_int(value):
    """int but not bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_field(value):
    """[c, r] with two ints."""
    return isinstance(value, (list, tuple)) and len(value) == len(("c", "r")) and all(is_int(v) for v in value)


CHECKS = {
    "int": is_int,
    "str": lambda v: isinstance(v, str),
    "bool": lambda v: isinstance(v, bool),
    "field": is_field,
    "path": lambda v: isinstance(v, list) and all(is_field(s) for s in v),
}


def plural(count, one, many):
    """'1 Division' / '3 Divisionen'."""
    return f"{count} {one if count == 1 else many}"


class Order:
    """Base class. Subclasses set type, phase, priority and fields."""
    type = ""
    phase = ""
    priority = 0
    fields = {}  # field name -> key of CHECKS

    def __init__(self, data):
        self.data = data

    def shape_errors(self):
        """Missing or wrongly typed fields."""
        for name, kind in self.fields.items():
            if name not in self.data or not CHECKS[kind](self.data[name]):
                return ["Ungültiger Befehl."]
        return []

    def prepare(self, state, player, pending):
        """Optional look-ahead before validation of a whole list."""

    def validate(self, state, player, pending):
        return self.shape_errors()

    def reserve(self, state, pending):
        """Note effects on pending."""

    def resolution_errors(self, state, player):
        """Check again at resolution time against the then-current state."""
        return self.validate(state, player, Pending())

    def apply(self, state, player, events):
        raise NotImplementedError


def gold_errors(state, player, pending, amount):
    """Gold check: amount + already reserved <= current gold, unless debt spending is allowed."""
    if state.rules["allow_spending_into_debt"]:
        return []
    if amount + pending.spent > state.players[player]["gold"]:
        return ["Nicht genug Gold."]
    return []


def own_army(state, player, army_id):
    """The army if it exists and belongs to player."""
    army = state.armies.get(army_id)
    return army if army and army["owner"] == player else None


def limit_errors(state, player, pending, count, cost):
    """Recruit limit (divisions and ships together) and gold."""
    limit = state.rules["recruit_limit_per_province"] * state.players[player]["provinces_at_turn_start"]
    fresh = sum(a["fresh"] for a in state.armies.values() if a["owner"] == player)
    if fresh + pending.recruited + count > limit:
        return ["Rekrutierungslimit überschritten."]
    return gold_errors(state, player, pending, cost)


def own_city(state, player, field):
    """The field is the city (capital) of a province the player owns."""
    code = state.is_capital(field)
    return bool(code) and state.owners[code] == player


@register
class SendGold(Order):
    type = "send_gold"
    phase = "gold"
    fields = {"to": "str", "amount": "int"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        to, amount = self.data["to"], self.data["amount"]
        if to not in state.players or to == player:
            return ["Ungültiger Empfänger."]
        if amount <= 0:
            return ["Betrag muss positiv sein."]
        return gold_errors(state, player, pending, amount)

    def reserve(self, state, pending):
        pending.spent += self.data["amount"]

    def apply(self, state, player, events):
        to, amount = self.data["to"], self.data["amount"]
        state.players[player]["gold"] -= amount
        state.players[to]["gold"] += amount
        events.append(make_event("send_gold", player,
                                 f"{state.nation_name(player)} sendet {amount} Gold an {state.nation_name(to)}.",
                                 to=to, amount=amount))


@register
class GiveProvince(Order):
    type = "give_province"
    phase = "gold"
    fields = {"province": "str", "to": "str"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        code, to = self.data["province"], self.data["to"]
        if state.owners.get(code) != player:
            return ["Provinz gehört dir nicht."]
        if to not in state.players or to == player:
            return ["Ungültiger Empfänger."]
        if code in pending.given:
            return ["Provinz wird schon verschenkt."]
        return []

    def reserve(self, state, pending):
        pending.given.add(self.data["province"])

    def apply(self, state, player, events):
        code, to = self.data["province"], self.data["to"]
        state.owners[code] = to
        state.gifts.append({"province": code, "from": player, "to": to, "turn": state.turn})
        name = state.map["provinces"][code]["name"]
        events.append(make_event("give_province", player,
                                 f"{state.nation_name(player)} schenkt {name} an {state.nation_name(to)}.",
                                 province=code, to=to))


@register
class Recruit(Order):
    type = "recruit"
    phase = "recruitment"
    fields = {"field": "field", "count": "int"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        field, count = self.data["field"], self.data["count"]
        if count <= 0:
            return ["Anzahl muss positiv sein."]
        if state.hostile_army_at(field, player):
            return ["Feld ist vom Feind besetzt."]
        if state.blockers_at(field, player):
            return ["Feld ist von fremden Truppen besetzt."]
        if not own_city(state, player, field):
            return ["Rekrutieren geht nur in eigenen Städten."]
        return limit_errors(state, player, pending, count, count * state.rules["division_cost"])

    def reserve(self, state, pending):
        pending.spent += self.data["count"] * state.rules["division_cost"]
        pending.recruited += self.data["count"]

    def apply(self, state, player, events):
        field, count = self.data["field"], self.data["count"]
        state.players[player]["gold"] -= count * state.rules["division_cost"]
        army = state.own_army_at(field, player)
        if army:
            army["divisions"] += count
            army["fresh"] += count
        else:
            army = state.new_army(player, field, count, fresh=count)
        events.append(make_event("recruit", player,
                                 f"{state.nation_name(player)} rekrutiert {plural(count, 'Division', 'Divisionen')} "
                                 f"in {state.place_name(field)}.",
                                 field=list(field), count=count, army=army["id"]))


@register
class BuildShip(Order):
    type = "build_ship"
    phase = "recruitment"
    fields = {"field": "field", "count": "int"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        field, count = self.data["field"], self.data["count"]
        if count <= 0:
            return ["Anzahl muss positiv sein."]
        if not state.next_to_own_port(field, player):
            return ["Schiffe werden auf einem Seefeld neben einem eigenen Hafen gebaut."]
        if state.hostile_units_at(field, player):
            return ["Feld ist vom Feind besetzt."]
        if state.blockers_at(field, player):
            return ["Feld ist von fremden Truppen besetzt."]
        return limit_errors(state, player, pending, count, count * state.rules["ship_cost"])

    def reserve(self, state, pending):
        pending.spent += self.data["count"] * state.rules["ship_cost"]
        pending.recruited += self.data["count"]

    def apply(self, state, player, events):
        field, count = self.data["field"], self.data["count"]
        unit = state.rules["sea_unit"]
        state.players[player]["gold"] -= count * state.rules["ship_cost"]
        fleet = state.own_army_at(field, player, unit)
        if fleet:
            fleet["divisions"] += count
            fleet["fresh"] += count
        else:
            fleet = state.new_army(player, field, count, fresh=count, unit=unit)
        events.append(make_event("build_ship", player,
                                 f"{state.nation_name(player)} baut {plural(count, 'Schiff', 'Schiffe')} "
                                 f"bei {state.place_name(field)}.",
                                 field=list(field), count=count, army=fleet["id"]))


@register
class Disband(Order):
    type = "disband"
    phase = "recruitment"
    fields = {"army": "str", "count": "int"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        army = own_army(state, player, self.data["army"])
        if not army:
            return ["Armee gehört dir nicht."]
        if not 0 < self.data["count"] <= army["divisions"]:
            return ["Ungültige Divisionenzahl."]
        if state.is_fleet(army):
            if not state.next_to_own_port(army["field"], player):
                return ["Schiffe werden nur neben einem eigenen Hafen abgerüstet."]
        elif not own_city(state, player, army["field"]):
            return ["Abrüsten geht nur in eigenen Städten."]
        return []

    def apply(self, state, player, events):
        army, count = state.armies[self.data["army"]], self.data["count"]
        field = list(army["field"])
        fleet = state.is_fleet(army)
        state.players[player]["gold"] += count * state.rules["ship_disband_refund" if fleet else "disband_refund"]
        state.lose_divisions(army, count)
        what = plural(count, "Schiff", "Schiffe") if fleet else plural(count, "Division", "Divisionen")
        events.append(make_event("disband", player,
                                 f"{state.nation_name(player)} löst {what} "
                                 f"bei {state.place_name(field)} auf.",
                                 army=army["id"], field=field, count=count))


@register
class ForcedMarch(Order):
    type = "forced_march"
    phase = "movement"
    priority = 0
    fields = {"army": "str", "on": "bool"}

    def prepare(self, state, player, pending):
        if not self.shape_errors() and own_army(state, player, self.data["army"]):
            pending.toggles[self.data["army"]] = self.data["on"]

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        army = own_army(state, player, self.data["army"])
        if not army:
            return ["Armee gehört dir nicht."]
        if state.is_fleet(army):
            return ["Flotten haben keinen Gewaltmarsch."]
        return []

    def apply(self, state, player, events):
        army, on = state.armies[self.data["army"]], self.data["on"]
        army["forced_march"] = on
        what = "marschiert im Gewaltmarsch" if on else "beendet den Gewaltmarsch"
        events.append(make_event("forced_march", player,
                                 f"{state.nation_name(player)}: Armee {army['id']} {what}.",
                                 army=army["id"], on=on))


def range_of(state, army, forced=None):
    """Fields per turn; forced = forced-march setting to assume (None = the army's current one)."""
    on = army["forced_march"] if forced is None else forced
    return state.rules["forced_march_range" if on else "move_range"]


def turn_range(state, army, forced=None, group=False):
    """Fields per turn for this unit where it stands: fleet, linked pair, transport at sea, or army on land."""
    rules = state.rules
    if group:
        return rules["fleet_linked_move_range"]
    if state.is_fleet(army):
        return rules["fleet_move_range"]
    if state.at_sea(army):
        return rules["transport_move_range"]
    return range_of(state, army, forced)


def this_turn(state, army, path, forced=None, group=False):
    """Number of path steps done this turn: the range, and putting to sea or landing ends the move (G34)."""
    count = 0
    here = state.terrain_at(army["field"])
    for step in path[:turn_range(state, army, forced, group)]:
        count += 1
        if state.terrain_at(step) != here:
            break
    return count


def link_partner(state, army, pending=None):
    """The linked unit, as it will be after this turn's link / unlink orders (pending) or now."""
    if pending is not None and army["id"] in pending.links:
        return state.armies.get(pending.links[army["id"]])
    return state.partner(army)


def moves_as_group(state, army, path, partner):
    """A linked fleet and army move together; only an army that lands moves alone (and ends the link)."""
    if not partner or not path:
        return False
    return state.is_fleet(army) or state.terrain_at(path[0]) == "sea"


def path_errors(state, army, path, pending, group=False):
    """Adjacency and terrain of a path for this unit. The range limits the path only when standing
    marches are off; otherwise only this turn's part is executed and the rest becomes a route (G58).
    Armies put to sea only from an own port (RULES.md 10.2); fleets and linked pairs stay at sea."""
    on = pending.toggles.get(army["id"], army["forced_march"])
    if not path:
        return ["Pfad ist leer."]
    if this_turn(state, army, path, on, group) < len(path) and not state.rules.get("standing_marches"):
        return ["Reichweite überschritten."]
    sea_only = group or state.is_fleet(army)
    current = army["field"]
    for step in path:
        if not is_adjacent(current, step):
            return ["Pfad ist nicht zusammenhängend."]
        terrain = state.terrain_at(step)
        if terrain is None or (sea_only and terrain != "sea"):
            return ["Feld ist nicht begehbar."]
        if terrain == "sea" and state.terrain_at(current) == "land" and not state.is_own_port(current, army["owner"]):
            return ["Ablegen geht nur von einem eigenen Hafen."]
        current = step
    return []


def group_errors(state, army, partner, pending=None, count=None):
    """A linked pair moves only as a whole and only without units built this turn."""
    moved = pending.moved if pending else {}
    if count is not None and count < army["divisions"]:
        return ["Verbundene Einheiten ziehen nur vollständig – erst trennen."]
    for unit in (army, partner):
        if state.movable(unit) < unit["divisions"] or moved.get(unit["id"]):
            return ["Verbundene Einheiten ziehen nur vollständig – erst trennen."]
    return []


@register
class Move(Order):
    type = "move"
    phase = "movement"
    priority = 1
    fields = {"army": "str", "count": "int", "path": "path"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        army = own_army(state, player, self.data["army"])
        if not army:
            return ["Armee gehört dir nicht."]
        if self.data["count"] <= 0:
            return ["Anzahl muss positiv sein."]
        if self.data["count"] > army["divisions"]:
            return [f"Armee hat nur {plural(army['divisions'], 'Division', 'Divisionen')}."]
        if state.movable(army) <= 0:
            return ["Neu rekrutierte Divisionen können nicht ziehen."]
        left = state.movable(army) - pending.moved.get(army["id"], 0)   # several moves split the army (G56)
        if left <= 0:
            return ["Alle Divisionen der Armee haben schon einen Zugbefehl."]
        if self.data["count"] > left:
            return [f"Nur noch {plural(left, 'Division kann', 'Divisionen können')} ziehen."]
        partner = link_partner(state, army, pending)
        group = moves_as_group(state, army, self.data["path"], partner)
        if group:
            errors = group_errors(state, army, partner, pending, self.data["count"])
            if errors:
                return errors
        return path_errors(state, army, self.data["path"], pending, group)

    def reserve(self, state, pending):
        army_id = self.data["army"]
        pending.moved[army_id] = pending.moved.get(army_id, 0) + self.data["count"]
        army = state.armies[army_id]
        partner = link_partner(state, army, pending)
        if moves_as_group(state, army, self.data["path"], partner):
            pending.moved[partner["id"]] = partner["divisions"]

    def resolution_errors(self, state, player):
        """Fewer divisions than ordered is fine: all remaining (movable) ones move."""
        army = own_army(state, player, self.data["army"])
        if not army:
            return ["Armee existiert nicht mehr."]
        if state.movable(army) <= 0:
            return ["Neu rekrutierte Divisionen können nicht ziehen."]
        partner = state.partner(army)
        group = moves_as_group(state, army, self.data["path"], partner)
        if group:
            errors = group_errors(state, army, partner)
            if errors:
                return errors
        return path_errors(state, army, self.data["path"], Pending(), group)

    def apply(self, state, player, events):
        from .phases.movement import execute_move  # late import: movement uses this module
        army = state.armies[self.data["army"]]
        path = self.data["path"]
        partner = state.partner(army)
        group = moves_as_group(state, army, path, partner)
        if partner and not group:
            state.unlink(army)   # the army lands: the link ends
        count = army["divisions"] if group else min(self.data["count"], state.movable(army))
        for unit in (army, partner if group else None):
            if unit:
                unit.pop("route", None)  # a new move order replaces a standing route
        here = this_turn(state, army, path, group=group)
        execute_move(state, army, count, path[:here], events, rest=path[here:], group=group)


class AutoMove(Order):
    """Internal (not registered, players cannot send it): the army's standing route continues."""
    type = "auto_move"
    phase = "movement"
    priority = Move.priority

    def __init__(self, army_id):
        super().__init__({"type": self.type, "army": army_id})

    def resolution_errors(self, state, player):
        army = own_army(state, player, self.data["army"])
        if not army or not army.get("route") or state.movable(army) <= 0:
            return []
        partner = state.partner(army)
        group = moves_as_group(state, army, army["route"], partner)
        errors = (group_errors(state, army, partner) if group else []) or \
            path_errors(state, army, army["route"], Pending(), group)
        if errors:
            army.pop("route")
        return errors

    def apply(self, state, player, events):
        from .phases.movement import execute_move
        army = own_army(state, player, self.data["army"])
        if not army or not army.get("route") or state.movable(army) <= 0:
            return
        route = army.pop("route")   # fresh divisions stay behind; the route goes with the moving part
        partner = state.partner(army)
        group = moves_as_group(state, army, route, partner)
        if partner and not group:
            state.unlink(army)
        here = this_turn(state, army, route, group=group)
        count = army["divisions"] if group else state.movable(army)
        execute_move(state, army, count, route[:here], events, rest=route[here:], auto=True, group=group)


@register
class Halt(Order):
    type = "halt"
    phase = "movement"
    priority = 0
    fields = {"army": "str"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        army = own_army(state, player, self.data["army"])
        if not army:
            return ["Armee gehört dir nicht."]
        if not army.get("route"):
            return ["Armee hat keinen Marschbefehl."]
        return []

    def apply(self, state, player, events):
        army = state.armies[self.data["army"]]
        army.pop("route", None)
        events.append(make_event("halt", player,
                                 f"{state.nation_name(player)}: Armee {army['id']} hält an und beendet den Marsch.",
                                 army=army["id"]))


@register
class Link(Order):
    type = "link"
    phase = "movement"
    priority = 0
    fields = {"fleet": "str", "army": "str"}

    def units(self, state, player):
        return own_army(state, player, self.data["fleet"]), own_army(state, player, self.data["army"])

    def prepare(self, state, player, pending):
        fleet, army = self.units(state, player) if not self.shape_errors() else (None, None)
        if fleet and army:
            for unit in (fleet, army):
                old = link_partner(state, unit, pending)
                if old:
                    pending.links[old["id"]] = None
            pending.links[fleet["id"]], pending.links[army["id"]] = army["id"], fleet["id"]

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        fleet, army = self.units(state, player)
        if not fleet or not army:
            return ["Einheit gehört dir nicht."]
        if not state.is_fleet(fleet) or state.is_fleet(army):
            return ["Verbinden geht nur zwischen einer Flotte und einer Armee."]
        if fleet["field"] != army["field"] or not state.at_sea(fleet):
            return ["Flotte und Armee müssen auf demselben Seefeld stehen."]
        return []

    def apply(self, state, player, events):
        fleet, army = self.units(state, player)
        state.link(fleet, army)
        events.append(make_event("link", player,
                                 f"{state.nation_name(player)}: Flotte {fleet['id']} und Armee {army['id']} "
                                 f"bei {state.place_name(fleet['field'])} verbunden.",
                                 fleet=fleet["id"], army=army["id"], field=list(fleet["field"])))


@register
class Unlink(Order):
    type = "unlink"
    phase = "movement"
    priority = 0
    fields = {"army": "str"}

    def prepare(self, state, player, pending):
        unit = own_army(state, player, self.data["army"]) if not self.shape_errors() else None
        partner = unit and link_partner(state, unit, pending)
        if partner:
            pending.links[unit["id"]] = pending.links[partner["id"]] = None

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        unit = own_army(state, player, self.data["army"])
        if not unit:
            return ["Einheit gehört dir nicht."]
        if not state.partner(unit):
            return ["Einheit ist nicht verbunden."]
        return []

    def apply(self, state, player, events):
        unit = state.armies[self.data["army"]]
        other = state.partner(unit)
        state.unlink(unit)
        events.append(make_event("unlink", player,
                                 f"{state.nation_name(player)}: Verbindung bei {state.place_name(unit['field'])} gelöst.",
                                 army=unit["id"], other=other["id"], field=list(unit["field"])))


def parse_order(data):
    """Order object for a dict, or None if the type is unknown."""
    cls = ORDER_TYPES.get(data.get("type")) if isinstance(data, dict) else None
    return cls(data) if cls else None


def skipped(state, player, data, reason):
    """The 'skipped' event."""
    return make_event("skipped", player, f"{state.nation_name(player)}: Befehl übersprungen ({reason})",
                      order=data, reason=reason)


def snapshot(state):
    """The board right now: armies and province owners (the replay's 'snap')."""
    armies = {i: {k: v for k, v in a.items() if k != "route"} for i, a in state.armies.items()}  # routes are secret
    return {"armies": copy.deepcopy(armies), "owners": dict(state.owners)}


def run_phase_orders(state, parsed, phase, events):
    """Run all orders of one phase: by priority, then players in player order, then entry order."""
    types = [cls for cls in ORDER_TYPES.values() if cls.phase == phase]
    for priority in sorted({cls.priority for cls in types}):
        for player in state.player_order:
            for order in parsed.get(player, []):
                if order.phase == phase and order.priority == priority:
                    first = len(events)
                    errors = order.resolution_errors(state, player)
                    if errors:
                        events.append(skipped(state, player, order.data, errors[0]))
                    else:
                        order.apply(state, player, events)
                    if len(events) > first:
                        events[-1]["snap"] = snapshot(state)  # board right after this order


from . import diplomacy_orders  # noqa: E402,F401  (registers the diplomacy orders; needs the classes above)
