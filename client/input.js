// Map interaction: selection, floating toolbar, route drawing (waypoints, range split), hotkeys, context menu, tooltip.
import * as R from './render.js';
import * as O from './orders.js';
import * as Chat from './chat.js';
import { api } from './api.js';
import { neighbours, key } from './hex.js';
import { $, esc, same, ctx, rules, P, tokenAt, passable, armyAt, ownArmyAt, isEnemyAt, ownCapitalAt, nName, pName, fieldName } from './ctx.js';

let hooks = { toast() {}, onEscape() {} };
let sel = null;            // { f: field, n: count }
let wps = [];              // fixed waypoints of the route being drawn (the last leg follows the mouse)
let reach = null;          // { kind: Map(key -> 'go'|'attack') } fields reachable this turn (informational overlay)
let hoverF = null, mouse = null;
let pv = new Map(), pvTimer = null, digitAt = 0;

export function init(h) {
  hooks = h;
  R.init($('map'), { onField, onHover, onMarker: i => O.removeAt(i), onContext, onStep: step });
  R.onViewChange(() => hideMenu());
  $('toolbar').onclick = e => { const b = e.target.closest('[data-act]'); if (b && !b.disabled) act(b.dataset.act); };
  $('ctxmenu').onclick = e => {
    const w = e.target.closest('[data-msg]');
    if (w) { hideMenu(); Chat.openChannel(w.dataset.msg, w.dataset.f.split(',').map(Number)); return; }
    const b = e.target.closest('[data-to]'); if (!b) return;
    O.add({ type: 'give_province', province: b.dataset.prov, to: b.dataset.to }); hideMenu();
  };
  document.addEventListener('click', e => {   // composedPath: the target may already be gone after a re-render
    const ids = (e.composedPath ? e.composedPath() : []).map(n => n.id);
    if (!ids.includes('ctxmenu')) hideMenu();
    if (sel && !['map', 'toolbar', 'chat', 'ctxmenu'].some(i => ids.includes(i))) select(null);   // click outside = deselect
  });
  document.addEventListener('keydown', onKey);
}

// ---------- selection ----------
const selArmy = () => sel && ownArmyAt(sel.f);
const canRecruitHere = () => !!sel && !!ownCapitalAt(sel.f);   // recruiting only in own cities (4.0)
const canDisband = a => !!ownCapitalAt(a.field);                  // disbanding too
const defaultN = () => { const a = selArmy(); return a ? Math.max(1, O.movableLeft(a)) : 1; };
function nMax() {
  const a = selArmy();
  return Math.max(1, a ? O.movableLeft(a) : 0, canRecruitHere() ? O.budget().canRecruit : 0);
}
const clampN = () => { if (sel) sel.n = Math.max(1, Math.min(sel.n, nMax())); };

function select(f) {
  sel = f ? { f, n: 1 } : null; wps = [];
  if (sel) sel.n = defaultN();
  R.clearHighlight('sel'); if (sel) R.highlight([f], 'sel');
  update();
}
export const hasSelection = () => !!sel;
export function reset() { sel = null; wps = []; pv.clear(); hideMenu(); R.clearHighlight('sel'); update(); }

// Called after new server state or a changed order list.
export function update() {
  if (sel && !(selArmy() || ownCapitalAt(sel.f))) { sel = null; R.clearHighlight('sel'); }
  if (!sel || !selArmy() || O.movableLeft(selArmy()) < 1) wps = [];
  clampN(); computeReach(); renderToolbar(); hint();
  if (hoverF) onHover(hoverF, null); else hideTip();
}
export const clearPreviews = () => pv.clear();

function cycle(dir) {
  const own = Object.values(ctx.G.armies).filter(a => a.owner === ctx.G.me).sort((a, b) => a.id.localeCompare(b.id, 'en', { numeric: true }));
  if (!own.length) return;
  const i = sel ? own.findIndex(a => same(a.field, sel.f)) : -1;
  select(own[(i + dir + own.length) % own.length].field);
}

