// The ONLY module that knows about SVG and colours (IMPLEMENTATION 4.2).
// Colours come from state.theme (theme.json) and CSS variables/classes in style.css.
import { neighbours, parseGrid } from './hex.js';

const S = 20, SQ3 = Math.sqrt(3), NS = 'http://www.w3.org/2000/svg';
let svg, L = {}, H = {}, theme = {}, mapKey = null, polys = {}, vb, full, down = null, hoverKey = null, rows = [], viewHooks = [], curMap = null;

const mk = (tag, attrs, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
};
const txt = (parent, x, y, s, cls) => {
  const t = mk('text', { x, y, 'text-anchor': 'middle', 'dominant-baseline': 'central', class: cls || '' }, parent);
  t.textContent = s;
  return t;
};
export const centre = f => ({ x: f[0] * 1.5 * S + S, y: (f[1] + (f[0] % 2 ? 0 : 0.5)) * SQ3 * S + S });
const corner = (x, y, i) => [x + S * Math.cos(i * Math.PI / 3), y + S * Math.sin(i * Math.PI / 3)];
const hexPts = (x, y) => [0, 1, 2, 3, 4, 5].map(i => corner(x, y, i).map(v => v.toFixed(1)).join(',')).join(' ');
const colorIn = (th, pid) => (th.nation_colors || {})[pid] || th.neutral_color || '#888';
export const colorOf = pid => colorIn(theme, pid);

export function init(svgEl, handlers) {
  svg = svgEl; H = handlers; svg.innerHTML = '';
  const defs = mk('defs', {}, svg);
  for (const err of [false, true]) {
    const m = mk('marker', { id: 'ah' + (err ? 'e' : ''), viewBox: '0 0 10 10', refX: 7, refY: 5, markerWidth: 4, markerHeight: 4, orient: 'auto' }, defs);
    mk('path', { d: 'M0 0L10 5L0 10z', class: 'arrowhead' + (err ? ' err' : '') }, m);
  }
  const mc = mk('marker', { id: 'ahc', viewBox: '0 0 10 10', refX: 7, refY: 5, markerWidth: 4, markerHeight: 4, orient: 'auto' }, defs);
  mk('path', { d: 'M0 0L10 5L0 10z', class: 'arrowhead chat' }, mc);
  for (const n of ['base', 'reach', 'hi', 'marks', 'armies', 'routes', 'orders', 'draft']) L[n] = mk('g', { id: 'l-' + n }, svg);
  svg.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY, moved: false }; });
  svg.addEventListener('pointermove', e => {
    if (down && e.buttons) {
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) down.moved = true;
      if (down.moved) {
        const k = svg.getScreenCTM().a;
        vb.x -= (e.clientX - down.x) / k; vb.y -= (e.clientY - down.y) / k;
        down.x = e.clientX; down.y = e.clientY; applyVb();
      }
      return;
    }
    const f = fieldAt(e.clientX, e.clientY);
    hoverKey = f ? f.join() : null;
    if (H.onHover) H.onHover(f, e);
  });
  svg.addEventListener('pointerleave', () => { hoverKey = null; if (H.onHover) H.onHover(null); });
  svg.addEventListener('click', e => {
    if (down && down.moved) { down = null; return; }
    const m = e.target.closest && e.target.closest('[data-idx]');
    if (m) { if (H.onMarker) H.onMarker(+m.dataset.idx); return; }
    const f = fieldAt(e.clientX, e.clientY);
    if (f && H.onField) H.onField(f, e);
  });
  svg.addEventListener('contextmenu', e => {
    e.preventDefault();
    if (down && down.moved) return;
    if (H.onContext) H.onContext(fieldAt(e.clientX, e.clientY), e);
  });
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    if (e.shiftKey) { const d = e.deltaY || e.deltaX; if (d && H.onStep) H.onStep(d < 0 ? 1 : -1); return; }
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    const nw = Math.min(full.w, Math.max(full.w / 10, vb.w * (e.deltaY < 0 ? 0.85 : 1 / 0.85)));
    const f = nw / vb.w;
    vb.x = p.x - (p.x - vb.x) * f; vb.y = p.y - (p.y - vb.y) * f; vb.h *= f; vb.w = nw; applyVb();
  }, { passive: false });
}
// Field under a screen position: nearest hex centre (independent of what element is on top).
function fieldAt(cx, cy) {
  const pt = svg.createSVGPoint(); pt.x = cx; pt.y = cy;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  const c0 = Math.round((p.x - S) / (1.5 * S)), r0 = Math.floor(p.y / (SQ3 * S));
  let best = null, bd = (S * 1.01) ** 2;
  for (let c = c0 - 1; c <= c0 + 1; c++) for (let r = r0 - 1; r <= r0 + 1; r++) {
    if (!rows[r] || !rows[r][c] || rows[r][c] === '..') continue;
    const q = centre([c, r]), d = (q.x - p.x) ** 2 + (q.y - p.y) ** 2;
    if (d < bd) { bd = d; best = [c, r]; }
  }
  return best;
}
// Position of a field's centre in pixels relative to the map element, and the hex radius in pixels.
export function fieldToScreen(f) {
  const { x, y } = centre(f), m = svg.getScreenCTM(), b = svg.getBoundingClientRect();
  return { x: m.a * x + m.e - b.left, y: m.d * y + m.f - b.top, r: m.a * S };
}
export const onViewChange = fn => { viewHooks.push(fn); };
const applyVb = () => { svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`); viewHooks.forEach(fn => fn()); };
const clear = g => { while (g.firstChild) g.removeChild(g.firstChild); };

// Symbols and patterns (colours from theme.json): castle icon, sea waves.
function buildDefs() {
  const defs = svg.querySelector('defs');
  defs.querySelectorAll('.themed').forEach(e => e.remove());
  const ink = theme.ink || theme.hex_outline || '#222', sea = ((theme.terrain || {})['~~'] || {}).fill || '#356';
  const pat = mk('pattern', { id: 'sea-pat', class: 'themed', width: 24, height: 14, patternUnits: 'userSpaceOnUse' }, defs);
  mk('rect', { width: 24, height: 14, fill: sea }, pat);
  mk('path', { d: 'M1 4Q4 1 7 4T13 4T19 4M13 11Q16 8 19 11T25 11M-5 11Q-2 8 1 11T7 11', fill: 'none', stroke: theme.sea_wave || '#fff', 'stroke-width': 0.9, 'stroke-opacity': 0.4, 'stroke-linecap': 'round' }, pat);
  const sym = mk('symbol', { id: 'castle', class: 'themed', viewBox: '0 0 24 24' }, defs);
  mk('path', { d: 'M3 21V9h3V6h2v3h2V6h4v3h2V6h2v3h3v12z M10 21v-5a2 2 0 0 1 4 0v5z', fill: '#efe0b4', stroke: ink, 'stroke-width': 1.6, 'stroke-linejoin': 'round', 'fill-rule': 'evenodd' }, sym);
  mk('path', { d: 'M12 6V1.5l4 1.5-4 1.5', fill: '#8c2a1e', stroke: ink, 'stroke-width': 1, 'stroke-linejoin': 'round' }, sym);
}

// Border path, province-area bounds and grid extent of a map (shared by the live map and the static renderer).
function layoutOf(grid, P) {
  let d = '', maxc = 0, maxr = 0;
  const pb = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  grid.forEach((row, r) => row.forEach((tok, c) => {
    if (tok === '..') return;
    maxc = Math.max(maxc, c); maxr = Math.max(maxr, r);
    if (!P[tok]) return;
    const { x, y } = centre([c, r]);
    pb.x0 = Math.min(pb.x0, x); pb.y0 = Math.min(pb.y0, y); pb.x1 = Math.max(pb.x1, x); pb.y1 = Math.max(pb.y1, y);
    for (const n of neighbours(c, r)) {
      const o = (grid[n[1]] || [])[n[0]];
      if (!P[o] || o <= tok) continue;
      const q = centre(n), a = Math.atan2(q.y - y, q.x - x) * 180 / Math.PI;
      const k = ((Math.round((a - 30) / 60) % 6) + 6) % 6;
      const p1 = corner(x, y, k), p2 = corner(x, y, k + 1);
      d += `M${p1[0].toFixed(1)} ${p1[1].toFixed(1)}L${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
  }));
  const full = { x: 0, y: 0, w: (maxc * 1.5 + 2) * S, h: (maxr + 1.5) * SQ3 * S + S };
  const m = 2 * S;   // province area + a margin
  const view = pb.x0 < Infinity ? { x: pb.x0 - m, y: pb.y0 - m, w: pb.x1 - pb.x0 + 2 * m, h: pb.y1 - pb.y0 + 2 * m } : { ...full };
  return { d, full, view };
}

