// Lobby screen: players with host crown, nation cards, host settings, random draw with a one-by-one reveal.
// The server decides everything; this file only shows the latest /lobby answer (polled every 2 s, faster during a reveal).
import { api } from './api.js';
import { thumbnail } from './minimap.js';

const $ = id => document.getElementById(id);

// Rule summary, built only from the merged rules the server sends.
function ruleLines(r, esc) {
  const t = r.turn_timer_seconds;
  return [
    ['Startgold', r.start_gold], ['Kosten pro Division', r.division_cost],
    ['Unterhalt', `${r.upkeep_per_division} je Division${r.upkeep_per_army ? ` + ${r.upkeep_per_army} je Armee` : ''}`],
    ['Bewegung', `${r.move_range} Feld(er)`], ['Gewaltmarsch', `bis ${r.forced_march_range} Felder`],
    ['Rekrutierung', `in eigenen Städten, max. ${r.recruit_limit_per_province} je Provinz`],
    ['Bündnisse', `bis ${r.max_alliance_size} Spieler`], ['Zugtimer', t ? `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')} min` : 'kein Timer'],
  ].map(([k, v]) => `<li><span>${k}:</span> ${esc(v)}</li>`).join('');
}

export function lobbyScreen(env, first) {
  const { gid, show, msg, esc, link, loadMap, colorOf, provsOf, gameScreen, ls } = env;
  const tok = () => env.token;
  show('screen-lobby');
  $('lb-link').value = link();
  $('lb-copy').onclick = async () => {
    const inp = $('lb-link');
    try { await navigator.clipboard.writeText(inp.value); }
    catch (e) { inp.select(); try { document.execCommand('copy'); } catch (e2) { /* ignore */ } }
    const b = $('lb-copy'); b.textContent = 'Kopiert ✓'; b.classList.add('ok');
    setTimeout(() => { b.textContent = 'Link kopieren'; b.classList.remove('ok'); }, 2000);
  };

  // --- online link (Cloudflare Quick Tunnel): offered only on the host PC itself (the server says local) ---
  const online = $('lb-online'), tunHint = $('lb-tun-hint'), tunBtn = $('lb-tun-btn');
  let T = null;
  function showTunnel() {
    online.hidden = !T || !T.local;
    if (online.hidden) return;
    const running = T.running && T.url;
    $('lb-link').value = running ? T.url + link().slice(location.origin.length) : link();
    $('lb-tun-cmdrow').hidden = T.available;
    tunBtn.textContent = !T.available ? 'Erneut prüfen' : running ? 'Online-Link beenden' : 'Online-Link erstellen';
    if (!tunHint.classList.contains('err')) {
      tunHint.textContent = !T.available ? 'cloudflared ist nicht installiert: In der Eingabeaufforderung ausführen, danach erneut prüfen.'
        : running ? 'Link an Mitspieler schicken. Es kann ein paar Sekunden dauern, bis er erreichbar ist.' : '';
    }
  }
  async function tunnelCall(fn, busy) {
    tunBtn.disabled = true;
    if (busy) msg('lb-tun-hint', busy);
    try { T = await fn(); msg('lb-tun-hint', ''); } catch (e) { msg('lb-tun-hint', e.message, true); }
    tunBtn.disabled = false; showTunnel();
  }
  tunBtn.onclick = () => tunnelCall(!T.available ? api.tunnel : T.running ? api.tunnelStop : api.tunnelStart, T.available && !T.running ? 'Tunnel wird gestartet …' : '');
  $('lb-tun-cmdcopy').onclick = async () => {
    const inp = $('lb-tun-cmd');
    try { await navigator.clipboard.writeText(inp.value); }
    catch (e) { inp.select(); try { document.execCommand('copy'); } catch (e2) { /* ignore */ } }
    const b = $('lb-tun-cmdcopy'); b.textContent = 'Kopiert ✓'; b.classList.add('ok');
    setTimeout(() => { b.textContent = 'Kopieren'; b.classList.remove('ok'); }, 2000);
  };
  api.tunnel().then(t => { T = t; showTunnel(); }).catch(() => { /* older server: no online link */ });

  let L = first, mapCtx = null, mini = null, rv = null, seenShown = null, timer = null, stopped = false;
  const isHost = () => L.is_host ?? (ls.get('dip_ishost_' + gid) === '1');
  const act = async (fn) => { try { await fn(); msg('lb-msg', ''); } catch (e) { msg('lb-msg', e.message, true); } poll(); };

  // --- reveal clock: a draw is shown entry by entry; the clock starts when this browser first sees the draw ---
  function revealed() {
    const r = L.reveal;
    if (!r) { rv = null; return { done: true, n: 0, entries: [] }; }
    const sig = JSON.stringify(r.entries) + r.pause;
    if (!rv || rv.sig !== sig) rv = { sig, base: r.elapsed, at: Date.now() };
    const t = rv.base + (Date.now() - rv.at) / 1000;
    const n = r.pause > 0 ? Math.min(r.entries.length, Math.floor(t / r.pause)) : r.entries.length;
    return { done: n >= r.entries.length, n, entries: r.entries };
  }

  function render() {
    if (!mapCtx) return;
    const rvl = revealed(), hidden = new Set(rvl.entries.slice(rvl.n).map(e => e.nation));
    const joined = {};   // nation -> player name, as far as it is revealed
    for (const [c, name] of Object.entries(L.joined || {})) if (!hidden.has(c)) joined[c] = name;
    const crowned = L.players.find(p => p.host);
    // players
    $('lb-list').innerHTML = L.players.map(p => {
      const shown = p.nation && !hidden.has(p.nation) ? p.nation : null;
      const nat = shown ? esc(L.nations[shown]) : (p.nation ? '<i>wird gelost …</i>' : '<i>wählt noch …</i>');
      const kick = isHost() && !p.host && !p.you ? ` <button class="x" data-kick="${esc(p.id)}" title="Spieler entfernen">✕</button>` : '';
      return `<li style="--c:${shown ? colorOf(mapCtx.theme, shown) : 'var(--dim)'}"><span class="dot"></span><span class="who">${esc(p.name)}${p === crowned ? ' <span class="crown" title="Host">♛</span>' : ''}${p.you ? ' <small>(du)</small>' : ''}</span><span class="nat">${nat}</span>${kick}</li>`;
    }).join('') || '<li class="free"><span class="who">noch niemand</span></li>';
    // nations
    const fresh = seenShown ? Object.keys(joined).filter(c => !seenShown.has(c)) : [];
    const lockedByMode = L.nation_mode === 'random';
    $('lb-nations').innerHTML = Object.entries(L.nations).map(([c, n]) => {
      const ps = provsOf(mapCtx.map, c), mine = c === L.me, who = joined[c];
      const cls = `ncard${mine ? ' sel' : ''}${who && !mine ? ' taken' : ''}${rvl.entries.length && fresh.includes(c) ? ' pop' : ''}`;
      const off = (who && !mine) || lockedByMode;
      return `<button type="button" class="${cls}" data-nation="${esc(c)}" style="--c:${colorOf(mapCtx.theme, c)}" ${off ? 'disabled' : ''}` +
        ` title="${esc(lockedByMode ? 'Der Spielleiter lost die Nationen aus.' : who && !mine ? 'Schon vergeben' : mine ? 'Nochmal klicken: Nation zurückgeben' : 'Diese Nation wählen')}">` +
        `<b>${esc(n)}</b><small>${ps.length} Provinzen</small><small>${who ? 'Spieler: ' + esc(who) : '&nbsp;'}</small></button>`;
    }).join('');
    seenShown = new Set(Object.keys(joined));
    mini.update({ joined: Object.keys(joined) });
    // reveal line
    const line = $('lb-reveal');
    line.hidden = !L.reveal || rvl.done;
    if (!line.hidden) line.textContent = `Die Nationen werden aufgedeckt … (${rvl.n} von ${rvl.entries.length})`;
    // settings
    const host = isHost(), r = L.rules;
    $('lb-host-note').textContent = host ? '' : '(nur der Spielleiter ändert sie)';
    for (const id of ['lb-min', 'lb-sec', 'lb-gold', 'lb-mode']) {
      const el = $(id); el.disabled = !host;
      if (document.activeElement === el) continue;
      el.value = id === 'lb-min' ? Math.floor(r.turn_timer_seconds / 60) : id === 'lb-sec' ? r.turn_timer_seconds % 60 : id === 'lb-gold' ? r.start_gold : L.nation_mode;
    }
    $('lb-draw').hidden = !host || L.nation_mode !== 'random';
    $('lb-draw').textContent = L.reveal ? 'Neu auslosen' : 'Nationen auslosen';
    $('lb-rules-list').innerHTML = ruleLines(r, esc);
    // start
    const missing = L.players.filter(p => !p.nation).length;
    $('lb-start').hidden = !host; $('lb-wait').hidden = host;
    $('lb-start').textContent = `Spiel starten (${L.players.length} Spieler)`;
    $('lb-start').disabled = !L.players.length || missing > 0 || !rvl.done;
    $('lb-start').title = missing ? 'Alle Spieler brauchen eine Nation.' : !rvl.done ? 'Die Nationen werden noch aufgedeckt.' : '';
    if (!$('lb-msg').classList.contains('err')) $('lb-msg').textContent = host ? (missing ? `${missing} Spieler ohne Nation.` : 'Link an die Mitspieler schicken, dann starten.') : '';
    if (!rvl.done && !timer) timer = setInterval(() => { if (!stopped) render(); }, 250);
    if (rvl.done && timer) { clearInterval(timer); timer = null; }
  }

  // --- events ---
  $('lb-nations').onclick = e => {
    const b = e.target.closest('[data-nation]'); if (!b || b.disabled) return;
    act(() => api.chooseNation(gid, tok(), b.dataset.nation === L.me ? null : b.dataset.nation));
  };
  $('lb-list').onclick = e => {
    const b = e.target.closest('[data-kick]'); if (!b) return;
    const p = L.players.find(x => x.id === b.dataset.kick);
    if (p && confirm(`${p.name} wirklich aus der Lobby entfernen?`)) act(() => api.kick(gid, tok(), { member: p.id }));
  };
  const send = () => {
    const total = Math.max(0, Math.floor(+$('lb-min').value || 0)) * 60 + Math.max(0, Math.floor(+$('lb-sec').value || 0));
    const rules = { turn_timer_seconds: total };
    if ($('lb-gold').value !== '') rules.start_gold = Math.max(0, +$('lb-gold').value);
    act(() => api.settings(gid, tok(), { rules, nation_mode: $('lb-mode').value }));
  };
  for (const id of ['lb-min', 'lb-sec', 'lb-gold', 'lb-mode']) $(id).onchange = send;
  $('lb-draw').onclick = () => act(() => api.assignRandom(gid, tok()));
  $('lb-start').onclick = async () => {
    try { await api.start(gid, tok()); msg('lb-msg', 'Wird gestartet …'); poll(); } catch (e) { msg('lb-msg', e.message, true); }
  };

  async function poll() {
    if (stopped) return;
    try {
      L = await api.lobby(gid, tok());
      if (L.status !== 'lobby') { stopped = true; clearInterval(timer); return gameScreen(); }
      if (L.me_name == null) { stopped = true; clearInterval(timer); location.href = '?game=' + encodeURIComponent(gid); return; }   // removed by the host
      if (!mapCtx) {
        mapCtx = await loadMap(L.map);
        mini = thumbnail(mapCtx.map, mapCtx.theme, { joined: [] });
        $('lb-mini').replaceChildren(mini);
        $('lb-map').textContent = mapCtx.map.name || L.map;
      }
      render();
    } catch (e) { msg('lb-msg', e.message, true); }
    clearTimeout(poll.t); poll.t = setTimeout(poll, L.reveal && !revealed().done ? 700 : 2000);
  }
  poll();
}
