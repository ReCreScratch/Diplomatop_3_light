"""End-of-game statistics (RULES.md 12), computed from the game archive. Pure functions, no I/O.

`compute_stats(map_data, rules, history, chat=None, meta=None)` recomputes everything from the raw archive rows
(API.md section 8), so a statistic added here also works for games played before it existed.

How to add a statistic:
  * a total, a kill count or a heatmap entry: write a handler with @on("fight", ...) that adds to ctx.totals /
    ctx.kills / ctx.heat (it is called for every event of that kind, in game order);
  * a curve: write a function with @series("name") returning {nation: [value per axis point]};
  * a number derived from other totals: write a function with @derived (runs after all events);
  * a title: add a row to TITLES.
"""
from collections import Counter

from .hexgrid import parse_grid

STATS_VERSION = 1

HANDLERS = {}     # event kind -> [handler(ctx, turn, event)]
SERIES = {}       # metric name -> function(ctx) -> {nation: [values]}
DERIVED = []      # functions(ctx) run after all events

# Every nation has these totals (zero when nothing happened), so the output always has the same shape.
TOTAL_KEYS = (
    "gold_earned", "gold_upkeep", "gold_spent_recruits", "gold_spent_ships", "gold_spent_purchases",
    "gold_sales_income", "gold_refunds", "gold_sent", "gold_received",
    "recruited", "disbanded", "ships_built", "ships_disbanded",
    "divisions_lost_fights", "divisions_lost_conquest", "ships_lost", "units_lost",
    "kills_divisions", "kills_ships", "kills",
    "fights", "fights_attacker", "fights_defender", "fights_won", "fights_lost", "fights_both",
    "fights_attacker_won", "fights_attacker_lost", "fights_attacker_both",
    "fights_defender_won", "fights_defender_lost", "fights_defender_both",
    "conquests", "conquests_failed", "provinces_lost",
    "gifts_given_provinces", "gifts_received_provinces", "sales", "purchases",
    "moves", "fields_marched", "ship_fields_marched", "forced_march_toggles", "forced_march_moves",
    "standing_march_steps", "blocked_moves", "no_attack_pacts",
    "timeouts", "chat_public", "chat_private", "chat_total",
    "alliances_joined", "alliances_left", "units_recruited", "gold_traded",
)
SNAPSHOT_METRICS = ("provinces", "fields", "cities", "ports", "armies", "divisions", "ships", "divisions_at_sea")
HEAT_METRICS = ("divisions_died", "ships_died", "fights", "conquests", "recruits", "traffic")


def on(*kinds):
    """Decorator: call the function for every event of these kinds."""
    def wrap(func):
        for kind in kinds:
            HANDLERS.setdefault(kind, []).append(func)
        return func
    return wrap


def series(name):
    """Decorator: register a curve function."""
    def wrap(func):
        SERIES[name] = func
        return func
    return wrap


def derived(func):
    """Decorator: a total computed from other totals after all events."""
    DERIVED.append(func)
    return func


def num(value):
    """Round float noise away; keep ints."""
    if isinstance(value, float):
        value = round(value, 4)
        return int(value) if value == int(value) else value
    return value


