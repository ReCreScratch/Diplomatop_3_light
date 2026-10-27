"""Saving maps from the editor (API.md): name and content are checked before anything is written."""
import copy
import json
import re
import shutil
from pathlib import Path

import engine

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
MAX_BYTES = 4_000_000   # technical cap for a map or theme sent by the editor


def check_name(name):
    """A map folder name: letters, digits, - and _ only (no paths, no dots)."""
    return isinstance(name, str) and bool(NAME_RE.match(name))


def validate(map_data):
    """The engine's own map check on a copy. Returns an error text or None."""
    try:
        if len(json.dumps(map_data)) > MAX_BYTES:
            return "Karte ist zu groß."
        engine.validate_map(copy.deepcopy(map_data))
    except engine.MapError as err:
        return str(err)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as err:
        return f"Karte ungültig: {err!r}"
    return None


def write_json(path, data):
    """Write a JSON file atomically (UTF-8, readable)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def save_map(maps_dir, name, map_data, theme=None, theme_from=None):
    """Validate and write maps/{name}/map.json (and theme.json). Returns an error text or None.
    A new map without a theme takes the theme of `theme_from` (an existing map)."""
    maps_dir = Path(maps_dir).resolve()
    if not check_name(name):
        return "Ungültiger Kartenname (nur Buchstaben, Ziffern, - und _)."
    if not isinstance(map_data, dict):
        return "Karte fehlt."
    error = validate(map_data)
    if error:
        return error
    if theme is not None and (not isinstance(theme, dict) or len(json.dumps(theme)) > MAX_BYTES):
        return "Theme ungültig."
    folder = maps_dir / name
    if folder.resolve().parent != maps_dir:
        return "Ungültiger Kartenname."
    folder.mkdir(exist_ok=True)
    write_json(folder / "map.json", map_data)
    if theme is not None:
        write_json(folder / "theme.json", theme)
    elif not (folder / "theme.json").exists() and check_name(theme_from) and (maps_dir / theme_from / "theme.json").exists():
        shutil.copyfile(maps_dir / theme_from / "theme.json", folder / "theme.json")
    return None
