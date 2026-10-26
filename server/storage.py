"""Save / load games as saves/{gid}.json."""
import json
from pathlib import Path

SAVES = Path(__file__).resolve().parent.parent / "saves"


def save(gid, data, folder=None):
    folder = Path(folder or SAVES)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f"{gid}.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / f"{gid}.json")


def load_all(folder=None):
    """All saved games as dicts."""
    folder = Path(folder or SAVES)
    games = []
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            games.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return games
