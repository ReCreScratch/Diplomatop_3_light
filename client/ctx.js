// Shared game-screen model: the latest server state plus small read-only helpers on it. No DOM drawing here.
import { parseGrid, key } from './hex.js';

export const $ = id => document.getElementById(id);
export const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const same = (a, b) => !!a && !!b && a[0] === b[0] && a[1] === b[1];

export const ctx = { gid: null, token: null, G: null, grid: null, gridMap: null, armyIdx: new Map() };

export function setState(v) {
  ctx.G = v;
  if (ctx.gridMap !== v.map.name) { ctx.grid = parseGrid(v.map.grid); ctx.gridMap = v.map.name; }
  ctx.armyIdx = new Map(Object.values(v.armies).map(a => [key(a.field), a]));
}

export const rules = () => ctx.G.rules;
export const P = () => ctx.G.map.provinces;
export const tokenAt = f => (ctx.grid[f[1]] || [])[f[0]];
export const passable = f => !!P()[tokenAt(f)];
export const armyAt = f => ctx.armyIdx.get(key(f));
export const ownArmyAt = f => { const a = armyAt(f); return a && a.owner === ctx.G.me ? a : null; };
export const isEnemyAt = f => { const a = armyAt(f); return !!a && a.owner !== ctx.G.me; };
export const movable = a => rules().recruits_can_move_same_turn ? a.divisions : a.divisions - (a.fresh || 0);
export const pName = pid => (ctx.G.players[pid] && ctx.G.players[pid].name) || pid;
export const nName = pid => (ctx.G.map.nations[pid] && ctx.G.map.nations[pid].name) || pid;
// own province whose capital stands on field f (recruiting without an army there)
export const ownCapitalAt = f => {
  const tok = tokenAt(f), p = P()[tok];
  return p && ctx.G.owners[tok] === ctx.G.me && same(p.capital, f) ? tok : null;
};
