// Game screen: polling, local order list, panels, move entry, board, replay. Drawing goes through render.js.
import * as R from './render.js';
import { api } from './api.js';
import { neighbours, parseGrid, key } from './hex.js';

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const same = (a, b) => !!a && !!b && a[0] === b[0] && a[1] === b[1];
const isField = x => Array.isArray(x) && x.length === 2 && typeof x[0] === 'number';

let gid, token, G = null, grid = null, gridMap = null, armyIdx = new Map();
let orders = [], errors = [], inflight = 0, seq = 0, version = null, fetchedAt = 0;
let sel = null, sendTo = null, mv = null, replay = null, hoverF = null;
let pv = new Map(), pvTimer = null;

export function startGame(gid_, token_) {
  gid = gid_; token = token_;
  R.init($('map'), { onField, onHover, onMarker });
  $('btn-ready').onclick = toggleReady;
  $('panel').onclick = onPanelClick;
  $('panel').onchange = onPanelChange;
  $('board').onclick = onBoardClick;
  $('replay').onclick = onReplayClick;
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { if (mv) cancelMove(); else closePanel(); } });
  setInterval(tickTimer, 1000);
  (function loop() { poll().finally(() => setTimeout(loop, 2000)); })();
}

async function poll(force) {
  try {
    const v = await api.state(gid, token, force ? null : version);
    $('conn').textContent = ''; $('conn').className = 'msg';
    if (v.changed !== false) apply(v);
  } catch (e) { $('conn').textContent = 'Verbindung: ' + e.message; $('conn').className = 'msg err'; }
}

function apply(v) {
  const newTurn = !G || G.turn !== v.turn;
  G = v; version = v.version; fetchedAt = Date.now(); pv.clear();
  if (gridMap !== v.map.name) { grid = parseGrid(v.map.grid); gridMap = v.map.name; }
  armyIdx = new Map(Object.values(v.armies).map(a => [key(a.field), a]));
  if (!inflight) { orders = v.my_orders || []; errors = v.order_errors || []; }
  if (newTurn) { mv = null; sel = null; sendTo = null; replay = null; R.clearHighlight(); R.showDraft(null); }
  R.drawMap(v);
  refreshAll();
}

function refreshAll() {
  R.showArrows(orders, errors, G);
  renderTop(); renderBoard(); renderPanel(); renderReplay();
}

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 3500);
}

// ---------- derived data ----------
const P = () => G.map.provinces;
const tokenAt = f => (grid[f[1]] || [])[f[0]];
const passable = f => !!P()[tokenAt(f)];
const armyAt = f => armyIdx.get(key(f));
const rules = () => G.rules;
const movable = a => rules().recruits_can_move_same_turn ? a.divisions : a.divisions - (a.fresh || 0);
const fmOn = a => { let on = a.forced_march; for (const o of orders) if (o.type === 'forced_march' && o.army === a.id) on = o.on; return on; };
const rangeOf = a => fmOn(a) ? rules().forced_march_range : rules().move_range;
const goldCost = () => orders.reduce((s, o) => s + (o.type === 'recruit' ? o.count * rules().division_cost : o.type === 'send_gold' ? o.amount : 0), 0);
const pName = pid => (G.players[pid] && G.players[pid].name) || pid;
const nName = pid => (G.map.nations[pid] && G.map.nations[pid].name) || pid;

function bfs(from, to, avoidEnemy = true) {
  const goal = key(to);
  if (key(from) === goal) return [];
  const prev = new Map([[key(from), null]]);
  let q = [from];
  while (q.length) {
    const nq = [];
    for (const f of q) for (const n of neighbours(f[0], f[1])) {
      const k = key(n);
      if (prev.has(k) || !passable(n)) continue;
      const ar = armyIdx.get(k);
      if (avoidEnemy && ar && ar.owner !== G.me && k !== goal) continue;
      prev.set(k, f);
      if (k === goal) {
        const path = []; let c = n;
        while (c && key(c) !== key(from)) { path.unshift(c); c = prev.get(key(c)); }
        return path;
      }
      nq.push(n);
    }
    q = nq;
  }
  return avoidEnemy ? bfs(from, to, false) : null;
}

