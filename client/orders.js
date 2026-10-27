// Own order list: budget, validation helpers, undo stack and saving. The server stays the judge:
// after every PUT an order that just got an error is taken out again and the German text is shown.
import { api } from './api.js';
import { ctx, rules, P, tokenAt, movable, pName } from './ctx.js';

export const book = { list: [], errors: [] };
let undo = [], inflight = 0, seq = 0, check = null;
let hooks = { onChange() {}, toast() {} };

export const init = h => { hooks = h; };
export function fromServer(list, errors) { if (!inflight) { book.list = list; book.errors = errors; } }
export function newTurn() { undo = []; check = null; }

// ---------- derived numbers (everything from state.rules / my_gold / my_recruit_limit) ----------
export function budget() {
  const r = rules(), G = ctx.G, debt = r.allow_spending_into_debt;
  let recruits = 0, sent = 0;
  for (const o of book.list) { if (o.type === 'recruit') recruits += o.count; else if (o.type === 'send_gold') sent += o.amount; }
  const gold = G.my_gold - recruits * r.division_cost - sent, limit = G.my_recruit_limit ?? 0;
  const recLeft = Math.max(0, limit - recruits);
  return {
    gold, recruits, limit, recLeft,
    canRecruit: Math.min(recLeft, debt ? Infinity : Math.floor(Math.max(0, gold) / r.division_cost)),
    canSend: debt ? Infinity : Math.floor(Math.max(0, gold)),
  };
}
const sum = (type, army, f = 'count') => book.list.reduce((s, o) => s + (o.type === type && o.army === army ? o[f] : 0), 0);
export const moveOf = id => book.list.find(o => o.type === 'move' && o.army === id);
export const fmOn = a => { let on = a.forced_march; for (const o of book.list) if (o.type === 'forced_march' && o.army === a.id) on = o.on; return on; };
export const rangeOf = a => fmOn(a) ? rules().forced_march_range : rules().move_range;
// several moves may split one army (G56); together they use at most its movable divisions
export const movableLeft = a => Math.max(0, movable(a) - sum('disband', a.id) - sum('move', a.id));
export const disbandMax = a => Math.max(0, a.divisions - sum('disband', a.id) - sum('move', a.id));
export const halted = a => book.list.some(o => o.type === 'halt' && o.army === a.id);
// standing march (army.route from the server) still in force next turn: not replaced by a new move, not halted
export const marching = a => !!(a.route && a.route.length) && !moveOf(a.id) && !halted(a);
export const roundsLeft = a => Math.ceil(a.route.length / rangeOf(a));
export const hasOrder = a => book.list.some(o => o.army === a.id);
export const gifted = prov => book.list.some(o => o.type === 'give_province' && o.province === prov);

// ---------- changing the list ----------
function commit(mutate) {   // mutate() may return the order the server should vet
  undo.push(JSON.stringify(book.list)); if (undo.length > 50) undo.shift();
  check = mutate() || null;
  hooks.onChange(); save();
}
export function add(o) {
  const L = book.list;
  const merge = (type, same) => L.find(x => x.type === type && same(x));
  commit(() => {
    const m = o.type === 'move' ? merge('move', x => x.army === o.army && JSON.stringify(x.path) === JSON.stringify(o.path))
      : o.type === 'recruit' ? merge('recruit', x => x.field[0] === o.field[0] && x.field[1] === o.field[1])
      : o.type === 'disband' ? merge('disband', x => x.army === o.army)
      : o.type === 'send_gold' ? merge('send_gold', x => x.to === o.to) : null;
    if (m) { if (o.type === 'send_gold') m.amount += o.amount; else m.count += o.count; return m; }
    book.list.push(o);
    return o;
  });
}
export function removeAt(i) { if (i >= 0 && i < book.list.length) commit(() => { book.list.splice(i, 1); }); }
export function setForcedMarch(a, on) {
  let dropped = 0;
  commit(() => {
    book.list = book.list.filter(o => !(o.type === 'forced_march' && o.army === a.id));
    if (on !== a.forced_march) book.list.push({ type: 'forced_march', army: a.id, on });
    const r = on ? rules().forced_march_range : rules().move_range;
    if (!rules().standing_marches) book.list = book.list.filter(o => !(o.type === 'move' && o.army === a.id && o.path.length > r && ++dropped));
  });
  if (dropped) hooks.toast('Der Zugbefehl war für diese Reichweite zu lang und wurde entfernt.');
}
export function undoLast() {
  if (!undo.length) return false;
  book.list = JSON.parse(undo.pop()); check = null;
  hooks.onChange(); save();
  return true;
}

async function save() {
  const n = ++seq; inflight++;
  try {
    const r = await api.putOrders(ctx.gid, ctx.token, book.list);
    if (n !== seq) return;
    book.errors = r.errors || [];
    const chk = check; check = null;
    const i = chk ? book.list.indexOf(chk) : -1;
    if (i >= 0 && (book.errors[i] || []).length) {
      hooks.toast(book.errors[i].join(' '));
      book.list = JSON.parse(undo.pop()); book.errors = [];
      hooks.onChange(); save();
      return;
    }
    hooks.onChange();
  } catch (e) { hooks.toast('Befehle nicht gespeichert: ' + e.message); }
  finally { inflight--; }
}

// ---------- German one-liner per order (order list) ----------
export function describe(o) {
  const army = o.army && ctx.G.armies[o.army];
  const pn = f => { const p = P()[tokenAt(f)]; return p ? p.name : 'Feld'; };
  switch (o.type) {
    case 'move': return army ? `Zug: ${o.count} Div. von ${pn(army.field)} nach ${pn(o.path[o.path.length - 1] || army.field)}${o.path.length > rangeOf(army) ? ` (${Math.ceil(o.path.length / rangeOf(army))} Runden)` : ''}` : 'Zug';
    case 'halt': return `Halt: Armee in ${army ? pn(army.field) : o.army} bleibt stehen`;
    case 'recruit': return `Rekrutieren: +${o.count} in ${pn(o.field)}`;
    case 'disband': return `Abrüsten: −${o.count} in ${army ? pn(army.field) : o.army}`;
    case 'forced_march': return `Gewaltmarsch ${o.on ? 'an' : 'aus'} (${army ? pn(army.field) : o.army})`;
    case 'send_gold': return `${o.amount} Gold an ${pName(o.to)}`;
    case 'give_province': return `Provinz ${(P()[o.province] || {}).name || o.province} an ${pName(o.to)}`;
  }
  return o.type;
}
