// Shared game-screen model: the latest server state plus small read-only helpers on it. No DOM drawing here.
import { parseGrid, key, neighbours } from './hex.js';

export const $ = id => document.getElementById(id);
export const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const same = (a, b) => !!a && !!b && a[0] === b[0] && a[1] === b[1];

export const ctx = { gid: null, token: null, G: null, grid: null, gridMap: null, armyIdx: new Map() };

export function setState(v) {
  ctx.G = v;
  if (ctx.gridMap !== v.map.name) { ctx.grid = parseGrid(v.map.grid); ctx.gridMap = v.map.name; }
  ctx.armyIdx = new Map();   // field key -> units on it, fleets first
  for (const a of Object.values(v.armies)) {
    const k = key(a.field);
    if (!ctx.armyIdx.has(k)) ctx.armyIdx.set(k, []);
    ctx.armyIdx.get(k).push(a);
  }
  for (const list of ctx.armyIdx.values()) list.sort((a, b) => isFleet(b) - isFleet(a));
}

export const rules = () => ctx.G.rules;
export const P = () => ctx.G.map.provinces;
export const tokenAt = f => (ctx.grid[f[1]] || [])[f[0]];
export const isSea = f => tokenAt(f) === '~~';
export const passable = f => !!P()[tokenAt(f)] || isSea(f);
export const unitsAt = f => ctx.armyIdx.get(key(f)) || [];
export const armyAt = f => unitsAt(f)[0];
export const ownUnitsAt = f => unitsAt(f).filter(a => a.owner === ctx.G.me);
export const ownArmyAt = f => ownUnitsAt(f)[0] || null;
export const isEnemyAt = f => unitsAt(f).some(a => a.owner !== ctx.G.me);
// unit types are data (rules.unit_types); a fleet is a unit that stays at sea
export const isFleet = a => !!a && (rules().unit_types[a.unit || rules().land_unit] || {}).terrain === 'sea';
export const isOwnPort = f => {
  const tok = tokenAt(f), p = P()[tok];
  return !!p && ctx.G.owners[tok] === ctx.G.me && (p.ports || []).some(q => same(q, f));
};
export const nextToOwnPort = f => isSea(f) && neighbours(f[0], f[1]).some(isOwnPort);
// one step of unit a from field `from` to `to` (RULES.md 10): fleets and linked pairs stay at sea,
// armies put to sea only from an own port and land anywhere
export const canStep = (a, from, to, group) => {
  if (!passable(to)) return false;
  if (isFleet(a) || group) return isSea(to);
  return !(isSea(to) && !isSea(from) && !isOwnPort(from));
};
export const movable = a => rules().recruits_can_move_same_turn ? a.divisions : a.divisions - (a.fresh || 0);
export const pName = pid => (ctx.G.players[pid] && ctx.G.players[pid].name) || pid;
export const nName = pid => (ctx.G.map.nations[pid] && ctx.G.map.nations[pid].name) || pid;
// readable field name for chat chips: capital name, else province + coordinates
export const fieldName = f => {
  const p = P()[tokenAt(f)];
  if (!p) return isSea(f) ? `Meer ${f[0]},${f[1]}` : `Feld ${f[0]},${f[1]}`;
  return same(p.capital, f) ? p.capital_name : `${p.name} ${f[0]},${f[1]}`;
};
// own province whose capital stands on field f (recruiting without an army there)
export const ownCapitalAt = f => {
  const tok = tokenAt(f), p = P()[tok];
  return p && ctx.G.owners[tok] === ctx.G.me && same(p.capital, f) ? tok : null;
};
