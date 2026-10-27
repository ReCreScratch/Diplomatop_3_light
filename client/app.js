// Screens: start (create game), join, lobby (lobby.js), rejoin (rejoin.js), game. Token lives in the URL (?game=..&token=..) and localStorage.
import { api } from './api.js';
import { startGame } from './game.js';
import { thumbnail } from './minimap.js';
import { lobbyScreen } from './lobby.js';
import { rejoinScreen } from './rejoin.js';

const $ = id => document.getElementById(id);
const q = new URLSearchParams(location.search);
const gid = q.get('game');
const ls = {
  get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};
let token = q.get('token') || (gid && ls.get('dip_token_' + gid));
const show = id => { for (const s of document.querySelectorAll('.screen, #screen-game')) s.hidden = s.id !== id; };
const msg = (id, text, err) => { const e = $(id); e.textContent = text || ''; e.className = 'msg' + (err ? ' err' : ''); };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const link = () => location.origin + location.pathname + '?game=' + encodeURIComponent(gid);

// Map + theme are static files (/maps/{name}/...); cached per map.
const mapCache = {};
const loadMap = name => mapCache[name] ||= Promise.all([
  fetch(`/maps/${encodeURIComponent(name)}/map.json`).then(r => r.json()),
  fetch(`/maps/${encodeURIComponent(name)}/theme.json`).then(r => r.json()).catch(() => ({})),
]).then(([map, theme]) => ({ map, theme }));
const colorOf = (theme, c) => (theme.nation_colors || {})[c] || theme.neutral_color || '#888';
const provsOf = (map, c) => Object.values(map.provinces).filter(p => p.owner === c);

const env = { gid, get token() { return token; }, ls, show, msg, esc, link, loadMap, colorOf, provsOf, gameScreen,
  goto: tok => { location.href = `?game=${encodeURIComponent(gid)}&token=${encodeURIComponent(tok)}`; } };

async function route() {
  if (!gid) return startScreen();
  let lobby;
  try { lobby = await api.lobby(gid, token); } catch (e) { show('screen-start'); msg('st-msg', 'Spiel nicht gefunden: ' + e.message, true); return startScreen(true); }
  if (token && lobby.me_name == null) {   // a token the server does not know any more (kicked, replaced by a rejoin)
    ls.set('dip_token_' + gid, ''); token = null;
    history.replaceState(null, '', `?game=${encodeURIComponent(gid)}`);
  }
  if (token) {
    if (!q.get('token')) history.replaceState(null, '', `?game=${encodeURIComponent(gid)}&token=${encodeURIComponent(token)}`);
    return lobby.status !== 'lobby' ? gameScreen() : lobbyScreen(env, lobby);
  }
  if (lobby.status === 'finished') { show('screen-start'); msg('st-msg', 'Das Spiel ist beendet.', true); return startScreen(true); }
  if (lobby.status !== 'lobby') return rejoinScreen(env, lobby);
  joinScreen(lobby);
}

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

// Joining needs only a name; the nation is chosen (or drawn) in the lobby.
async function joinScreen(lobby) {
  show('screen-join');
  const { map, theme } = await loadMap(lobby.map);
  $('jn-mini').replaceChildren(thumbnail(map, theme));
  $('jn-name').value = ls.get('dip_name') || '';
  $('jn-go').onclick = async () => {
    const name = $('jn-name').value.trim();
    if (!name) { msg('jn-msg', 'Bitte einen Namen eingeben.', true); $('jn-name').focus(); return; }
    const host = ls.get('dip_host_' + gid);
    try {
      const r = await api.join(gid, host ? { name, host_token: host } : { name });
      ls.set('dip_name', name); ls.set('dip_token_' + gid, r.token);
      if (host) ls.set('dip_ishost_' + gid, '1');
      env.goto(r.token);
    } catch (e) { msg('jn-msg', e.message, true); }
  };
  $('jn-name').onkeydown = e => { if (e.key === 'Enter') $('jn-go').click(); };
}

function gameScreen() { show('screen-game'); startGame(gid, token, env); }

route();
