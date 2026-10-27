// Map editor (RULES.md 12): load a map from maps/, change provinces, borders (painting), ports, nations, victory rules
// and the AI ruleset, then save through PUT /api/maps/{name} (the server validates with the engine's map loader).
// Looks come from the map's theme.json; nothing here is game logic beyond keeping the map self-consistent.
import { api } from './api.js';
import { neighbours, parseGrid } from './hex.js';

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const NS = 'http://www.w3.org/2000/svg', SQ3 = Math.sqrt(3);
const SEA = '~~';
// Rule overrides the editor offers (victory conditions and the AI ruleset). Values come from the server's defaults.
const RULE_FIELDS = [
  ['max_alliance_size', 'Maximale Bündnisgröße', 1], ['victory_share_single', 'Sieg allein ab Anteil (0–1)', 0.01],
  ['victory_share_alliance', 'Sieg im Bündnis ab Anteil (0–1)', 0.01], ['alliance_min_turns', 'Mindestalter eines Bündnisses (Runden)', 1],
  ['victory_hold_turns', 'Siegbedingung halten (Runden)', 1], ['ai_recruit_per_city', 'KI: Rekruten pro Stadt und Runde', 1],
  ['start_gold', 'Startgold (Standard aller Nationen)', 1],
];

let M = null, T = {}, grid = [], defaults = {}, S = 14, tool = 'select', sel = null, cells = [], painting = false, dirty = false;
let svg, gCells, gBorders, gMarks;

const msg = (text, err) => { $('ed-msg').textContent = text || ''; $('ed-msg').className = 'msg' + (err ? ' err' : ''); };
const provs = () => M.provinces;
const tok = (c, r) => (grid[r] || [])[c];
const isLand = t => !!provs()[t];
const colorOfNation = n => (T.nation_colors || {})[n] || T.neutral_color || '#888';
const center = (c, r) => [c * 1.5 * S + S, (r + (c % 2 ? 0 : 0.5)) * SQ3 * S + S];
const hexPoints = (c, r) => { const [x, y] = center(c, r); return [0, 1, 2, 3, 4, 5].map(i => `${(x + S * Math.cos(i * Math.PI / 3)).toFixed(1)},${(y + S * Math.sin(i * Math.PI / 3)).toFixed(1)}`).join(' '); };
const mk = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
const same = (a, b) => a && b && a[0] === b[0] && a[1] === b[1];
const cellFill = t => isLand(t) ? colorOfNation(provs()[t].owner) : ((T.terrain || {})[t] || {}).fill || (t === SEA ? '#3d6670' : (t[0] === '#' || t[0] === '.') ? (T.background || '#222') : (T.neutral_color || '#888'));

