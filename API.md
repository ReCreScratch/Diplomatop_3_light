# Diplomatio 3.0 – Interface contract (milestones 1–5)

Binding contract between `engine/`, `server/` and `client/`. Rules: [RULES.md](RULES.md). Plan: [IMPLEMENTATION.md](IMPLEMENTATION.md).
Coordinates are always `[c, r]` lists in JSON. Neighbours (flat-top, odd columns raised half a field):
odd c → `(c,r-1),(c,r+1),(c-1,r-1),(c-1,r),(c+1,r-1),(c+1,r)`; even c → `(c,r-1),(c,r+1),(c-1,r),(c-1,r+1),(c+1,r),(c+1,r+1)`.

## 1. Conventions
- **Player id = nation code** (`"GB"`, `"FR"` …). One player per nation. Nations nobody picked are **AI nations**
  (milestone 4, see `ai` below) when the server starts a game; `engine.new_game` without `ai=` keeps them **neutral**
  (provinces with owner `null`), and map provinces with owner `null` are always neutral.
- Passable for land armies in milestone 1: fields whose token is a province code. `~~`, `##`, `..`, `?XX` are not passable.
- Gold may have decimals (JSON int when whole, else float; computed exactly). Upkeep is rounded on the nation total
  only if `upkeep_rounding` is not `none` (default `none`).
- Army ids are strings `"a1"`, `"a2"` … from `state.next_army_id`.