// ---------- reach (informational overlay) ----------
function computeReach() {
  reach = null;
  const a = selArmy();
  if (a && O.movableLeft(a) > 0) {
    const origin = a.field, maxD = O.rangeOf(a);
    const dist = new Map([[key(origin), 0]]), kind = new Map();
    let q = [origin];
    for (let d = 0; d < maxD; d++) {
      const nq = [];
      for (const f of q) for (const n of neighbours(f[0], f[1])) {
        const k = key(n);
        if (dist.has(k) || !passable(n)) continue;
        dist.set(k, d + 1);
        if (isEnemyAt(n)) kind.set(k, 'attack'); else { kind.set(k, 'go'); nq.push(n); }  // enemy armies stop movement
      }
      q = nq;
    }
    kind.delete(key(a.field));
    reach = { kind };
  }
  R.setReach(reach ? [...reach.kind].map(([k, v]) => [k.split(',').map(Number), v]) : []);
}

// ---------- route ----------
// Shortest passable leg (no range limit); enemy armies are only entered when they are the goal, if there is a way around.
function leg(from, to) {
  for (const avoid of [true, false]) {
    const prev = new Map([[key(from), null]]);
    let q = [from];
    while (q.length && !prev.has(key(to))) {
      const nq = [];
      for (const f of q) for (const n of neighbours(f[0], f[1])) {
        const k = key(n);
        if (prev.has(k) || !passable(n) || (avoid && isEnemyAt(n) && !same(n, to))) continue;
        prev.set(k, f); nq.push(n);
      }
      q = nq;
    }
    if (prev.has(key(to))) {
      const out = []; let c = to;
      while (c && !same(c, from)) { out.unshift(c); c = prev.get(key(c)); }
      return out;
    }
  }
  return null;
}
// Route from the army over the fixed waypoints to the cursor; near = the part reachable this turn.
function buildRoute(cursor) {
  const a = selArmy(); if (!a) return null;
  const pts = [a.field, ...wps];
  if (cursor && !same(cursor, pts[pts.length - 1])) pts.push(cursor);
  const full = [];
  for (let i = 1; i < pts.length; i++) { const l = leg(pts[i - 1], pts[i]); if (!l) return null; full.push(...l); }
  if (!full.length) return null;
  let stop = Math.min(full.length, O.rangeOf(a)), attack = false;
  for (let i = 0; i < stop; i++) if (isEnemyAt(full[i])) { stop = i + 1; attack = true; break; }
  return { a, full, near: full.slice(0, stop), far: full.slice(stop - 1), attack };
}
function drawRoute(rt) {
  if (!rt) { R.showRoute(null); return; }
  R.showRoute([rt.a.field, ...rt.near], rt.far.length > 1 ? rt.far : [], wps, rt.near[rt.near.length - 1], rt.attack);
}
const routing = () => { const a = selArmy(); return !!a && O.movableLeft(a) > 0; };
function addWp(f) {
  if (same(f, selArmy().field)) return;
  if (!buildRoute(f)) { hooks.toast('Kein Weg dorthin.'); return; }
  wps.push(f); update();
}
// The ONE place that turns a drawn route into a move order: the full route (standing march, G58);
// the server executes one turn's part per turn and keeps the rest.
function routeToOrder(a, count, rt) {
  return { type: 'move', army: a.id, count, path: rt.full };
}
function confirmRoute(cursor) {
  const a = selArmy(), rt = a && buildRoute(cursor);
  if (!rt) return;
  const k = Math.min(sel.n, O.movableLeft(a));
  if (k < 1) { hooks.toast('Alle Divisionen dieser Armee haben schon einen Zugbefehl.'); return; }
  const o = routeToOrder(a, k, rt);
  if (rt.near.length < rt.full.length) {
    hooks.toast(`Marsch nach ${fieldName(rt.full[rt.full.length - 1])}: ca. ${Math.ceil(rt.full.length / O.rangeOf(a))} Runden`);
  }
  wps = []; R.showRoute(null);
  O.add(o);                       // a further move splits the army more (G56)
  sel.n = O.movableLeft(a);       // the next route sends the rest
  update();
}