class Ctx:
    """Everything the handlers need: the archive plus the accumulators."""

    def __init__(self, map_data, rules, history, chat, meta):
        self.map, self.rules, self.meta = map_data, rules, meta or {}
        history = history or []
        self.rows = [r for r in history if not r.get("final")]
        finals = [r for r in history if r.get("final")]
        self.final = finals[-1] if finals else None
        self.chat = chat or []
        self.nations = list(map_data["nations"])
        cells = parse_grid(map_data["grid"])
        self.sea = {f for f, token in cells.items() if token == "~~"}
        self.sizes = {}
        for token in cells.values():
            if token in map_data["provinces"]:
                self.sizes[token] = self.sizes.get(token, 0) + 1
        self.land_fields = sum(self.sizes.values())
        # boards: (turn, {armies, owners}) at the start of each turn, then the end board
        self.boards = [(r["turn"], r["before"]) for r in self.rows if r.get("before")]
        if self.final and self.final.get("board"):
            self.boards.append((self.final.get("turn", (self.boards[-1][0] + 1) if self.boards else 1), self.final["board"]))
        self.axis = [t for t, _ in self.boards]
        self.totals = {n: {k: 0 for k in TOTAL_KEYS} for n in self.nations}
        for t in self.totals.values():
            t["orders_given"], t["orders_skipped"] = {}, {}
        self.kills = {}                                   # attacker -> victim -> {divisions, ships}
        self.heat = {m: Counter() for m in HEAT_METRICS}
        self.chat_matrix = {}
        self.changes = Counter()                          # province -> owner changes
        self.biggest_fight = None
        self.flows = {m: {n: [0] * len(self.rows) for n in self.nations} for m in ("income", "upkeep", "gold_sent", "gold_received")}
        self.row_index = 0                                # index of the row whose events are processed

    def add(self, nation, key, amount=1):
        if nation in self.totals:
            self.totals[nation][key] = self.totals[nation].get(key, 0) + amount

    def add_dict(self, nation, key, sub, amount=1):
        if nation in self.totals:
            d = self.totals[nation][key]
            d[sub] = d.get(sub, 0) + amount

    def flow(self, metric, nation, amount):
        if nation in self.flows[metric]:
            self.flows[metric][nation][self.row_index] += amount

    def unit_is_fleet(self, unit):
        return (self.rules.get("unit_types", {}).get(unit) or {}).get("terrain") == "sea"

    def kill(self, killer, victim, divisions, ships):
        if not (divisions or ships) or killer == victim:
            return
        cell = self.kills.setdefault(killer, {}).setdefault(victim, {"divisions": 0, "ships": 0})
        cell["divisions"] += divisions
        cell["ships"] += ships
        self.add(killer, "kills_divisions", divisions)
        self.add(killer, "kills_ships", ships)

    def heat_add(self, metric, field, amount=1):
        if amount:
            self.heat[metric][f"{field[0]},{field[1]}"] += amount


# ---------------------------------------------------------------- event handlers
@on("income")
def _income(ctx, turn, ev):
    ctx.add(ev["player"], "gold_earned", ev["amount"])
    ctx.flow("income", ev["player"], ev["amount"])


@on("upkeep")
def _upkeep(ctx, turn, ev):
    ctx.add(ev["player"], "gold_upkeep", ev["amount"])
    ctx.flow("upkeep", ev["player"], ev["amount"])


@on("send_gold")
def _send_gold(ctx, turn, ev):
    ctx.add(ev["player"], "gold_sent", ev["amount"])
    ctx.add(ev["to"], "gold_received", ev["amount"])
    ctx.flow("gold_sent", ev["player"], ev["amount"])
    ctx.flow("gold_received", ev["to"], ev["amount"])


@on("recruit", "build_ship")
def _recruit(ctx, turn, ev):
    ship = ev["kind"] == "build_ship"
    cost = ev.get("cost")
    if cost is None:
        cost = 0 if ev.get("ai") else ev["count"] * ctx.rules.get("ship_cost" if ship else "division_cost", 0)
    who = ev["player"]
    ctx.add(who, "ships_built" if ship else "recruited", ev["count"])
    ctx.add(who, "gold_spent_ships" if ship else "gold_spent_recruits", cost)
    ctx.heat_add("recruits", ev["field"], ev["count"])


@on("disband")
def _disband(ctx, turn, ev):
    ship = ctx.unit_is_fleet(ev.get("unit", ctx.rules.get("land_unit")))
    ctx.add(ev["player"], "ships_disbanded" if ship else "disbanded", ev["count"])
    ctx.add(ev["player"], "gold_refunds", ev.get("refund", 0))


@on("fight")
def _fight(ctx, turn, ev):
    attacker, defender, winner = ev["attacker"], ev["defender"], ev["winner"]
    a_units, d_units = ev["attacker_units"], ev["defender_units"]
    divisions = ships = 0
    for u in a_units + d_units:
        if u["fleet"]:
            ctx.add(u["owner"], "ships_lost", u["lost"])
            ships += u["lost"]
        else:
            ctx.add(u["owner"], "divisions_lost_fights", u["lost"])
            divisions += u["lost"]
    for u in d_units:     # the attacker destroyed these (with allied defenders the kills go to the first defender below)
        ctx.kill(attacker, u["owner"], 0 if u["fleet"] else u["lost"], u["lost"] if u["fleet"] else 0)
    for u in a_units:
        ctx.kill(defender, u["owner"], 0 if u["fleet"] else u["lost"], u["lost"] if u["fleet"] else 0)
    ctx.add(attacker, "fights")
    ctx.add(attacker, "fights_attacker")
    outcome = "both" if winner == "both" else "won" if winner == attacker else "lost"   # both destroyed counts as lost
    ctx.add(attacker, "fights_" + outcome)
    ctx.add(attacker, "fights_attacker_" + outcome)
    for owner in dict.fromkeys(u["owner"] for u in d_units):
        outcome = "both" if winner == "both" else "won" if winner == defender else "lost"
        ctx.add(owner, "fights")
        ctx.add(owner, "fights_defender")
        ctx.add(owner, "fights_" + outcome)
        ctx.add(owner, "fights_defender_" + outcome)
    ctx.heat_add("fights", ev["field"])
    ctx.heat_add("divisions_died", ev["field"], divisions)
    ctx.heat_add("ships_died", ev["field"], ships)
    size = sum(u["count"] for u in a_units + d_units)
    if ctx.biggest_fight is None or size > ctx.biggest_fight["units"]:
        ctx.biggest_fight = {"turn": turn, "field": ev["field"], "attacker": attacker, "defender": defender, "units": size,
                             "attacker_units": sum(u["count"] for u in a_units), "defender_units": sum(u["count"] for u in d_units),
                             "attacker_losses": ev["attacker_losses"], "defender_losses": ev["defender_losses"],
                             "winner": winner, "sea": ev.get("sea", False)}


