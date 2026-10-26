# Diplomatio 3.0 – Interface contract (milestone 1)

Binding contract between `engine/`, `server/` and `client/`. Rules: [RULES.md](RULES.md). Plan: [IMPLEMENTATION.md](IMPLEMENTATION.md).
Coordinates are always `[c, r]` lists in JSON. Neighbours (flat-top, odd columns raised half a field):
odd c → `(c,r-1),(c,r+1),(c-1,r-1),(c-1,r),(c+1,r-1),(c+1,r)`; even c → `(c,r-1),(c,r+1),(c-1,r),(c-1,r+1),(c+1,r),(c+1,r+1)`.

## 1. Conventions
- **Player id = nation code** (`"GB"`, `"FR"` …). One player per nation. Nations nobody picked are **neutral**
  (their provinces get owner `null`).
- Passable for land armies in milestone 1: fields whose token is a province code. `~~`, `##`, `..`, `?XX` are not passable.
- Gold is an integer. Upkeep is rounded on the nation total (`upkeep_rounding`).
- Army ids are strings `"a1"`, `"a2"` … from `state.next_army_id`.

## 2. Engine API (`engine/__init__.py` exports these)
```python
load_map(folder: str | Path) -> dict            # parsed + validated map.json (raises MapError)
load_rules(map_rules: dict, overrides: dict) -> dict   # rules/default.json <- map "rules" <- lobby overrides
new_game(map_data, players: dict[str, str], rules: dict, seed: int) -> GameState
    # players: {nation: player_name}. Runs the start of turn 1 (income, upkeep, player order).
validate_orders(state, player_id, orders: list[dict]) -> list[list[str]]
    # one list of German error strings per order (empty = valid), checked in entry order against the
    # current state (gold total, recruit limit, ranges, paths, ownership …)
resolve_turn(state, orders: dict[str, list[dict]]) -> list[dict]
    # mutates state: phases from rules["phases"], then start of next turn. Returns events (section 5).
    # Invalid orders at resolution time are skipped with a "skipped" event, never raise.
preview_move(state, player_id, army_id, count, path) -> dict    # section 6
board(state) -> list[dict]                                      # section 7
GameState.to_dict() / GameState.from_dict(d)                    # JSON-safe, round-trips exactly
```

## 3. GameState (as dict)
```json
{
  "turn": 1, "seed": 123,
  "rules": {"...merged rules config..."},
  "map": {"...the loaded map dict (name, grid, nations, provinces)..."},
  "players": {"GB": {"name": "Felix", "gold": 20, "provinces_at_turn_start": 9}},
  "owners": {"GB1": "GB", "GB2": "GB", "XX3": null},
  "armies": {"a1": {"id": "a1", "owner": "GB", "field": [16, 3], "divisions": 5, "fresh": 0, "forced_march": false}},
  "next_army_id": 2,
  "player_order": ["FR", "GB"], "prev_player_order": [],
  "gifts": [{"province": "GB3", "from": "GB", "to": "FR", "turn": 4}]
}
```
`fresh` = divisions recruited this turn (cannot move unless `recruits_can_move_same_turn`); reset to 0 at turn start.

## 4. Orders (dicts, `type` is the registry key)
| type | fields | phase |
|---|---|---|
| `send_gold` | `to`, `amount` | transfers |
| `give_province` | `province`, `to` | transfers |
| `recruit` | `field`, `count` | recruitment |
| `disband` | `army`, `count` | recruitment |
| `forced_march` | `army`, `on` (bool) | movement (all toggles first, then moves) |
| `move` | `army`, `count`, `path` (list of fields, start field excluded) | movement |

Rule details beyond RULES.md (*[default]*):
- `recruit` on an own capital joins the own army there or creates a new army; on any field with an own army it joins it.
- `move` with `count` < movable divisions splits; the moving part is a new army that inherits forced march.
  Merging at the end of a move: the army already standing there keeps its id and its forced-march flag.
