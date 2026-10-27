// Rejoin screen of a running game without a personal link (RULES.md G62): pick your nation and ask the host,
// or enter the personal rejoin code (shown in the game menu) to get back in at once.
import { api } from './api.js';
import { thumbnail } from './minimap.js';

const $ = id => document.getElementById(id);

export async function rejoinScreen(env, lobby) {
  const { gid, show, msg, esc, loadMap, colorOf, provsOf, ls } = env;
  show('screen-rejoin');
  const { map, theme } = await loadMap(lobby.map);
  $('rj-sub').textContent = map.name || lobby.map;
  const out = new Set(lobby.ai || []);   // surrendered, removed or never played: cannot be entered again
  const players = Object.entries(lobby.joined || {}).filter(([c]) => !out.has(c));
  let sel = null, waiting = false;
  const grid = $('rj-nations');
  const draw = () => {
    grid.innerHTML = Object.entries(lobby.nations).map(([c, n]) => {
      const who = (lobby.joined || {})[c], ok = who && !out.has(c);
      return `<button type="button" class="ncard${sel === c ? ' sel' : ''}" data-nation="${esc(c)}" style="--c:${colorOf(theme, c)}" ${ok && !waiting ? '' : 'disabled'}>` +
        `<b>${esc(n)}</b><small>${provsOf(map, c).length} Provinzen</small><small>${ok ? 'Spieler: ' + esc(who) : out.has(c) && who ? 'hat aufgegeben / entfernt' : 'KI'}</small></button>`;
    }).join('');
    $('rj-ask').disabled = !sel || waiting;
    $('rj-code-go').disabled = !sel || waiting || !$('rj-code').value.trim();
  };
  if (!players.length) msg('rj-msg', 'Keine Nation kann wieder betreten werden.', true); else msg('rj-msg', '');
  grid.onclick = e => { const b = e.target.closest('[data-nation]'); if (b && !b.disabled) { sel = b.dataset.nation; draw(); } };
  $('rj-code').oninput = draw;
  const finish = token => { ls.set('dip_token_' + gid, token); env.goto(token); };

  $('rj-ask').onclick = async () => {
    try {
      const r = await api.rejoin(gid, { nation: sel });
      waiting = true; draw(); $('rj-ask').textContent = 'Warte auf den Spielleiter …';
      msg('rj-msg', 'Anfrage gesendet. Der Spielleiter muss dich bestätigen – dieses Fenster offen lassen.');
      (async function ask() {
        try {
          const s = await api.rejoinStatus(gid, r.request_id);
          if (s.status === 'approved') return finish(s.token);
          if (s.status === 'declined') { waiting = false; draw(); $('rj-ask').textContent = 'Beim Spielleiter anfragen'; msg('rj-msg', 'Der Spielleiter hat die Anfrage abgelehnt.', true); return; }
        } catch (e) { waiting = false; draw(); $('rj-ask').textContent = 'Beim Spielleiter anfragen'; msg('rj-msg', e.message, true); return; }
        setTimeout(ask, 1500);
      })();
    } catch (e) { msg('rj-msg', e.message, true); }
  };
  $('rj-code-go').onclick = async () => {
    try { finish((await api.rejoin(gid, { nation: sel, code: $('rj-code').value.trim() })).token); } catch (e) { msg('rj-msg', e.message, true); }
  };
  draw();
}
