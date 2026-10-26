# Diplomatio 3.0 – Implementation Plan

Status: agreed plan, nothing built yet (2026-10-26). The rules themselves are in [RULES.md](RULES.md).

## 1. Goals and constraints
- Playable online prototype for up to 12 players, each on their own device. Diplomacy runs over voice chat.
- Looks don't matter. Correct rules and fast iteration do.
- **No hardcoded gameplay numbers:** all of them live in a rules config.
- **Modular:** ships, alliances, new unit types, other combat formulas or turn-order rules can be added as new
  pieces without rewriting existing ones.
- Small and cheap to maintain: few dependencies, no build step, small files.
- The user reads Python best; most code will be written by Claude.

## 2. Technology

| Part | Choice | Why |
|---|---|---|
| Rules engine | Python 3, standard library only | Easy to read and test, no game-engine overhead |
| Server | FastAPI + uvicorn | One small dependency, JSON in/out, built-in API docs page for debugging |
| Client | One HTML page with plain JavaScript, map drawn as SVG | No build step; works in every browser |
| Updates | Client asks the server for news every ~2 s (polling) | Simplest option; plenty for a turn-based game |
| Storage | Game state saved as a JSON file after every turn | Saving/loading for free, easy to inspect |
| Tests | pytest scenario tests for the engine | Rules can be checked without clicking through the game |
| Hosting for tests | Server on the host's PC, shared via Tailscale or cloudflared | Friends join with a link, no router setup |

Rejected: Unreal (far too heavy), Godot/Unity (binary scene files, more effort for no gain at this stage),
live WebSocket connections (more moving parts than needed for turns).

## 3. Architecture

```
diplomatio/
  engine/                 pure game logic, no networking, no files
    config.py             RulesConfig: loads defaults + map/lobby overrides
    hexgrid.py            hex coordinates, neighbours, paths
    state.py              GameState, Player, Province, Field, Army (plain dataclasses)
    orders.py             order types + registry
    phases/               one module per resolution phase
      start_of_turn.py    income, upkeep, new player order
      transfers.py
      recruitment.py
      movement.py         moves, calls combat and conquest
    combat.py             combat formula interface + default formula
    conquest.py
    turn_order.py         turn-order rule interface + default rule
    resolve.py            runs the phase pipeline
  server/
    app.py                HTTP endpoints
    games.py              running games, players, ready state, timer
    storage.py            save/load JSON
  client/
    index.html            map, order panel, order list
  maps/europa/            map.json (logic), theme.json (looks), reference + preview images
  tools/map_preview.py    draws a map preview PNG for checking
  rules/default.json      default rules config
  tests/
```

### 3.1 How modularity works
- **Config:** every number and rule choice is read from `RulesConfig`. Load order: `rules/default.json` →
  overrides in the map file → overrides set in the lobby. New settings only need a default value.
- **Order registry:** every order type (recruit, disband, move, forced march, send gold, give province) is a small
  class with `validate(state, player)` and `apply(state)`. A new order type (e.g. "build fleet") is a new class
  registered by name; the server and the client order list handle it generically.
- **Phase pipeline:** resolution is a list of phase names in the config, e.g.
  `["transfers", "recruitment", "movement"]`. Each phase takes the orders of its kind and runs them in player order.
  New mechanics add a phase or hook into an existing one.
- **Swappable rules:** combat formula and turn-order rule are chosen by name from a registry
  (`combat_formula: "default"`, `turn_order_rule: "no_repeat_first_last"`). A new variant is one new function.
- **Unit types as data:** a unit type (division now; transport, fleet later) is defined in config with its move
  range, combat value, cost, upkeep and allowed terrain. Forced march is a modifier on top. Ships therefore
  mostly need new data plus the few special rules (embarking, tank rule).
- **Deterministic engine:** the random player order uses a seed stored in the game state, so every turn can be
  replayed exactly from the save – useful for bug reports.

