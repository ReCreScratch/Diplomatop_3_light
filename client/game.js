// Game screen glue: polling, top bar, order list, board with inline gold sending, last-turn replay.
// Map interaction lives in input.js, the order book in orders.js, drawing in render.js.
import * as R from './render.js';
import * as O from './orders.js';
import * as In from './input.js';
import * as Chat from './chat.js';
import * as Replay from './replay.js';
import * as Session from './session.js';
import * as Stats from './stats.js';
import { api } from './api.js';
import { $, esc, ctx, setState, P, nName, pName, ownArmyAt, fieldName, allianceOf, noAttackOn } from './ctx.js';

let version = null, fetchedAt = 0, sendTo = null, stopped = false;

export function startGame(gid, token) {
  ctx.gid = gid; ctx.token = token;
  O.init({ onChange: refresh, toast });
  Chat.init({ toast, poll: () => poll(true) });
  Session.init({ toast, poll: () => poll(true) });
  In.init({ toast, onEscape: () => { if (Replay.active()) Replay.skip(); } });
  Replay.init({ onEnd: () => { R.drawMap(ctx.G); In.clearPreviews(); refresh(); } });
  $('btn-ready').onclick = toggleReady;
  $('winbar').onclick = e => { if (e.target.closest('[data-stats]')) Stats.open(); };
  $('board').onclick = onBoardClick;
  $('board').onkeydown = e => { if (e.key === 'Enter' && e.target.id === 'b-amt') sendGold(); };
  $('board').oninput = e => { if (e.target.id === 'b-amt') clampAmount(e.target); };
  $('olist').onclick = e => { const h = e.target.closest('[data-halt]'); if (h) { O.add({ type: 'halt', army: h.dataset.halt }); return; } const d = e.target.closest('[data-del]'); if (d) O.removeAt(+d.dataset.del); };
  $('olist').onmouseover = e => { const li = e.target.closest('[data-i]'); R.focusOrder(li ? +li.dataset.i : null); };
  $('olist').onmouseleave = () => R.focusOrder(null);
  $('replay').onclick = onReplayClick;
  setInterval(() => { tickTimer(); Session.tick(); }, 1000);
  (function loop() { if (!stopped) poll().finally(() => setTimeout(loop, 2000)); })();
}

async function poll(force) {
  try {
    const v = await api.state(ctx.gid, ctx.token, force ? null : version);
    $('conn').textContent = ''; $('conn').className = 'msg';
    if (v.changed !== false) apply(v);
  } catch (e) {
    if (e.message === 'Ungültiger Token.') { gone(); return; }
    $('conn').textContent = 'Verbindung: ' + e.message; $('conn').className = 'msg err';
  }
}
// The token was replaced (rejoin elsewhere) or the host removed this player: stop polling and say so.
function gone() {
  stopped = true;
  document.body.insertAdjacentHTML('beforeend', '<div id="gone"><div><h2>Zugang beendet</h2><p>Dein Zugang gilt nicht mehr – du wurdest vom Spielleiter entfernt, oder du bist auf einem anderen Gerät wieder beigetreten.</p>' +
    `<a href="?game=${encodeURIComponent(ctx.gid)}">Zur Startseite des Spiels</a></div></div>`);
}

