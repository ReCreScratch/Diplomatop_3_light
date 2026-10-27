// Session extras of the game screen: pause, surrender, kick (host), rejoin requests and rejoin code, public notices,
// spectator banner and the idle warning. All state comes from the server view (ctx.G); the server decides.
import { api } from './api.js';
import { $, esc, ctx, nName } from './ctx.js';

let hooks = { toast() {}, poll() {} };
let lastInput = Date.now(), seenId = null, menuOpen = false;
const SHOWN_KINDS = ['timeout', 'surrender', 'kick', 'rejoin', 'end'];   // notices that stay in the bar for the whole turn

export function init(h) {
  hooks = h;
  const touch = () => { lastInput = Date.now(); };
  for (const ev of ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart']) document.addEventListener(ev, touch, { passive: true });
  $('btn-pause').onclick = onPause;
  $('btn-menu').onclick = e => { e.stopPropagation(); setMenu(!menuOpen); };
  $('gamemenu').onclick = onMenuClick;
  $('noticebar').onclick = onBarClick;
  document.addEventListener('click', e => { if (menuOpen && !e.target.closest('#gamemenu')) setMenu(false); });
}

const act = async fn => { try { await fn(); } catch (e) { hooks.toast(e.message); } hooks.poll(); };

// ---------- pause ----------
function onPause() {
  const G = ctx.G;
  act(() => api.pause(ctx.gid, ctx.token, !G.pause));
}
function renderPauseButton() {
  const G = ctx.G, b = $('btn-pause');
  const timed = G.timer_remaining != null && !G.winner && G.status === 'running';
  b.hidden = !timed || (!G.is_host && !G.me);
  if (b.hidden) return;
  if (G.pause) {
    b.textContent = '▶ Pause beenden'; b.disabled = !G.is_host;
    b.title = G.is_host ? 'Den Rundentimer weiterlaufen lassen.' : 'Nur der Spielleiter beendet die Pause.';
  } else {
    const own = !G.is_host;
    b.textContent = own ? '⏸ Meine Pause' : '⏸ Pause';
    b.disabled = own && !G.pause_available;
    b.title = !own ? 'Rundentimer anhalten (der Spielleiter darf das jederzeit).'
      : G.pause_available ? 'Rundentimer anhalten – du hast eine Pause pro Spiel, nur der Spielleiter beendet sie.' : 'Deine Pause ist verbraucht.';
  }
}

// ---------- notice bar ----------
export function update() {
  const G = ctx.G, bar = $('noticebar'), lines = [];
  renderPauseButton();
  if (G.pause) {
    const by = esc(G.pause.name || nName(G.pause.by));
    lines.push(`<div class="nb pause">⏸ Pause ${G.pause.host ? 'vom Spielleiter' : 'von ' + by} – der Rundentimer steht.${G.is_host ? ' <button data-act="resume">Pause beenden</button>' : ' Nur der Spielleiter beendet die Pause.'}</div>`);
  }
  if (G.spectator) {
    lines.push(`<div class="nb spec">👁 ${G.status === 'finished' ? 'Das Spiel ist beendet.' : `Du schaust nur zu – ${esc(nName(G.my_nation))} folgt der KI.`}</div>`);
  }
  for (const n of (G.notices || []).filter(n => n.turn === G.turn && SHOWN_KINDS.includes(n.kind))) lines.push(`<div class="nb">${esc(n.text)}</div>`);
  for (const r of G.rejoin_requests || []) {
    lines.push(`<div class="nb ask">${esc(r.name || r.nation)} (${esc(nName(r.nation))}) möchte wieder ins Spiel. ` +
      `<button data-act="accept" data-id="${esc(r.id)}">Zulassen</button> <button data-act="decline" data-id="${esc(r.id)}">Ablehnen</button></div>`);
  }
  bar.innerHTML = lines.join(''); bar.hidden = !lines.length;
  // toasts for news since the last state (not for what was already there when the page opened)
  const top = (G.notices || []).reduce((m, n) => Math.max(m, n.id), 0);
  if (seenId === null) seenId = top;
  else if (top > seenId) {
    for (const n of G.notices.filter(n => n.id > seenId)) hooks.toast(n.text);
    seenId = top;
  }
  if (menuOpen) renderMenu();
}
function onBarClick(e) {
  const b = e.target.closest('[data-act]'); if (!b) return;
  if (b.dataset.act === 'resume') act(() => api.pause(ctx.gid, ctx.token, false));
  else act(() => api.rejoinAnswer(ctx.gid, ctx.token, b.dataset.id, b.dataset.act === 'accept'));
}

// ---------- idle warning (client side only) ----------
export function tick() {
  const G = ctx.G, el = $('idlewarn');
  if (!G) return;
  const limit = G.rules.idle_warning_seconds, rd = G.ready && G.ready[G.me];
  const idle = (Date.now() - lastInput) / 1000;
  const warn = !!G.me && !rd && !G.winner && G.status === 'running' && !G.pause && limit > 0 && idle >= limit;
  el.hidden = !warn;
  if (warn) el.textContent = `Du warst seit ${Math.floor(idle)} Sekunden inaktiv. Bitte drücke „Bereit“, damit die Runde weitergehen kann.`;
  $('btn-ready').classList.toggle('nudge', warn);
}

// ---------- game menu ----------
function setMenu(open) {
  menuOpen = open; $('gamemenu').hidden = !open; $('btn-menu').setAttribute('aria-expanded', String(open));
  if (open) renderMenu();
}
function renderMenu() {
  const G = ctx.G, el = $('gamemenu');
  let h = '';
  if (G.me) {
    h += `<section><h4>Dein Zugang</h4><p>Persönlicher Code: <b class="code">${esc(G.my_rejoin_code || '–')}</b></p>` +
      '<p class="hint">Falls du deinen Link verlierst: Spiel-Link öffnen, Nation wählen und diesen Code eingeben (der Code gilt einmal und wird danach erneuert). Ohne Code bestätigt dich der Spielleiter.</p></section>';
    if (G.status === 'running') h += '<section><button data-act="surrender" class="danger">Aufgeben</button><p class="hint">Du schaust danach nur noch zu; deine Nation folgt der KI.</p></section>';
  }
  if (G.is_host) {
    const rows = Object.keys(G.members || {}).map(n => {
      const state = G.ai[n] ? (G.ai[n].reason === 'surrender' ? 'Zuschauer (aufgegeben)' : 'Zuschauer') : 'aktiv';
      const mine = n === G.my_nation;
      return `<li><span class="sw" style="background:${ctx.G.theme.nation_colors ? (ctx.G.theme.nation_colors[n] || '#888') : '#888'}"></span><b>${esc(G.members[n])}</b> <small>${esc(nName(n))} · ${state}</small>` +
        (mine || G.status !== 'running' ? '' : ` <button data-act="kick" data-n="${esc(n)}" class="danger">Entfernen</button>`) + '</li>';
    }).join('');
    h += `<section><h4>Spieler (Spielleiter)</h4><ul>${rows}</ul></section>`;
  }
  el.innerHTML = h || '<section><p class="hint">Keine Aktionen.</p></section>';
}
function onMenuClick(e) {
  const b = e.target.closest('[data-act]'); if (!b) return;
  if (b.dataset.act === 'surrender') {
    if (!confirm('Wirklich aufgeben? Du schaust danach nur noch zu und deine Nation folgt der KI.')) return;
    setMenu(false); act(() => api.surrender(ctx.gid, ctx.token));
  } else if (b.dataset.act === 'kick') {
    const n = b.dataset.n;
    if (!confirm(`${(ctx.G.members || {})[n] || n} (${nName(n)}) wirklich aus dem Spiel entfernen? Die Nation folgt danach der KI.`)) return;
    act(() => api.kick(ctx.gid, ctx.token, { nation: n }));
  }
}
