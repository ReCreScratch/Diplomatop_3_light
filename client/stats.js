// End-of-game statistics (RULES.md 12): overview, curves, heatmaps, fights and the video export.
// Numbers come from GET /stats (engine/stats.py); the map and the video frames are drawn by render.js (boardSvg).
import * as R from './render.js';
import { api } from './api.js';
import { $, esc, ctx, fieldName } from './ctx.js';

const NS = 'http://www.w3.org/2000/svg';
const TABS = [['overview', 'Übersicht'], ['curves', 'Verläufe'], ['map', 'Karte'], ['fights', 'Kämpfe'], ['video', 'Video']];
const LABEL = {   // totals (German)
  gold_earned: 'Einkommen gesamt', gold_upkeep: 'Unterhalt gezahlt', gold_spent_recruits: 'Gold für Rekruten', gold_spent_ships: 'Gold für Schiffe',
  gold_spent_purchases: 'Gold für Provinzkäufe', gold_sales_income: 'Gold aus Verkäufen', gold_refunds: 'Gold aus Abrüstung', gold_sent: 'Gold gesendet',
  gold_received: 'Gold erhalten', gold_traded: 'Gold gehandelt (gesendet + verkauft)', recruited: 'Divisionen rekrutiert', disbanded: 'Divisionen abgerüstet',
  ships_built: 'Schiffe gebaut', ships_disbanded: 'Schiffe abgerüstet', units_recruited: 'Einheiten rekrutiert', divisions_lost_fights: 'Divisionen in Kämpfen verloren',
  divisions_lost_conquest: 'Divisionen bei Eroberungen verloren', ships_lost: 'Schiffe verloren', units_lost: 'Einheiten verloren',
  kills_divisions: 'Feindliche Divisionen vernichtet', kills_ships: 'Feindliche Schiffe versenkt', kills: 'Feindliche Einheiten vernichtet',
  fights: 'Kämpfe', fights_attacker: 'Kämpfe als Angreifer', fights_defender: 'Kämpfe als Verteidiger', fights_won: 'Kämpfe gewonnen', fights_lost: 'Kämpfe verloren',
  fights_both: 'Kämpfe unentschieden (beide überleben)', fights_attacker_won: 'Angriffe gewonnen', fights_attacker_lost: 'Angriffe verloren', fights_attacker_both: 'Angriffe unentschieden',
  fights_defender_won: 'Verteidigungen gewonnen', fights_defender_lost: 'Verteidigungen verloren', fights_defender_both: 'Verteidigungen unentschieden',
  conquests: 'Eroberungen', conquests_failed: 'Gescheiterte Eroberungen', provinces_lost: 'Provinzen verloren', gifts_given_provinces: 'Provinzen verschenkt',
  gifts_received_provinces: 'Provinzen geschenkt bekommen', sales: 'Provinzen verkauft', purchases: 'Provinzen gekauft', moves: 'Züge', fields_marched: 'Marschierte Divisionen-Felder',
  ship_fields_marched: 'Gesegelte Schiff-Felder', forced_march_toggles: 'Gewaltmärsche angeordnet', forced_march_moves: 'Züge im Gewaltmarsch',
  standing_march_steps: 'Schritte von Dauermärschen', blocked_moves: 'Blockierte Züge', no_attack_pacts: 'Nichtangriffs-Zusagen', timeouts: 'Zeitüberschreitungen',
  chat_public: 'Chat öffentlich', chat_private: 'Chat privat', chat_total: 'Chatnachrichten', alliances_joined: 'Bündnisse beigetreten', alliances_left: 'Bündnisse verlassen',
  avg_ready_seconds: 'Ø Sekunden bis Bereit', peak_share: 'Höchster Landanteil', peak_share_turn: 'Runde des Höchstanteils', knocked_out_turn: 'Ausgeschieden in Runde',
  status: 'Status', ai_since_turn: 'KI seit Runde', orders_given: 'Befehle gegeben', orders_skipped: 'Befehle übersprungen',
};
const SERIES_LABEL = { gold: 'Gold', income: 'Einkommen', upkeep: 'Unterhalt', gold_sent: 'Gold gesendet', gold_received: 'Gold erhalten', provinces: 'Provinzen', fields: 'Landfelder',
  share: 'Landanteil (%)', cities: 'Städte', ports: 'Häfen', armies: 'Armeen', divisions: 'Divisionen', ships: 'Schiffe', divisions_at_sea: 'Divisionen auf See' };