function apply(v) {
  const newTurn = !ctx.G || ctx.G.turn !== v.turn;
  setState(v); version = v.version; fetchedAt = Date.now();
  O.fromServer(v.my_orders || [], v.order_errors || []);
  if (newTurn) { O.newTurn(); sendTo = null; In.reset(); }
  if (!Replay.active()) { R.drawMap(v); In.clearPreviews(); }  // a running replay owns the map; onEnd redraws it
  refresh();
  Chat.update();
  Session.update();
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
  $('tb-gold').innerHTML = G.me ? `<span class="lbl">Gold</span><span class="val"><b>${G.my_gold}</b> → <b class="${b.gold < 0 ? 'bad' : ''}">${b.gold}</b></span>` : '';
  $('tb-rec').innerHTML = G.me ? `<span class="lbl">Rekruten</span><span class="val"><b>${b.recruits}/${b.limit}</b></span>` : '';
  const c = t => L.filter(o => o.type === t).length;
  const parts = [[c('move'), 'Zug', 'Züge'], [c('recruit'), 'Rekrutierung', 'Rekrutierungen'], [c('disband'), 'Abrüstung', 'Abrüstungen'],
    [c('forced_march'), 'Gewaltmarsch', 'Gewaltmärsche'], [c('halt'), 'Halt', 'Halts'], [c('send_gold') + c('give_province') + c('buy'), 'Überweisung', 'Überweisungen'],
    [c('no_attack') + c('invite') + c('accept') + c('leave') + c('offer_sale'), 'Diplomatiebefehl', 'Diplomatiebefehle']]
    .filter(p => p[0]).map(p => `${p[0]} ${p[0] === 1 ? p[1] : p[2]}`);
  const sum = parts.length ? parts.join(', ') : 'keine';
  $('tb-sum').innerHTML = !G.me ? '' : `<span class="lbl">Befehle</span><span class="val">${esc(sum)}</span>`;
  $('tb-sum').title = G.me ? sum : '';
  const rd = G.ready && G.ready[G.me], btn = $('btn-ready');
  btn.textContent = rd ? 'Bereit ✓' : 'Bereit'; btn.title = rd ? 'Bereit zurücknehmen' : 'Runde beenden: ich bin fertig'; btn.hidden = !G.me || !!G.winner;
  renderVictory();
  const idle = Object.values(G.armies).filter(a => ownArmyAt(a.field) && O.movableLeft(a) > 0 && !O.hasOrder(a) && !O.marching(a)).length;
  $('tb-idle').textContent = idle && !rd ? `⚠ ${idle} ohne Befehl` : '';
  $('tb-idle').title = idle && !rd ? `${idle} ${idle === 1 ? 'Armee' : 'Armeen'} ohne Befehl` : '';
  tickTimer();
}
// victory countdown (who leads, how many resolutions held) and, at the end, the winner (RULES.md 11.5)
function renderVictory() {
  const G = ctx.G, V = G.victory || {}, lead = V.leader, r = G.rules;
  const who = ps => ps.map(nName).join(' + ');
  const el = $('tb-victory'), win = $('winbar');
  el.title = `Sieg: mehr als ${Math.round(r.victory_share_single * 100)} % der Landfelder allein oder mehr als ${Math.round(r.victory_share_alliance * 100)} % im Bündnis `
    + `(Bündnis mindestens ${r.alliance_min_turns} Runden alt), ${r.victory_hold_turns} Runden in Folge gehalten.`;
  el.className = lead ? 'lead' : '';
  el.innerHTML = G.winner ? '' : lead ? `<span class="lbl">Siegbedingung</span><span class="val"><b>${esc(who(lead.players))}</b> ${lead.turns}/${V.need}</span>` : '';
  win.hidden = !G.winner && G.status !== 'finished';
  if (!G.winner && G.status === 'finished') win.innerHTML = 'Spiel beendet – alle Spieler haben das Spiel verlassen.';
  if (G.winner) win.innerHTML = `Spiel beendet – <b>${esc(who(G.winner.players))}</b> ${G.winner.players.length > 1 ? 'gewinnen' : 'gewinnt'} in Runde ${G.winner.turn}${G.winner.alliance ? ' (Bündnis)' : ''}.`;
  if (G.status === 'finished') win.insertAdjacentHTML('beforeend', ' <button data-stats="1" class="primary" title="Auswertung, Karten, Verläufe und Video">Statistik</button>');
}
function tickTimer() {
  const G = ctx.G;
  if (!G) return;
  if (G.timer_remaining == null) { $('tb-timer').textContent = ''; return; }
  const s = G.pause ? G.timer_remaining : Math.max(0, Math.round(G.timer_remaining - (Date.now() - fetchedAt) / 1000));   // frozen during a pause
  $('tb-timer').textContent = (G.pause ? '⏸ ' : '⏱ ') + Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

// ---------- order list (reaches markers hidden under others) ----------
function renderOrderList() {
  const L = O.book.list, M = marchers();
  const marches = M.map(a => `<li class="marsch" data-army="${esc(a.id)}">${esc(`Marsch: ${a.divisions - a.fresh} Div. → ${fieldName(a.route[a.route.length - 1])} (noch ~${O.roundsLeft(a)} Runden)`)} <a data-halt="${esc(a.id)}" title="Halt: Marsch beenden">✕</a></li>`).join('');
  $('olist-panel').hidden = !ctx.G.me; $('olist-count').textContent = L.length + M.length || '';
  $('olist').innerHTML = L.length || M.length ? '<ul>' + marches + L.map((o, i) => {
    const er = (O.book.errors[i] || []).join(' ');
    return `<li data-i="${i}" class="${er ? 'bad' : ''}" title="${esc(er)}">${esc(O.describe(o))}${er ? ' – ' + esc(er) : ''} <a data-del="${i}" title="Löschen">✕</a></li>`;
  }).join('') + '</ul>' : '<p class="empty">Noch keine Befehle.</p>';
  R.focusOrder(null);
}

// ---------- board with inline gold field and diplomacy buttons ----------
const pct = x => Math.round(x * 100);
function renderBoard() {
  const G = ctx.G, old = $('b-amt'), keep = old ? { v: old.value, focus: document.activeElement === old } : null;
  if (sendTo && !G.players[sendTo]) sendTo = null;
  const maxSend = O.budget().canSend;
  let h = '<thead><tr><th title="Provinzen">Prov.</th><th title="Zählender Anteil an allen Landfeldern (tatsächlicher Anteil in Klammern). Geschenkte und gekaufte Provinzen zählen erst nach einiger Zeit.">% Land</th><th title="Einkommen pro Runde">Eink.</th><th title="Unterhalt pro Runde">Unt.</th><th title="Armeen">Arm.</th><th title="Divisionen">Div.</th><th title="Schiffe">Sch.</th></tr></thead>';
  for (const r of G.board || []) {
    const pend = O.book.list.map((o, i) => [o, i]).filter(([o]) => (o.type === 'send_gold' || o.type === 'give_province') && o.to === r.player)
      .map(([o, i]) => {
        const er = (O.book.errors[i] || []).join(' ');
        return `<span class="pend ${er ? 'bad' : ''}" title="${esc(er)}">← ${esc(O.describe(o).replace(/ an .*$/, ''))} <a data-del="${i}" title="Löschen">✕</a></span>`;
      }).join('');
    const form = sendTo !== r.player ? '' : maxSend < 1
      ? '<span class="pend bad">Kein Gold übrig</span>'
      : `<span class="sendform">Gold senden: <input id="b-amt" type="number" min="1" max="${maxSend}" value="1"> <button data-send="1">OK</button> <small>max. ${maxSend}</small></span>`;
    const al = r.alliance && G.alliances && G.alliances[r.alliance];
    const badge = al ? ` <span class="ally" title="Bündnis: ${esc(al.members.map(nName).join(' + '))}">Bündnis ${esc(r.alliance.replace(/^\D+/, ''))}</span>` : '';
    h += `<tbody data-p="${r.player}" class="${sendTo === r.player ? 'open' : ''}${r.player === G.me ? ' me' : ''}"><tr class="pn"><td colspan="7"><div class="pname"><span class="sw" style="background:${R.colorOf(r.player)}"></span><b title="${esc(r.name)}">${esc(r.name)}</b> <small class="pn-nat" title="${esc(nName(r.player))}">${esc(nName(r.player))}</small>${badge}${G.me && r.player !== G.me && !r.ai ? ` <button class="gold-btn" data-gold="${r.player}" title="Gold senden">Gold</button>` : ''}</div>${pend}${form}</td></tr>` +
      `<tr class="ps"><td>${r.provinces}</td><td>${pct(r.share_counted ?? r.share)} <small>(${pct(r.share)})</small></td><td>${r.income}</td><td>${r.upkeep}</td><td>${r.armies}</td><td>${r.divisions}</td><td>${r.ships || 0}</td></tr>`;
    if (G.me && r.player !== G.me && !G.winner && !r.ai) h += dipRow(r.player);
    h += '</tbody>';
  }
  $('board').innerHTML = h;
  const nw = $('b-amt');
  if (nw && keep) { nw.value = keep.v; if (keep.focus) nw.focus(); } else if (nw) nw.focus();
}

// Diplomacy buttons under a player's row: do-not-attack toggle, alliance (invite / accept / leave), sale offers.
// A button toggles its pending order (clicking again takes it back).
function dipRow(p) {
  const G = ctx.G, me = G.me, max = G.rules.max_alliance_size, myAl = allianceOf(me), hisAl = allianceOf(p), b = O.budget();
  const btn = (kind, label, on, title = '', attrs = '', off = false) =>
    `<button data-dip="${kind}" data-dp="${esc(p)}" ${attrs} class="${on ? 'on' : ''}" ${off ? 'disabled' : ''} title="${esc(title)}">${label}${on ? ' ✓' : ''}</button>`;
  const pend = (type, pred) => !!O.pendingOrder(type, pred);
  const bits = [];
  const np = O.pendingOrder('no_attack', o => o.to === p), eff = np ? np.on : noAttackOn(me, p);
  bits.push(btn('noatk', 'Nicht angreifen', eff, 'Du greifst diesen Spieler nicht an. Tut er das auch, kämpfen eure Truppen nicht gegeneinander.')
    + (noAttackOn(p, me) ? ` <small>${eff ? 'gegenseitig' : 'er verzichtet auf Angriffe'}</small>` : ''));
  if (myAl && myAl === hisAl) {
    bits.push(btn('leave', 'Austreten', pend('leave', () => true), 'Aus dem Bündnis austreten (wirksam nach dieser Runde).'));
  } else {
    const inv = (G.invitations.incoming || []).find(i => i.from === p);
    if (inv && !myAl) bits.push(btn('accept', 'Annehmen', pend('accept', o => o.from === p), 'Die Einladung zum Bündnis annehmen (gilt nur diese Runde).'));
    const room = myAl ? myAl.members.length < max : max >= 2;
    if (!hisAl && room) bits.push(btn('invite', 'Bündnis anbieten', pend('invite', o => o.to === p), 'Zum Bündnis einladen; der andere kann in der nächsten Runde annehmen.'));
    if ((G.invitations.outgoing || []).some(i => i.to === p)) bits.push('<small>Einladung läuft (nur diese Runde)</small>');
  }
  for (const o of (G.offers.incoming || []).filter(o => o.from === p)) {
    const prov = (P()[o.province] || {}).name || o.province, sel = pend('buy', x => x.province === o.province);
    const poor = !sel && !G.rules.allow_spending_into_debt && b.gold < o.price;
    bits.push(`<span class="offer">Angebot: ${esc(prov)} für ${o.price} Gold ` + btn('buy', 'Kaufen', sel, poor ? 'Nicht genug Gold.' : 'Provinz zu diesem Preis kaufen (bezahlt in der Goldphase).', `data-prov="${esc(o.province)}"`, poor) + '</span>');
  }
  for (const o of (G.offers.outgoing || []).filter(o => o.to === p)) bits.push(`<small>Dein Angebot: ${esc((P()[o.province] || {}).name || o.province)} für ${o.price} Gold (nur diese Runde)</small>`);
  return `<tr class="dip"><td colspan="7"><div class="dipbits">${bits.join(' ')}</div></td></tr>`;
}
function onDip(el) {
  const p = el.dataset.dp, L = O.book.list, kind = el.dataset.dip;
  const idx = (type, pred) => L.findIndex(o => o.type === type && pred(o));
  const toggle = (type, pred, order) => { const i = idx(type, pred); if (i >= 0) O.removeAt(i); else O.add(order); };
  if (kind === 'noatk') {
    const i = idx('no_attack', o => o.to === p), now = noAttackOn(ctx.G.me, p), want = !(i >= 0 ? L[i].on : now);
    if (want === now) { if (i >= 0) O.removeAt(i); } else O.add({ type: 'no_attack', to: p, on: want });   // back to the current state = no order
  }
  else if (kind === 'invite') toggle('invite', o => o.to === p, { type: 'invite', to: p });
  else if (kind === 'accept') toggle('accept', o => o.from === p, { type: 'accept', from: p });
  else if (kind === 'leave') toggle('leave', () => true, { type: 'leave' });
  else if (kind === 'buy') toggle('buy', o => o.province === el.dataset.prov, { type: 'buy', province: el.dataset.prov });
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
  const dip = e.target.closest('[data-dip]');
  if (dip) { if (!dip.disabled) onDip(dip); return; }
  if (e.target.closest('tr.dip')) return;
  if (e.target.closest('[data-send]')) { sendGold(); return; }
  const d = e.target.closest('[data-del]');
  if (d) { O.removeAt(+d.dataset.del); return; }
  if (e.target.closest('.sendform')) return;
  const tr = e.target.closest('tbody[data-p]');
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