function buildBase(state) {
  buildDefs();
  clear(L.base); polys = {};
  const grid = rows = parseGrid(state.map.grid), P = state.map.provinces;
  const border = mk('path', { class: 'border', stroke: theme.province_border || '#fff', 'stroke-width': 2.4, 'stroke-opacity': 0.85 }, null);
  grid.forEach((row, r) => row.forEach((tok, c) => {
    if (tok === '..') return;
    const { x, y } = centre([c, r]);
    const poly = mk('polygon', { points: hexPts(x, y), stroke: theme.hex_outline || '#000', 'stroke-width': 0.5, 'stroke-opacity': P[tok] ? 0.22 : 0.08, class: P[tok] ? 'land' : 'terr' }, L.base);
    if (P[tok]) (polys[tok] = polys[tok] || []).push(poly);
    else poly.setAttribute('fill', tok === '~~' ? 'url(#sea-pat)' : ((theme.terrain || {})[tok] || {}).fill || '#444');
  }));
  const lay = layoutOf(grid, P);
  border.setAttribute('d', lay.d); L.base.appendChild(border);
  for (const p of Object.values(P)) for (const f of p.ports || []) {   // ports: a small anchor at the field's sea-side edge
    const { x, y } = centre(f), t = txt(L.base, x + S * 0.5, y + S * 0.45, theme.port_icon || '⚓', 'port');
    const ti = mk('title', {}, t); ti.textContent = 'Hafen von ' + p.name;
  }
  for (const p of Object.values(P)) {
    const { x, y } = centre(p.capital);
    let t;
    if (theme.capital_icon === 'castle') t = mk('use', { href: '#castle', x: x - 8, y: y - S * 0.3 - 10, width: 16, height: 16, class: 'cap' }, L.base);
    else t = txt(L.base, x, y - S * 0.3, theme.capital_icon || '*', 'cap');
    const ti = mk('title', {}, t); ti.textContent = p.capital_name;
  }
  full = lay.full;
  vb = { ...lay.view };   // start zoomed to the province area (+ a margin), the wheel still zooms out to the full map
  applyVb();
}

