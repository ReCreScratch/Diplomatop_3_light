"""Rules config and map loading/validation. The only module that reads files."""
import copy
import json
import math
from fractions import Fraction
from pathlib import Path

from .hexgrid import neighbours, parse_grid, tup

RULES_FILE = Path(__file__).resolve().parent.parent / "rules" / "default.json"
SEA_TOKEN = "~~"


class MapError(Exception):
    """The map file is broken."""


# Rounding modes usable by the settings upkeep_rounding, strength_rounding and survivor_rounding.
ROUNDERS = {
    "none": lambda x: x,
    "half_up": lambda x: math.floor(x + Fraction(1, 2)),
    "up": math.ceil,
    "down": math.floor,
}


def exact(value):
    """Exact number from a setting, so 0.25 * 3 never has float noise."""
    return Fraction(str(value))


def round_by(mode, value):
    """Round a Fraction with one of the ROUNDERS ('none' keeps it exact)."""
    result = ROUNDERS[mode](value)
    return result if mode == "none" else int(result)


def as_number(value):
    """JSON-safe number for an exact value: int if whole, else float (gold may have decimals)."""
    value = Fraction(value)
    return int(value) if value.denominator == 1 else float(value)


def merge(base, extra):
    """Recursive dict merge: values of extra win."""
    result = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_rules(map_rules=None, overrides=None):
    """rules/default.json <- map 'rules' <- lobby overrides."""
    base = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    return merge(merge(base, map_rules), overrides)


def load_map(folder):
    """Read folder/map.json and validate it. Raises MapError."""
    path = Path(folder) / "map.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise MapError(f"Karte nicht lesbar: {err}")
    validate_map(data)
    return data


def validate_map(data):
    """Check grid, provinces, capitals, owners, start armies."""
    for key in ("grid", "nations", "provinces"):
        if key not in data:
            raise MapError(f"Eintrag fehlt: {key}")
    cells = parse_grid(data["grid"])
    fields = {}
    for field, token in cells.items():
        fields.setdefault(token, []).append(field)
    for token in fields:
        known = token in data["provinces"] or token == SEA_TOKEN
        if not known and token[:1] not in ("#", ".", "?"):
            raise MapError(f"Unbekanntes Feld-Token: {token}")
    for code, prov in data["provinces"].items():
        check_province(code, prov, fields, data["nations"])
        check_ports(code, prov, cells)
    for army in data.get("start_armies", []):
        check_start_army(army, cells, data)


def check_province(code, prov, fields, nations):
    """A province needs fields, one capital inside it and a known owner."""
    if code not in fields:
        raise MapError(f"Provinz {code} hat keine Felder")
    if tuple(prov["capital"]) not in fields[code]:
        raise MapError(f"Hauptstadt von {code} liegt nicht in der Provinz")
    if prov["owner"] is not None and prov["owner"] not in nations:
        raise MapError(f"Besitzer von {code} existiert nicht: {prov['owner']}")


def check_ports(code, prov, cells):
    """Ports: fields of the province with at least one sea neighbour."""
    for port in prov.get("ports", []):
        if cells.get(tup(port)) != code:
            raise MapError(f"Hafen von {code} liegt nicht in der Provinz")
        if not any(cells.get(n) == SEA_TOKEN for n in neighbours(*tup(port))):
            raise MapError(f"Hafen von {code} liegt nicht an der Küste")


def check_start_army(army, cells, data):
    """Start army: {'owner', 'field', 'divisions'}."""
    if army["owner"] not in data["nations"]:
        raise MapError(f"Startarmee: Nation unbekannt: {army['owner']}")
    token = cells.get(tup(army["field"]))
    if token not in data["provinces"]:
        raise MapError("Startarmee steht nicht auf einem Provinzfeld")