// ---------- orders ----------
function changed() { refreshAll(); save(); }
async function save() {
  const n = ++seq; inflight++;
  try {
    const r = await api.putOrders(gid, token, orders);
    if (n === seq) { errors = r.errors || []; refreshAll(); }
  } catch (e) { toast('Befehle nicht gespeichert: ' + e.message); }
  finally { inflight--; }
}
function addOrder(o) {
  if (o.type === 'move') orders = orders.filter(x => !(x.type === 'move' && x.army === o.army));
  orders.push(o); changed();
}
function onMarker(i) { orders.splice(i, 1); changed(); }
async function toggleReady() {
  const want = !(G.ready && G.ready[G.me]);
  try { await api.ready(gid, token, want); G.ready[G.me] = want; renderTop(); poll(true); } catch (e) { toast(e.message); }
}

// ---------- top bar ----------
function renderTop() {
  $('tb-turn').textContent = 'Runde ' + G.turn;
  $('tb-order').innerHTML = G.player_order.map(p =>
    `<span class="chip${p === G.me ? ' me' : ''}${G.ready[p] ? ' rdy' : ''}" style="border-color:${R.colorOf(p)}" title="${esc(nName(p))}">${G.ready[p] ? '✓ ' : ''}${esc(pName(p))}</span>`).join('');
  const left = G.my_gold - goldCost();
  $('tb-gold').innerHTML = `Gold: <b>${G.my_gold}</b> (nach Befehlen: <b class="${left < 0 ? 'bad' : ''}">${left}</b>)`;
  const c = t => orders.filter(o => o.type === t).length;
  const parts = [[c('move'), 'Zug', 'Züge'], [c('recruit'), 'Rekrutierung', 'Rekrutierungen'], [c('disband'), 'Abrüstung', 'Abrüstungen'],
    [c('forced_march'), 'Gewaltmarsch', 'Gewaltmärsche'], [c('send_gold') + c('give_province'), 'Überweisung', 'Überweisungen']]
    .filter(p => p[0]).map(p => `${p[0]} ${p[0] === 1 ? p[1] : p[2]}`);
  $('tb-sum').textContent = 'Befehle: ' + (parts.length ? parts.join(', ') : 'keine');
  const b = $('btn-ready'), rd = G.ready && G.ready[G.me];
  b.textContent = rd ? 'Bereit ✓ (zurücknehmen)' : 'Bereit'; b.hidden = !G.me;
  tickTimer();
}
function tickTimer() {
  if (!G) return;
  if (G.timer_remaining == null) { $('tb-timer').textContent = ''; return; }
  const s = Math.max(0, Math.round(G.timer_remaining - (Date.now() - fetchedAt) / 1000));
  $('tb-timer').textContent = '⏱ ' + Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

// ---------- board ----------
function renderBoard() {
  const pend = {};
  orders.forEach((o, i) => { if (o.type === 'send_gold' || o.type === 'give_province') (pend[o.to] = pend[o.to] || []).push([o, i]); });
  let h = '<tr><th>Spieler</th><th>Prov.</th><th>%</th><th>Eink.</th><th>Unterh.</th><th>Arm.</th><th>Div.</th></tr>';
  for (const r of G.board || []) {
    const p = (pend[r.player] || []).map(([o, i]) => {
      const er = (errors[i] || []).join(' ');
      const t = o.type === 'send_gold' ? `+${o.amount} Gold` : `Provinz ${esc((P()[o.province] || {}).name || o.province)}`;
      return `<span class="pend ${er ? 'bad' : ''}" title="${esc(er)}">← ${t} <a data-del="${i}" title="Löschen">✕</a></span>`;
    }).join('');
    h += `<tr data-p="${r.player}"><td><span class="sw" style="background:${R.colorOf(r.player)}"></span><b>${esc(r.name)}</b> <small>${esc(nName(r.player))}</small>${p}</td>` +
      `<td>${r.provinces}</td><td>${Math.round(r.share * 100)}</td><td>${r.income}</td><td>${r.upkeep}</td><td>${r.armies}</td><td>${r.divisions}</td></tr>`;
  }
  $('board').innerHTML = h;
}
function onBoardClick(e) {
  const d = e.target.closest('[data-del]');
  if (d) { onMarker(+d.dataset.del); return; }
  const tr = e.target.closest('tr[data-p]');
  if (!tr || !G.me || tr.dataset.p === G.me) return;
  cancelMove(); sel = null; R.clearHighlight('sel'); sendTo = tr.dataset.p; renderPanel();
}

// ---------- panel ----------
function closePanel() { sel = null; sendTo = null; R.clearHighlight('sel'); renderPanel(); }
function onField(f) {
  if (mv) return onMoveClick(f);
  if (!G.me) return;
  const tok = tokenAt(f), prov = P()[tok], a = armyAt(f);
  if (!((a && a.owner === G.me) || (prov && G.owners[tok] === G.me))) { closePanel(); return; }
  sendTo = null; sel = f; R.clearHighlight('sel'); R.highlight([f], 'sel'); renderPanel();
}
function renderPanel() {
  const el = $('panel');
  if (mv) { el.hidden = false; el.innerHTML = movePanel(); return; }
  if (sendTo) {
    el.hidden = false;
    el.innerHTML = `<h3>Gold senden an ${esc(pName(sendTo))}</h3><div class="row"><input id="p-amt" type="number" min="1" value="1"> Gold ` +
      `<button data-act="send">Senden</button><button data-act="close">Abbrechen</button></div>`;
    return;
  }
  if (!sel) { el.hidden = true; el.innerHTML = ''; return; }
  const tok = tokenAt(sel), prov = P()[tok], a = armyAt(sel), own = a && a.owner === G.me ? a : null;
  const ownProv = prov && G.owners[tok] === G.me, isCap = ownProv && same(prov.capital, sel);
  if (!own && !ownProv) { closePanel(); return; }
  const lim = G.my_recruit_limit ?? 0;
  const used = orders.reduce((s, o) => s + (o.type === 'recruit' ? o.count : 0), 0);
  let h = `<h3>${prov ? esc(prov.name) + ' · ' + esc(prov.capital_name) : 'Feld'} <button data-act="close" style="float:right">✕</button></h3>`;
  if (own) h += `<div>Armee ${esc(own.id)}: ${own.divisions} Div.${own.fresh ? ` (${own.fresh} neu, nicht beweglich)` : ''}</div>`;
  if (own || (isCap && !a)) {
    h += `<div class="row">Rekrutieren <input id="p-rec" type="number" min="1" value="1"> <button data-act="rec">+ Rekrutieren</button>` +
      `<small>${rules().division_cost} Gold je Div., noch ${Math.max(0, lim - used)} möglich</small></div>`;
  }
  if (own) {
    h += `<div class="row">Abrüsten <input id="p-dis" type="number" min="1" max="${own.divisions}" value="1"> <button data-act="dis">− Abrüsten</button>` +
      `<small>${rules().disband_refund} Gold je Div.</small></div>`;
    h += `<div class="row"><label><input type="checkbox" id="p-fm" ${fmOn(own) ? 'checked' : ''}> Gewaltmarsch</label>` +
      `<small>Reichweite ${rangeOf(own)}</small></div>`;
    const m = movable(own);
    h += m > 0 ? `<div class="row">Ziehen <input id="p-mv" type="number" min="1" max="${m}" value="${m}"> von ${m} <button data-act="move">Ziehen…</button></div>`
      : '<div class="row"><small>Keine beweglichen Divisionen.</small></div>';
  }
  if (ownProv) {
    const others = Object.keys(G.players).filter(p => p !== G.me);
    if (others.length) h += `<div class="row"><select id="p-gift">${others.map(p => `<option value="${p}">${esc(pName(p))}</option>`).join('')}</select> ` +
      `<button data-act="gift">Provinz verschenken</button></div>`;
  }
  el.hidden = false; el.innerHTML = h;
}
const num = id => Math.max(1, Math.floor(+$(id).value || 1));
function onPanelChange(e) {
  if (e.target.id !== 'p-fm') return;
  const a = armyAt(sel); if (!a) return;
  orders = orders.filter(o => !(o.type === 'forced_march' && o.army === a.id));
  if (e.target.checked !== a.forced_march) orders.push({ type: 'forced_march', army: a.id, on: e.target.checked });
  changed();
}
function onPanelClick(e) {
  const act = e.target.dataset.act; if (!act) return;
  const a = sel && armyAt(sel);
  if (act === 'close') closePanel();
  else if (act === 'rec') addOrder({ type: 'recruit', field: sel, count: num('p-rec') });
  else if (act === 'dis' && a) addOrder({ type: 'disband', army: a.id, count: Math.min(a.divisions, num('p-dis')) });
  else if (act === 'gift') addOrder({ type: 'give_province', province: tokenAt(sel), to: $('p-gift').value });
  else if (act === 'send') { addOrder({ type: 'send_gold', to: sendTo, amount: num('p-amt') }); closePanel(); }
  else if (act === 'move' && a) startMove(a, Math.min(movable(a), num('p-mv')));
  else if (act === 'mv-ok') confirmMove();
  else if (act === 'mv-back') { mv.wps.pop(); rebuildPath(); }
  else if (act === 'mv-cancel') cancelMove();
}

// ---------- move entry ----------
function startMove(a, count) { mv = { army: a.id, from: a.field, count, wps: [], path: [] }; drawDraft(); renderPanel(); }
function cancelMove() { if (!mv) return; mv = null; R.showDraft(null); $('ib-preview').textContent = ''; renderPanel(); }
const mvArmy = () => G.armies[mv.army];
function rebuildPath() {
  let at = mv.from; mv.path = [];
  for (const w of mv.wps) { mv.path = mv.path.concat(bfs(at, w) || []); at = w; }
  drawDraft(); renderPanel();
}
function onMoveClick(f) {
  if (!passable(f)) { toast('Dieses Feld ist nicht passierbar.'); return; }
  const last = mv.wps[mv.wps.length - 1];
  if (same(last, f)) { confirmMove(); return; }
  const seg = bfs(last || mv.from, f);
  if (!seg) { toast('Kein Weg dorthin.'); return; }
  if (!seg.length) return;
  mv.wps.push(f); mv.path = mv.path.concat(seg); drawDraft(); renderPanel();
}
function drawDraft(extra = []) {
  if (!mv) return;
  const path = mv.path.concat(extra);
  R.showDraft([mv.from, ...path], path.length <= rangeOf(mvArmy()), mv.wps);
}
function movePanel() {
  const a = mvArmy(), r = rangeOf(a), n = mv.path.length, bad = n > r;
  return `<h3>Ziehen: Armee ${esc(a.id)}, ${mv.count} Div.</h3>` +
    `<div>${n ? `Weg: <b class="${bad ? 'bad' : ''}">${n}</b> Felder (max. ${r})` : 'Ziel anklicken. Weitere Klicks = Zwischenziele (Umwege).'}</div>` +
    `<div class="row"><button class="primary" data-act="mv-ok" ${!n || bad ? 'disabled' : ''}>Bestätigen</button>` +
    `<button data-act="mv-back" ${n ? '' : 'disabled'}>Zurück</button><button data-act="mv-cancel">Abbrechen</button></div>` +
    `<small>Erneuter Klick auf das letzte Ziel bestätigt.</small>`;
}
function confirmMove() {
  const a = mvArmy();
  if (!mv.path.length) return;
  if (mv.path.length > rangeOf(a)) { toast(`Zu weit: maximal ${rangeOf(a)} Felder.`); return; }
  const o = { type: 'move', army: mv.army, count: mv.count, path: mv.path };
  mv = null; R.showDraft(null); $('ib-preview').textContent = ''; addOrder(o); closePanel();
}

// ---------- hover & preview ----------
function onHover(f) {
  hoverF = f;
  if (!f) { $('ib-hover').textContent = ''; if (mv) { drawDraft(); $('ib-preview').textContent = ''; } return; }
  $('ib-hover').textContent = fieldInfo(f);
  if (mv && passable(f)) {
    const seg = bfs(mv.wps[mv.wps.length - 1] || mv.from, f) || [];
    drawDraft(seg);
    const path = mv.path.concat(seg), a = mvArmy();
    if (!path.length) { $('ib-preview').textContent = ''; return; }
    if (path.length > rangeOf(a)) { $('ib-preview').textContent = `Zu weit: ${path.length} Felder, maximal ${rangeOf(a)}.`; return; }
    preview(a.id, mv.count, path);
  }
}
function fieldInfo(f) {
  const tok = tokenAt(f), prov = P()[tok], a = armyAt(f);
  let s;
  if (prov) {
    const o = G.owners[tok];
    s = `${prov.name} (${o ? nName(o) : 'neutral'}) · Hauptstadt ${prov.capital_name} · Einkommen ${prov.income} · Eroberung kostet ${prov.income * rules().conquest_cost_factor} Div.`;
  } else s = tok === '~~' ? 'Meer' : 'Nicht passierbar';
  if (a) s += ` · Armee ${a.id} (${nName(a.owner)}): ${a.divisions} Div.${a.forced_march ? ', Gewaltmarsch' : ''}`;
  return s;
}
function preview(army, count, path) {
  const k = JSON.stringify([army, count, path]), box = $('ib-preview');
  const show = r => { box.className = r.valid ? '' : 'bad'; box.textContent = r.valid ? r.text : (r.errors || []).join(' ') || r.text || ''; };
  clearTimeout(pvTimer);
  if (pv.has(k)) { show(pv.get(k)); return; }
  pvTimer = setTimeout(async () => {
    try {
      const r = await api.preview(gid, token, { army, count, path });
      pv.set(k, r);
      if (mv && JSON.stringify([mv.army, mv.count, mv.path.concat(bfs(mv.wps[mv.wps.length - 1] || mv.from, hoverF || mv.from) || [])]) === k) show(r);
    } catch (e) { box.textContent = e.message; }
  }, 250);
}

// ---------- last turn replay ----------
function renderReplay() {
  const box = $('replay'), lt = G.last_turn;
  R.clearHighlight('rp');
  if (!lt || !lt.events || !lt.events.length) { box.innerHTML = ''; return; }
  if (!replay) { box.innerHTML = `<button data-r="open">Letzte Runde (${lt.turn}) ansehen</button>`; return; }
  replay.i = Math.max(0, Math.min(lt.events.length - 1, replay.i));
  const ev = lt.events[replay.i];
  box.innerHTML = `<button data-r="prev">◀</button> <button data-r="next">▶</button> <button data-r="close">✕</button> ` +
    `Runde ${lt.turn} · ${replay.i + 1}/${lt.events.length}: ${esc(ev.text)}`;
  const hl = (v, kind) => { const fs = isField(v) ? [v] : Array.isArray(v) ? v.filter(isField) : []; if (fs.length) R.highlight(fs, kind); };
  hl(ev.from, 'rp-from'); hl(ev.back_to, 'rp-from'); hl(ev.path, 'rp-path'); hl(ev.to, 'rp-to'); hl(ev.field, 'rp-field');
  if (ev.province && P()[ev.province]) hl(P()[ev.province].capital, 'rp-field');
}
function onReplayClick(e) {
  const r = e.target.dataset.r; if (!r) return;
  if (r === 'open') replay = { i: 0 }; else if (r === 'close') replay = null;
  else if (replay) replay.i += r === 'next' ? 1 : -1;
  renderReplay();
}
