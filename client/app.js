// Screens: start (create game), join, lobby, game. Token lives in the URL (?game=..&token=..) and localStorage.
import { api } from './api.js';
import { startGame } from './game.js';

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

async function startScreen(keepMsg) {
  show('screen-start');
  try {
    const maps = await api.maps();
    $('st-map').innerHTML = maps.map(m => `<option>${esc(m)}</option>`).join('');
  } catch (e) { msg('st-msg', 'Karten nicht ladbar: ' + e.message, true); }
  if (!keepMsg) msg('st-msg', '');
  $('st-create').onclick = async () => {
    try {
      const r = await api.createGame($('st-map').value);
      ls.set('dip_host_' + r.game_id, r.host_token);
      location.href = '?game=' + encodeURIComponent(r.game_id);
    } catch (e) { msg('st-msg', e.message, true); }
  };
}

function joinScreen(lobby) {
  show('screen-join');
  const taken = lobby.joined || {};
  const free = Object.entries(lobby.nations).filter(([c]) => !taken[c]);
  $('jn-nation').innerHTML = free.map(([c, n]) => `<option value="${esc(c)}">${esc(n)}</option>`).join('');
  $('jn-name').value = ls.get('dip_name') || '';
  if (!free.length) msg('jn-msg', 'Keine Nation mehr frei.', true);
  $('jn-go').onclick = async () => {
    const name = $('jn-name').value.trim(), nation = $('jn-nation').value;
    if (!name) { msg('jn-msg', 'Bitte einen Namen eingeben.', true); return; }
    const host = ls.get('dip_host_' + gid);
    try {
      const r = await api.join(gid, host ? { name, nation, host_token: host } : { name, nation });
      ls.set('dip_name', name); ls.set('dip_token_' + gid, r.token);
      if (host) ls.set('dip_ishost_' + gid, '1');
      location.href = `?game=${encodeURIComponent(gid)}&token=${encodeURIComponent(r.token)}`;
    } catch (e) { msg('jn-msg', e.message, true); }
  };
}

function lobbyScreen(first) {
  show('screen-lobby');
  $('lb-link').value = link();
  let isHost = first.is_host ?? (ls.get('dip_ishost_' + gid) === '1');
  $('lb-start').hidden = !isHost;
  $('lb-start').onclick = async () => {
    try { await api.start(gid, token); msg('lb-msg', 'Wird gestartet …'); } catch (e) { msg('lb-msg', e.message, true); }
  };
  async function tick() {
    try {
      const l = await api.lobby(gid, token);
      if (l.is_host !== undefined) { isHost = l.is_host; $('lb-start').hidden = !isHost; }
      if (l.status === 'running') return gameScreen();
      $('lb-list').innerHTML = Object.entries(l.joined || {}).map(([c, n]) => `<li>${esc(n)} – ${esc(l.nations[c] || c)}</li>`).join('');
      msg('lb-msg', isHost ? 'Link an die Mitspieler schicken, dann starten.' : 'Warten auf den Start durch den Host …');
    } catch (e) { msg('lb-msg', e.message, true); }
    setTimeout(tick, 2000);
  }
  tick();
}

function gameScreen() { show('screen-game'); startGame(gid, token); }

route();
