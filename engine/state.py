"""GameState: plain data (JSON-safe dicts) plus small lookup helpers."""
import copy

from .config import SEA_TOKEN, fill_defaults
from .hexgrid import is_adjacent, parse_grid, tup

PLAYER_KEYS = ("name", "gold", "provinces_at_turn_start")


class GameState:
    """Whole game. Units ("armies") are dicts {id, owner, field, divisions, fresh, forced_march, unit, [linked], [route]}.
    unit is a key of rules['unit_types'] (division or ship); for a fleet, 'divisions' counts its ships."""

    def __init__(self, turn, seed, rules, map, players, owners, armies, next_army_id,
                 player_order, prev_player_order, gifts, diplomacy=None):
        self.turn = turn
        self.seed = seed
        self.rules = rules
        self.map = map
        self.players = players
        self.owners = owners
        self.armies = armies
        self.next_army_id = next_army_id
        self.player_order = player_order
        self.prev_player_order = prev_player_order
        self.gifts = gifts
        d = diplomacy or {}   # milestone 3 state; saves from before it have none of these keys
        self.alliances = d.get("alliances", {})          # id -> {id, members, since}
        self.next_alliance_id = d.get("next_alliance_id", 1)
        self.no_attack = d.get("no_attack", {})          # player -> [players he will not attack]
        self.invitations = d.get("invitations", [])      # [{from, to, turn}], valid in the turn after `turn`
        self.offers = d.get("offers", [])                # [{province, from, to, price, turn}], same
        self.victory = d.get("victory")                  # running candidate {kind, id, players, turns} or None
        self.winner = d.get("winner")                    # {players, alliance, turn} once the game is won
        self.leaving = []                                # members who leave at the end of this resolution (transient)
        self.cells = parse_grid(map["grid"])  # derived, not saved
        self.ports = {tup(f): code for code, p in map["provinces"].items() for f in p.get("ports", [])}

    # --- save / load -------------------------------------------------
    def to_dict(self):
        """JSON-safe copy of the state."""
        return copy.deepcopy({
            "turn": self.turn, "seed": self.seed, "rules": self.rules, "map": self.map,
            "players": self.players, "owners": self.owners, "armies": self.armies,
            "next_army_id": self.next_army_id, "player_order": self.player_order,
            "prev_player_order": self.prev_player_order, "gifts": self.gifts,
            "alliances": self.alliances, "next_alliance_id": self.next_alliance_id, "no_attack": self.no_attack,
            "invitations": self.invitations, "offers": self.offers, "victory": self.victory, "winner": self.winner,
        })

    @classmethod
    def from_dict(cls, data):
        """Inverse of to_dict."""
        d = copy.deepcopy(data)
        old = "alliances" not in d   # a save from before milestone 3 gets the new settings and the diplomacy phase
        rules = fill_defaults(d["rules"], diplomacy_phase=old)
        return cls(d["turn"], d["seed"], rules, d["map"], d["players"], d["owners"],
                   d["armies"], d["next_army_id"], d["player_order"], d["prev_player_order"], d["gifts"], d)

    # --- map lookups -------------------------------------------------
    def province_at(self, field):
        """Province code of a field, or None (sea, blocked, outside)."""
        token = self.cells.get(tup(field))
        return token if token in self.map["provinces"] else None

    def terrain_at(self, field):
        """'land', 'sea' or None (not playable)."""
        token = self.cells.get(tup(field))
        if token in self.map["provinces"]:
            return "land"
        return "sea" if token == SEA_TOKEN else None

    def is_capital(self, field):
        """Province code if the field is a capital, else None."""
        code = self.province_at(field)
        if code and tup(self.map["provinces"][code]["capital"]) == tup(field):
            return code
        return None

    def is_own_port(self, field, player):
        """The field is a port of a province the player owns."""
        code = self.ports.get(tup(field))
        return bool(code) and self.owners[code] == player

    def next_to_own_port(self, field, player):
        """A sea field next to a port of the player."""
        return self.terrain_at(field) == "sea" and any(
            is_adjacent(field, port) and self.owners[code] == player for port, code in self.ports.items())

    def provinces_of(self, player):
        """Province codes owned by player."""
        return [code for code, owner in self.owners.items() if owner == player]

    # --- naming for event texts -------------------------------------
    def nation_name(self, player):
        """German nation name, 'Niemand' for neutral."""
        if player is None:
            return "Niemand"
        return self.map["nations"][player]["name"]

    def place_name(self, field):
        """Capital name for a capital, else province name, else 'Feld c/r'."""
        code = self.province_at(field)
        if code is None:
            return f"Feld {field[0]}/{field[1]}"
        prov = self.map["provinces"][code]
        return prov["capital_name"] if self.is_capital(field) else prov["name"]

    # --- units -------------------------------------------------------
    def units_at(self, field):
        """All units on a field, fleets first. Land: at most one army. Sea: one fleet and one army per player
        (allies may share a sea field)."""
        units = [a for a in self.armies.values() if tup(a["field"]) == tup(field)]
        return sorted(units, key=lambda a: not self.is_fleet(a))

    def army_at(self, field):
        """The first unit on a field, or None."""
        units = self.units_at(field)
        return units[0] if units else None

    def own_army_at(self, field, player, unit=None):
        """Unit of player of the given type (default: land unit) on field, or None."""
        unit = unit or self.rules["land_unit"]
        for army in self.units_at(field):
            if army["owner"] == player and self.unit_of(army) == unit:
                return army
        return None

    # --- diplomacy ---------------------------------------------------
    def alliance_of(self, player):
        """The alliance record the player is a member of, or None."""
        return next((a for a in self.alliances.values() if player in a["members"]), None)

    def allied(self, a, b):
        """Two different players in the same alliance."""
        alliance = self.alliance_of(a) if a != b and a is not None and b is not None else None
        return bool(alliance) and b in alliance["members"]

    def hostile(self, a, b):
        """Units and cities of a and b are enemies (RULES.md 11.1): not the same player, not allied and not
        both on 'do not attack'. None (neutral / AI province owner) is hostile to everyone."""
        if a is None or b is None:
            return True
        if a == b or self.allied(a, b):
            return False
        return not (b in self.no_attack.get(a, ()) and a in self.no_attack.get(b, ()))

    def hostile_units_at(self, field, player):
        """Units on field that player's units must fight, fleets first."""
        return [a for a in self.units_at(field) if self.hostile(player, a["owner"])]

    def hostile_army_at(self, field, player):
        """First hostile unit on field, or None."""
        units = self.hostile_units_at(field, player)
        return units[0] if units else None

    def blockers_at(self, field, player):
        """Units of other, non-hostile players that stop player's units from ending a move on field
        (passing through is fine). Allies may share a sea field (RULES.md 11.1)."""
        sea = self.terrain_at(field) == "sea"
        return [a for a in self.units_at(field) if a["owner"] != player and not self.hostile(player, a["owner"])
                and not (sea and self.allied(player, a["owner"]))]

    def free_steps(self, player, path):
        """Length of the part of path (without the start field) that ends on a field player's units may end on."""
        count = len(path)
        while count and self.blockers_at(path[count - 1], player):
            count -= 1
        return count

    def new_army(self, owner, field, divisions, fresh=0, forced_march=False, unit=None):
        """Create a unit with the next free id."""
        army_id = f"a{self.next_army_id}"
        self.next_army_id += 1
        self.armies[army_id] = {"id": army_id, "owner": owner, "field": list(field), "divisions": divisions,
                                "fresh": fresh, "forced_march": forced_march, "unit": unit or self.rules["land_unit"]}
        return self.armies[army_id]

    def partner(self, army):
        """The unit linked to this one, or None."""
        return self.armies.get(army.get("linked"))

    def link(self, fleet, army):
        """Link a fleet and an army (older links of both end)."""
        self.unlink(fleet)
        self.unlink(army)
        fleet["linked"], army["linked"] = army["id"], fleet["id"]

    def unlink(self, army):
        """End the link of this unit and its partner."""
        other = self.partner(army)
        army.pop("linked", None)
        if other:
            other.pop("linked", None)

    def lose_divisions(self, army, count):
        """Remove divisions or ships (fresh ones last); delete the unit when empty."""
        army["divisions"] -= min(count, army["divisions"])
        army["fresh"] = min(army["fresh"], army["divisions"])
        if army["divisions"] <= 0:
            self.unlink(army)
            self.armies.pop(army["id"], None)

    def movable(self, army):
        """Divisions (ships) that may move this turn."""
        if self.rules["recruits_can_move_same_turn"]:
            return army["divisions"]
        return army["divisions"] - army["fresh"]

    def unit_of(self, army):
        """Unit type key of a unit (saves from before ships have none: land unit)."""
        return army.get("unit", self.rules["land_unit"])

    def unit_type(self, army):
        """Unit type data of a unit."""
        return self.rules["unit_types"][self.unit_of(army)]

    def is_fleet(self, army):
        """A unit that moves on sea only (ships)."""
        return self.unit_type(army)["terrain"] == "sea"

    def at_sea(self, army):
        """The unit stands on a sea field."""
        return self.terrain_at(army["field"]) == "sea"