export function drawMap(state) {
  theme = state.theme || {};
  svg.style.background = theme.background || '#000';
  if (mapKey !== state.map.name) { mapKey = state.map.name; buildBase(state); }
  curMap = state.map; curRules = state.rules || curRules;
  paintOwners(state.owners);
  drawArmies(Object.values(state.armies));
}
function paintOwners(owners) {
  for (const tok in polys) {
    const o = owners[tok];
    for (const p of polys[tok]) p.setAttribute('fill', o ? colorOf(o) : (theme.neutral_color || '#888'));
  }
}
function drawArmies(list) {
  clear(L.armies);
  const caps = new Set(Object.values(curMap.provinces).map(p => p.capital.join()));
  list.forEach(a => armyToken(a, caps, list));
}
// Unit types are data: a unit whose type has terrain 'sea' is a fleet.
const isFleet = a => ((curRules.unit_types || {})[a.unit || curRules.land_unit] || {}).terrain === 'sea';
let curRules = {};
// Shield offset: a fleet and an army sharing a sea field sit side by side.
const shareOffset = (a, list) => {
  const k = a.field.join(), mates = (list || []).filter(b => b.field.join() === k);
  return mates.length < 2 ? 0 : (isFleet(a) ? -S * 0.55 : S * 0.55);
};
// One unit shield in L.armies (returns its <g>); also used by the replay block at the end of this file.
function armyToken(a, caps, list) {
  const capSet = caps || new Set(Object.values(curMap.provinces).map(p => p.capital.join()));
  {
    const c = centre(a.field), x = c.x + shareOffset(a, list), y = c.y, yy = y + (capSet.has(a.field.join()) ? S * 0.35 : 0);
    const fresh = a.fresh || 0, label = String(a.divisions - fresh) + (fresh ? '+' + fresh : '');
    // light parchment shield with a band in the owner's colour, so it stands out on its own land
    const w = Math.max(24, label.length * 9 + 12), l = x - w / 2, r = x + w / 2, t0 = yy - 13;
    const sh = `M${l} ${t0}H${r}V${yy + 3}Q${r} ${yy + 9} ${x} ${yy + 13}Q${l} ${yy + 9} ${l} ${yy + 3}Z`;
    const fleet = isFleet(a);
    const g = mk('g', { class: 'army' + (fleet ? ' fleet' : '') + (fresh ? ' has-fresh' : ''), 'data-army': a.id }, L.armies);
    // fleets: a hull-shaped badge instead of the shield
    const hull = `M${l - 3} ${t0 + 4}H${r + 3}L${r - 3} ${yy + 10}H${l + 3}Z`;
    mk('path', { d: fleet ? hull : sh, class: 'badge-rim' }, g);
    mk('path', { d: fleet ? hull : sh, class: 'badge' }, g);
    mk('rect', { x: l, y: t0, width: w, height: 6, fill: colorOf(a.owner), class: 'badge-chief' }, g);
    const t = txt(g, x, yy + 2, '', 'divs');
    const s1 = mk('tspan', {}, t); s1.textContent = String(a.divisions - fresh);
    if (fresh) { const s2 = mk('tspan', { class: 'fresh' }, t); s2.textContent = '+' + fresh; }
    if (a.linked) txt(g, r + 2, t0 + 2, '⛓', 'linkflag');
    if (a.forced_march && !fleet && !(rows[a.field[1]] && rows[a.field[1]][a.field[0]] === '~~')) {
      mk('circle', { cx: l - 1, cy: t0 + 3, r: 6, class: 'fmseal' }, g);
      txt(g, l - 1, t0 + 3, '»', 'fmflag');
    }
    return g;
  }
}