@on("conquest")
def _conquest(ctx, turn, ev):
    ctx.add(ev["player"], "conquests")
    ctx.add(ev["player"], "divisions_lost_conquest", ev.get("lost", ev["cost"]))
    if ev.get("old_owner"):
        ctx.add(ev["old_owner"], "provinces_lost")
    ctx.heat_add("conquests", ev["field"])
    ctx.heat_add("divisions_died", ev["field"], ev.get("lost", ev["cost"]))
    ctx.changes[ev["province"]] += 1


@on("conquest_failed")
def _conquest_failed(ctx, turn, ev):
    ctx.add(ev["player"], "conquests_failed")


@on("give_province")
def _give(ctx, turn, ev):
    ctx.add(ev["player"], "gifts_given_provinces")
    ctx.add(ev["to"], "gifts_received_provinces")
    ctx.changes[ev["province"]] += 1


@on("buy")
def _buy(ctx, turn, ev):
    ctx.add(ev["seller"], "sales")
    ctx.add(ev["seller"], "gold_sales_income", ev["price"])
    ctx.add(ev["to"], "purchases")
    ctx.add(ev["to"], "gold_spent_purchases", ev["price"])
    ctx.changes[ev["province"]] += 1


@on("move")
def _move(ctx, turn, ev):
    who, fields = ev["player"], len(ev["path"])
    units = [(ev.get("unit", ctx.rules.get("land_unit")), ev["count"])]
    if ev.get("with"):
        units.append((ev.get("with_unit"), ev.get("with_count", 0)))
    ctx.add(who, "moves")
    if ev.get("auto"):
        ctx.add(who, "standing_march_steps")
    if ev.get("forced_march"):
        ctx.add(who, "forced_march_moves")
    for unit, count in units:
        if ctx.unit_is_fleet(unit):
            ctx.add(who, "ship_fields_marched", count * fields)
        else:
            ctx.add(who, "fields_marched", count * fields)
            for f in ev["path"]:
                ctx.heat_add("traffic", f, count)


@on("move_blocked")
def _blocked(ctx, turn, ev):
    ctx.add(ev["player"], "blocked_moves")


@on("forced_march")
def _forced(ctx, turn, ev):
    if ev.get("on"):
        ctx.add(ev["player"], "forced_march_toggles")


@on("no_attack")
def _no_attack(ctx, turn, ev):
    if ev.get("on"):
        ctx.add(ev["player"], "no_attack_pacts")


@on("skipped")
def _skipped(ctx, turn, ev):
    order = ev.get("order")
    ctx.add_dict(ev["player"], "orders_skipped", order.get("type", "?") if isinstance(order, dict) else "?")


# ---------------------------------------------------------------- derived totals
@derived
def _derive_sums(ctx):
    for t in ctx.totals.values():
        t["units_lost"] = t["divisions_lost_fights"] + t["divisions_lost_conquest"] + t["ships_lost"]
        t["kills"] = t["kills_divisions"] + t["kills_ships"]
        t["units_recruited"] = t["recruited"] + t["ships_built"]
        t["gold_traded"] = t["gold_sent"] + t["gold_sales_income"]
        t["chat_total"] = t["chat_public"] + t["chat_private"]