const HEAT_LABEL = { divisions_died: 'Gefallene Divisionen', ships_died: 'Versenkte Schiffe', fights: 'Kämpfe', conquests: 'Eroberungen', recruits: 'Rekrutierungen', traffic: 'Durchmarsch (Divisionen)' };
const STATUS = { player: 'Spieler', unpicked: 'KI (nicht gewählt)', surrender: 'Aufgegeben', kick: 'Entfernt' };
// ranking table: [key, header, tooltip]
const COLS = [['share_end', 'Endanteil %', 'Landanteil am Ende'], ['peak_share', 'Spitze %', 'Höchster Landanteil'], ['gold_earned', 'Einkommen', LABEL.gold_earned],
  ['units_recruited', 'Rekrutiert', LABEL.units_recruited], ['units_lost', 'Verluste', LABEL.units_lost], ['kills', 'Vernichtet', LABEL.kills], ['fights', 'Kämpfe', LABEL.fights],
  ['fights_won', 'Siege', LABEL.fights_won], ['conquests', 'Eroberungen', LABEL.conquests], ['fields_marched', 'Marschiert', LABEL.fields_marched],
  ['chat_total', 'Chat', LABEL.chat_total], ['avg_ready_seconds', 'Ø Bereit (s)', LABEL.avg_ready_seconds]];

const S = { data: null, tab: 'overview', sort: 'share_end', desc: true, metric: 'share', hidden: new Set(), heat: 'divisions_died', video: null, error: null };
let el = null;

