// The ONLY module that knows about SVG and colours (IMPLEMENTATION 4.2).
// Colours come from state.theme (theme.json) and CSS variables/classes in style.css.
import { neighbours, parseGrid } from './hex.js';

const S = 20, SQ3 = Math.sqrt(3), NS = 'http://www.w3.org/2000/svg';
let svg, L = {}, H = {}, theme = {}, mapKey = null, polys = {}, vb, full, down = null, hoverKey = null, rows = [], viewHooks = [];

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
export const colorOf = pid => (theme.nation_colors || {})[pid] || theme.neutral_color || '#888';

export function init(svgEl, handlers) {
  svg = svgEl; H = handlers; svg.innerHTML = '';
  const defs = mk('defs', {}, svg);
  for (const err of [false, true]) {
    const m = mk('marker', { id: 'ah' + (err ? 'e' : ''), viewBox: '0 0 10 10', refX: 7, refY: 5, markerWidth: 4, markerHeight: 4, orient: 'auto' }, defs);
    mk('path', { d: 'M0 0L10 5L0 10z', class: 'arrowhead' + (err ? ' err' : '') }, m);
  }
  const mc = mk('marker', { id: 'ahc', viewBox: '0 0 10 10', refX: 7, refY: 5, markerWidth: 4, markerHeight: 4, orient: 'auto' }, defs);
  mk('path', { d: 'M0 0L10 5L0 10z', class: 'arrowhead chat' }, mc);
  for (const n of ['base', 'reach', 'hi', 'marks', 'armies', 'orders', 'draft']) L[n] = mk('g', { id: 'l-' + n }, svg);
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

function buildBase(state) {
  buildDefs();
  clear(L.base); polys = {};
  const grid = rows = parseGrid(state.map.grid), P = state.map.provinces;
  const border = mk('path', { class: 'border', stroke: theme.province_border || '#fff', 'stroke-width': 2.4, 'stroke-opacity': 0.85 }, null);
  let d = '', maxc = 0, maxr = 0;
  const pb = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  grid.forEach((row, r) => row.forEach((tok, c) => {
    if (tok === '..') return;
    maxc = Math.max(maxc, c); maxr = Math.max(maxr, r);
    const { x, y } = centre([c, r]);
    const poly = mk('polygon', { points: hexPts(x, y), stroke: theme.hex_outline || '#000', 'stroke-width': 0.5, 'stroke-opacity': P[tok] ? 0.22 : 0.08, class: P[tok] ? 'land' : 'terr' }, L.base);
    if (P[tok]) (polys[tok] = polys[tok] || []).push(poly);
    else poly.setAttribute('fill', tok === '~~' ? 'url(#sea-pat)' : ((theme.terrain || {})[tok] || {}).fill || '#444');
    if (!P[tok]) return;
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
  border.setAttribute('d', d); L.base.appendChild(border);
  for (const p of Object.values(P)) {
    const { x, y } = centre(p.capital);
    let t;
    if (theme.capital_icon === 'castle') t = mk('use', { href: '#castle', x: x - 8, y: y - S * 0.3 - 10, width: 16, height: 16, class: 'cap' }, L.base);
    else t = txt(L.base, x, y - S * 0.3, theme.capital_icon || '*', 'cap');
    const ti = mk('title', {}, t); ti.textContent = p.capital_name;
  }
  full = { x: 0, y: 0, w: (maxc * 1.5 + 2) * S, h: (maxr + 1.5) * SQ3 * S + S };
  // start zoomed to the province area (+ a margin), the wheel still zooms out to the full map
  const m = 2 * S;
  vb = pb.x0 < Infinity ? { x: pb.x0 - m, y: pb.y0 - m, w: pb.x1 - pb.x0 + 2 * m, h: pb.y1 - pb.y0 + 2 * m } : { ...full };
  applyVb();
}

export function drawMap(state) {
  theme = state.theme || {};
  svg.style.background = theme.background || '#000';
  if (mapKey !== state.map.name) { mapKey = state.map.name; buildBase(state); }
  for (const tok in polys) {
    const o = state.owners[tok];
    for (const p of polys[tok]) p.setAttribute('fill', o ? colorOf(o) : (theme.neutral_color || '#888'));
  }
  clear(L.armies);
  const capSet = new Set(Object.values(state.map.provinces).map(p => p.capital.join()));
  for (const a of Object.values(state.armies)) {
    const { x, y } = centre(a.field), yy = y + (capSet.has(a.field.join()) ? S * 0.35 : 0);
    const fresh = a.fresh || 0, label = String(a.divisions - fresh) + (fresh ? '+' + fresh : '');
    // light parchment shield with a band in the owner's colour, so it stands out on its own land
    const w = Math.max(24, label.length * 9 + 12), l = x - w / 2, r = x + w / 2, t0 = yy - 13;
    const sh = `M${l} ${t0}H${r}V${yy + 3}Q${r} ${yy + 9} ${x} ${yy + 13}Q${l} ${yy + 9} ${l} ${yy + 3}Z`;
    const g = mk('g', { class: 'army' + (fresh ? ' has-fresh' : ''), 'data-army': a.id }, L.armies);
    mk('path', { d: sh, class: 'badge-rim' }, g);
    mk('path', { d: sh, class: 'badge' }, g);
    mk('rect', { x: l, y: t0, width: w, height: 6, fill: colorOf(a.owner), class: 'badge-chief' }, g);
    const t = txt(g, x, yy + 2, '', 'divs');
    const s1 = mk('tspan', {}, t); s1.textContent = String(a.divisions - fresh);
    if (fresh) { const s2 = mk('tspan', { class: 'fresh' }, t); s2.textContent = '+' + fresh; }
    if (a.forced_march) {
      mk('circle', { cx: l - 1, cy: t0 + 3, r: 6, class: 'fmseal' }, g);
      txt(g, l - 1, t0 + 3, '»', 'fmflag');
    }
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
    } else if (o.type === 'recruit') {
      const c = centre(o.field), p = slot('r' + o.field, c.x + 9, c.y - 11);
      marker(i, p.x, p.y, '+' + o.count, errs, 'Rekrutieren');
    } else if (o.type === 'disband' && army) {
      const c = centre(army.field), p = slot('d' + army.field, c.x + 9, c.y + 11);
      marker(i, p.x, p.y, '−' + o.count, errs, 'Abrüsten');
    } else if (o.type === 'forced_march' && army) {
      const c = centre(army.field);
      marker(i, c.x - 12, c.y + 11, o.on ? '»' : '»×', errs, o.on ? 'Gewaltmarsch an' : 'Gewaltmarsch aus');
    }
  });
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