# ---------------------------------------------------------------- snapshots and curves
def summarize(ctx, board):
    """{nation: {provinces, fields, cities, ports, armies, divisions, ships, divisions_at_sea}} for one board."""
    out = {n: {m: 0 for m in SNAPSHOT_METRICS} for n in ctx.nations}
    provinces = ctx.map["provinces"]
    for code, owner in (board.get("owners") or {}).items():
        if owner in out and code in provinces:
            row = out[owner]
            row["provinces"] += 1
            row["fields"] += ctx.sizes.get(code, 0)
            row["cities"] += 1 if provinces[code].get("capital") else 0
            row["ports"] += len(provinces[code].get("ports", []))
    for army in (board.get("armies") or {}).values():
        row = out.get(army["owner"])
        if row is None:
            continue
        if ctx.unit_is_fleet(army.get("unit", ctx.rules.get("land_unit"))):
            row["ships"] += army["divisions"]
        else:
            row["armies"] += 1
            row["divisions"] += army["divisions"]
            if tuple(army["field"]) in ctx.sea:
                row["divisions_at_sea"] += army["divisions"]
    return out


def snapshot_series(metric):
    def build(ctx):
        sums = [summarize(ctx, b) for _, b in ctx.boards]
        return {n: [s[n][metric] for s in sums] for n in ctx.nations}
    return build


for _metric in SNAPSHOT_METRICS:
    SERIES[_metric] = snapshot_series(_metric)


@series("share")
def _share(ctx):
    fields = SERIES["fields"](ctx)
    total = ctx.land_fields or 1
    return {n: [round(v / total, 4) for v in fields[n]] for n in ctx.nations}


@series("gold")
def _gold(ctx):
    golds = [r.get("gold_before") or {} for r in ctx.rows]
    if ctx.final and ctx.final.get("board"):
        golds.append(ctx.final.get("gold") or {})
    return {n: [num(g.get(n)) if g.get(n) is not None else None for g in golds] for n in ctx.nations}


def flow_series(metric):
    def build(ctx):   # one value per resolved turn; the end board has none
        pad = len(ctx.axis) - len(ctx.rows)
        return {n: [num(v) for v in ctx.flows[metric][n]] + [None] * pad for n in ctx.nations}
    return build


for _metric in ("income", "upkeep", "gold_sent", "gold_received"):
    SERIES[_metric] = flow_series(_metric)


# ---------------------------------------------------------------- per-row data (orders, timing, alliances, chat)
def read_rows(ctx):
    """Walk the archive rows: events, orders, timeouts, ready times, alliances."""
    ready = {n: [] for n in ctx.nations}
    alliance_of = {n: None for n in ctx.nations}
    for index, row in enumerate(ctx.rows):
        ctx.row_index, turn = index, row.get("turn", index + 1)
        for ev in row.get("events", []):
            for handler in HANDLERS.get(ev.get("kind"), ()):
                handler(ctx, turn, ev)
        for nation, orders in (row.get("orders") or {}).items():
            for order in orders if isinstance(orders, list) else []:
                ctx.add_dict(nation, "orders_given", order.get("type", "?") if isinstance(order, dict) else "?")
        timeouts = set(row.get("timeouts") or [])
        for nation in timeouts:
            ctx.add(nation, "timeouts")
        for nation, secs in (row.get("ready_at") or {}).items():
            if secs is not None and nation in ready and nation not in timeouts:
                ready[nation].append(secs)
        now = {n: None for n in ctx.nations}
        for ident, alliance in (row.get("alliances") or {}).items():
            for member in alliance.get("members", []):
                if member in now:
                    now[member] = ident
        for nation, ident in now.items():
            before = alliance_of[nation]
            if before != ident:
                if before is not None:
                    ctx.add(nation, "alliances_left")
                if ident is not None:
                    ctx.add(nation, "alliances_joined")
            alliance_of[nation] = ident
    for nation, values in ready.items():
        ctx.totals[nation]["avg_ready_seconds"] = round(sum(values) / len(values), 2) if values else None


def read_chat(ctx):
    for msg in ctx.chat:
        who, to = msg.get("from"), msg.get("to")
        ctx.chat_matrix.setdefault(who, {})
        ctx.chat_matrix[who][to or "all"] = ctx.chat_matrix[who].get(to or "all", 0) + 1
        ctx.add(who, "chat_private" if to else "chat_public")


def peaks_and_exits(ctx, curves):
    """Peak share and its turn; the turn a nation was knocked out (nothing left after having had something)."""
    sums = [summarize(ctx, b) for _, b in ctx.boards]
    for nation in ctx.nations:
        t = ctx.totals[nation]
        shares = curves["share"][nation]
        best = max(shares) if shares else 0
        t["peak_share"] = best
        t["peak_share_turn"] = ctx.axis[shares.index(best)] if best > 0 else None
        t["knocked_out_turn"], had = None, False
        for turn, s in zip(ctx.axis, sums):
            row = s[nation]
            if row["provinces"] or row["armies"] or row["ships"]:
                had = True
            elif had:
                t["knocked_out_turn"] = turn
                break