### 3.2 Server endpoints (milestone 1)
- Create game (host picks map file and settings), join game (name + nation), start game.
- Get state (map, armies, own gold, own orders, turn number, player order, who is ready).
- Submit / reorder / delete own orders, set Ready.
- Turn resolves when all active players are ready or the timer runs out; result saved to disk.
- Identity: each player gets a secret link when joining. No accounts or passwords.

### 3.3 Client (milestone 1)
**General:** UI language **German**. Made for **PC browsers**; phones should work where it's cheap
(layout that wraps), but no mobile-specific effort. Guiding idea: giving orders must be fast, so everything
happens on the map with as few clicks as possible.

**Interaction model (revised after the first playtest).** Everything happens on the map; there is no side panel
for actions. Nothing illegal can be entered.
- **Selection:** left-click an own army or own capital selects it (pulsing outline). Esc, right-click on an
  empty field or a click on non-reachable sea/void deselects. Tab / Shift+Tab cycles through own armies.
- **Floating toolbar** (HTML overlay next to the selected field, follows pan/zoom): count stepper `− N +`,
  buttons "Rekrutieren +N" (R), "Abrüsten N" (D), "Gewaltmarsch an/aus" (G). Buttons that are not possible are
  disabled with the reason as tooltip (e.g. "Kein Gold mehr"). Hotkeys do the same: +/−, digits, Shift+wheel change N.
  On a capital without army only the recruit part is shown.
- **Move:** with an army selected, all fields reachable within its range (including a pending forced-march toggle)
  are highlighted. Hovering a field draws the shortest path and shows the preview (fight/conquest via `/preview`)
  in a tooltip at the cursor. **Left-click on a reachable field issues the move immediately** with N divisions
  (default: all movable). Shift+click adds a waypoint for detours. If divisions remain (split), the army stays
  selected with N set to the rest, so the next click sends the rest elsewhere (G56: several moves per army).
- **Default N:** all movable divisions for moves/disband, 1 for recruiting; clamped to what is possible.
- **Prevention:** a client `budget()` computes gold left (gold − recruits × cost − gold sent) and recruits left
  (`my_recruit_limit` − pending recruits); all counts are clamped to it. If the server still returns an error for
  the order just added, the client removes it again and shows the server text as a toast. Orders that became
  invalid later (rare) stay red with the reason.
- **Delete / undo:** clicking an order's marker (the numbered badge on an arrow, "+3", "−2") deletes that order
  (arrows themselves are not clickable, so clicks on fields under them still work); Ctrl+Z undoes the
  last change. A compact order list in the side area (hover = highlight on map, ✕ = delete) reaches hidden markers.
- **Feedback:** context hint line below the map ("Ziel anklicken · Shift+Klick Umweg · G Gewaltmarsch · Esc"),
  cursor tooltip, top bar "Gold 33 → 18", "Rekruten 4/27"; next to Ready an info "2 Armeen ohne Befehl" (no dialog).
- **Transfers:** clicking a board row opens an inline gold field in that row (max = gold left, Enter sends).
  Right-click on an own province opens a small on-map menu "Provinz verschenken an …" – the only menu.
- Own orders are drawn on the map: numbered move arrows with division count, "+3" recruit and "−2" disband
  markers, forced-march marker. Freshly recruited divisions are shown as not movable.

**Top bar:** turn number, timer, player order with ready marks, gold → gold after orders, recruits left, order
summary, Ready button.

**Board:** for every player provinces, province share, income, upkeep, armies, total divisions (no gold).

**Lobby / start:** map tiles with a mini-map preview; nations as cards (theme colour, name, province count,
taken ones greyed with player name); live player list with host crown; "Link kopieren" button; host button
"Spiel starten (N Spieler)"; collapsible short rule summary from the rules config.

**Last turn:** step-by-step replay (◀ ▶) through the resolution in player order, highlighting each move, fight
and conquest on the map, with a one-line text per step.

