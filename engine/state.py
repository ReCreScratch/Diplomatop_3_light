"""GameState: plain data (JSON-safe dicts) plus small lookup helpers."""
import copy

from .config import SEA_TOKEN
from .hexgrid import parse_grid, tup

PLAYER_KEYS = ("name", "gold", "provinces_at_turn_start")


class GameState:
    """Whole game. Armies are dicts {id, owner, field, divisions, fresh, forced_march}."""

    def __init__(self, turn, seed, rules, map, players, owners, armies, next_army_id,
                 player_order, prev_player_order, gifts):
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
        self.cells = parse_grid(map["grid"])  # derived, not saved

    # --- save / load -------------------------------------------------
    def to_dict(self):
        """JSON-safe copy of the state."""
        return copy.deepcopy({
            "turn": self.turn, "seed": self.seed, "rules": self.rules, "map": self.map,
            "players": self.players, "owners": self.owners, "armies": self.armies,
            "next_army_id": self.next_army_id, "player_order": self.player_order,
            "prev_player_order": self.prev_player_order, "gifts": self.gifts,
        })

    @classmethod
    def from_dict(cls, data):
        """Inverse of to_dict."""
        d = copy.deepcopy(data)
        return cls(d["turn"], d["seed"], d["rules"], d["map"], d["players"], d["owners"],
                   d["armies"], d["next_army_id"], d["player_order"], d["prev_player_order"], d["gifts"])

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

    # --- armies ------------------------------------------------------
    def army_at(self, field):
        """The army standing on a field (at most one per player, never two players)."""
        for army in self.armies.values():
            if tup(army["field"]) == tup(field):
                return army
        return None

    def own_army_at(self, field, player):
        """Army of player on field, or None."""
        army = self.army_at(field)
        return army if army and army["owner"] == player else None

    def enemy_army_at(self, field, player):
        """Army of another player on field, or None."""
        army = self.army_at(field)
        return army if army and army["owner"] != player else None

    def new_army(self, owner, field, divisions, fresh=0, forced_march=False):
        """Create an army with the next free id."""
        army_id = f"a{self.next_army_id}"
        self.next_army_id += 1
        self.armies[army_id] = {"id": army_id, "owner": owner, "field": list(field),
                                "divisions": divisions, "fresh": fresh, "forced_march": forced_march}
        return self.armies[army_id]

    def lose_divisions(self, army, count):
        """Remove divisions (fresh ones last); delete the army when empty."""
        army["divisions"] -= min(count, army["divisions"])
        army["fresh"] = min(army["fresh"], army["divisions"])
        if army["divisions"] <= 0:
            self.armies.pop(army["id"], None)

    def movable(self, army):
        """Divisions that may move this turn."""
        if self.rules["recruits_can_move_same_turn"]:
            return army["divisions"]
        return army["divisions"] - army["fresh"]

    def unit_type(self, army):
        """Unit type data of an army (only land divisions so far)."""
        return self.rules["unit_types"][self.rules["land_unit"]]