def status_of(ctx):
    """How each nation ended: player / unpicked (AI from the start) / surrender / kick, and from which turn."""
    last = (ctx.final or (ctx.rows[-1] if ctx.rows else {})).get("ai") or {}
    players = dict(ctx.meta.get("players") or (ctx.final or {}).get("players") or {})
    result = {}
    for nation in ctx.nations:
        info = last.get(nation)
        since = None
        if info:
            since = 1 if info.get("reason") == "unpicked" else next(
                (r["turn"] for r in ctx.rows if nation in (r.get("ai") or {})), (ctx.final or {}).get("turn"))
        result[nation] = {"status": info["reason"] if info else "player", "ai_since_turn": since,
                          "player": players.get(nation) or (info or {}).get("name")}
    return result


# ---------------------------------------------------------------- game facts and titles
def game_facts(ctx):
    rows, final = ctx.rows, ctx.final
    started = rows[0].get("started") if rows else None
    ended = (final or {}).get("ts") or (rows[-1].get("resolved") if rows else None)
    contested = ctx.changes.most_common(1)
    bloody = Counter()
    for metric in ("divisions_died", "ships_died"):
        bloody.update(ctx.heat[metric])
    field = bloody.most_common(1)
    provinces = ctx.map["provinces"]
    return {
        "turns": len(rows), "final_turn": (final or {}).get("turn") or (rows[-1]["turn"] + 1 if rows else None),
        "started": started, "ended": ended,
        "duration_seconds": round(ended - started, 1) if started and ended else None,
        "winner": (final or {}).get("winner"),
        "biggest_fight": ctx.biggest_fight,
        "most_contested_province": ({"province": contested[0][0], "name": provinces.get(contested[0][0], {}).get("name"),
                                     "changes": contested[0][1]} if contested else None),
        "bloodiest_field": ({"field": [int(v) for v in field[0][0].split(",")], "units": field[0][1]} if field else None),
    }


# (German title, total it ranks, "max" or "min")
TITLES = (
    ("Schlächter", "kills", "max"),
    ("Kaufmann", "gold_traded", "max"),
    ("Wanderer", "fields_marched", "max"),
    ("Baumeister", "units_recruited", "max"),
    ("Eroberer", "conquests", "max"),
    ("Plaudertasche", "chat_total", "max"),
    ("Pechvogel", "units_lost", "max"),
    ("Blitzmerker", "avg_ready_seconds", "min"),
)


def titles(ctx):
    """The best nation per category; skipped when nobody has anything (max: value > 0; min: any value)."""
    found = []
    for title, metric, sense in TITLES:
        values = {n: t.get(metric) for n, t in ctx.totals.items() if t.get(metric) is not None}
        if sense == "max":
            values = {n: v for n, v in values.items() if v > 0}
        if not values:
            continue
        best = max(values.values()) if sense == "max" else min(values.values())
        winners = [n for n in ctx.nations if values.get(n) == best]
        found.append({"title": title, "nation": winners[0], "value": num(best), "metric": metric,
                      **({"tied": winners[1:]} if len(winners) > 1 else {})})
    return found


# ---------------------------------------------------------------- entry point
def compute_stats(map_data, rules, history, chat=None, meta=None):
    """All statistics of a game. history: archive rows (turn rows, then an optional final row); chat: the game's chat
    messages (only who wrote to whom is used); meta: {"players": {nation: name}} (optional). JSON-safe."""
    ctx = Ctx(map_data, rules, history, chat, meta)
    read_rows(ctx)
    read_chat(ctx)
    for func in DERIVED:
        func(ctx)
    curves = {name: func(ctx) for name, func in SERIES.items()}
    peaks_and_exits(ctx, curves)
    status = status_of(ctx)
    for nation, info in status.items():
        ctx.totals[nation]["status"] = info["status"]
        ctx.totals[nation]["ai_since_turn"] = info["ai_since_turn"]
    return {
        "version": STATS_VERSION, "empty": not ctx.rows, "order": ctx.nations, "axis": ctx.axis,
        "players": {n: i["player"] for n, i in status.items()},
        "series": curves,
        "totals": {n: {k: num(v) for k, v in t.items()} for n, t in ctx.totals.items()},
        "kills": ctx.kills,
        "chat_matrix": ctx.chat_matrix,
        "heat": {m: dict(c) for m, c in ctx.heat.items()},
        "game": game_facts(ctx),
        "titles": titles(ctx),
    }
