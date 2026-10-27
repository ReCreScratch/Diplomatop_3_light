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
        if path.name.endswith(".stats.json"):   # statistics cache, not a game
            continue
        try:
            games.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return games


# --- turn archive (milestone 5): saves/{gid}.history.jsonl, one JSON object per line, appended after every resolution ---
def history_path(gid, folder=None):
    return Path(folder or SAVES) / f"{gid}.history.jsonl"


def append_history(gid, row, folder=None):
    """Append one archive row. Append mode: a crash loses at most the line being written."""
    folder = Path(folder or SAVES)
    folder.mkdir(parents=True, exist_ok=True)
    with history_path(gid, folder).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_history(gid, folder=None):
    """All archive rows of a game, oldest first. A broken line (crash while writing) is skipped. If a turn was archived
    twice (crash between archive and save, then replayed), the last copy wins; the final row stays last."""
    path = history_path(gid, folder)
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    final = [r for r in rows if r.get("final")][-1:]
    turns = {}
    for r in rows:
        if not r.get("final"):
            turns[r.get("turn")] = r
    return sorted(turns.values(), key=lambda r: r.get("turn") or 0) + final


def stats_cache_path(gid, folder=None):
    return Path(folder or SAVES) / f"{gid}.stats.json"


def load_stats_cache(gid, folder=None):
    try:
        return json.loads(stats_cache_path(gid, folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_stats_cache(gid, data, folder=None):
    folder = Path(folder or SAVES)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f"{gid}.stats.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(stats_cache_path(gid, folder))
