// Game screen glue: polling, top bar, order list, board with inline gold sending, last-turn replay.
// Map interaction lives in input.js, the order book in orders.js, drawing in render.js.
import * as R from './render.js';
import * as O from './orders.js';
import * as In from './input.js';
import * as Chat from './chat.js';
import * as Replay from './replay.js';
import { api } from './api.js';
import { $, esc, ctx, setState, P, nName, pName, ownArmyAt, fieldName } from './ctx.js';

let version = null, fetchedAt = 0, sendTo = null;

export function startGame(gid, token) {
  ctx.gid = gid; ctx.token = token;
  O.init({ onChange: refresh, toast });
  Chat.init({ toast, poll: () => poll(true) });
  In.init({ toast, onEscape: () => { if (Replay.active()) Replay.skip(); } });
  Replay.init({ onEnd: () => { R.drawMap(ctx.G); In.clearPreviews(); refresh(); } });
  $('btn-ready').onclick = toggleReady;
  $('board').onclick = onBoardClick;
  $('board').onkeydown = e => { if (e.key === 'Enter' && e.target.id === 'b-amt') sendGold(); };
  $('board').oninput = e => { if (e.target.id === 'b-amt') clampAmount(e.target); };
  $('olist').onclick = e => { const h = e.target.closest('[data-halt]'); if (h) { O.add({ type: 'halt', army: h.dataset.halt }); return; } const d = e.target.closest('[data-del]'); if (d) O.removeAt(+d.dataset.del); };
  $('olist').onmouseover = e => { const li = e.target.closest('[data-i]'); R.focusOrder(li ? +li.dataset.i : null); };
  $('olist').onmouseleave = () => R.focusOrder(null);
  $('replay').onclick = onReplayClick;
  setInterval(tickTimer, 1000);
  (function loop() { poll().finally(() => setTimeout(loop, 2000)); })();
}

async function poll(force) {
  try {
    const v = await api.state(ctx.gid, ctx.token, force ? null : version);
    $('conn').textContent = ''; $('conn').className = 'msg';
    if (v.changed !== false) apply(v);
  } catch (e) { $('conn').textContent = 'Verbindung: ' + e.message; $('conn').className = 'msg err'; }
}

function apply(v) {
  const newTurn = !ctx.G || ctx.G.turn !== v.turn;
  setState(v); version = v.version; fetchedAt = Date.now();
  O.fromServer(v.my_orders || [], v.order_errors || []);
  if (newTurn) { O.newTurn(); sendTo = null; In.reset(); }
  if (!Replay.active()) { R.drawMap(v); In.clearPreviews(); }  // a running replay owns the map; onEnd redraws it
  refresh();
  Chat.update();
  Replay.maybeAuto(v);
  renderReplay();
}

function refresh() {
  if (!Replay.active()) { R.showArrows(O.book.list, O.book.errors, ctx.G); drawStanding(); In.update(); }
  renderTop(); renderOrderList(); renderBoard(); renderReplay();
}

function drawStanding() {
  R.showStanding(Object.values(ctx.G.armies).filter(a => a.owner === ctx.G.me && O.marching(a)).map(a => [a.field, ...a.route]));
}
const marchers = () => Object.values(ctx.G.armies).filter(a => a.owner === ctx.G.me && O.marching(a));

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 3500);
}

async function toggleReady() {
  const G = ctx.G, want = !(G.ready && G.ready[G.me]);
  try { await api.ready(ctx.gid, ctx.token, want); G.ready[G.me] = want; renderTop(); poll(true); } catch (e) { toast(e.message); }
}

