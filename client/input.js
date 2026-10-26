// Map interaction: selection, floating toolbar, reach highlight, one-click moves, hotkeys, context menu, tooltip.
import * as R from './render.js';
import * as O from './orders.js';
import { api } from './api.js';
import { neighbours, key } from './hex.js';
import { $, esc, same, ctx, rules, P, tokenAt, passable, armyAt, ownArmyAt, isEnemyAt, ownCapitalAt, nName, pName } from './ctx.js';

let hooks = { toast() {}, onEscape() {} };
let sel = null;            // { f: field, n: count }
let draft = null;          // { wps: [waypoints], path: [fields so far] } while Shift+click collects detours
let reach = null;          // { origin, prev: Map(key -> field), kind: Map(key -> 'go'|'attack') }
let hoverF = null, mouse = null;
let pv = new Map(), pvTimer = null, digitAt = 0;

export function init(h) {
  hooks = h;
  R.init($('map'), { onField, onHover, onMarker: i => O.removeAt(i), onContext, onStep: step });
  R.onViewChange(() => { place(); hideMenu(); });
  $('toolbar').onclick = e => { const b = e.target.closest('[data-act]'); if (b && !b.disabled) act(b.dataset.act); };
  $('ctxmenu').onclick = e => {
    const b = e.target.closest('[data-to]'); if (!b) return;
    O.add({ type: 'give_province', province: b.dataset.prov, to: b.dataset.to }); hideMenu();
  };
  document.addEventListener('click', e => { if (!e.target.closest('#ctxmenu')) hideMenu(); });
  document.addEventListener('keydown', onKey);
}

// ---------- selection ----------
const selArmy = () => sel && ownArmyAt(sel.f);
const canRecruitHere = () => !!sel && (!!selArmy() || !!ownCapitalAt(sel.f));
const defaultN = () => { const a = selArmy(); return a ? Math.max(1, O.movableLeft(a)) : 1; };
function nMax() {
  const a = selArmy();
  return Math.max(1, a ? O.movableLeft(a) : 0, canRecruitHere() ? O.budget().canRecruit : 0);
}
const clampN = () => { if (sel) sel.n = Math.max(1, Math.min(sel.n, nMax())); };

function select(f) {
  sel = f ? { f, n: 1 } : null; draft = null;
  if (sel) sel.n = defaultN();
  R.clearHighlight('sel'); if (sel) R.highlight([f], 'sel');
  update();
}
export const hasSelection = () => !!sel;
export function reset() { sel = null; draft = null; pv.clear(); hideMenu(); R.clearHighlight('sel'); update(); }