// ---------- load / save ----------
async function loadMapByName(name) {
  const [m, t] = await Promise.all([fetch(`/maps/${encodeURIComponent(name)}/map.json`).then(r => r.json()),
    fetch(`/maps/${encodeURIComponent(name)}/theme.json`).then(r => r.json()).catch(() => ({}))]);
  setMap(m, t); $('ed-name').value = name; msg(`Karte „${name}“ geladen.`);
}
function setMap(m, t) {
  M = m; T = t; M.rules = M.rules || {}; M.start_armies = M.start_armies || []; T.nation_colors = T.nation_colors || {};
  grid = parseGrid(M.grid); sel = Object.keys(provs())[0] || null; dirty = false;
  $('ed-title').value = M.name || '';
  buildAll();
}
function newMap(w, h) {
  const t = JSON.parse(JSON.stringify(T));
  const colors = Object.values(t.nation_colors || {});
  t.nation_colors = { AA: colors[0] || '#888', BB: colors[1] || '#888' };
  setMap({ name: 'Neue Karte', version: 1, nations: { AA: { name: 'Nation A' }, BB: { name: 'Nation B' } }, provinces: {},
    grid: Array.from({ length: h }, () => Array(w).fill(SEA).join(' ')), start_armies: [], rules: {} }, t);
  $('ed-name').value = ''; msg('Neue Karte: Provinzen mit „Neue Provinz“ anlegen und mit „Malen“ Felder zuweisen.');
}
// Keep the map self-consistent after edits: no empty provinces, capital and ports inside, start armies on land.
function normalize() {
  const fields = {};
  grid.forEach((row, r) => row.forEach((t, c) => { if (isLand(t)) (fields[t] ||= []).push([c, r]); }));
  for (const code of Object.keys(provs())) {
    const f = fields[code], p = provs()[code];
    if (!f) { delete provs()[code]; if (sel === code) sel = null; continue; }
    if (!p.capital || !f.some(x => same(x, p.capital))) p.capital = f[0];
    p.ports = (p.ports || []).filter(q => f.some(x => same(x, q)) && neighbours(q[0], q[1]).some(n => tok(...n) === SEA));
    if (!p.ports.length) delete p.ports;
  }
  M.start_armies = M.start_armies.filter(a => isLand(tok(...a.field)));
  for (const [code, p] of Object.entries(provs())) if (p.owner && !M.nations[p.owner]) { p.owner = null; msg(`Besitzer von ${code} entfernt.`, true); }
  M.grid = grid.map(r => r.join(' '));
}
async function save() {
  const name = $('ed-name').value.trim();
  if (!name) { msg('Bitte einen Ordnernamen zum Speichern eingeben.', true); $('ed-name').focus(); return; }
  M.name = $('ed-title').value.trim() || name;
  normalize(); buildAll();
  try {
    await api.saveMap(name, { map: M, theme: T, theme_from: $('ed-load').value });
    dirty = false; msg(`Gespeichert als „${name}“. Die Karte erscheint jetzt in der Lobby.`); listMaps(name);
  } catch (e) { msg(e.message, true); }
}
async function listMaps(select) {
  const names = await api.maps();
  $('ed-load').innerHTML = names.map(n => `<option>${esc(n)}</option>`).join('');
  $('ed-names').innerHTML = names.map(n => `<option value="${esc(n)}">`).join('');
  if (select) $('ed-load').value = select;
}