// Orders as arrows/markers. errors[i] = list of German strings for orders[i]. Click -> handlers.onMarker(i).
export function showArrows(orders, errors, state) {
  clear(L.orders);
  let seq = 0; const stack = {};
  const marker = (idx, x, y, s, errs, title) => {
    const g = mk('g', { class: 'mk' + (errs.length ? ' err' : ''), 'data-idx': idx, 'data-ord': idx }, L.orders);
    const w = Math.max(16, s.length * 6.5 + 9);
    mk('rect', { x: x - w / 2, y: y - 8, width: w, height: 16, rx: 8 }, g);
    txt(g, x, y, s, '');
    const ti = mk('title', {}, g);
    ti.textContent = (title || '') + (errs.length ? '\n' + errs.join('\n') : '') + '\n(Klick: Befehl löschen)';
  };
  const slot = (k, x, y) => { stack[k] = (stack[k] || 0) + 1; return { x: x + (stack[k] - 1) * 4, y: y + (stack[k] - 1) * 12 }; };
  orders.forEach((o, i) => {
    const errs = (errors && errors[i]) || [];
    const army = o.army && state.armies[o.army];
    if (o.type === 'move' && army) {
      const pts = [army.field, ...o.path].map(centre);
      const ps = pts.map(p => p.x + ',' + p.y).join(' ');
      mk('polyline', { points: ps, class: 'ord-move' + (errs.length ? ' err' : ''), 'data-ord': i, 'marker-end': `url(#ah${errs.length ? 'e' : ''})` }, L.orders);
      const a = pts[0], b = pts[1] || pts[0];
      marker(i, (a.x + b.x) / 2, (a.y + b.y) / 2, String(++seq), errs, `Zug ${seq}: ${o.count} Div.`);
    } else if (o.type === 'recruit' || o.type === 'build_ship') {
      const c = centre(o.field), p = slot('r' + o.field, c.x + 9, c.y - 11);
      marker(i, p.x, p.y, '+' + o.count, errs, o.type === 'recruit' ? 'Rekrutieren' : 'Schiffe bauen');
    } else if ((o.type === 'link' || o.type === 'unlink') && state.armies[o.fleet || o.army]) {
      const c = centre(state.armies[o.fleet || o.army].field);
      marker(i, c.x, c.y + 15, o.type === 'link' ? '⛓' : '⛓×', errs, o.type === 'link' ? 'Verbinden' : 'Trennen');
    } else if (o.type === 'disband' && army) {
      const c = centre(army.field), p = slot('d' + army.field, c.x + 9, c.y + 11);
      marker(i, p.x, p.y, '−' + o.count, errs, 'Abrüsten');
    } else if (o.type === 'forced_march' && army) {
      const c = centre(army.field);
      marker(i, c.x - 12, c.y + 11, o.on ? '»' : '»×', errs, o.on ? 'Gewaltmarsch an' : 'Gewaltmarsch aus');
    }
  });
}

// Standing marches of own armies: faint dotted line with a small destination flag. routes = [[start, ...fields]].
export function showStanding(routes) {
  clear(L.routes);
  for (const r of routes) {
    if (r.length < 2) continue;
    mk('polyline', { points: r.map(centre).map(p => p.x + ',' + p.y).join(' '), class: 'standing' }, L.routes);
    const c = centre(r[r.length - 1]);
    mk('path', { d: `M${c.x - 2} ${c.y + 6}V${c.y - 9}L${c.x + 7} ${c.y - 5}L${c.x - 2} ${c.y - 1}`, class: 'standing-flag' }, L.routes);
  }
}

// Reachable fields as a subtle overlay. cells = [[field, kind]], kind 'go' | 'attack'. Empty/null clears it.
export function setReach(cells) {
  clear(L.reach);
  svg.classList.toggle('picking', !!(cells && cells.length));
  for (const [f, kind] of cells || []) {
    const { x, y } = centre(f);
    mk('polygon', { points: hexPts(x, y), class: 'reach ' + kind }, L.reach);
  }
}
// Emphasise the map elements of order i (order list hover); null = none.
export function focusOrder(i) {
  L.orders.querySelectorAll('.focus').forEach(e => e.classList.remove('focus'));
  if (i != null) L.orders.querySelectorAll(`[data-ord="${i}"]`).forEach(e => e.classList.add('focus'));
}

// Path preview under the cursor / while collecting waypoints. fields = [start, ...path] or null; ok=false draws red.
export function showDraft(fields, ok = true, waypoints = []) {
  clear(L.draft);
  if (!fields || fields.length < 2) return;
  const pts = fields.map(centre);
  mk('polyline', { points: pts.map(p => p.x + ',' + p.y).join(' '), class: 'draft' + (ok ? '' : ' bad'), 'marker-end': `url(#ah${ok ? '' : 'e'})` }, L.draft);
  for (const w of waypoints) { const c = centre(w); mk('circle', { cx: c.x, cy: c.y, r: 4, class: 'wp' }, L.draft); }
}

// Outline fields; kind is free text used for CSS ("sel", "rp-from" ...).
export function highlight(fields, kind = 'sel') {
  for (const f of fields) {
    const { x, y } = centre(f);
    mk('polygon', { points: hexPts(x, y), class: 'hx', 'data-kind': kind }, L.hi);
  }
}
export function clearHighlight(prefix = '') {
  [...L.hi.children].forEach(e => { if (e.dataset.kind.startsWith(prefix)) e.remove(); });
}

// Chat references on the map. marks = [{kind: 'field', f} | {kind: 'arrow', path: [f, ...]}];
// cls is a CSS class for the look (e.g. 'chat', 'chat-flash'). Empty/null clears that class.
export function showMarks(marks, cls = 'chat') {
  [...L.marks.children].forEach(e => { if (e.dataset.cls === cls) e.remove(); });
  for (const m of marks || []) {
    if (m.kind === 'field') {
      const { x, y } = centre(m.f);
      mk('polygon', { points: hexPts(x, y), class: 'mark ' + cls, 'data-cls': cls }, L.marks);
    } else if (m.kind === 'arrow' && m.path && m.path.length > 1) {
      const ps = m.path.map(centre).map(p => p.x + ',' + p.y).join(' ');
      mk('polyline', { points: ps, class: 'mark-arrow ' + cls, 'data-cls': cls, 'marker-end': 'url(#ahc)' }, L.marks);
    }
  }
}
// Centre the view on a field (zoom unchanged).
export function panTo(f) {
  const { x, y } = centre(f);
  vb.x = x - vb.w / 2; vb.y = y - vb.h / 2; applyVb();
}