// Called after new server state or a changed order list.
export function update() {
  if (sel && !(selArmy() || ownCapitalAt(sel.f))) { sel = null; draft = null; R.clearHighlight('sel'); }
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

// ---------- reach ----------
function computeReach() {
  reach = null;
  const a = selArmy();
  if (a && O.movableLeft(a) > 0) {
    const origin = draft && draft.wps.length ? draft.wps[draft.wps.length - 1] : a.field;
    const maxD = O.rangeOf(a) - (draft ? draft.path.length : 0);
    const dist = new Map([[key(origin), 0]]), prev = new Map(), kind = new Map();
    let q = [origin];
    for (let d = 0; d < maxD; d++) {
      const nq = [];
      for (const f of q) for (const n of neighbours(f[0], f[1])) {
        const k = key(n);
        if (dist.has(k) || !passable(n)) continue;
        dist.set(k, d + 1); prev.set(k, f);
        if (isEnemyAt(n)) kind.set(k, 'attack'); else { kind.set(k, 'go'); nq.push(n); }  // enemy armies stop movement
      }
      q = nq;
    }
    kind.delete(key(a.field));
    reach = { origin, prev, kind };
  }
  R.setReach(reach ? [...reach.kind].map(([k, v]) => [k.split(',').map(Number), v]) : []);
}
function pathTo(f) {   // full path from the army's field (incl. collected waypoints) to f
  const seg = []; let c = f;
  while (c && !same(c, reach.origin)) { seg.unshift(c); c = reach.prev.get(key(c)); }
  return (draft ? draft.path : []).concat(seg);
}
const reachable = f => !!reach && reach.kind.has(key(f));

// ---------- clicks ----------
function onField(f, e) {
  hideMenu();
  if (!ctx.G.me) return;
  if (reachable(f)) {
    const path = pathTo(f);
    if (e && e.shiftKey && reach.kind.get(key(f)) === 'go') {   // detour waypoint
      draft = { wps: [...(draft ? draft.wps : []), f], path };
      update();
    } else doMove(path);
    return;
  }
  if (ownArmyAt(f) || ownCapitalAt(f)) { if (!sel || !same(sel.f, f)) select(f); return; }
  if (sel && passable(f)) { hooks.toast(selArmy() ? 'Außer Reichweite.' : 'Hier kann nichts angeordnet werden.'); return; }
  select(null);
}
function onContext(f) {
  hideMenu();
  const tok = f && tokenAt(f), prov = tok && P()[tok], others = Object.keys(ctx.G.players).filter(p => p !== ctx.G.me);
  if (prov && ctx.G.owners[tok] === ctx.G.me && others.length && !O.gifted(tok)) {
    const m = $('ctxmenu');
    m.innerHTML = `<div>Provinz ${esc(prov.name)} verschenken an:</div>` +
      others.map(p => `<button data-prov="${esc(tok)}" data-to="${esc(p)}">${esc(pName(p))}</button>`).join('');
    const s = R.fieldToScreen(f);
    m.style.left = s.x + 'px'; m.style.top = s.y + 'px'; m.hidden = false;
  } else if (sel) select(null);
}
const hideMenu = () => { $('ctxmenu').hidden = true; };

// ---------- actions ----------
function doMove(path) {
  const a = selArmy(), k = Math.min(sel.n, O.movableLeft(a));
  if (k < 1) { hooks.toast('Alle Divisionen dieser Armee haben schon einen Zugbefehl.'); return; }
  draft = null; R.showDraft(null);
  O.add({ type: 'move', army: a.id, count: k, path });   // a second move splits the army further
  sel.n = O.movableLeft(a);                              // next click sends the rest
  update();
}
function doRecruit() {
  if (!canRecruitHere()) return;
  const b = O.budget(), k = Math.min(sel.n, b.canRecruit);
  if (k < 1) { hooks.toast(recruitReason(b)); return; }
  O.add({ type: 'recruit', field: sel.f, count: k });
}
function doDisband() {
  const a = selArmy(); if (!a) return;
  const k = Math.min(sel.n, O.disbandMax(a));
  if (k < 1) { hooks.toast(disbandReason(a)); return; }
  O.add({ type: 'disband', army: a.id, count: k });
}
function doForcedMarch() {
  const a = selArmy(); if (!a) return;
  draft = null; O.setForcedMarch(a, !O.fmOn(a));
}
const act = name => ({ dec: () => step(-1), inc: () => step(1), rec: doRecruit, dis: doDisband, fm: doForcedMarch })[name]();
function setN(v) { if (sel) { sel.n = Math.max(1, Math.min(nMax(), v)); renderToolbar(); if (hoverF) onHover(hoverF, null); } }
function step(d) { if (sel) setN(sel.n + d); }
const recruitReason = b => b.recLeft < 1 ? 'Rekrutierungslimit erreicht.' : 'Kein Gold mehr.';
const disbandReason = a => O.moveOf(a.id) ? 'Alle übrigen Divisionen haben einen Zugbefehl.' : 'Keine Division zum Abrüsten.';

// ---------- keyboard ----------
function onKey(e) {
  if (!ctx.G || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
  const k = e.key;
  if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === 'z') { e.preventDefault(); if (!O.undoLast()) hooks.toast('Nichts rückgängig zu machen.'); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (k === 'Tab') { e.preventDefault(); cycle(e.shiftKey ? -1 : 1); }
  else if (k === 'Escape') {
    if (draft) { draft = null; update(); } else if (sel) select(null); else hooks.onEscape();
    hideMenu();
  } else if (!sel) return;
  else if (k === '+' || k === '=') step(1);
  else if (k === '-') step(-1);
  else if (/^[0-9]$/.test(k)) {   // a second digit within 0.7 s makes a two-digit number
    const now = Date.now(), v = now - digitAt < 700 && sel.n < 10 ? sel.n * 10 + +k : +k;
    digitAt = now; setN(v || 1);
  }
  else if (k === 'r' || k === 'R') doRecruit();
  else if (k === 'd' || k === 'D') doDisband();
  else if (k === 'g' || k === 'G') doForcedMarch();
}

// ---------- toolbar ----------
function renderToolbar() {
  const tb = $('toolbar');
  if (!sel) { tb.hidden = true; tb.innerHTML = ''; return; }
  const a = selArmy(), b = O.budget(), mx = nMax();
  const btn = (name, label, hot, ok, why) => `<button data-act="${name}" ${ok ? '' : 'disabled'} title="${esc(ok ? '' : why)}">${label} <kbd>${hot}</kbd></button>`;
  let h = `<span class="tb-step"><button data-act="dec" ${sel.n > 1 ? '' : 'disabled'}>−</button><b>${sel.n}</b>` +
    `<button data-act="inc" ${sel.n < mx ? '' : 'disabled'}>+</button></span>`;
  if (canRecruitHere()) h += btn('rec', `Rekrutieren +${Math.max(1, Math.min(sel.n, b.canRecruit))}`, 'R', b.canRecruit > 0, recruitReason(b));
  if (a) {
    const dm = O.disbandMax(a);
    h += btn('dis', `Abrüsten ${Math.max(1, Math.min(sel.n, dm))}`, 'D', dm > 0, disbandReason(a));
    h += btn('fm', `Gewaltmarsch ${O.fmOn(a) ? 'aus' : 'an'}`, 'G', true, '');
    h = `<span class="tb-info">Armee ${esc(a.id)}: ${a.divisions} Div.${a.fresh ? ` (${a.fresh} neu)` : ''}</span>` + h;
  }
  tb.innerHTML = h; tb.hidden = false; place();
}
function place() {
  const tb = $('toolbar');
  if (!sel || tb.hidden) return;
  // centred under the selection and below the whole reach area (above it if there is no room),
  // so the toolbar never covers a possible move target
  const s = R.fieldToScreen(sel.f), W = $('map').clientWidth, H = $('map').clientHeight;
  const w = tb.offsetWidth, h = tb.offsetHeight;
  const ys = [s.y, ...(reach ? [...reach.kind.keys()].map(k => R.fieldToScreen(k.split(',').map(Number)).y) : [])];
  let y = Math.max(...ys) + s.r + 6;
  if (y + h > H) y = Math.min(...ys) - s.r - 6 - h;
  const x = Math.min(Math.max(0, s.x - w / 2), Math.max(0, W - w));
  tb.style.left = x + 'px'; tb.style.top = Math.min(Math.max(0, y), Math.max(0, H - h)) + 'px';
}

// ---------- hover, tooltip, hint ----------
function hideTip() {
  $('tip').hidden = true;
  R.showDraft(draft && draft.path.length ? [selArmy().field, ...draft.path] : null, true, draft ? draft.wps : []);
}
function onHover(f, e) {
  hoverF = f;
  if (e) mouse = { x: e.clientX, y: e.clientY };
  $('ib-hover').textContent = f ? fieldInfo(f) : '';
  if (!f || !reachable(f)) { hideTip(); return; }
  const a = selArmy(), path = pathTo(f), n = Math.min(sel.n, O.movableLeft(a));
  R.showDraft([a.field, ...path], true, draft ? draft.wps : []);
  const fm = O.fmOn(a), k = JSON.stringify([a.id, n, path, fm]), base = `${path.length} ${path.length === 1 ? 'Feld' : 'Felder'}`;
  moveTip(base, '');
  if (pv.has(k)) { showPreview(pv.get(k), base); return; }
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    try {
      const r = await api.preview(ctx.gid, ctx.token, { army: a.id, count: n, path, forced_march: fm });
      pv.set(k, r);
      if (hoverF && reachable(hoverF) && JSON.stringify([a.id, n, pathTo(hoverF), fm]) === k) showPreview(r, base);
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
    : a ? (reach ? 'Ziel anklicken · Shift+Klick Umweg · G Gewaltmarsch · +/− Anzahl · Esc' : 'Keine beweglichen Divisionen · R rekrutieren · D abrüsten · Esc')
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