// ---------- drawing ----------
function buildAll() {
  buildMap(); renderProv(); renderNations(); renderRules();
}
function buildMap() {
  const cols = Math.max(...grid.map(r => r.length));
  svg = $('ed-map'); svg.innerHTML = '';
  svg.setAttribute('width', (cols * 1.5 + 1) * S + S); svg.setAttribute('height', (grid.length + 1) * SQ3 * S + S);
  gCells = mk('g', {}, svg); gBorders = mk('g', { class: 'ed-borders' }, svg); gMarks = mk('g', { class: 'ed-marks' }, svg);
  cells = grid.map((row, r) => row.map((t, c) => {
    const p = mk('polygon', { points: hexPoints(c, r), 'data-c': c, 'data-r': r, class: 'ed-cell' }, gCells);
    p.setAttribute('fill', cellFill(t)); return p;
  }));
  drawOverlay();
}
const recolor = () => grid.forEach((row, r) => row.forEach((t, c) => cells[r][c].setAttribute('fill', cellFill(t))));
function drawOverlay() {
  // province borders: the edge between two cells with different tokens
  let d = '';
  grid.forEach((row, r) => row.forEach((t, c) => {
    const [x, y] = center(c, r);
    for (const [nc, nr] of neighbours(c, r)) {
      if (tok(nc, nr) === undefined || tok(nc, nr) === t || (nc < c) || (nc === c && nr < r)) continue;
      const [nx, ny] = center(nc, nr), a = Math.atan2(ny - y, nx - x), i = ((Math.round((a * 180 / Math.PI - 30) / 60) % 6) + 6) % 6;
      const p1 = [x + S * Math.cos(i * Math.PI / 3), y + S * Math.sin(i * Math.PI / 3)], p2 = [x + S * Math.cos((i + 1) * Math.PI / 3), y + S * Math.sin((i + 1) * Math.PI / 3)];
      d += `M${p1[0].toFixed(1)} ${p1[1].toFixed(1)}L${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
  }));
  gBorders.innerHTML = ''; mk('path', { d }, gBorders);
  gMarks.innerHTML = '';
  for (const [code, p] of Object.entries(provs())) {
    if (p.capital) { const [x, y] = center(...p.capital); mk('circle', { cx: x, cy: y, r: S * 0.42, class: 'ed-cap' + (code === sel ? ' sel' : '') }, gMarks); }
    for (const q of p.ports || []) { const [x, y] = center(...q); mk('text', { x, y: y + S * 0.85, 'text-anchor': 'middle', class: 'ed-port' }, gMarks).textContent = '⚓'; }
  }
  if (sel && provs()[sel]) {   // outline the selected province
    grid.forEach((row, r) => row.forEach((t, c) => { if (t === sel) cells[r][c].classList.add('insel'); else cells[r][c].classList.remove('insel'); }));
  } else gCells.querySelectorAll('.insel').forEach(e => e.classList.remove('insel'));
}

// ---------- editing ----------
function setCell(c, r, token) {
  if (tok(c, r) === token || tok(c, r) === undefined) return;
  grid[r][c] = token; cells[r][c].setAttribute('fill', cellFill(token)); dirty = true;
}
function onCell(c, r, first) {
  const t = tok(c, r);
  if (tool === 'select') { if (isLand(t)) { sel = t; renderProv(); drawOverlay(); } return; }
  if (!sel && tool !== 'paint') return;
  const p = provs()[sel];
  if (tool === 'capital') {
    if (t === sel) { p.capital = [c, r]; dirty = true; drawOverlay(); renderProv(); } else msg('Die Hauptstadt muss in der gewählten Provinz liegen.', true);
  } else if (tool === 'port') {
    if (t !== sel) { msg('Der Hafen muss in der gewählten Provinz liegen.', true); return; }
    if (!neighbours(c, r).some(n => tok(...n) === SEA)) { msg('Ein Hafen braucht ein Nachbarfeld mit Meer.', true); return; }
    p.ports = p.ports || [];
    const i = p.ports.findIndex(q => same(q, [c, r]));
    if (i >= 0) p.ports.splice(i, 1); else p.ports.push([c, r]);
    dirty = true; drawOverlay(); renderProv();
  } else if (tool === 'paint') {
    const brush = document.querySelector('input[name=brush]:checked').value, token = brush === 'prov' ? sel : brush;
    if (!token) { if (first) msg('Erst eine Provinz wählen oder anlegen.', true); return; }
    setCell(c, r, token);
    if (token === sel && !p.capital) p.capital = [c, r];
  }
}
function newProvince() {
  const owner = $('ed-newowner').value || null, prefix = owner || 'N';
  let n = 1; while (provs()[prefix + n]) n++;
  const code = prefix + n;
  provs()[code] = { name: 'Neue Provinz', capital_name: 'Neue Stadt', capital: null, income: 1, owner };
  sel = code; dirty = true; tool = 'paint'; setTool('paint');
  msg(`Provinz ${code} angelegt. Mit „Malen“ Felder zuweisen – das erste Feld wird zur Hauptstadt.`);
  renderProv(); drawOverlay();
}
function deleteProvince() {
  if (!sel || !confirm(`Provinz ${sel} (${provs()[sel].name}) löschen? Ihre Felder werden zu Meer.`)) return;
  grid.forEach((row, r) => row.forEach((t, c) => { if (t === sel) setCell(c, r, SEA); }));
  delete provs()[sel]; sel = Object.keys(provs())[0] || null; dirty = true;
  renderProv(); drawOverlay();
}

// ---------- panels ----------
function renderProv() {
  const keys = Object.keys(provs());
  $('ed-prov').innerHTML = keys.map(k => `<option value="${esc(k)}" ${k === sel ? 'selected' : ''}>${esc(k)} – ${esc(provs()[k].name)}</option>`).join('');
  $('ed-newowner').innerHTML = Object.entries(M.nations).map(([c, n]) => `<option value="${esc(c)}">${esc(n.name)}</option>`).join('') + '<option value="">neutral</option>';
  const p = sel && provs()[sel];
  $('ed-provform').innerHTML = !p ? '<p class="hint">Keine Provinz gewählt.</p>' :
    `<label>Name <input data-f="name" value="${esc(p.name)}"></label>` +
    `<label>Hauptstadt (Name) <input data-f="capital_name" value="${esc(p.capital_name)}"></label>` +
    `<label>Einkommen (Gold) <input data-f="income" type="number" min="0" step="0.5" value="${esc(p.income)}"></label>` +
    `<label>Besitzer <select data-f="owner">${Object.entries(M.nations).map(([c, n]) => `<option value="${esc(c)}" ${p.owner === c ? 'selected' : ''}>${esc(n.name)}</option>`).join('')}<option value="" ${p.owner ? '' : 'selected'}>neutral</option></select></label>` +
    `<p class="hint">Hauptstadt: ${p.capital ? p.capital.join('/') : '–'} · Häfen: ${(p.ports || []).map(q => q.join('/')).join(', ') || 'keine'}</p>` +
    '<button data-del="1" type="button" class="danger">Provinz löschen</button>';
}
function renderNations() {
  const count = {}; for (const p of Object.values(provs())) if (p.owner) count[p.owner] = (count[p.owner] || 0) + 1;
  $('ed-nations').innerHTML = '<table>' + Object.entries(M.nations).map(([c, n]) =>
    `<tr data-n="${esc(c)}"><td><input type="color" data-nf="color" value="${esc(colorOfNation(c).length === 7 ? colorOfNation(c) : '#888888')}" title="Farbe (theme.json)"></td>` +
    `<td><b>${esc(c)}</b></td><td><input data-nf="name" value="${esc(n.name)}" size="14"></td>` +
    `<td><input data-nf="start_gold" type="number" min="0" step="1" value="${esc(n.start_gold ?? '')}" placeholder="Startgold" title="Startgold dieser Nation (leer = Standard)"></td>` +
    `<td><small>${count[c] || 0} Prov.</small></td><td>${count[c] ? '' : '<button data-ndel="1" type="button" title="Nation löschen">✕</button>'}</td></tr>`).join('') + '</table>';
}
function renderRules() {
  $('ed-rules').innerHTML = RULE_FIELDS.map(([k, label, step]) =>
    `<label>${esc(label)} <input data-r="${k}" type="number" min="0" step="${step}" value="${esc(M.rules[k] ?? '')}" placeholder="${esc(defaults[k] ?? '')}"></label>`).join('');
}

// ---------- wiring ----------
function setTool(t) {
  tool = t;
  for (const b of $('ed-toolbtns').children) b.classList.toggle('on', b.dataset.tool === t);
  $('ed-brush').hidden = t !== 'paint';
}
function wire() {
  $('ed-toolbtns').onclick = e => { const b = e.target.closest('[data-tool]'); if (b) setTool(b.dataset.tool); };
  const wrap = $('ed-map');
  wrap.addEventListener('pointerdown', e => { const p = e.target.closest('.ed-cell'); if (!p || e.button) return; painting = true; onCell(+p.dataset.c, +p.dataset.r, true); });
  wrap.addEventListener('pointermove', e => {
    const p = e.target.closest('.ed-cell'); if (!p) return;
    const c = +p.dataset.c, r = +p.dataset.r, t = tok(c, r);
    $('ed-hover').textContent = `Feld ${c}/${r} · ${isLand(t) ? `${t} (${provs()[t].name})` : t === SEA ? 'Meer' : t}`;
    if (painting && tool === 'paint') onCell(c, r, false);
  });
  window.addEventListener('pointerup', () => { if (painting) { painting = false; if (tool === 'paint') { normalize(); drawOverlay(); renderProv(); renderNations(); } } });
  $('ed-prov').onchange = e => { sel = e.target.value; renderProv(); drawOverlay(); };
  $('ed-provform').oninput = e => {
    const f = e.target.dataset.f, p = provs()[sel]; if (!f || !p) return;
    p[f] = f === 'income' ? Math.max(0, +e.target.value || 0) : f === 'owner' ? (e.target.value || null) : e.target.value;
    dirty = true; if (f === 'owner') { recolor(); renderNations(); }
    if (f === 'name') $('ed-prov').selectedOptions[0].textContent = `${sel} – ${p.name}`;
  };
  $('ed-provform').onclick = e => { if (e.target.dataset.del) deleteProvince(); };
  $('ed-newprov').onclick = newProvince;
  $('ed-nations').oninput = e => {
    const tr = e.target.closest('tr'), c = tr && tr.dataset.n, f = e.target.dataset.nf; if (!c || !f) return;
    if (f === 'color') { T.nation_colors[c] = e.target.value; recolor(); }
    else if (f === 'name') M.nations[c].name = e.target.value;
    else if (e.target.value === '') delete M.nations[c].start_gold; else M.nations[c].start_gold = Math.max(0, +e.target.value || 0);
    dirty = true;
  };
  $('ed-nations').onclick = e => {
    const tr = e.target.closest('tr'); if (!tr || !e.target.dataset.ndel) return;
    const c = tr.dataset.n;
    if (Object.keys(M.nations).length <= 2) { msg('Mindestens zwei Nationen bleiben.', true); return; }
    if (!confirm(`Nation ${c} löschen?`)) return;
    delete M.nations[c]; delete T.nation_colors[c]; M.start_armies = M.start_armies.filter(a => a.owner !== c);
    dirty = true; renderNations(); renderProv();
  };
  $('ed-nadd').onclick = () => {
    const c = $('ed-ncode').value.trim().toUpperCase(), name = $('ed-nname').value.trim();
    if (!/^[A-Z]{2,3}$/.test(c)) { msg('Kürzel: 2–3 Buchstaben.', true); return; }
    if (M.nations[c]) { msg('Dieses Kürzel gibt es schon.', true); return; }
    if (!name) { msg('Bitte einen Namen eingeben.', true); return; }
    M.nations[c] = { name }; T.nation_colors[c] = T.neutral_color || '#888888';
    $('ed-ncode').value = $('ed-nname').value = ''; dirty = true; msg(`Nation ${c} hinzugefügt – Farbe links wählen.`);
    renderNations(); renderProv();
  };
  $('ed-rules').oninput = e => {
    const k = e.target.dataset.r; if (!k) return;
    if (e.target.value === '') delete M.rules[k]; else M.rules[k] = +e.target.value;
    dirty = true;
  };
  $('ed-load').onchange = () => { if (!dirty || confirm('Ungespeicherte Änderungen verwerfen?')) loadMapByName($('ed-load').value); else listMaps(); };
  $('ed-save').onclick = save;
  $('ed-new').onclick = () => { $('ed-newform').hidden = false; };
  $('ed-new-cancel').onclick = () => { $('ed-newform').hidden = true; };
  $('ed-new-go').onclick = () => {
    const w = Math.floor(+$('ed-w').value), h = Math.floor(+$('ed-h').value);
    if (!(w >= 3 && w <= 120 && h >= 3 && h <= 80)) { msg('Größe: Breite 3–120, Höhe 3–80.', true); return; }
    newMap(w, h); $('ed-newform').hidden = true;
  };
  $('ed-zoom-in').onclick = () => { S = Math.min(40, S + 3); buildMap(); };
  $('ed-zoom-out').onclick = () => { S = Math.max(6, S - 3); buildMap(); };
  window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
}

(async function start() {
  wire(); setTool('select');
  try {
    defaults = await fetch('/api/rules').then(r => r.json());
    await listMaps();
    const first = new URLSearchParams(location.search).get('map') || $('ed-load').value;
    if (first) { $('ed-load').value = first; await loadMapByName(first); }
  } catch (e) { msg('Karten nicht ladbar: ' + e.message, true); }
})();