const fmt = v => v == null ? '–' : typeof v === 'number' ? v.toLocaleString('de-DE', { maximumFractionDigits: 2 }) : String(v);
const pct = v => v == null ? '–' : (v * 100).toLocaleString('de-DE', { maximumFractionDigits: 1 });
const dur = s => s == null ? '–' : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 3600) ? Math.floor(s / 3600) + ' h ' : ''}${Math.floor(s % 3600 / 60)} min ${Math.round(s % 60)} s`;
const nameOf = c => (S.data.nations[c] || {}).name || c;
const who = c => `<span class="sw" style="background:${R.colorOf(c)}"></span>${esc(nameOf(c))}`;
const whoP = c => { const p = (S.data.nations[c] || {}).player; return who(c) + (p ? ` <small>${esc(p)}</small>` : ''); };
const metricLabel = k => LABEL[k] || SERIES_LABEL[k] || k;
const lastOf = a => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
const cell = (c, key) => key === 'share_end' ? (lastOf(S.data.series.share[c] || []) ?? 0) * 100 : key === 'peak_share' ? (S.data.totals[c].peak_share || 0) * 100 : S.data.totals[c][key];

// ---------- download ----------
function download(name, text, type = 'application/json') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

// ---------- overlay ----------
function build() {
  el = document.createElement('div');
  el.id = 'stats'; el.hidden = true;
  el.innerHTML = `<div class="st-box" role="dialog" aria-label="Statistik">
    <header><h2>Statistik</h2><span id="st-sub"></span>
      <button id="st-dl-stats" title="Berechnete Statistik als JSON">Statistik herunterladen (JSON)</button>
      <button id="st-dl-raw" title="Rundenarchiv mit allen Rohdaten als JSON">Rohdaten herunterladen (JSON)</button>
      <button id="st-close" title="Schließen (Esc)">✕ Schließen</button></header>
    <nav id="st-tabs">${TABS.map(([k, l]) => `<button data-tab="${k}">${l}</button>`).join('')}</nav>
    <div id="st-body"></div></div>`;
  document.body.appendChild(el);
  el.onclick = onClick;
  el.onchange = onChange;
  el.onmousemove = onMove;
  el.onmouseleave = () => hideChartTip();
  $('st-close').onclick = close;
  $('st-dl-stats').onclick = () => S.data && download(`diplomatio-${ctx.gid}-statistik.json`, JSON.stringify(S.data, null, 1));
  $('st-dl-raw').onclick = async () => {
    try { download(`diplomatio-${ctx.gid}-rohdaten.json`, JSON.stringify(await api.history(ctx.gid, ctx.token))); } catch (e) { alert(e.message); }
  };
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !el.hidden) close(); });
}

export async function open() {
  if (!el) build();
  el.hidden = false; document.body.classList.add('stats-open');
  if (!S.data) {
    $('st-body').innerHTML = '<p class="msg">Statistik wird berechnet …</p>';
    try { S.data = await api.stats(ctx.gid, ctx.token); S.error = null; } catch (e) { S.error = e.message; }
  }
  render();
}
export function close() {
  if (!el) return;
  if (S.video) S.video.cancel = true;
  el.hidden = true; document.body.classList.remove('stats-open');
}

function render() {
  const body = $('st-body');
  if (S.error) { body.innerHTML = `<p class="msg err">${esc(S.error)}</p>`; return; }
  const d = S.data;
  $('st-sub').textContent = `${d.map || ''} · ${d.game.turns} ${d.game.turns === 1 ? 'Runde' : 'Runden'}`;
  $('st-tabs').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.tab === S.tab));
  if (d.empty && S.tab !== 'video') {
    body.innerHTML = '<p class="msg">Für dieses Spiel gibt es kein Rundenarchiv (es wurde vor der Statistik gestartet oder endete in Runde 1). Es sind keine Auswertungen möglich.</p>';
    return;
  }
  body.innerHTML = { overview, curves, map, fights, video }[S.tab]();
  if (S.tab === 'curves') drawChart();
  if (S.tab === 'video') bindVideo();
}

function onClick(e) {
  const tab = e.target.closest('[data-tab]');
  if (tab) { S.tab = tab.dataset.tab; render(); return; }
  const th = e.target.closest('[data-sort]');
  if (th) { S.desc = S.sort === th.dataset.sort ? !S.desc : true; S.sort = th.dataset.sort; render(); return; }
  const lg = e.target.closest('[data-nation]');
  if (lg) { S.hidden.has(lg.dataset.nation) ? S.hidden.delete(lg.dataset.nation) : S.hidden.add(lg.dataset.nation); render(); }
}
function onChange(e) {
  if (e.target.id === 'st-metric') { S.metric = e.target.value; render(); }
  else if (e.target.id === 'st-heat') { S.heat = e.target.value; render(); }
}

// ---------- tab: overview ----------
function overview() {
  const d = S.data, g = d.game, t = d.totals;
  const cards = d.titles.map(x => `<div class="card"><h4>${esc(x.title)}</h4><div class="who">${whoP(x.nation)}</div>
    <div class="val">${fmt(x.metric === 'peak_share' ? x.value * 100 : x.value)}</div><small>${esc(metricLabel(x.metric))}${x.tied ? ` · gleichauf mit ${x.tied.map(nameOf).map(esc).join(', ')}` : ''}</small></div>`).join('');
  const facts = [
    ['Runden', g.turns], ['Dauer', dur(g.duration_seconds)],
    ['Sieger', g.winner ? g.winner.players.map(nameOf).map(esc).join(' + ') + (g.winner.alliance ? ' (Bündnis)' : '') : 'kein Sieger'],
    ['Größter Kampf', g.biggest_fight ? `Runde ${g.biggest_fight.turn} bei ${esc(fieldName(g.biggest_fight.field))}: ${esc(nameOf(g.biggest_fight.attacker))} gegen ${esc(nameOf(g.biggest_fight.defender))}, ${g.biggest_fight.units} Einheiten` : '–'],
    ['Umkämpfteste Provinz', g.most_contested_province ? `${esc(g.most_contested_province.name || g.most_contested_province.province)} (${g.most_contested_province.changes}× den Besitzer gewechselt)` : '–'],
    ['Blutigstes Feld', g.bloodiest_field ? `${esc(fieldName(g.bloodiest_field.field))}: ${g.bloodiest_field.units} gefallene Einheiten` : '–'],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('');
  const sorted = [...d.order].sort((a, b) => {
    const x = cell(a, S.sort), y = cell(b, S.sort);
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
    return (S.desc ? y - x : x - y) || d.order.indexOf(a) - d.order.indexOf(b);
  });
  const head = COLS.map(([k, h, tip]) => `<th data-sort="${k}" title="${esc(tip)} (Klick: sortieren)" class="${S.sort === k ? 'on' : ''}">${esc(h)}${S.sort === k ? (S.desc ? ' ▼' : ' ▲') : ''}</th>`).join('');
  const rows = sorted.map(c => {
    const tt = t[c], tag = tt.status !== 'player' ? ` <small>${STATUS[tt.status] || tt.status}${tt.ai_since_turn ? ' ab R' + tt.ai_since_turn : ''}</small>` : '';
    const out = tt.knocked_out_turn ? ` <small>ausgeschieden R${tt.knocked_out_turn}</small>` : '';
    return `<tr><td>${whoP(c)}${tag}${out}</td>${COLS.map(([k]) => `<td class="${S.sort === k ? 'on' : ''}">${fmt(cell(c, k))}</td>`).join('')}</tr>`;
  }).join('');
  const allKeys = Object.keys(t[d.order[0]] || {});
  const all = allKeys.map(k => `<tr><th>${esc(metricLabel(k))}</th>${d.order.map(c => `<td>${allCell(t[c][k], k)}</td>`).join('')}</tr>`).join('');
  return `${cards ? `<div class="cards">${cards}</div>` : '<p class="msg">Keine Titel vergeben – es ist zu wenig passiert.</p>'}
    <h3>Spielfakten</h3><dl class="facts">${facts}</dl>
    <h3>Rangliste</h3><div class="scroll"><table class="st-table"><tr><th>Nation</th>${head}</tr>${rows}</table></div>
    <details><summary>Alle Zahlen</summary><div class="scroll"><table class="st-table all"><tr><th></th>${d.order.map(c => `<th>${who(c)}</th>`).join('')}</tr>${all}</table></div></details>`;
}
function allCell(v, key) {
  if (v && typeof v === 'object') return Object.keys(v).length ? Object.entries(v).map(([k, n]) => `${esc(k)} ${n}`).join(' · ') : '–';
  if (key === 'status') return STATUS[v] || esc(v);
  return key === 'peak_share' ? pct(v) + ' %' : fmt(v);
}

// ---------- tab: curves ----------
function curves() {
  const d = S.data;
  const opts = Object.keys(d.series).map(k => `<option value="${k}" ${k === S.metric ? 'selected' : ''}>${esc(SERIES_LABEL[k] || k)}</option>`).join('');
  const legend = d.order.map(c => `<button data-nation="${c}" class="lg ${S.hidden.has(c) ? 'off' : ''}" title="Linie ein- oder ausblenden">${who(c)}</button>`).join('');
  return `<div class="bar"><label>Kennzahl <select id="st-metric">${opts}</select></label><span class="legend">${legend}</span></div>
    <div id="st-chartbox"><svg id="st-chart" class="st-chart" xmlns="${NS}" viewBox="0 0 900 440" preserveAspectRatio="xMidYMid meet"></svg><div id="st-tip" hidden></div></div>`;
}
const CH = { w: 900, h: 440, l: 58, r: 18, t: 16, b: 40 };
let chart = null;   // data of the drawn chart, for the hover
function niceTicks(lo, hi) {
  const span = hi - lo || 1, raw = span / 5, mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * mag, out = [];
  for (let v = Math.floor(lo / step) * step; v < hi + step * 0.999; v += step) out.push(+v.toFixed(10));
  return out;
}
function drawChart() {
  const d = S.data, svg = $('st-chart'), axis = d.axis, isShare = S.metric === 'share', mul = isShare ? 100 : 1;
  const vis = d.order.filter(c => !S.hidden.has(c)), series = {};
  for (const c of d.order) series[c] = (d.series[S.metric][c] || []).map(v => v == null ? null : v * mul);
  const vals = vis.flatMap(c => series[c]).filter(v => v != null);
  const lo = Math.min(0, ...vals), hi = Math.max(1e-9, ...vals), ticks = niceTicks(lo, hi), top = ticks[ticks.length - 1], bottom = ticks[0];
  const px = i => CH.l + (CH.w - CH.l - CH.r) * (axis.length < 2 ? 0.5 : i / (axis.length - 1));
  const py = v => CH.t + (CH.h - CH.t - CH.b) * (1 - (v - bottom) / ((top - bottom) || 1));
  let s = '';
  for (const v of ticks) s += `<line class="gr" x1="${CH.l}" x2="${CH.w - CH.r}" y1="${py(v)}" y2="${py(v)}"/><text class="ax" x="${CH.l - 8}" y="${py(v)}" text-anchor="end" dominant-baseline="central">${esc(fmt(v))}</text>`;
  const every = Math.max(1, Math.ceil(axis.length / Math.floor((CH.w - CH.l - CH.r) / 44)));
  axis.forEach((t, i) => { if (i % every === 0 || i === axis.length - 1) s += `<text class="ax" x="${px(i)}" y="${CH.h - CH.b + 18}" text-anchor="middle">${t}</text>`; });
  s += `<text class="ax" x="${(CH.l + CH.w - CH.r) / 2}" y="${CH.h - 4}" text-anchor="middle">Runde</text>`;
  s += `<line class="axis" x1="${CH.l}" x2="${CH.l}" y1="${CH.t}" y2="${CH.h - CH.b}"/><line class="axis" x1="${CH.l}" x2="${CH.w - CH.r}" y1="${CH.h - CH.b}" y2="${CH.h - CH.b}"/>`;
  for (const c of vis) {
    let path = '';
    series[c].forEach((v, i) => { path += v == null ? '' : `${path && series[c][i - 1] != null ? 'L' : 'M'}${px(i).toFixed(1)} ${py(v).toFixed(1)}`; });
    s += `<path class="ln" d="${path}" stroke="${R.colorOf(c)}"/>`;
    if (axis.length <= 40) series[c].forEach((v, i) => { if (v != null) s += `<circle class="pt" cx="${px(i).toFixed(1)}" cy="${py(v).toFixed(1)}" r="2.6" fill="${R.colorOf(c)}"/>`; });
  }
  s += `<line id="st-guide" class="guide" y1="${CH.t}" y2="${CH.h - CH.b}" hidden/>`;
  svg.innerHTML = s;
  chart = { axis, series, vis, px, mul };
}
function hideChartTip() {
  const tip = $('st-tip'), g = $('st-guide');
  if (tip) tip.hidden = true;
  if (g) g.setAttribute('hidden', '');
}
function onMove(e) {
  const svg = e.target.closest && e.target.closest('#st-chart');
  if (!svg || !chart || !chart.axis.length) { if (!e.target.closest || !e.target.closest('#st-tip')) hideChartTip(); return; }
  const box = svg.getBoundingClientRect(), x = (e.clientX - box.left) / box.width * CH.w;
  let best = 0, bd = Infinity;
  chart.axis.forEach((_, i) => { const dist = Math.abs(chart.px(i) - x); if (dist < bd) { bd = dist; best = i; } });
  const g = $('st-guide'), tip = $('st-tip');
  g.removeAttribute('hidden'); g.setAttribute('x1', chart.px(best)); g.setAttribute('x2', chart.px(best));
  const rows = chart.vis.map(c => [c, chart.series[c][best]]).filter(([, v]) => v != null).sort((a, b) => b[1] - a[1]);
  tip.innerHTML = `<b>Runde ${chart.axis[best]}</b>` + rows.map(([c, v]) => `<div>${who(c)} <span>${fmt(v)}${S.metric === 'share' ? ' %' : ''}</span></div>`).join('');
  tip.hidden = false;
  const bx = $('st-chartbox').getBoundingClientRect(), left = e.clientX - bx.left + 14;
  tip.style.left = Math.min(left, bx.width - tip.offsetWidth - 4) + 'px'; tip.style.top = Math.max(4, e.clientY - bx.top - tip.offsetHeight / 2) + 'px';
}

// ---------- tab: map (heatmap) ----------
function map() {
  const d = S.data, G = ctx.G, heat = d.heat[S.heat] || {}, vals = Object.values(heat), max = Math.max(0, ...vals);
  const opts = Object.keys(HEAT_LABEL).map(k => `<option value="${k}" ${k === S.heat ? 'selected' : ''}>${esc(HEAT_LABEL[k])}</option>`).join('');
  const svg = R.boardSvg(G.map, G.theme, G.rules, { owners: G.owners, armies: G.armies }, {
    width: 1000, armies: false, heat, heatMax: max || 1, titleOf: (key, v) => `${fieldName(key.split(',').map(Number))}: ${fmt(v)}` });
  const lo = R.heatStyle(G.theme, 0), hi = R.heatStyle(G.theme, 1);
  const top = Object.entries(heat).sort((a, b) => b[1] - a[1]).slice(0, 5)
    .map(([k, v]) => `<li>${esc(fieldName(k.split(',').map(Number)))} <b>${fmt(v)}</b></li>`).join('');
  return `<div class="bar"><label>Kennzahl <select id="st-heat">${opts}</select></label>
    <span class="hl"><small>0</small><svg width="160" height="14" xmlns="${NS}"><defs><linearGradient id="st-hg"><stop offset="0" stop-color="${esc(lo.fill)}" stop-opacity="${lo.opacity}"/><stop offset="1" stop-color="${esc(hi.fill)}" stop-opacity="${hi.opacity}"/></linearGradient></defs>
      <rect width="160" height="14" class="hbg"/><rect width="160" height="14" fill="url(#st-hg)"/></svg><small>Höchstwert: <b>${fmt(max)}</b></small></span></div>
    <div class="st-map">${svg}</div>
    ${max ? `<h3>Spitzenreiter</h3><ol class="top">${top}</ol>` : '<p class="msg">Dafür gibt es in diesem Spiel keine Werte.</p>'}`;
}

// ---------- tab: fights (kill matrix, chat matrix) ----------
function fights() {
  const d = S.data, kills = d.kills, ch = d.chat_matrix;
  const kn = d.order.filter(c => kills[c] || d.order.some(a => (kills[a] || {})[c]));
  const amount = k => k ? (k.divisions || k.ships ? [k.divisions ? `${k.divisions} Div.` : '', k.ships ? `${k.ships} Sch.` : ''].filter(Boolean).join(' + ') : '') : '';
  const sum = list => { const o = { divisions: 0, ships: 0 }; list.forEach(k => { if (k) { o.divisions += k.divisions; o.ships += k.ships; } }); return amount(o) || '0'; };
  const killTable = !kn.length ? '<p class="msg">Es wurde nichts vernichtet.</p>'
    : `<div class="scroll"><table class="st-table mx"><tr><th title="Zeile: wer vernichtet hat · Spalte: wessen Einheiten">Angreifer ↓ / Opfer →</th>${kn.map(c => `<th>${who(c)}</th>`).join('')}<th>Summe</th></tr>
      ${kn.map(a => `<tr><th>${who(a)}</th>${kn.map(v => `<td>${a === v ? '' : esc(amount((kills[a] || {})[v]))}</td>`).join('')}<td><b>${esc(sum(kn.map(v => (kills[a] || {})[v])))}</b></td></tr>`).join('')}
      <tr><th>Verloren</th>${kn.map(v => `<td><b>${esc(sum(kn.map(a => (kills[a] || {})[v])))}</b></td>`).join('')}<td></td></tr></table></div>`;
  const from = d.order.filter(c => ch[c]), to = [...d.order.filter(c => from.some(f => (ch[f] || {})[c])), 'all'];
  const chatTable = !from.length ? '<p class="msg">Es wurde nichts geschrieben.</p>'
    : `<div class="scroll"><table class="st-table mx"><tr><th title="Zeile: Absender · Spalte: Empfänger (nur Anzahl, nie der Text)">Von ↓ / An →</th>${to.map(c => `<th>${c === 'all' ? 'Alle (öffentlich)' : who(c)}</th>`).join('')}<th>Summe</th></tr>
      ${from.map(f => `<tr><th>${who(f)}</th>${to.map(c => `<td>${(ch[f] || {})[c] || ''}</td>`).join('')}<td><b>${Object.values(ch[f]).reduce((a, b) => a + b, 0)}</b></td></tr>`).join('')}</table></div>`;
  return `<h3>Wer hat wessen Einheiten vernichtet?</h3>${killTable}<h3>Wer hat mit wem geschrieben?</h3>${chatTable}`;
}

// ---------- tab: video ----------
const VW = 1280, VH = 720;
function videoSeconds() { return (S.data && S.data.video_seconds_per_turn) ?? (ctx.G.rules || {}).video_seconds_per_turn ?? 1; }
function pickMime() {
  const list = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
  if (typeof MediaRecorder === 'undefined' || !HTMLCanvasElement.prototype.captureStream) return null;
  return list.find(t => MediaRecorder.isTypeSupported(t)) || '';
}
function video() {
  const d = S.data, mime = pickMime(), n = d.game.turns + 1, secs = videoSeconds();
  const note = mime === null ? 'Dieser Browser kann kein Video aufnehmen (MediaRecorder fehlt).'
    : mime.startsWith('video/mp4') ? 'Das Video wird als MP4 aufgenommen.' : 'Dieser Browser kann kein MP4 aufnehmen – das Video wird als WebM erstellt.';
  return `<p>Jede Runde (${n} Bilder inklusive Endstand) wird ${fmt(secs)} ${secs === 1 ? 'Sekunde' : 'Sekunden'} gezeigt, also etwa ${dur(Math.round(n * secs))}.
    Das Video wird in Echtzeit aufgenommen; bitte lass diesen Tab so lange offen und sichtbar.</p><p class="msg">${note}</p>
    <div class="bar"><button id="st-vstart" class="primary" ${mime === null ? 'disabled' : ''}>Video erstellen</button><button id="st-vcancel" hidden>Abbrechen</button></div>
    <div id="st-vprog" hidden><progress id="st-vbar" value="0" max="1"></progress> <span id="st-vtext"></span></div>
    <p id="st-vmsg" class="msg"></p><div id="st-vout"></div>`;
}
function bindVideo() {
  const start = $('st-vstart');
  if (start) start.onclick = makeVideo;
  $('st-vcancel').onclick = () => { if (S.video) S.video.cancel = true; };
  if (S.video && S.video.result) showVideoResult(S.video.result);
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
// SVG text -> canvas (through an <img>; the SVG carries all its styles inline)
async function rasterise(svg) {
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    const img = new Image();
    await new Promise((ok, fail) => { img.onload = ok; img.onerror = () => fail(new Error('Ein Bild des Videos konnte nicht erzeugt werden.')); img.src = url; });
    const c = document.createElement('canvas'); c.width = VW; c.height = VH;
    c.getContext('2d').drawImage(img, 0, 0, VW, VH);
    return c;
  } finally { URL.revokeObjectURL(url); }
}
function provinceSizes(map) {
  const sizes = {};
  for (const row of map.grid) for (const tok of row.trim().split(/\s+/)) if (map.provinces[tok]) sizes[tok] = (sizes[tok] || 0) + 1;
  return sizes;
}
async function makeVideo() {
  const G = ctx.G, d = S.data, mime = pickMime(), ms = videoSeconds() * 1000;
  const V = S.video = { cancel: false, result: null };
  const ui = { start: $('st-vstart'), cancel: $('st-vcancel'), prog: $('st-vprog'), bar: $('st-vbar'), text: $('st-vtext'), msg: $('st-vmsg'), out: $('st-vout') };
  const say = (t, err) => { if (ui.msg.isConnected) { ui.msg.textContent = t || ''; ui.msg.className = 'msg' + (err ? ' err' : ''); } };
  ui.start.disabled = true; ui.cancel.hidden = false; ui.prog.hidden = false; ui.out.innerHTML = ''; say('Rohdaten werden geladen …');
  let rec = null;
  try {
    const rows = await api.history(ctx.gid, ctx.token);
    const frames = rows.filter(r => !r.final && r.before).map(r => ({ turn: r.turn, board: r.before }));
    const fin = rows.filter(r => r.final && r.board).pop();
    if (fin) frames.push({ turn: fin.turn, board: fin.board, final: true, winner: fin.winner });
    if (!frames.length) throw new Error('Für dieses Spiel gibt es kein Rundenarchiv – ein Video ist nicht möglich.');
    const sizes = provinceSizes(G.map), total = Object.values(sizes).reduce((a, b) => a + b, 0) || 1;
    const frameSvg = f => {
      const share = {};
      for (const [code, owner] of Object.entries(f.board.owners || {})) if (owner && sizes[code]) share[owner] = (share[owner] || 0) + sizes[code] / total;
      const bar = Object.entries(share).sort((a, b) => b[1] - a[1]).map(([c, v]) => ({ color: R.colorOf(c), share: v, label: `${c} ${Math.round(v * 100)} %` }));
      const win = f.winner && f.winner.players ? 'Sieger: ' + f.winner.players.map(nameOf).join(' + ') : '';
      return R.boardSvg(G.map, G.theme, G.rules, f.board, { width: VW, height: VH, label: f.final ? { title: 'Spielende', sub: win } : { title: 'Runde ' + f.turn }, bar });
    };
    const canvas = document.createElement('canvas'); canvas.width = VW; canvas.height = VH;
    const g = canvas.getContext('2d'), chunks = [];
    rec = new MediaRecorder(canvas.captureStream(30), { ...(mime ? { mimeType: mime } : {}), videoBitsPerSecond: 4000000 });
    rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    const stopped = new Promise(res => { rec.onstop = res; });
    let next = rasterise(frameSvg(frames[0]));
    next.catch(() => {});
    g.drawImage(await next, 0, 0);
    rec.start(1000);
    say('Aufnahme läuft – bitte diesen Tab offen lassen.');
    for (let i = 0; i < frames.length && !V.cancel; i++) {
      const cur = await next;
      g.drawImage(cur, 0, 0);
      const shownAt = performance.now();
      ui.bar.max = frames.length; ui.bar.value = i + 1;
      ui.text.textContent = `${frames[i].final ? 'Endstand' : 'Runde ' + frames[i].turn} · Bild ${i + 1} / ${frames.length}`;
      if (i + 1 < frames.length) { next = rasterise(frameSvg(frames[i + 1])); next.catch(() => {}); }
      while (!V.cancel && performance.now() - shownAt < ms) { await sleep(Math.min(100, ms)); g.drawImage(cur, 0, 0); }   // redraw keeps the stream producing frames
    }
    if (rec.state !== 'inactive') rec.stop();
    await stopped;
    if (V.cancel) { say('Abgebrochen.'); return; }
    const type = (rec.mimeType || mime || 'video/webm').split(';')[0];
    V.result = { blob: new Blob(chunks, { type }), ext: type.includes('mp4') ? 'mp4' : 'webm' };
    say('Fertig.');
    showVideoResult(V.result);
  } catch (e) {
    say(e.message || String(e), true);
    try { if (rec && rec.state !== 'inactive') rec.stop(); } catch (x) { /* already stopped */ }
  } finally {
    if (ui.start.isConnected) { ui.start.disabled = false; ui.cancel.hidden = true; ui.prog.hidden = true; }
  }
}
function showVideoResult(r) {
  const out = $('st-vout');
  if (!out) return;
  const url = r.url || (r.url = URL.createObjectURL(r.blob));
  out.innerHTML = `<p><a class="dl" href="${url}" download="diplomatio-${esc(ctx.gid)}.${r.ext}">Video herunterladen (${r.ext.toUpperCase()}, ${(r.blob.size / 1048576).toFixed(1)} MB)</a></p><video controls src="${url}"></video>`;
}
