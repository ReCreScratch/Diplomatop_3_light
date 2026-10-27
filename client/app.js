// Screens: start (create game), join, lobby, game. Token lives in the URL (?game=..&token=..) and localStorage.
import { api } from './api.js';
import { startGame } from './game.js';
import { thumbnail } from './minimap.js';

const $ = id => document.getElementById(id);
const q = new URLSearchParams(location.search);
const gid = q.get('game');
const ls = {
  get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};
const token = q.get('token') || (gid && ls.get('dip_token_' + gid));
const show = id => { for (const s of document.querySelectorAll('.screen, #screen-game')) s.hidden = s.id !== id; };
const msg = (id, text, err) => { const e = $(id); e.textContent = text || ''; e.className = 'msg' + (err ? ' err' : ''); };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const link = () => location.origin + location.pathname + '?game=' + encodeURIComponent(gid);

async function route() {
  if (!gid) return startScreen();
  let lobby;
  try { lobby = await api.lobby(gid, token); } catch (e) { show('screen-start'); msg('st-msg', 'Spiel nicht gefunden: ' + e.message, true); return startScreen(true); }
  if (token) {
    if (!q.get('token')) history.replaceState(null, '', `?game=${encodeURIComponent(gid)}&token=${encodeURIComponent(token)}`);
    return lobby.status === 'running' ? gameScreen() : lobbyScreen(lobby);
  }
  if (lobby.status === 'running') { show('screen-start'); msg('st-msg', 'Das Spiel läuft bereits.', true); return startScreen(true); }
  joinScreen(lobby);
}

// Map + theme are static files (/maps/{name}/...); cached per map.
const mapCache = {};
const loadMap = name => mapCache[name] ||= Promise.all([
  fetch(`/maps/${encodeURIComponent(name)}/map.json`).then(r => r.json()),
  fetch(`/maps/${encodeURIComponent(name)}/theme.json`).then(r => r.json()),
]).then(([map, theme]) => ({ map, theme }));
const colorOf = (theme, c) => (theme.nation_colors || {})[c] || theme.neutral_color || '#888';
const provsOf = (map, c) => Object.values(map.provinces).filter(p => p.owner === c);

async function startScreen(keepMsg) {
  show('screen-start');
  if (!keepMsg) msg('st-msg', '');
  let sel = null;
  try {
    const names = await api.maps();
    const box = $('st-maps'); box.innerHTML = '';
    for (const name of names) {
      const b = document.createElement('button');
      b.className = 'tile'; b.type = 'button'; b.innerHTML = `<b>${esc(name)}</b><small>…</small>`;
      b.onclick = () => { sel = name; for (const t of box.children) t.classList.toggle('sel', t === b); };
      box.appendChild(b);
      if (!sel) b.click();
      loadMap(name).then(({ map, theme }) => {
        b.innerHTML = '';
        b.appendChild(thumbnail(map, theme));
        b.insertAdjacentHTML('beforeend', `<b>${esc(map.name || name)}</b><small>${Object.keys(map.nations).length} Nationen · ${Object.keys(map.provinces).length} Provinzen</small>`);
      }).catch(() => { b.querySelector('small').textContent = 'Vorschau nicht ladbar'; });
    }
  } catch (e) { msg('st-msg', 'Karten nicht ladbar: ' + e.message, true); }
  $('st-create').onclick = async () => {
    if (!sel) return;
    try {
      const r = await api.createGame(sel);
      ls.set('dip_host_' + r.game_id, r.host_token);
      location.href = '?game=' + encodeURIComponent(r.game_id);
    } catch (e) { msg('st-msg', e.message, true); }
  };
}

async function joinScreen(lobby) {
  show('screen-join');
  const taken = lobby.joined || {};
  const { map, theme } = await loadMap(lobby.map);
  const mini = thumbnail(map, theme);
  $('jn-mini').replaceChildren(mini);
  $('jn-name').value = ls.get('dip_name') || '';
  let sel = null, hov = null;
  const cards = {}, grid = $('jn-nations');
  grid.innerHTML = '';
  const light = () => mini.update({ highlight: hov || sel });
  for (const [c, n] of Object.entries(lobby.nations)) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'ncard'; b.style.setProperty('--c', colorOf(theme, c));
    const ps = provsOf(map, c), caps = ps.map(p => p.capital_name).filter(Boolean).slice(0, 3).join(', ');
    b.innerHTML = `<b>${esc(n)}</b><small>${ps.length} Provinzen</small><small>${esc(taken[c] ? 'Spieler: ' + taken[c] : caps)}</small>`;
    if (taken[c]) b.disabled = true;
    else {
      b.onclick = () => { sel = c; for (const k in cards) cards[k].classList.toggle('sel', k === c); light(); };
      b.onmouseenter = () => { hov = c; light(); };
      b.onmouseleave = () => { hov = null; light(); };
    }
    cards[c] = b; grid.appendChild(b);
  }
  if (Object.keys(lobby.nations).every(c => taken[c])) msg('jn-msg', 'Keine Nation mehr frei.', true); else msg('jn-msg', '');
  $('jn-go').onclick = async () => {
    const name = $('jn-name').value.trim(), nation = sel;
    if (!name) { msg('jn-msg', 'Bitte einen Namen eingeben.', true); $('jn-name').focus(); return; }
    if (!nation) { msg('jn-msg', 'Bitte eine Nation wählen.', true); return; }
    const host = ls.get('dip_host_' + gid);
    try {
      const r = await api.join(gid, host ? { name, nation, host_token: host } : { name, nation });
      ls.set('dip_name', name); ls.set('dip_token_' + gid, r.token);
      if (host) ls.set('dip_ishost_' + gid, '1');
      location.href = `?game=${encodeURIComponent(gid)}&token=${encodeURIComponent(r.token)}`;
    } catch (e) { msg('jn-msg', e.message, true); }
  };
}

