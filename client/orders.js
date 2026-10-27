// Own order list: budget, validation helpers, undo stack and saving. The server stays the judge:
// after every PUT an order that just got an error is taken out again and the German text is shown.
import { api } from './api.js';
import { ctx, rules, P, tokenAt, movable, pName, isFleet, isSea } from './ctx.js';

export const book = { list: [], errors: [] };
let undo = [], inflight = 0, seq = 0, check = null;
let hooks = { onChange() {}, toast() {} };

export const init = h => { hooks = h; };
export function fromServer(list, errors) { if (!inflight) { book.list = list; book.errors = errors; } }
export function newTurn() { undo = []; check = null; }

// ---------- derived numbers (everything from state.rules / my_gold / my_recruit_limit) ----------
export function budget() {
  const r = rules(), G = ctx.G, debt = r.allow_spending_into_debt;
  let recruits = 0, ships = 0, sent = 0;
  for (const o of book.list) {
    if (o.type === 'recruit') recruits += o.count; else if (o.type === 'build_ship') ships += o.count; else if (o.type === 'send_gold') sent += o.amount;
    else if (o.type === 'buy') sent += (offerFor(o.province) || { price: 0 }).price;   // bought provinces are paid like sent gold
  }
  const gold = G.my_gold - recruits * r.division_cost - ships * r.ship_cost - sent, limit = G.my_recruit_limit ?? 0;
  const recLeft = Math.max(0, limit - recruits - ships);   // divisions and ships share the limit
  return {
    gold, recruits: recruits + ships, limit, recLeft,
    canRecruit: Math.min(recLeft, debt ? Infinity : Math.floor(Math.max(0, gold) / r.division_cost)),
    canBuild: Math.min(recLeft, debt ? Infinity : Math.floor(Math.max(0, gold) / r.ship_cost)),
    canSend: debt ? Infinity : Math.floor(Math.max(0, gold)),
  };
}
const sum = (type, army, f = 'count') => book.list.reduce((s, o) => s + (o.type === type && o.army === army ? o[f] : 0), 0);
export const moveOf = id => book.list.find(o => o.type === 'move' && o.army === id);
export const fmOn = a => { let on = a.forced_march; for (const o of book.list) if (o.type === 'forced_march' && o.army === a.id) on = o.on; return on; };
// linked partner after this turn's link / unlink orders
export function partnerOf(a) {
  let id = a.linked || null;
  for (const o of book.list) {
    if (o.type === 'link') { if (o.fleet === a.id) id = o.army; else if (o.army === a.id) id = o.fleet; else if (id === o.fleet || id === o.army) id = null; }
    if (o.type === 'unlink' && (o.army === a.id || o.army === id)) id = null;
  }
  return id ? ctx.G.armies[id] || null : null;
}
// a linked pair moves together; only an army that lands moves alone (engine: moves_as_group)
export const groupMove = (a, path) => !!partnerOf(a) && (isFleet(a) || (path && path.length > 0 && isSea(path[0])));
// fields per turn where the unit stands (engine: turn_range)
export function rangeOf(a, group = false) {
  const r = rules();
  if (group) return r.fleet_linked_move_range;
  if (isFleet(a)) return r.fleet_move_range;
  if (isSea(a.field)) return r.transport_move_range;
  return fmOn(a) ? r.forced_march_range : r.move_range;
}
// path steps done this turn: range, and putting to sea or landing ends the move (engine: this_turn)
export function thisTurn(a, path) {
  const sea = isSea(a.field), n = Math.min(path.length, rangeOf(a, groupMove(a, path)));
  for (let i = 0; i < n; i++) if (isSea(path[i]) !== sea) return i + 1;
  return n;
}
// several moves may split one army (G56); together they use at most its movable divisions
export const movableLeft = a => Math.max(0, movable(a) - sum('disband', a.id) - sum('move', a.id));
export const disbandMax = a => Math.max(0, a.divisions - sum('disband', a.id) - sum('move', a.id));
export const halted = a => book.list.some(o => o.type === 'halt' && o.army === a.id);
// standing march (army.route from the server) still in force next turn: not replaced by a new move, not halted
export const marching = a => !!(a.route && a.route.length) && !moveOf(a.id) && !halted(a);
export const roundsLeft = a => Math.ceil(a.route.length / rangeOf(a));
export const hasOrder = a => book.list.some(o => o.army === a.id);
export const gifted = prov => book.list.some(o => o.type === 'give_province' && o.province === prov);
export const offered = prov => book.list.some(o => o.type === 'offer_sale' && o.province === prov);
// diplomacy: the offer / invitation made to me last turn (server view), and my pending order of a kind
export const offerFor = prov => ((ctx.G.offers || {}).incoming || []).find(o => o.province === prov) || null;
export const pendingOrder = (type, pred = () => true) => book.list.find(o => o.type === type && pred(o)) || null;
const SINGLE = { no_attack: o => o.to, invite: o => o.to, accept: () => '', leave: () => '', offer_sale: o => o.province, buy: o => o.province };

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
    if (SINGLE[o.type]) book.list = book.list.filter(x => !(x.type === o.type && SINGLE[o.type](x) === SINGLE[o.type](o)));   // a new one replaces the old
    const m = o.type === 'move' ? merge('move', x => x.army === o.army && JSON.stringify(x.path) === JSON.stringify(o.path))
      : o.type === 'recruit' || o.type === 'build_ship' ? merge(o.type, x => x.field[0] === o.field[0] && x.field[1] === o.field[1])
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
  const pn = f => { const p = P()[tokenAt(f)]; return p ? p.name : isSea(f) ? 'Meer' : 'Feld'; };
  switch (o.type) {
    case 'move': {
      if (!army) return 'Zug';
      const r = rangeOf(army, groupMove(army, o.path)), what = isFleet(army) ? 'Schiffe' : 'Div.';
      return `Zug: ${o.count} ${what} von ${pn(army.field)} nach ${pn(o.path[o.path.length - 1] || army.field)}${o.path.length > r ? ` (ca. ${Math.ceil(o.path.length / r)} Runden)` : ''}`;
    }
    case 'build_ship': return `Schiffe bauen: +${o.count} bei ${pn(o.field)}`;
    case 'link': return `Flotte und Armee bei ${army ? pn(army.field) : pn((ctx.G.armies[o.fleet] || {}).field || [0, 0])} verbinden`;
    case 'unlink': return `Verbindung bei ${army ? pn(army.field) : o.army} lösen`;
    case 'halt': return `Halt: Armee in ${army ? pn(army.field) : o.army} bleibt stehen`;
    case 'recruit': return `Rekrutieren: +${o.count} in ${pn(o.field)}`;
    case 'disband': return `Abrüsten: −${o.count} in ${army ? pn(army.field) : o.army}`;
    case 'forced_march': return `Gewaltmarsch ${o.on ? 'an' : 'aus'} (${army ? pn(army.field) : o.army})`;
    case 'send_gold': return `${o.amount} Gold an ${pName(o.to)}`;
    case 'give_province': return `Provinz ${(P()[o.province] || {}).name || o.province} an ${pName(o.to)}`;
    case 'no_attack': return o.on ? `Nicht angreifen: ${pName(o.to)}` : `Angriffsverzicht gegenüber ${pName(o.to)} zurücknehmen`;
    case 'invite': return `Bündnis anbieten: ${pName(o.to)}`;
    case 'accept': return `Bündnis annehmen: ${pName(o.from)}`;
    case 'leave': return 'Aus dem Bündnis austreten';
    case 'offer_sale': return `Provinz ${(P()[o.province] || {}).name || o.province} verkaufen an ${pName(o.to)} für ${o.price} Gold`;
    case 'buy': { const sale = offerFor(o.province); return `Provinz ${(P()[o.province] || {}).name || o.province} kaufen${sale ? ` von ${pName(sale.from)} für ${sale.price} Gold` : ''}`; }
  }
  return o.type;
}