// ======================= replay (replay.js) =======================
// Everything below serves the animated turn replay. Looks come from replay.css (.fx-*) and theme colours.
const capKeys = () => new Set(Object.values(curMap.provinces).map(p => p.capital.join()));
const tokenPos = (f, caps) => { const c = centre(f); return { x: c.x, y: c.y + (caps.has(f.join()) ? S * 0.35 : 0) }; };
const fxLayer = () => L.fx || (L.fx = mk('g', { id: 'l-fx' }, svg));
const ease = 'cubic-bezier(.4,0,.2,1)';

// Replay mode: hides order arrows and selection overlays, blocks nothing else (input is ignored by the caller).
export function setReplayMode(on) {
  svg.classList.toggle('replaying', !!on);
  for (const n of ['orders', 'draft', 'reach', 'hi']) L[n].style.display = on ? 'none' : '';
  if (!on) clear(fxLayer());
}
// Draw a whole board: armies = {id: army}, owners = {province: owner}. Instant.
export function drawBoard(armies, owners) {
  paintOwners(owners);
  drawArmies(Object.values(armies));
}
// Add or replace the shield of one army (e.g. after a split changed its number); returns the <g>.
export function putToken(a) {
  tokenEl(a.id)?.remove();
  return armyToken(a);
}
export const tokenEl = id => L.armies.querySelector(`[data-army="${id}"]`);
export const removeToken = id => tokenEl(id)?.remove();
// Slide a token along fields [from, ...path]; ms per hex. Resolves when done. Honors prefers-reduced-motion by jumping.
export function animateToken(g, fields, msPerHex) {
  if (!g || fields.length < 2) return Promise.resolve();
  const caps = capKeys(), pts = fields.map(f => tokenPos(f, caps)), p0 = pts[0];
  g.classList.add('moving');
  g.parentNode.appendChild(g); // on top
  const frames = pts.map(p => ({ transform: `translate(${p.x - p0.x}px,${p.y - p0.y}px)` }));
  const dur = msPerHex * (pts.length - 1);
  const anim = g.animate(frames, { duration: dur, easing: 'linear', fill: 'forwards' });
  return anim.finished.then(() => { g.classList.remove('moving'); }, () => {});
}
// Change a province's colour smoothly (the base fill already switches, the animation fades from the old one).
export function setProvinceFill(code, owner, ms) {
  const to = owner ? colorOf(owner) : (theme.neutral_color || '#888');
  const jobs = [];
  for (const p of polys[code] || []) {
    const from = p.getAttribute('fill');
    p.setAttribute('fill', to);
    if (ms > 0) jobs.push(p.animate([{ fill: from }, { fill: to }], { duration: ms, easing: ease }).finished.catch(() => {}));
  }
  return Promise.all(jobs);
}
// Flash the hexes of a province (all its fields) once.
export function flashProvince(code, ms, cls = 'fx-prov') {
  const jobs = [];
  for (const p of polys[code] || []) {
    const c = mk('polygon', { points: p.getAttribute('points'), class: cls }, fxLayer());
    jobs.push(c.animate([{ opacity: 0 }, { opacity: 0.85 }, { opacity: 0 }], { duration: ms }).finished.catch(() => {}).then(() => c.remove()));
  }
  return Promise.all(jobs);
}
// Short effect on a field. kind: 'fight' | 'conquest' | 'fail' | 'recruit' | 'disband' | 'merge' | 'gift' | 'march'.
// text: string, or for 'fight' [attackerText, defenderText]. Resolves after ms.
export function effect(field, kind, text, ms = 1000) {
  const { x, y } = centre(field), k = Math.min(3, Math.max(1, 0.9 / svg.getScreenCTM().a));  // keep effects readable when zoomed out
  const g = mk('g', { class: 'fx fx-' + kind, transform: `translate(${x} ${y}) scale(${k.toFixed(2)})` }, fxLayer());
  const run = (el, frames, o = {}) => el.animate(frames, { duration: ms, easing: ease, fill: 'forwards', ...o }).finished.catch(() => {});
  const jobs = [];
  const float = (s, dx, cls, delay = 0) => {
    const t = txt(g, dx, -4, s, 'fxt ' + cls);
    jobs.push(run(t, [{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(-6px)', offset: 0.2 },
      { opacity: 1, transform: 'translateY(-18px)', offset: 0.75 }, { opacity: 0, transform: 'translateY(-26px)' }], { delay }));
  };
  if (kind === 'fight') {
    mk('polygon', { points: hexPts(0, 0), class: 'fx-flash' }, g);
    jobs.push(run(g.firstChild, [{ opacity: 0 }, { opacity: 0.7, offset: 0.2 }, { opacity: 0 }]));
    const sw = mk('g', { class: 'fx-swords' }, g);
    mk('path', { d: 'M-10 -10L9 9M-10 10L9 -9M-12 -6L-6 -12M-12 6L-6 12M12 -6L6 -12M12 6L6 12' }, sw);
    jobs.push(run(sw, [{ transform: 'scale(.3) rotate(-30deg)', opacity: 0 }, { transform: 'scale(1.25) rotate(0deg)', opacity: 1, offset: 0.25 },
      { transform: 'scale(1) rotate(0deg)', opacity: 1, offset: 0.7 }, { transform: 'scale(1.1)', opacity: 0 }]));
    if (Array.isArray(text)) { float(text[0], -S * 0.8, 'fx-neg'); float(text[1], S * 0.8, 'fx-neg', 120); }
  } else if (kind === 'conquest' || kind === 'fail') {
    const ring = mk('polygon', { points: hexPts(0, 0), class: 'fx-ring' }, g);
    jobs.push(run(ring, [{ transform: 'scale(.6)', opacity: 0.9 }, { transform: 'scale(1.9)', opacity: 0 }]));
    if (text) float(text, 0, kind === 'fail' ? 'fx-dim' : 'fx-gold');
  } else {
    float(text || '', 0, kind === 'recruit' ? 'fx-pos' : kind === 'disband' ? 'fx-neg' : 'fx-gold');
    if (kind === 'recruit' || kind === 'gift' || kind === 'merge') {
      const ring = mk('polygon', { points: hexPts(0, 0), class: 'fx-ring soft' }, g);
      jobs.push(run(ring, [{ transform: 'scale(.7)', opacity: 0.7 }, { transform: 'scale(1.3)', opacity: 0 }]));
    }
  }
  return Promise.all(jobs).then(() => g.remove());
}
export const clearFx = () => { if (L.fx) clear(L.fx); };

// Camera: is the field comfortably inside the current view? / smoothly centre on a field (zoom unchanged).
export function isVisible(f, margin = 0.12) {
  const { x, y } = centre(f);
  return x > vb.x + vb.w * margin && x < vb.x + vb.w * (1 - margin) && y > vb.y + vb.h * margin && y < vb.y + vb.h * (1 - margin);
}
let panId = 0;
export const viewCentre = () => ({ x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 });
export function panSmooth(pt, ms) {
  const lim = (v, lo, hi) => (hi < lo ? (lo + hi) / 2 : Math.min(hi, Math.max(lo, v)));  // stay inside the map
  const x0 = vb.x, y0 = vb.y, t0 = performance.now();
  const x1 = lim(pt.x - vb.w / 2, full.x, full.x + full.w - vb.w), y1 = lim(pt.y - vb.h / 2, full.y, full.y + full.h - vb.h);
  const id = ++panId;  // a newer pan (or an instant one) cancels this one
  if (!(ms > 0)) { vb.x = x1; vb.y = y1; applyVb(); return Promise.resolve(); }
  return new Promise(res => {
    const step = now => {
      if (id !== panId) { res(); return; }
      const k = Math.min(1, (now - t0) / ms), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      vb.x = x0 + (x1 - x0) * e; vb.y = y0 + (y1 - y0) * e; applyVb();
      if (k < 1) requestAnimationFrame(step); else res();
    };
    requestAnimationFrame(step);
  });
}

// ---------- route drawing (input.js) ----------
// solid = [start, ...fields] reachable this turn, faint = [stop, ...rest] beyond range, waypoints = fields, stop = end of this turn's march.
export function showRoute(solid, faint = [], waypoints = [], stop = null, attack = false) {
  clear(L.draft);
  if (!solid || solid.length < 2) return;
  const line = (fields, cls, end) => mk('polyline', { points: fields.map(centre).map(p => p.x + ',' + p.y).join(' '), class: cls, ...(end ? { 'marker-end': `url(#ah${attack ? 'e' : ''})` } : {}) }, L.draft);
  if (faint && faint.length > 1) line(faint, 'route-far');
  line(solid, 'route-near' + (attack ? ' attack' : ''), !(faint && faint.length > 1));
  for (const w of waypoints) { const c = centre(w); mk('circle', { cx: c.x, cy: c.y, r: 4.5, class: 'wp' }, L.draft); }
  if (stop) {
    const c = centre(stop);
    mk('circle', { cx: c.x, cy: c.y, r: S * 0.62, class: 'route-stop' + (attack ? ' attack' : '') }, L.draft);
    if (!attack) mk('path', { d: `M${c.x + 3} ${c.y + 4}V${c.y - 11}L${c.x + 12} ${c.y - 7}L${c.x + 3} ${c.y - 3}`, class: 'route-flag' }, L.draft);
  }
}

// ======================= static rendering (statistics map, video frames) =======================
// boardSvg() returns SVG markup with every style inline (no CSS classes, no external fonts), so it works as innerHTML
// and as the source of an <img> (the video). Colours come from theme.json; theme.stats may override the fallbacks below.
const XFONT = "'Palatino Linotype','Book Antiqua',Georgia,serif";
const xe = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const statsTheme = th => ({ heat: '#e0482b', heat_min_opacity: 0.18, heat_max_opacity: 0.9, veil_opacity: 0.5,
  panel: '#2b1a10', panel_opacity: 0.8, text: '#fbf3dc', ...((th || {}).stats || {}) });
// Heat colour and opacity for a value between 0 and 1 (also used by the legend).
export const heatStyle = (th, t) => {
  const st = statsTheme(th);
  return { fill: st.heat, opacity: +(st.heat_min_opacity + (st.heat_max_opacity - st.heat_min_opacity) * Math.max(0, Math.min(1, t))).toFixed(3) };
};
let geoCache = {};
// Everything about a map that does not depend on the board: sea and terrain hexes, land hex outlines, borders, ports, capitals.
function geometry(map, th) {
  if (geoCache.map === map && geoCache.th === th) return geoCache.geo;
  const grid = parseGrid(map.grid), P = map.provinces, ink = th.ink || th.hex_outline || '#222', sea = ((th.terrain || {})['~~'] || {}).fill || '#356';
  const lay = layoutOf(grid, P), pts = {};
  let seaS = '', terr = '', ports = '', caps = '';
  const land = [];
  grid.forEach((row, r) => row.forEach((tok, c) => {
    if (tok === '..') return;
    const { x, y } = centre([c, r]), hp = hexPts(x, y);
    pts[c + ',' + r] = hp;
    if (P[tok]) land.push([tok, hp]);
    else if (tok === '~~') seaS += `<polygon points="${hp}" fill="url(#stx-sea)" stroke="${xe(th.hex_outline || '#000')}" stroke-width="0.5" stroke-opacity="0.08"/>`;
    else terr += `<polygon points="${hp}" fill="${xe(((th.terrain || {})[tok] || {}).fill || '#444')}" stroke="${xe(th.hex_outline || '#000')}" stroke-width="0.5" stroke-opacity="0.08"/>`;
  }));
  for (const p of Object.values(P)) {
    for (const f of p.ports || []) { const { x, y } = centre(f); ports += `<text x="${x + S * 0.5}" y="${y + S * 0.45}" font-size="9" opacity="0.75" text-anchor="middle" style="fill:#1d1008;stroke:none">${xe(th.port_icon || '⚓')}</text>`; }
    const { x, y } = centre(p.capital);
    caps += th.capital_icon === 'castle' ? `<use href="#stx-castle" x="${x - 8}" y="${y - S * 0.3 - 10}" width="16" height="16"/>`
      : `<text x="${x}" y="${y - S * 0.3}" font-size="12" text-anchor="middle" style="fill:#fbf3dc;stroke:none">${xe(th.capital_icon || '*')}</text>`;
  }
  const defs = `<defs><pattern id="stx-sea" width="24" height="14" patternUnits="userSpaceOnUse"><rect width="24" height="14" fill="${xe(sea)}"/>`
    + `<path d="M1 4Q4 1 7 4T13 4T19 4M13 11Q16 8 19 11T25 11M-5 11Q-2 8 1 11T7 11" fill="none" stroke="${xe(th.sea_wave || '#fff')}" stroke-width="0.9" stroke-opacity="0.4" stroke-linecap="round"/></pattern>`
    + `<symbol id="stx-castle" viewBox="0 0 24 24"><path d="M3 21V9h3V6h2v3h2V6h4v3h2V6h2v3h3v12z M10 21v-5a2 2 0 0 1 4 0v5z" fill="#efe0b4" stroke="${xe(ink)}" stroke-width="1.6" stroke-linejoin="round" fill-rule="evenodd"/>`
    + `<path d="M12 6V1.5l4 1.5-4 1.5" fill="#8c2a1e" stroke="${xe(ink)}" stroke-width="1" stroke-linejoin="round"/></symbol></defs>`;
  const geo = { grid, pts, land, seaS, terr, ports, caps, defs, full: lay.full, view: lay.view, border: lay.d };
  geoCache = { map, th, geo };
  return geo;
}
function shieldSvg(a, x, y, fleet, th) {
  const label = String(a.divisions), w = Math.max(24, label.length * 9 + 12), l = x - w / 2, r = x + w / 2, t0 = y - 13;
  const sh = `M${l} ${t0}H${r}V${y + 3}Q${r} ${y + 9} ${x} ${y + 13}Q${l} ${y + 9} ${l} ${y + 3}Z`;
  const hull = `M${l - 3} ${t0 + 4}H${r + 3}L${r - 3} ${y + 10}H${l + 3}Z`, d = fleet ? hull : sh;
  return `<path d="${d}" fill="none" stroke="#1d1008" stroke-width="3.4" stroke-linejoin="round"/>`
    + `<path d="${d}" fill="${fleet ? '#dfe9ef' : '#f4e6c2'}" stroke="${fleet ? '#7fa3b8' : '#d9b25a'}" stroke-width="1.3"/>`
    + `<rect x="${l}" y="${t0}" width="${w}" height="6" fill="${xe(colorIn(th, a.owner))}" stroke="#1d1008" stroke-width="0.8"/>`
    + `<text x="${x}" y="${y + 2}" font-size="15" font-weight="700" text-anchor="middle" dominant-baseline="central" style="fill:#2b1a10;stroke:none">${xe(label)}</text>`;
}
// board = {armies, owners} (a replay snapshot or the end board). opts:
//   width (px, default 1000), height (px; default follows the map's shape; if set the map is centred in it),
//   view: 'province' (default, the province area) or 'full'; armies: false hides the unit shields;
//   heat: {"c,r": value} + heatMax -> heatmap over a veil; titleOf(fieldKey, value) -> tooltip text;
//   label: {title, sub} panel at the top left; bar: [{color, share, label}] land-share bar at the bottom.
export function boardSvg(map, th, rules, board, opts = {}) {
  th = th || {};
  const geo = geometry(map, th), st = statsTheme(th), owners = board.owners || {};
  const W = opts.width || 1000;
  let view = opts.view === 'full' ? geo.full : geo.view, H = opts.height;
  if (H) {
    let { x, y, w, h } = view; const aspect = W / H;
    if (w / h < aspect) { const nw = h * aspect; x -= (nw - w) / 2; w = nw; } else { const nh = w / aspect; y -= (nh - h) / 2; h = nh; }
    view = { x, y, w, h };
  } else H = Math.round(W * view.h / view.w);
  const neutral = th.neutral_color || '#888', bg = th.background || '#000';
  let out = `<svg xmlns="${NS}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="${XFONT}">`
    + `<rect width="${W}" height="${H}" fill="${xe(bg)}"/>`
    + `<svg x="0" y="0" width="${W}" height="${H}" viewBox="${view.x} ${view.y} ${view.w} ${view.h}">${geo.defs}${geo.seaS}${geo.terr}`;
  for (const [tok, hp] of geo.land) out += `<polygon points="${hp}" fill="${xe(owners[tok] ? colorIn(th, owners[tok]) : neutral)}" stroke="${xe(th.hex_outline || '#000')}" stroke-width="0.5" stroke-opacity="0.22"/>`;
  out += `<path d="${geo.border}" fill="none" stroke="${xe(th.province_border || '#fff')}" stroke-width="2.4" stroke-opacity="0.85" stroke-linecap="round" stroke-linejoin="round"/>${geo.ports}${geo.caps}`;
  if (opts.heat) {
    out += `<rect x="${view.x}" y="${view.y}" width="${view.w}" height="${view.h}" fill="${xe(bg)}" fill-opacity="${st.veil_opacity}"/>`;
    const max = opts.heatMax || Math.max(1, ...Object.values(opts.heat));
    for (const key in opts.heat) {
      const v = opts.heat[key], hp = geo.pts[key];
      if (!hp || !(v > 0)) continue;
      const h = heatStyle(th, v / max);
      out += `<polygon points="${hp}" fill="${xe(h.fill)}" fill-opacity="${h.opacity}" stroke="${xe(st.text)}" stroke-width="0.6" stroke-opacity="0.35">${opts.titleOf ? `<title>${xe(opts.titleOf(key, v))}</title>` : ''}</polygon>`;
    }
  }
  if (opts.armies !== false) {
    const caps = new Set(Object.values(map.provinces).map(p => p.capital.join())), list = Object.values(board.armies || {});
    const isF = a => ((rules.unit_types || {})[a.unit || rules.land_unit] || {}).terrain === 'sea';
    for (const a of list) {
      const c = centre(a.field), fleet = isF(a), mates = list.filter(b => b.field.join() === a.field.join()).length;
      out += shieldSvg(a, c.x + (mates < 2 ? 0 : fleet ? -S * 0.55 : S * 0.55), c.y + (caps.has(a.field.join()) ? S * 0.35 : 0), fleet, th);
    }
  }
  out += '</svg>';
  const panel = (x, y, w, h) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="${xe(st.panel)}" fill-opacity="${st.panel_opacity}"/>`;
  if (opts.label) {
    const sub = opts.label.sub ? String(opts.label.sub) : '', w = Math.max(190, 30 + Math.max(String(opts.label.title).length * 22, sub.length * 11));
    out += panel(16, 16, w, sub ? 84 : 56) + `<text x="30" y="${sub ? 54 : 52}" font-size="34" font-weight="700" style="fill:${xe(st.text)};stroke:none">${xe(opts.label.title)}</text>`;
    if (sub) out += `<text x="30" y="84" font-size="18" style="fill:${xe(st.text)};fill-opacity:0.85;stroke:none">${xe(sub)}</text>`;
  }
  if (opts.bar && opts.bar.length) {
    const bw = W - 32, y = H - 46;
    let x = 16, used = 0;
    out += panel(10, y - 8, W - 20, 40);
    for (const seg of opts.bar) {
      const w = bw * seg.share;
      if (!(w > 0)) continue;
      used += seg.share;
      out += `<rect x="${x.toFixed(1)}" y="${y}" width="${w.toFixed(1)}" height="24" fill="${xe(seg.color)}"/>`;
      if (w > 64) out += `<text x="${(x + w / 2).toFixed(1)}" y="${y + 12}" font-size="15" font-weight="700" text-anchor="middle" dominant-baseline="central" style="fill:#fff;stroke:#000;stroke-width:2.5px;paint-order:stroke">${xe(seg.label)}</text>`;
      x += w;
    }
    if (used < 1) out += `<rect x="${x.toFixed(1)}" y="${y}" width="${(bw * (1 - used)).toFixed(1)}" height="24" fill="${xe(neutral)}"/>`;
  }
  return out + '</svg>';
}