// Rule summary, built only from the merged rules the server sends.
function ruleLines(r) {
  const t = r.turn_timer_seconds;
  return [
    ['Startgold', r.start_gold], ['Kosten pro Division', r.division_cost],
    ['Unterhalt', `${r.upkeep_per_division} je Division${r.upkeep_per_army ? ` + ${r.upkeep_per_army} je Armee` : ''}`],
    ['Bewegung', `${r.move_range} Feld(er)`], ['Gewaltmarsch', `bis ${r.forced_march_range} Felder`],
    ['Rekrutierung', `in eigenen Städten, max. ${r.recruit_limit_per_province} je Provinz`],
    ['Zugtimer', t ? `${t} s` : 'kein Timer'],
  ].map(([k, v]) => `<li><span>${k}:</span> ${esc(v)}</li>`).join('');
}

function lobbyScreen(first) {
  show('screen-lobby');
  $('lb-link').value = link();
  $('lb-copy').onclick = async () => {
    const inp = $('lb-link');
    try { await navigator.clipboard.writeText(inp.value); }
    catch (e) { inp.select(); try { document.execCommand('copy'); } catch (e2) { /* ignore */ } }
    const b = $('lb-copy'); b.textContent = 'Kopiert ✓'; b.classList.add('ok');
    setTimeout(() => { b.textContent = 'Link kopieren'; b.classList.remove('ok'); }, 2000);
  };
  let isHost = first.is_host ?? (ls.get('dip_ishost_' + gid) === '1');
  let mini = null, ctx = null, sig = '', seen = null;
  const setHostUi = () => { $('lb-start').hidden = !isHost; $('lb-wait').hidden = isHost; };
  setHostUi();
  $('lb-start').onclick = async () => {
    try { await api.start(gid, token); msg('lb-msg', 'Wird gestartet …'); } catch (e) { msg('lb-msg', e.message, true); }
  };
  async function tick() {
    try {
      const l = await api.lobby(gid, token);
      if (l.is_host !== undefined) { isHost = l.is_host; setHostUi(); }
      if (l.status === 'running') return gameScreen();
      if (!ctx) {
        ctx = await loadMap(l.map);
        mini = thumbnail(ctx.map, ctx.theme, { joined: [] });
        $('lb-mini').replaceChildren(mini);
        $('lb-map').textContent = ctx.map.name || l.map;
        $('lb-rules-list').innerHTML = l.rules ? ruleLines(l.rules) : '';
      }
      const joined = l.joined || {};
      const s = JSON.stringify([joined, isHost]);
      if (s !== sig) {
        sig = s;
        mini.update({ joined });
        const crown = l.host;
        $('lb-list').innerHTML = Object.entries(l.nations).map(([c, n]) => {
          if (joined[c] === undefined) return `<li class="free"><span class="dot"></span><span class="who">frei</span><span class="nat">${esc(n)}</span></li>`;
          const isNew = seen && !seen.has(c);
          return `<li class="${isNew ? 'in' : ''}" style="--c:${colorOf(ctx.theme, c)}"><span class="dot"></span><span class="who">${esc(joined[c])}${c === crown ? ' <span class="crown" title="Host">♛</span>' : ''}${c === l.me ? ' <small>(du)</small>' : ''}</span><span class="nat">${esc(n)}</span></li>`;
        }).join('');
        seen = new Set(Object.keys(joined));
        $('lb-start').textContent = `Spiel starten (${seen.size} Spieler)`;
      }
      msg('lb-msg', isHost ? 'Link an die Mitspieler schicken, dann starten.' : '');
    } catch (e) { msg('lb-msg', e.message, true); }
    setTimeout(tick, 2000);
  }
  tick();
}

function gameScreen() { show('screen-game'); startGame(gid, token); }

route();
