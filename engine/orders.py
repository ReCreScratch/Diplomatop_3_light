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
        if state.enemy_army_at(field, player):
            return ["Feld ist vom Feind besetzt."]
        if not own_city(state, player, field):
            return ["Rekrutieren geht nur in eigenen Städten."]
        limit = state.rules["recruit_limit_per_province"] * state.players[player]["provinces_at_turn_start"]
        fresh = sum(a["fresh"] for a in state.armies.values() if a["owner"] == player)
        if fresh + pending.recruited + count > limit:
            return ["Rekrutierungslimit überschritten."]
        return gold_errors(state, player, pending, count * state.rules["division_cost"])

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
        if not own_city(state, player, army["field"]):
            return ["Abrüsten geht nur in eigenen Städten."]
        return []

    def apply(self, state, player, events):
        army, count = state.armies[self.data["army"]], self.data["count"]
        field = list(army["field"])
        state.players[player]["gold"] += count * state.rules["disband_refund"]
        state.lose_divisions(army, count)
        events.append(make_event("disband", player,
                                 f"{state.nation_name(player)} löst {plural(count, 'Division', 'Divisionen')} "
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
        if not own_army(state, player, self.data["army"]):
            return ["Armee gehört dir nicht."]
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


def path_errors(state, army, path, pending):
    """Adjacency and terrain of a path for this army. The range limits the path only when standing
    marches are off; otherwise only this turn's part is executed and the rest becomes a route (G58)."""
    on = pending.toggles.get(army["id"], army["forced_march"])
    if not path:
        return ["Pfad ist leer."]
    if len(path) > range_of(state, army, on) and not state.rules.get("standing_marches"):
        return ["Reichweite überschritten."]
    terrain = state.unit_type(army)["terrain"]
    current = army["field"]
    for step in path:
        if not is_adjacent(current, step):
            return ["Pfad ist nicht zusammenhängend."]
        if state.terrain_at(step) != terrain:
            return ["Feld ist nicht begehbar."]
        current = step
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
        return path_errors(state, army, self.data["path"], pending)

    def reserve(self, state, pending):
        army_id = self.data["army"]
        pending.moved[army_id] = pending.moved.get(army_id, 0) + self.data["count"]

    def resolution_errors(self, state, player):
        """Fewer divisions than ordered is fine: all remaining (movable) ones move."""
        army = own_army(state, player, self.data["army"])
        if not army:
            return ["Armee existiert nicht mehr."]
        if state.movable(army) <= 0:
            return ["Neu rekrutierte Divisionen können nicht ziehen."]
        return path_errors(state, army, self.data["path"], Pending())

    def apply(self, state, player, events):
        from .phases.movement import execute_move  # late import: movement uses this module
        army = state.armies[self.data["army"]]
        count = min(self.data["count"], state.movable(army))
        path = self.data["path"]
        army.pop("route", None)  # a new move order replaces a standing route
        here = range_of(state, army)
        execute_move(state, army, count, path[:here], events, rest=path[here:], goal=path[-1])


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
        errors = path_errors(state, army, army["route"], Pending())
        if errors:
            army.pop("route")
        return errors

    def apply(self, state, player, events):
        from .phases.movement import execute_move
        army = own_army(state, player, self.data["army"])
        if not army or not army.get("route") or state.movable(army) <= 0:
            return
        route = army.pop("route")   # fresh divisions stay behind; the route goes with the moving part
        here = range_of(state, army)
        execute_move(state, army, state.movable(army), route[:here], events, rest=route[here:],
                     goal=route[-1], auto=True)


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