## 2. Engine API (`engine/__init__.py` exports these)
```python
load_map(folder: str | Path) -> dict            # parsed + validated map.json (raises MapError)
load_rules(map_rules: dict, overrides: dict) -> dict   # rules/default.json <- map "rules" <- lobby overrides
new_game(map_data, players: dict[str, str], rules: dict, seed: int, ai=()) -> GameState
    # players: {nation: player_name}. ai: nations run by the AI ruleset (RULES.md 8.2; their provinces get the nation
    # as owner, their start armies are placed). Runs the start of turn 1 (player order). Income is paid in the gold phase.
    # A nation's `start_gold` in map["nations"] overrides rules["start_gold"].
make_ai(state, nation, reason: "surrender" | "kick", events: list) -> None
    # hands a player's nation to the AI ruleset: leaves players / player order / alliance / pacts / invitations / offers,
    # standing routes end, units and provinces stay. Appends the public event {"kind": reason, ...}.
validate_map(map_dict)                                          # engine's map check on a dict (raises MapError)
validate_orders(state, player_id, orders: list[dict]) -> list[list[str]]
    # one list of German error strings per order (empty = valid), checked in entry order against the
    # current state (gold total, recruit limit, ranges, paths, ownership …)
resolve_turn(state, orders: dict[str, list[dict]]) -> list[dict]
    # mutates state: phases from rules["phases"], then start of next turn. Returns events (section 5).
    # Invalid orders at resolution time are skipped with a "skipped" event, never raise.
preview_move(state, player_id, army_id, count, path) -> dict    # section 6
board(state) -> list[dict]                                      # section 7
compute_stats(map_data, rules, history, chat=None, meta=None) -> dict      # section 9
    # pure statistics from the game archive (server/ stores it, section 8); STATS_VERSION = int, bumped when the output changes
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
  "armies": {"a1": {"id": "a1", "owner": "GB", "field": [16, 3], "divisions": 5, "fresh": 0, "forced_march": false, "unit": "division"},
             "a2": {"id": "a2", "owner": "GB", "field": [15, 5], "divisions": 2, "fresh": 0, "forced_march": false, "unit": "ship", "linked": "a3"}},
  "next_army_id": 2,
  "player_order": ["FR", "GB"], "prev_player_order": [],
  "gifts": [{"province": "GB3", "from": "GB", "to": "FR", "turn": 4}],
  "alliances": {"b1": {"id": "b1", "members": ["GB", "FR"], "since": 7}}, "next_alliance_id": 2,
  "no_attack": {"GB": ["DE"]},
  "invitations": [{"from": "GB", "to": "IT", "turn": 7}],
  "offers": [{"province": "GB3", "from": "GB", "to": "FR", "price": 5, "turn": 7}],
  "victory": {"kind": "player", "id": "GB", "players": ["GB"], "turns": 2},
  "winner": null,
  "ai": {"FR": {"reason": "surrender", "name": "Anna"}}
}
```
Milestone 3 keys (old saves lack them and still load; `rules` gets the new settings and the diplomacy phase):
`alliances` = id -> {id, members, since}; `since` = turn of the last change of members. `no_attack` = player -> players he
does not attack (hostile only if not mutual, not allied). `invitations` / `offers` are valid in the turn after `turn`
(the turn they were made in) and are dropped at the end of the next resolution. `gifts` also records sales (`price`).
`victory` = the running candidate (`kind` "player" / "alliance", `turns` = resolutions held in a row) or null;
`winner` = `{players, alliance, turn}` once the game is won, then `resolve_turn` returns no events.
Milestone 4 key: `ai` = nation -> {`reason`: "unpicked" / "surrender" / "kick", `name`: former player name or null}. AI
nations are not in `players` (no gold, no orders, not in the player order) but keep their provinces and units. They never
move; each recruitment phase (after the players' orders) they recruit `ai_recruit_per_city` divisions in every own city
(`recruit` events with `"ai": true`). `state.hostile` is true between an AI nation and every other nation. AI nations hold
land fields but are never victory candidates. Old saves lack `ai` and load with `{}`.
`state.hostile(a, b)`: false for the same player, allies and mutual `no_attack`; true for `None` (neutral).
`fresh` = divisions recruited this turn (cannot move unless `recruits_can_move_same_turn`); reset to 0 at turn start.
`unit` = key of `rules.unit_types` (`division`, `ship`); a unit of ships is a fleet and `divisions` counts its ships.
`linked` = id of the linked fleet / army (both carry it). `route` = standing march (owner only).

## 4. Orders (dicts, `type` is the registry key)
| type | fields | phase |
|---|---|---|
| `send_gold` | `to`, `amount` | gold |
| `give_province` | `province`, `to` | gold |
| `recruit` | `field`, `count` | recruitment |
| `disband` | `army`, `count` | recruitment |
| `forced_march` | `army`, `on` (bool) | movement (all toggles first, then moves) |
| `halt` | `army` | movement (with the toggles, before moves): deletes the army's standing route |
| `move` | `army`, `count`, `path` (list of fields, start field excluded) | movement |
| `build_ship` | `field` (sea field next to an own port), `count` | recruitment |
| `link` | `fleet`, `army` (same sea field) | movement (with the toggles, before moves) |
| `unlink` | `army` (either unit of the pair) | movement (with the toggles, before moves) |
| `no_attack` | `to`, `on` (bool) | diplomacy (priority 0): standing toggle, effective at once |
| `leave` | – | diplomacy (1): leaves the alliance at the end of the resolution |
| `invite` | `to` | diplomacy (2): invitation valid in the next turn only (private, no event) |
| `accept` | `from` | diplomacy (3): accepts last turn's invitation; founds or joins an alliance (max `max_alliance_size`) |
| `offer_sale` | `province`, `to`, `price` (int > 0) | diplomacy (4): offer valid in the next turn only (private, no event) |
| `buy` | `province` | gold (after income / upkeep): accepts last turn's offer; gold checked like `send_gold`; skipped if the seller no longer owns it |

Rule details beyond RULES.md (*[default]*):
- Hostility (RULES.md 11.1): `move` fights and conquers only hostile units / cities. Fields with non-hostile foreign units
  can be passed but not ended on (allies may share a sea field): the move ends on the last free field of the walked
  part, or does nothing (event `move_blocked`). The unwalked fields stay in the route (`standing_marches`).
  `recruit` / `build_ship` there: "Feld ist von fremden Truppen besetzt.".
- `recruit` on an own capital joins the own army there or creates a new army. `build_ship` likewise joins the own fleet.
- A `move` of a linked unit moves both whole units (`count` must be all), unless an army lands: then it moves alone and
  the link ends. Events: `move` gets `with` (partner id); `fight` gets `losses` = {unit id: lost divisions/ships}.
- `move` with `count` < movable divisions splits; the moving part is a new army that inherits forced march.
  Merging at the end of a move: the army already standing there keeps its id and its forced-march flag.
- Path: adjacent passable fields (forced march state *after* this turn's toggle orders of the same army). With
  `standing_marches` (G58) the path may be longer than the range: only the first `range` fields run this turn and the
  rest is stored as `army.route` (list of fields; only in the owner's own army objects, never shown to others, never in
  `snap`/`before`). With the setting off, a longer path is the error "Reichweite überschritten.".
- Standing routes run automatically each turn in the owner's slot before their new orders (internal auto move, not an
  order type). A new `move` for the army or a `halt` replaces/clears the route; a fight, a conquest attempt or a merge
  ends it. Auto events are `move` events with `"auto": true` and text "… marschiert weiter: … (Ziel …)".
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
`give_province` (`province`, `to`), `recruit` (`field`, `count`, `army`, `cost`), `disband` (`army`, `field`, `count`, `refund`, `unit`),
`forced_march` (`army`, `on`), `move` (`army`, `from`, `path`, `to`, `count`, `unit`, `fleet`, `forced_march`, optional `auto`: true, optional `with` / `with_count` / `with_unit`), `halt` (`army`), `merge` (`army`, `into`, `field`),
`fight` (`field`, `attacker`, `defender`, `attacker_losses`, `defender_losses`, `winner`: pid|null, plus the raw record below),
`conquest` (`province`, `field`, `cost`, `old_owner`, `army`, `divisions`, `lost`), `conquest_failed` (`province`, `field`, `cost`, `back_to`, `army`, `divisions`, `lost`: 0),
`skipped` (`order`, `reason`). Milestone 3: `no_attack` (`to`, `on`, `mutual`), `alliance` (`alliance`, `members`; founded,
joined or changed), `leave` (`alliance`), `alliance_end` (`alliance`), `buy` (`province`, `to` = buyer, `seller`, `price`),
`move_blocked` (`army`, `field`, `count`), `victory_progress` (`players`, `turns`, `need`), `victory` (`players`, `alliance`).
Milestone 4: `surrender` and `kick` (`player` = the nation; only returned by `make_ai`, the server shows them as notices).
Diplomacy events come first (with snaps); `alliance`/`leave`-removal/`alliance_end`/`victory*` at the end of the
resolution have no snap. `invite` and `offer_sale` produce no event.
Income/upkeep events come at the start of the gold phase (after recruitment, before movement); `turn_start` comes last.
`fight.winner` is a player, `null` (both destroyed) or `"both"` (both survive, G59).
Milestone 5 added fields (raw data for the statistics, only ever added, nothing renamed):
- `build_ship` (`field`, `count`, `army`, `cost`) like `recruit`; `cost` = gold actually paid (AI recruits: `cost` 0, `ai` true).
  `disband.refund` = gold paid back, `disband.unit` = unit type key (`division` / `ship`).
- `move.path` = the fields actually walked (start excluded), `move.count` the moving part, `unit` its type key, `fleet` bool,
  `forced_march` the mover's flag; with a linked partner `with` (id), `with_count` and `with_unit` describe the partner, which
  moves along the same path. Division-fields marched = `count` x `len(path)`; per-field traffic uses the fields of `path`.
- `fight.sea` = the fight involves the sea; `fight.attacker_units` / `defender_units` = one record per unit before the fight:
  `{army, owner, unit, fleet, count, value, forced_march, transport, lost}` (`value` = combat value per division or ship that was
  used, `transport` = a land unit fighting at sea with the transport value, `lost` = divisions or ships lost); `attacker_damage` /
  `defender_damage` = total combat value of the side; `attacker_divisions_lost`, `attacker_ships_lost`, `defender_divisions_lost`,
  `defender_ships_lost` split the losses. `losses` (unit id -> lost) and the old fields are unchanged. Several defender units may
  belong to different (allied) owners; `defender` is the first one's owner.
- `conquest.lost` = divisions the conquest cost (= `cost`), `divisions` = the army's size before paying; `conquest_failed.lost` is 0.
**Snapshots:** after each order of the recruitment/gold/movement phases (applied or skipped) the *last* event that
order produced carries `"snap": {"armies": {id: {id, owner, field, divisions, fresh, forced_march}}, "owners": {province: owner}}`
= the whole board right after that order. So all events up to and including one with a `snap` form one group (a move with
its fight, conquest and merge). Unknown-order `skipped` events and the start-of-turn block have no snap.

## 6. preview_move result
```json
{"valid": true, "errors": [], "end_field": [c, r],
 "fight": {"defender": "FR", "attacker_losses": 3, "defender_losses": 4, "winner": "GB"} | null,
 "conquest": {"province": "FR2", "cost": 4, "possible": true} | null,
 "text": "Kampf gegen Frankreich: du verlierst 3, sie verlieren 4. Eroberung kostet 4 Divisionen."}
```
Based on the current board (ignores other orders).

## 7. board rows
`{"player": "GB", "name": "Felix", "provinces": 9, "fields": 40, "share": 0.14, "share_counted": 0.1, "alliance": "b1" | null, "income": 22, "upkeep": 1.75, "armies": 2, "divisions": 7, "ships": 0}`
– `share` = real share of all land fields, `share_counted` = the part that counts for victory (gifts / sales younger than
`gift_delay_turns` excluded, RULES.md section 11).
`upkeep` = what the player would pay at the next turn start with the current armies.
AI nations get a row too, with `"ai": true` and `name` = `"KI"` or `"KI (former player)"` (player rows have no `ai` key).

## 8. HTTP API (`server/app.py`, FastAPI, JSON). Token = secret per player, passed as `?token=`.
| Method & path | Body → Response |
|---|---|
| `GET /api/maps` | → `["europa", ...]` (folders in `maps/` with a `map.json`) |
| `GET /api/rules` | → the default rules (rules/default.json merged; the editor shows them as placeholders) |
| `PUT /api/maps/{name}` | editor: `{map: {...map.json...}, theme?: {...}, theme_from?: "europa"}` → `{ok, name}`. Name must match `[A-Za-z0-9][A-Za-z0-9_-]{0,39}` (no paths). The map is validated with the engine's `validate_map` (incl. income / names / start gold / `rules` keys) before anything is written; 400 with the German engine message otherwise. Writes `maps/{name}/map.json`; `theme.json` from `theme`, else copied from `theme_from` if the map has none. Overwrites an existing map of that name. |
| `POST /api/games` | `{map, rules?: {}}` → `{game_id, host_token}` |
| `GET /api/games/{gid}/lobby?token=` | → `{game_id, map, status: "lobby"/"running"/"finished", nations: {code: name}, joined: {code: player_name}, me: code\|null, me_name: str\|null (null = token unknown), is_host: bool, host: code\|null, players: [{id, name, nation: code\|null, host, you}] (join order), ai: [nation codes run by the AI, once started], nation_mode: "choose"/"random", reveal: null \| {elapsed, pause, entries: [{nation, name}]}, editable: [rule keys the host may set], rules: {merged rules}}` (token optional) |
| `POST /api/games/{gid}/join` | lobby only: `{name, nation?, host_token?}` → `{token}`. Name ≤ 30 characters, at most as many players as nations. The nation is optional (choose later / random draw). The first joiner passing the game's `host_token` becomes host. |
| `POST /api/games/{gid}/nation?token=` | lobby: `{nation: code\|null}` picks a free nation (null gives it back); 400 in random mode, if taken or unknown. Clears `reveal`. |
| `POST /api/games/{gid}/settings?token=` | lobby, host only: `{rules?: {key: number}, nation_mode?: "choose"/"random"}`. Allowed rule keys (`LOBBY_SETTINGS` in server/games.py): `turn_timer_seconds`, `start_gold`, `victory_hold_turns`, `max_alliance_size`, `alliance_min_turns`, `idle_warning_seconds`, `nation_reveal_pause_seconds`; values are non-negative numbers (integers where the rule is one). They go into the game's overrides. |
| `POST /api/games/{gid}/assign_random?token=` | lobby, host only: hands out all nations at random to all players and stores the reveal `{started, pause = nation_reveal_pause_seconds, order}`; clients show entry i after (i+1) × pause seconds. 400 if more players than nations. Any join / nation change / kick clears the reveal. |
| `POST /api/games/{gid}/start?token=` | host only, ≥1 player, every player has a nation, reveal over → `{ok: true}`. Nations nobody picked become AI nations. Creates each player's rejoin code. |
| `POST /api/games/{gid}/pause?token=` | running: `{paused: bool}`. Pause: needs a running timer; the host any time (unlimited), a player once per game (`pause_used`); 400 "Es ist schon pausiert." / "Du hast deine Pause schon benutzt." / "Es läuft kein Zugtimer.". Resume: host only (403 otherwise). While paused the timer is frozen and does not expire; resuming moves the deadline by the paused time; the pause carries over into the next turn. Public notice for both. |
| `POST /api/games/{gid}/surrender?token=` | running, active players: the nation becomes AI (`make_ai`), the token stays valid as a spectator; orders / ready of the nation are dropped; resolves the turn if all remaining players are ready; the last player leaving finishes the game (no winner). Public notice. |
| `POST /api/games/{gid}/kick?token=` | host only: `{nation}` (or `{member}` = lobby player id): lobby: the player is removed; running: the token becomes invalid, the nation becomes AI (`reason: "kick"`), requests of that nation are dropped. 400 for the host himself. Public notice. |
| `POST /api/games/{gid}/rejoin` | no token. `{nation}` → `{request_id}` (a rejoin request for the host; one per nation) or `{nation, code}` → `{token}` (the personal rejoin code gives a new token at once, the old one dies, the code is replaced; 403 "Falscher Code."; after 8 wrong codes per 60 s: 400). 400 if the game is not running or the nation is surrendered / kicked / AI. |
| `GET /api/games/{gid}/rejoin/{rid}` | the requester polls: `{status: "pending"}`, `{status: "declined"}` or `{status: "approved", token}` (delivered once, then the request is gone / 404). Requests older than 10 minutes are dropped when a new one is made. |
| `POST /api/games/{gid}/rejoin/{rid}/answer?token=` | host only: `{accept: bool}`. Accept: the nation's token is replaced by a new one (the old one is invalid at once; orders and ready state stay), public notice. |
| `GET /api/games/{gid}/state?token=&since=N` | → `{changed: false}` if `version == N`, else the view below |
| `PUT /api/games/{gid}/orders?token=` | `{orders: [...]}` replaces own list → `{errors: [[...], ...]}` |
| `POST /api/games/{gid}/ready?token=` | `{ready: bool}` → `{ok: true}` |
| `POST /api/games/{gid}/preview?token=` | `{army, count, path, forced_march?}` (setting after pending toggle) → preview_move result |
| `POST /api/games/{gid}/chat?token=` | `{to: nation\|null, text, marks?: [{kind:"field", f:[c,r]} \| {kind:"arrow", path:[[c,r],...]}]}` → `{ok, message}`. `to: null` = public channel. Running game only. |
| `GET /api/games/{gid}/stats?token=` | **finished games only** (else 400 "Die Statistik gibt es erst am Spielende."): `compute_stats` of the archive and the game's chat, plus `nations` = {code: {name, player}}, `map` (name) and `video_seconds_per_turn`. The token is optional; a given token must belong to a member or spectator (403 otherwise). Cached in `saves/{gid}.stats.json` as `{key: {version, rows, chat}, result}`; a different `STATS_VERSION`, archive length or chat length recomputes it. |
| `GET /api/tunnel` | → `{local: bool, available?, running?, url}`. Optional Cloudflare Quick Tunnel (`server/tunnel.py`, child process `cloudflared tunnel --url http://localhost:{port}`). `local` = the request comes from a browser on the host PC itself: Host header `localhost` / `127.0.0.1` / `[::1]`, loopback client IP, no `cf-connecting-ip` / `cf-ray` / `x-forwarded-for` header, no foreign `Origin` (a loopback IP alone is not enough: cloudflared connects from 127.0.0.1 too). Non-local callers get only `{local: false, url}`. `available` = cloudflared found (PATH, winget / Program Files folders; looked up on every call). |
| `POST /api/tunnel/start` | local only (else 403 "Das darf nur der Spielleiter am eigenen PC."): starts the tunnel on the port of the request and waits up to 30 s for the public `https://….trycloudflare.com` URL → `{local: true, available, running, url}`; already running: returns the existing one. 400 with German text if cloudflared is missing, exits or times out. |
| `POST /api/tunnel/stop` | local only (403 otherwise): terminates cloudflared → status as above. The tunnel is also stopped when the server shuts down. |
| `GET /api/games/{gid}/history?token=` | finished games only (same rules): the raw archive rows as a JSON list (see below). A game without an archive gives `[]`. |

Archive (milestone 5, RULES.md 12 "Recording"): `saves/{gid}.history.jsonl`, one JSON object per line, appended (append mode) at the end
of every `resolve_turn` before the next turn starts. Turn rows:
```json
{"turn": 3, "player_order": ["FR", "GB"], "before": {"armies": {}, "owners": {}},
 "gold_before": {"GB": 12}, "gold_after": {"GB": 9.5}, "orders": {"GB": [{"type": "recruit", "field": [16, 3], "count": 1}]},
 "events": [], "alliances": {}, "no_attack": {}, "ai": {}, "timeouts": ["FR"], "ready_at": {"GB": 41.2, "FR": null},
 "started": 1760000000.1, "resolved": 1760000060.4}
```
`before` = the board at the start of the turn (as `last_turn.before`); `orders` = the raw submitted orders of every player (valid or not);
`events` = all events of the resolution **without** their `snap`; `alliances` / `no_attack` / `ai` = the state after the resolution;
`ready_at` = seconds from the turn's start until each player last set Ready (`null` = never, e.g. timeout); `started` / `resolved` = unix time.
When the game ends (victory, or the last player leaves) one more row is appended:
`{"final": true, "turn": 14, "ts": 1760001000.0, "board": {"armies": {}, "owners": {}}, "gold": {"GB": 40}, "winner": {...}|null, "alliances": {}, "ai": {}, "players": {"GB": "Felix"}}`
(`players` = nation -> player name of everybody who joined). A turn archived twice (crash between archive and save) keeps its last copy.
The save (`saves/{gid}.json`) also holds `turn_started` and `ready_at` so a restart keeps the timing. Old games have no archive; their
`/stats` answer has `"empty": true`. The archive and the statistics stay unreachable until the game is finished.

State view:
```json
{"changed": true, "version": 17, "status": "running", "me": "GB", "is_host": true,
 "turn": 3, "timer_remaining": null, "player_order": [...], "ready": {"GB": true, "FR": false},
 "players": {"GB": {"name": "Felix"}}, "my_gold": 12, "rules": {...},
 "map": {...}, "theme": {...theme.json...}, "owners": {...}, "armies": {...},
 "board": [...], "my_orders": [...], "order_errors": [[...]],
 "incoming": [{"type": "send_gold", "from": "FR", "amount": 5}],
 "last_turn": {"turn": 2, "events": [...], "before": {"armies": {...}, "owners": {...}}, "player_order": ["FR", "GB"], "timeouts": ["FR"]},
 "chat": [{"id": 4, "from": "FR", "to": null, "text": "Hallo", "marks": [{"kind": "field", "f": [3, 4]}], "turn": 2, "ts": 1760000000}]}
```
`chat` holds the public messages (`to: null`) plus private ones where the caller is sender or receiver, oldest first
(`id` increases per game). Other players' private messages are never sent. Chat limits (server/games.py):
`CHAT_MAX_LEN` 1000 characters, `CHAT_MAX_MARKS` 20 marks; text may be empty if there is at least one mark;
fields must lie inside the grid; `to` must be another joined player. Chat is stored in `saves/{gid}.json`
and bumps `version`.
`last_turn.before` is the board (armies, owners) at the start of that resolved turn and `last_turn.player_order` the order
in which it was resolved; the client replay starts there
and applies each group's `snap`. (Saves from before this feature have no `before`; the client then skips the auto-replay.)
`my_recruit_limit` (= `recruit_limit_per_province` × own provinces at turn start) is also in the view.
Milestone 4 view fields: `me` is `null` for a **spectator** (surrendered player; `spectator: true`, `my_nation` = the nation he had,
`my_gold` null, `my_orders` / `order_errors` empty; `PUT orders`, `ready`, `preview`, `surrender` and `chat` answer 400 "Du schaust nur noch zu.").
`ai` = {nation: {reason, name}}; `members` = {nation: player name} of everybody who joined (also surrendered); `host` flag `is_host`;
`timer_remaining` is frozen while `pause` = `{by: nation, host: bool, name}` is set (else `null`); `pause_available` = the caller may still
use his own pause; `last_turn.timeouts` = nations that were not ready when the timer ended; `notices` = public messages
`[{id, turn, kind: "timeout"/"pause"/"surrender"/"kick"/"rejoin"/"end", text}]` (the last 30; the notice of a timeout carries the
turn that just started, so clients show it during that turn); `my_rejoin_code` (active players only); `rejoin_requests`
`[{id, nation, name, ts}]` (host only, else `[]`). A kicked or replaced token gets 403 "Ungültiger Token.".
Chat: spectators can read (public messages and private ones they took part in) but not write; `to` must be an active player.
Milestone 3 view fields: `alliances` (all, public), `no_attack` (all, public), `invitations` and `offers` as
`{"incoming": [...], "outgoing": [...]}` (only the caller's own; offers whose seller lost the province are left out),
`victory` = `{"leader": {kind, id, players, turns} | null, "need": victory_hold_turns}`, `winner` (null or `{players, alliance, turn}`).
When the game is won `status` becomes `"finished"`: `PUT orders`, `ready` and `preview` answer 400 "Das Spiel ist beendet.",
the state and chat stay readable (chat still works).
A finished game's `status` is the signal for the client to offer the statistics (`GET stats` / `GET history`, section 8; the end banner gets a "Statistik" button).
While `status == "lobby"`, `GET state` returns only `{changed, version, status}`; the client uses `/lobby` there.
Errors: HTTP 400 (bad input), 403 (wrong token / not host), 404 (unknown game), body `{"detail": "German text"}`.
`fresh` in armies counts only divisions recruited in earlier resolutions of this turn; the client adds pending
recruit orders itself.
`version` increases on every change (join, orders, ready, resolution, pause, notices, rejoin requests). The client polls every 2 s with `since`.
`incoming` is empty in milestone 1 (other players' orders stay hidden; the client shows *own* sends/gifts in the
receiver's board row). Static files: `/` → `client/index.html`, `/client/*`, `/maps/*`.
Saves: `saves/{gid}.json` after every change (state + members/tokens + orders + ready + pause + notices + codes), loaded on server start.
Milestone 4 changed the save layout from `tokens` / `joined` / `host` to `members: [{id, token, name, nation, host}]`; saves of the old layout are converted
on load. Static files: also `/editor` → `client/editor.html`.
Run: `python -m uvicorn server.app:app --host 0.0.0.0 --port 8000`.

## 9. Statistics (`engine/stats.py`, milestone 5)
`compute_stats(map_data, rules, history, chat=None, meta=None)` is pure and recomputes everything from the archive rows
(section 8) each time, so a new statistic also works for old games. `history` = turn rows, optionally followed by the `final` row
(`None` / `[]` = empty). `chat` = the game's chat messages (only `from` / `to` are read, never the text). `meta` = `{"players": {nation: name}}`.
Result (JSON-safe; nation codes are keys; `order` lists all map nations):
```json
{"version": 1, "empty": false, "order": ["GB", "FR"], "axis": [1, 2, 3], "players": {"GB": "Felix", "FR": null},
 "series": {"gold": {"GB": [10, 9.5, 12]}},
 "totals": {"GB": {"gold_earned": 40, "kills": 7, "orders_given": {"move": 4}, "status": "player"}},
 "kills": {"GB": {"FR": {"divisions": 5, "ships": 2}}},
 "chat_matrix": {"GB": {"all": 3, "FR": 1}},
 "heat": {"fights": {"3,4": 2}},
 "game": {"turns": 2, "final_turn": 3, "started": 1760000000.1, "ended": 1760000100.0, "duration_seconds": 99.9, "winner": null,
          "biggest_fight": {"turn": 2, "field": [3, 4], "attacker": "GB", "defender": "FR", "units": 9}, "most_contested_province": {"province": "FR1", "name": "...", "changes": 2},
          "bloodiest_field": {"field": [3, 4], "units": 6}},
 "titles": [{"title": "Schlächter", "nation": "GB", "value": 7, "metric": "kills"}]}
```
- `axis` = turn numbers of the board snapshots (one per archived turn: the board at its start, then the end board). Every series
  list has one value per axis point. Series (`SERIES` registry): `gold` (start of the turn; `null` for nations without a player),
  `income`, `upkeep`, `gold_sent`, `gold_received` (flows of the resolved turn; `null` at the end board), and from the boards `provinces`,
  `fields`, `share` (of all land fields, 0..1), `cities`, `ports`, `armies`, `divisions`, `ships`, `divisions_at_sea`.
- `totals` (`TOTAL_KEYS` + `avg_ready_seconds`, `peak_share`, `peak_share_turn`, `knocked_out_turn` (null if never), `status` (`player` / `unpicked` /
  `surrender` / `kick`), `ai_since_turn`, `orders_given` / `orders_skipped` = {order type: count}): gold earned / upkeep / spent on recruits, ships and
  purchases / sales income / refunds / sent / received; recruited, disbanded, ships built / disbanded, divisions lost in fights and conquests, ships
  lost, `kills_divisions` / `kills_ships`; fights as attacker and defender, `won` / `lost` / `both` (both destroyed counts as lost), conquests, failed
  conquests, provinces lost, gifts and sales, `fields_marched` (division-fields), `ship_fields_marched`, forced marches (`forced_march_toggles`, `forced_march_moves`),
  `standing_march_steps` (auto `move` events), `blocked_moves`, `timeouts`, chat counts, alliances joined / left; derived: `units_lost`, `kills`,
  `units_recruited`, `gold_traded` (sent + sales), `chat_total`.
- `kills[attacker][victim]` = {divisions, ships}; the killer of a fight is the side that dealt the damage (allied defenders: the first defender's nation gets the credit).
- `heat[metric]["c,r"]`: `divisions_died` (fights and conquest costs), `ships_died`, `fights`, `conquests`, `recruits` (divisions and ships), `traffic` (divisions walking over a field).
- `titles`: best nation per category (`TITLES`), skipped when nobody has a value > 0 (`Blitzmerker` = lowest `avg_ready_seconds`); `tied` lists equal nations.
- How to add a statistic: see the module docstring (`@on(kind)` handlers, `@series(name)`, `@derived`, `TITLES`).