// ---------- clicks ----------
function onField(f, e) {
  hideMenu();
  if (!ctx.G.me) return;
  if ((e && e.altKey) || Chat.pinning()) { Chat.toggleMark(f); return; }   // chat reference instead of orders
  if (routing() && wps.length) {            // a route is under construction: clicks set waypoints
    if (same(f, wps[wps.length - 1])) confirmRoute(null); else if (passable(f)) addWp(f); else hooks.toast('Nicht passierbar.');
    return;
  }
  if (ownArmyAt(f) || ownCapitalAt(f)) { if (!sel || !same(sel.f, f)) select(f); return; }
  if (routing() && passable(f)) { addWp(f); return; }
  if (sel && passable(f) && selArmy()) { hooks.toast('Alle Divisionen dieser Armee haben schon einen Zugbefehl.'); return; }
  select(null);
}
function onContext(f) {
  hideMenu();
  if (wps.length) { wps.pop(); update(); return; }   // right-click takes the last waypoint back
  const tok = f && tokenAt(f), prov = tok && P()[tok], others = Object.keys(ctx.G.players).filter(p => p !== ctx.G.me);
  const give = prov && ctx.G.owners[tok] === ctx.G.me && others.length && !O.gifted(tok);
  const a = f && armyAt(f), talk = f ? [...new Set([prov && ctx.G.owners[tok], a && a.owner])].filter(p => p && p !== ctx.G.me && ctx.G.players[p]) : [];
  if (give || talk.length) {
    const m = $('ctxmenu');
    m.innerHTML = (give ? `<div>Provinz ${esc(prov.name)} verschenken an:</div>` +
      others.map(p => `<button data-prov="${esc(tok)}" data-to="${esc(p)}">${esc(pName(p))}</button>`).join('') : '') +
      talk.map(p => `<button data-msg="${esc(p)}" data-f="${f[0]},${f[1]}">✉ Nachricht an ${esc(pName(p))}</button>`).join('');
    const s = R.fieldToScreen(f);
    m.style.left = s.x + 'px'; m.style.top = s.y + 'px'; m.hidden = false;
  } else if (sel) select(null);
}
const hideMenu = () => { $('ctxmenu').hidden = true; };

// ---------- actions ----------
function doRecruit() {
  if (!canRecruitHere()) return;
  const b = O.budget(), k = Math.min(sel.n, b.canRecruit);
  if (k < 1) { hooks.toast(recruitReason(b)); return; }
  O.add({ type: 'recruit', field: sel.f, count: k });
}
function doDisband() {
  const a = selArmy(); if (!a) return;
  const k = canDisband(a) ? Math.min(sel.n, O.disbandMax(a)) : 0;
  if (k < 1) { hooks.toast(disbandReason(a)); return; }
  O.add({ type: 'disband', army: a.id, count: k });
}
function doForcedMarch() {
  const a = selArmy(); if (!a) return;
  O.setForcedMarch(a, !O.fmOn(a));
}
function doHalt() {
  const a = selArmy();
  if (a && O.marching(a)) O.add({ type: 'halt', army: a.id });
}
const baseN = () => { const a = selArmy(); return a ? Math.max(1, O.movableLeft(a)) : nMax(); };
const act = name => ({ dec: () => step(-1), inc: () => step(1), q1: () => setN(1), qh: () => setN(Math.max(1, Math.floor(baseN() / 2))), qa: () => setN(baseN()), rec: doRecruit, dis: doDisband, fm: doForcedMarch, halt: doHalt })[name]();
function setN(v) { if (sel) { sel.n = Math.max(1, Math.min(nMax(), v)); renderToolbar(); if (hoverF) onHover(hoverF, null); } }
function step(d) { if (sel) setN(sel.n + d); }
const recruitReason = b => b.recLeft < 1 ? 'Rekrutierungslimit erreicht.' : 'Kein Gold mehr.';
const disbandReason = a => !canDisband(a) ? 'Abrüsten geht nur in eigenen Städten.' : O.moveOf(a.id) ? 'Alle übrigen Divisionen haben einen Zugbefehl.' : 'Keine Division zum Abrüsten.';