- Path: adjacent passable fields, length ≤ range (forced march state *after* this turn's toggle orders of the same army).
  Passing over own armies is fine (merge only at the end). Entering a field with an enemy army → fight, stop there.
- Conquest is attempted on the field where the move **ends** (path end or fight stop) if it is the capital of a
  province not owned by the mover. Capitals passed mid-path are not conquered. Failed conquest → army goes back to
  the field before the capital.
- Several `move` orders for the same army are allowed; their counts together must not exceed its movable divisions.
  Each one splits off its divisions (the last one taking the rest moves the army itself, keeping its id).
  Split-off armies cannot get further orders this turn.

## 5. Events (returned by `resolve_turn`, shown in the replay)
Each event: `{"kind": ..., "player": pid|null, "text": "German one-liner", ...extra}`. Kinds and extras:
`turn_start` (`player_order`), `income` (`amount`), `upkeep` (`amount`), `send_gold` (`to`, `amount`),
`give_province` (`province`, `to`), `recruit` (`field`, `count`, `army`), `disband` (`army`, `field`, `count`),
`forced_march` (`army`, `on`), `move` (`army`, `from`, `path`, `to`, `count`), `merge` (`army`, `into`, `field`),
`fight` (`field`, `attacker`, `defender`, `attacker_losses`, `defender_losses`, `winner`: pid|null),
`conquest` (`province`, `field`, `cost`, `old_owner`), `conquest_failed` (`province`, `field`, `cost`, `back_to`),
`skipped` (`order`, `reason`).
Income/upkeep events of the new turn start come last.

## 6. preview_move result
```json
{"valid": true, "errors": [], "end_field": [c, r],
 "fight": {"defender": "FR", "attacker_losses": 3, "defender_losses": 4, "winner": "GB"} | null,
 "conquest": {"province": "FR2", "cost": 4, "possible": true} | null,
 "text": "Kampf gegen Frankreich: du verlierst 3, sie verlieren 4. Eroberung kostet 4 Divisionen."}
```
Based on the current board (ignores other orders).

## 7. board rows
`{"player": "GB", "name": "Felix", "provinces": 9, "share": 0.14, "income": 22, "upkeep": 4, "armies": 2, "divisions": 7}`
`upkeep` = what the player would pay at the next turn start with the current armies.

## 8. HTTP API (`server/app.py`, FastAPI, JSON). Token = secret per player, passed as `?token=`.
| Method & path | Body → Response |
|---|---|
| `GET /api/maps` | → `["europa", ...]` (folders in `maps/`) |
| `POST /api/games` | `{map, rules?: {}}` → `{game_id, host_token}` |
| `GET /api/games/{gid}/lobby?token=` | → `{game_id, map, status: "lobby"/"running", nations: {code: name}, joined: {code: player_name}, me: code\|null, is_host: bool, host: code\|null, rules: {merged rules}}` (token optional) |
| `POST /api/games/{gid}/join` | `{name, nation, host_token?}` → `{token}`. Passing host_token marks this player as host. |
| `POST /api/games/{gid}/start?token=` | host only, ≥1 player → `{ok: true}` |
| `GET /api/games/{gid}/state?token=&since=N` | → `{changed: false}` if `version == N`, else the view below |
| `PUT /api/games/{gid}/orders?token=` | `{orders: [...]}` replaces own list → `{errors: [[...], ...]}` |
| `POST /api/games/{gid}/ready?token=` | `{ready: bool}` → `{ok: true}` |
| `POST /api/games/{gid}/preview?token=` | `{army, count, path, forced_march?}` (setting after pending toggle) → preview_move result |
| `POST /api/games/{gid}/chat?token=` | `{to: nation\|null, text, marks?: [{kind:"field", f:[c,r]} \| {kind:"arrow", path:[[c,r],...]}]}` → `{ok, message}`. `to: null` = public channel. Running game only. |

State view:
```json
{"changed": true, "version": 17, "status": "running", "me": "GB", "is_host": true,
 "turn": 3, "timer_remaining": null, "player_order": [...], "ready": {"GB": true, "FR": false},
 "players": {"GB": {"name": "Felix"}}, "my_gold": 12, "rules": {...},
 "map": {...}, "theme": {...theme.json...}, "owners": {...}, "armies": {...},
 "board": [...], "my_orders": [...], "order_errors": [[...]],
 "incoming": [{"type": "send_gold", "from": "FR", "amount": 5}],
 "last_turn": {"turn": 2, "events": [...]},
 "chat": [{"id": 4, "from": "FR", "to": null, "text": "Hallo", "marks": [{"kind": "field", "f": [3, 4]}], "turn": 2, "ts": 1760000000}]}
```
`chat` holds the public messages (`to: null`) plus private ones where the caller is sender or receiver, oldest first
(`id` increases per game). Other players' private messages are never sent. Chat limits (server/games.py):
`CHAT_MAX_LEN` 1000 characters, `CHAT_MAX_MARKS` 20 marks; text may be empty if there is at least one mark;
fields must lie inside the grid; `to` must be another joined player. Chat is stored in `saves/{gid}.json`
and bumps `version`.
`my_recruit_limit` (= `recruit_limit_per_province` × own provinces at turn start) is also in the view.
While `status == "lobby"`, `GET state` returns only `{changed, version, status}`; the client uses `/lobby` there.
Errors: HTTP 400 (bad input), 403 (wrong token / not host), 404 (unknown game), body `{"detail": "German text"}`.
`fresh` in armies counts only divisions recruited in earlier resolutions of this turn; the client adds pending
recruit orders itself.
`version` increases on every change (join, orders, ready, resolution). The client polls every 2 s with `since`.
`incoming` is empty in milestone 1 (other players' orders stay hidden; the client shows *own* sends/gifts in the
receiver's board row). Static files: `/` → `client/index.html`, `/client/*`, `/maps/*`.
Saves: `saves/{gid}.json` after every change (state + tokens + orders + ready), loaded on server start.
Run: `python -m uvicorn server.app:app --host 0.0.0.0 --port 8000`.
