# Diplomatio 3.0 light

Lightweight online prototype of Diplomatio, a hex-map diplomacy strategy game for up to 12 players.

- **Rules:** [RULES.md](RULES.md) is the source of truth. Rules marked *[decided]* are settled with the user;
  *[default]* ones may still change. Gap IDs (G1 …) are kept for traceability.
- **Plan:** [IMPLEMENTATION.md](IMPLEMENTATION.md) – tech stack, architecture, map format, UI, milestones.
- **Interfaces:** [API.md](API.md) – engine functions, state/order/event shapes, HTTP endpoints.
- **Sources:** `docs/` holds the original design documents (German).

## Run
- Server + client: `python -m uvicorn server.app:app --host 0.0.0.0 --port 8000`, then open http://localhost:8000 (map editor: http://localhost:8000/editor)
- Tests: `python -m pytest -q`

## Principles
- No gameplay number in code. Every value comes from the rules config (RULES.md section 13).
- Modular: order types, resolution phases, combat formula and turn-order rule are registries; unit types are data.
- Engine (`engine/`) is pure Python with no I/O and is covered by pytest scenario tests.
- Keep it small: few dependencies, no client build step, plain JS + SVG.
- Graphics stay replaceable: no colours or images in engine or `map.json`; looks come from `theme.json` and the
  single client render module (IMPLEMENTATION.md section 4.2).
- UI text is German. PC browser first; mobile only where cheap.
- Work milestone by milestone (IMPLEMENTATION.md section 5). Milestone 1 excludes ships, alliances and the editor.