// ---------- keyboard ----------
function onKey(e) {
  if (!ctx.G || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
  const k = e.key;
  if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === 'z') { e.preventDefault(); if (!O.undoLast()) hooks.toast('Nichts rückgängig zu machen.'); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (k === 'Tab') { e.preventDefault(); cycle(e.shiftKey ? -1 : 1); }
  else if (k === 'Escape') {
    if (Chat.cancelPin()) { /* pin mode off */ } else if (wps.length) { wps = []; update(); } else if (sel) select(null); else hooks.onEscape();
    hideMenu();
  } else if (k === 'Enter' && !sel && e.target === document.body) { e.preventDefault(); Chat.focusInput(); }
  else if (!sel) return;
  else if (k === 'Backspace') { if (wps.length) { e.preventDefault(); wps.pop(); update(); } }
  else if (k === 'Enter') { if (routing() && e.target.tagName !== 'BUTTON') { e.preventDefault(); confirmRoute(hoverF && passable(hoverF) ? hoverF : null); } }
  else if (k === '+' || k === '=') step(1);
  else if (k === '-') step(-1);
  else if (/^[0-9]$/.test(k)) {   // a second digit within 0.7 s makes a two-digit number
    const now = Date.now(), v = now - digitAt < 700 && sel.n < 10 ? sel.n * 10 + +k : +k;
    digitAt = now; setN(v || 1);
  }
  else if (k === 'r' || k === 'R') doRecruit();
  else if (k === 'd' || k === 'D') doDisband();
  else if (k === 'g' || k === 'G') doForcedMarch();
  else if (k === 'h' || k === 'H') doHalt();
}

// ---------- toolbar ----------
function renderToolbar() {
  const tb = $('toolbar');
  if (!sel) { tb.hidden = true; tb.innerHTML = ''; return; }
  const a = selArmy(), b = O.budget(), mx = nMax(), base = baseN(), left = a ? O.movableLeft(a) : 0;
  const btn = (name, label, hot, ok, why) => `<button data-act="${name}" ${ok ? '' : 'disabled'} title="${esc(ok ? '' : why)}">${label} <kbd>${hot}</kbd></button>`;
  let h = '';
  if (a) h += `<div class="tb-row"><span class="tb-info">Armee ${esc(a.id)}: ${a.divisions} Div.${a.fresh ? ` (${a.fresh} neu)` : ''}${a.route ? ` · marschiert nach ${esc(fieldName(a.route[a.route.length - 1]))}` : ''}</span></div>`;
  h += `<div class="tb-row"><span class="tb-step"><button data-act="dec" ${sel.n > 1 ? '' : 'disabled'}>−</button><b>${sel.n}</b>` +
    `<button data-act="inc" ${sel.n < mx ? '' : 'disabled'}>+</button></span><span class="tb-von">von ${base}</span>` +
    `<button data-act="q1" title="Eine Division">1</button><button data-act="qh" title="Die Hälfte">½</button><button data-act="qa" title="Alle">Alle</button></div>`;
  if (a) h += `<div class="tb-row tb-rest ${left ? '' : 'done'}">Ohne Befehl: <b>${left}</b> von ${a.divisions} Div.</div>`;
  let row = '';
  if (canRecruitHere()) row += btn('rec', `Rekrutieren +${Math.max(1, Math.min(sel.n, b.canRecruit))}`, 'R', b.canRecruit > 0, recruitReason(b));
  if (a) {
    const dm = O.disbandMax(a);
    row += btn('dis', `Abrüsten ${Math.max(1, Math.min(sel.n, dm))}`, 'D', dm > 0 && canDisband(a), disbandReason(a));
    row += btn('fm', `Gewaltmarsch ${O.fmOn(a) ? 'aus' : 'an'}`, 'G', true, '');
    if (O.marching(a)) row += btn('halt', 'Halt', 'H', true, '');
  }
  if (row) h += `<div class="tb-row">${row}</div>`;
  if (left) h += '<div class="tb-help">Anzahl wählen · Felder anklicken für den Weg · gleiches Feld nochmal = bestätigen</div>';
  tb.innerHTML = h; tb.hidden = false;
}


// ---------- hover, tooltip, hint ----------
function hideTip() {
  $('tip').hidden = true;
  drawRoute(routing() && wps.length ? buildRoute(null) : null);
}
function onHover(f, e) {
  hoverF = f;
  if (e) mouse = { x: e.clientX, y: e.clientY };
  $('ib-hover').textContent = f ? fieldInfo(f) : '';
  const rt = f && routing() && passable(f) ? buildRoute(f) : null;
  if (!rt) { hideTip(); return; }
  drawRoute(rt);
  const a = rt.a, n = Math.min(sel.n, O.movableLeft(a)), path = rt.near, fm = O.fmOn(a);
  const k = JSON.stringify([a.id, n, path, fm]), cnt = x => `${x} ${x === 1 ? 'Feld' : 'Felder'}`;
  const base = cnt(rt.full.length) + (path.length < rt.full.length ? ` (diese Runde ${path.length})` : '') +
    (wps.length && same(f, wps[wps.length - 1]) ? ' · nochmal klicken = bestätigen' : '');
  moveTip(base, '');
  if (pv.has(k)) { showPreview(pv.get(k), base); return; }
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    try {
      const r = await api.preview(ctx.gid, ctx.token, { army: a.id, count: n, path, forced_march: fm });
      pv.set(k, r);
      const cur = hoverF && routing() && passable(hoverF) ? buildRoute(hoverF) : null;
      if (cur && JSON.stringify([a.id, n, cur.near, fm]) === k) showPreview(r, base);
    } catch (err) { /* tooltip only */ }
  }, 250);
}
function showPreview(r, base) { moveTip(base + ' · ' + (r.valid ? r.text || '' : (r.errors || []).join(' ')), r.valid ? '' : 'bad'); }
function moveTip(text, cls) {
  const t = $('tip'), b = $('map').getBoundingClientRect();
  t.textContent = text; t.className = cls; t.hidden = false;
  if (!mouse) return;
  let x = mouse.x - b.left + 16;
  if (x + t.offsetWidth > b.width) x = mouse.x - b.left - 16 - t.offsetWidth;
  t.style.left = Math.max(0, x) + 'px'; t.style.top = (mouse.y - b.top + 16) + 'px';
}
function hint() {
  const a = sel && selArmy();
  $('ib-hint').textContent = !sel ? 'Eigene Armee oder Hauptstadt anklicken · Tab: nächste Armee · Strg+Z: rückgängig'
    : a ? (reach ? (wps.length ? 'Weiter klicken · letztes Feld nochmal oder Enter = bestätigen · Rücktaste/Rechtsklick: Wegpunkt zurück · Esc: Weg verwerfen'
        : 'Felder anklicken für den Weg · G Gewaltmarsch · +/− Anzahl · Esc') : 'Keine beweglichen Divisionen · R rekrutieren · D abrüsten · Esc')
      : 'R rekrutieren · +/− Anzahl · Esc';
}
function fieldInfo(f) {
  const tok = tokenAt(f), prov = P()[tok], a = armyAt(f);
  let s;
  if (prov) {
    const o = ctx.G.owners[tok];
    s = `${prov.name} (${o ? nName(o) : 'neutral'}) · Hauptstadt ${prov.capital_name} · Einkommen ${prov.income} · Eroberung kostet ${prov.income * rules().conquest_cost_factor} Div.`;
  } else s = tok === '~~' ? 'Meer' : 'Nicht passierbar';
  if (a) s += ` · Armee ${a.id} (${nName(a.owner)}): ${a.divisions} Div.${a.forced_march ? ', Gewaltmarsch' : ''}`;
  return s;
}