// ---------- top bar ----------
function renderTop() {
  const G = ctx.G, b = O.budget(), L = O.book.list;
  $('tb-turn').textContent = 'Runde ' + G.turn;
  $('tb-order').innerHTML = G.player_order.map(p =>
    `<span class="chip${p === G.me ? ' me' : ''}${G.ready[p] ? ' rdy' : ''}" style="border-color:${R.colorOf(p)}" title="${esc(nName(p))}">${G.ready[p] ? '✓ ' : ''}${esc(pName(p))}</span>`).join('');
  $('tb-gold').innerHTML = `Gold <b>${G.my_gold}</b> → <b class="${b.gold < 0 ? 'bad' : ''}">${b.gold}</b>`;
  $('tb-rec').innerHTML = `Rekruten <b>${b.recruits}/${b.limit}</b>`;
  const c = t => L.filter(o => o.type === t).length;
  const parts = [[c('move'), 'Zug', 'Züge'], [c('recruit'), 'Rekrutierung', 'Rekrutierungen'], [c('disband'), 'Abrüstung', 'Abrüstungen'],
    [c('forced_march'), 'Gewaltmarsch', 'Gewaltmärsche'], [c('halt'), 'Halt', 'Halts'], [c('send_gold') + c('give_province'), 'Überweisung', 'Überweisungen']]
    .filter(p => p[0]).map(p => `${p[0]} ${p[0] === 1 ? p[1] : p[2]}`);
  $('tb-sum').textContent = parts.length ? parts.join(', ') : 'keine Befehle';
  const rd = G.ready && G.ready[G.me], btn = $('btn-ready');
  btn.textContent = rd ? 'Bereit ✓ (zurücknehmen)' : 'Bereit'; btn.hidden = !G.me;
  const idle = Object.values(G.armies).filter(a => ownArmyAt(a.field) && O.movableLeft(a) > 0 && !O.hasOrder(a) && !O.marching(a)).length;
  $('tb-idle').textContent = idle && !rd ? `${idle} ${idle === 1 ? 'Armee' : 'Armeen'} ohne Befehl` : '';
  tickTimer();
}
function tickTimer() {
  const G = ctx.G;
  if (!G) return;
  if (G.timer_remaining == null) { $('tb-timer').textContent = ''; return; }
  const s = Math.max(0, Math.round(G.timer_remaining - (Date.now() - fetchedAt) / 1000));
  $('tb-timer').textContent = '⏱ ' + Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

// ---------- order list (reaches markers hidden under others) ----------
function renderOrderList() {
  const L = O.book.list, M = marchers();
  const marches = M.map(a => `<li class="marsch" data-army="${esc(a.id)}">${esc(`Marsch: ${a.divisions - a.fresh} Div. → ${fieldName(a.route[a.route.length - 1])} (noch ~${O.roundsLeft(a)} Runden)`)} <a data-halt="${esc(a.id)}" title="Halt: Marsch beenden">✕</a></li>`).join('');
  $('olist').innerHTML = L.length || M.length ? '<h4>Befehle</h4><ul>' + marches + L.map((o, i) => {
    const er = (O.book.errors[i] || []).join(' ');
    return `<li data-i="${i}" class="${er ? 'bad' : ''}" title="${esc(er)}">${esc(O.describe(o))}${er ? ' – ' + esc(er) : ''} <a data-del="${i}" title="Löschen">✕</a></li>`;
  }).join('') + '</ul>' : '';
  R.focusOrder(null);
}

// ---------- board with inline gold field ----------
function renderBoard() {
  const G = ctx.G, old = $('b-amt'), keep = old ? { v: old.value, focus: document.activeElement === old } : null;
  if (sendTo && !G.players[sendTo]) sendTo = null;
  const maxSend = O.budget().canSend;
  let h = '<tr><th>Spieler</th><th>Prov.</th><th title="Anteil an allen Landfeldern">% Land</th><th>Eink.</th><th>Unterh.</th><th>Arm.</th><th>Div.</th></tr>';
  for (const r of G.board || []) {
    const pend = O.book.list.map((o, i) => [o, i]).filter(([o]) => (o.type === 'send_gold' || o.type === 'give_province') && o.to === r.player)
      .map(([o, i]) => {
        const er = (O.book.errors[i] || []).join(' ');
        return `<span class="pend ${er ? 'bad' : ''}" title="${esc(er)}">← ${esc(O.describe(o).replace(/ an .*$/, ''))} <a data-del="${i}" title="Löschen">✕</a></span>`;
      }).join('');
    const form = sendTo !== r.player ? '' : maxSend < 1
      ? '<span class="pend bad">Kein Gold übrig</span>'
      : `<span class="sendform">Gold senden: <input id="b-amt" type="number" min="1" max="${maxSend}" value="1"> <button data-send="1">OK</button> <small>max. ${maxSend}</small></span>`;
    h += `<tr data-p="${r.player}" class="${sendTo === r.player ? 'open' : ''}"><td><span class="sw" style="background:${R.colorOf(r.player)}"></span><b>${esc(r.name)}</b> <small>${esc(nName(r.player))}</small>${r.player !== G.me ? ` <button class="gold-btn" data-gold="${r.player}" title="Gold senden">Gold</button>` : ''}${pend}${form}</td>` +
      `<td>${r.provinces}</td><td>${Math.round(r.share * 100)}</td><td>${r.income}</td><td>${r.upkeep}</td><td>${r.armies}</td><td>${r.divisions}</td></tr>`;
  }
  $('board').innerHTML = h;
  const nw = $('b-amt');
  if (nw && keep) { nw.value = keep.v; if (keep.focus) nw.focus(); } else if (nw) nw.focus();
}
function clampAmount(el) {
  const max = O.budget().canSend;
  if (+el.value > max) el.value = max;
}
function sendGold() {
  const el = $('b-amt'); if (!el) return;
  clampAmount(el);
  const amount = Math.floor(+el.value);
  if (!(amount >= 1)) return;
  const to = sendTo; sendTo = null;
  O.add({ type: 'send_gold', to, amount });
}
function onBoardClick(e) {
  if (e.target.closest('[data-send]')) { sendGold(); return; }
  const d = e.target.closest('[data-del]');
  if (d) { O.removeAt(+d.dataset.del); return; }
  if (e.target.closest('.sendform')) return;
  const tr = e.target.closest('tr[data-p]');
  if (!tr || !ctx.G.me || tr.dataset.p === ctx.G.me) return;
  if (e.target.closest('[data-gold]')) { sendTo = sendTo === tr.dataset.p ? null : tr.dataset.p; renderBoard(); return; }
  Chat.openChannel(tr.dataset.p);
}

// ---------- last turn replay (cinematic: replay.js) ----------
function renderReplay() {
  const box = $('replay'), lt = ctx.G.last_turn;
  box.innerHTML = Replay.canReplay(lt) && !Replay.active() ? `<button data-r="open">Letzte Runde ansehen (${lt.turn})</button>` : '';
}
function onReplayClick(e) {
  if (e.target.dataset.r === 'open' && Replay.canReplay(ctx.G.last_turn)) { Replay.start(ctx.G.last_turn); renderReplay(); }
}