## 4. Maps and graphics

### 4.1 Map folder
Each map is a folder under `maps/`, e.g. `maps/europa/`:

| File | Content | Used by |
|---|---|---|
| `map.json` | Game logic only: grid, provinces, nations, start armies, rule overrides | engine |
| `theme.json` | Looks only: nation colours, terrain colours, outlines, borders, capital icon, (later) textures | client |
| `reference.webp` | The original picture the map was recreated from | humans |
| `preview.png` | Drawn from `map.json` + `theme.json` by `tools/map_preview.py` to check the map | humans |

**Grid:** hexes are **flat-top**, laid out in columns; **odd columns sit half a field higher** than even ones.
`grid` is a list of text rows, one token per field, separated by spaces. Coordinates are `[column, row]`, counted from
the top-left token. Tokens:
- a province code (`GB1`, `ES10`, …) – land belonging to that province
- `~~` sea, `##` edge of the map (not playable), `..` no field
- `?SE`, `?RU`, `?TR` – land without provinces yet (Scandinavia, Russia, Ottoman region); blocked for now

**Provinces:** `{"name", "capital_name", "capital": [c, r], "income", "owner"}`. Ports are added in milestone 2.

The loader checks: known tokens, every province has fields and its capital inside it, every owner exists,
start armies stand on province fields. Connectivity is not checked, because provinces may have separate parts
(islands, GB2, ES5). Start armies: `[{"owner", "field", "divisions"}]`.

### 4.2 Keeping graphics replaceable
- The engine and `map.json` contain **no colours, sizes or images**. Nations and terrain are only IDs.
- All looks come from `theme.json` (per map) and a few CSS variables in the client.
- The client has **one rendering module** (`client/render.js`) that turns game state into SVG. Everything else
  (panels, input, server calls) talks to it only through functions like `drawMap(state)`, `highlight(field)`,
  `showArrows(orders)`. A graphics update (textures, icons, a different renderer such as canvas or a game engine)
  means replacing this module and the theme – nothing else.
- Icons and textures go to `client/assets/` and are referenced by name from `theme.json`
  (e.g. `"textures": {"~~": "sea.png"}`), so new art drops in without code changes.

### 4.3 Europa map (recreated from the user's picture)
- 61 × 35 fields, 64 provinces in 7 nations: Großbritannien (9), Spanien (10), Frankreich (10), Deutsches Reich (10),
  Österreich-Ungarn (10), Italien (8), Nordafrika (7).
- The three marked single-field islands belong to the province their arrow points to
  (Shetland and Orkney → Highlands, Balearen → Katalonien).
- Province and capital names were chosen by Claude and are free to change.
- **Placeholders:** income = half the field count (1–5); no start armies; start gold from the rules config.
- Open points: see RULES.md section 14 ("Europa map").

## 5. Milestones

| # | Content | Done when |
|---|---|---|
| 1 | Engine core: map loading, economy, recruit/disband, movement, split/merge, forced march, combat, conquest, turn order, gold/province gifts. Server, client, save/load. Test map + real map. | A full game can be played online by 2+ players on the real map, and all rules in RULES.md sections 1–9 have tests |
| 2 | Ships: ports, transports, fleets, tank rule | Sea scenarios from RULES.md section 10 work |
| 3 | Alliances, province selling, victory display with 10-turn rule | RULES.md section 11 works |
| 4 | Comfort: lobby map preview, random nation reveal, pause, idle warning, surrender/spectator, kick, map editor | as needed |

Milestone 1 build order: engine with tests on a tiny test map → server → client → real map → playtest.

## 6. Before building starts
- [x] User confirms or changes the small open defaults G50–G53 (RULES.md section 14)
- [x] User provides the map picture → recreated as `maps/europa/` (open points M1–M6 in RULES.md)
- [x] User gives the go to start
- [x] Milestone 1 built (engine, server, client); 105 tests pass. Next: playtest online with friends.
