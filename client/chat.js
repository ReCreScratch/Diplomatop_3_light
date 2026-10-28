// Diplomacy chat panel (IMPLEMENTATION.md 3.4): channels, composer with map marks, notifications.
// Marks are drawn through render.js showMarks(); state comes from ctx.G.chat (server view).
import * as R from './render.js';
import * as O from './orders.js';
import { api } from './api.js';
import { $, esc, same, ctx, P, pName, fieldName } from './ctx.js';

let hooks = { toast() {}, poll() {} };
let cur = 'all', collapsed = false, pin = false, lastId = null, sig = '';
const drafts = {};                       // channel -> { text, marks }
let hoverId = null, flashT = null, toastT = null;
const el = {};

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
const seenKey = () => 'dipl-chat-seen-' + ctx.gid;
const seen = () => store.get(seenKey(), {});
const msgs = () => (ctx.G && ctx.G.chat) || [];
const others = () => ctx.G.me ? Object.keys(ctx.G.players).filter(p => p !== ctx.G.me) : [];   // spectators read the public channel only
const chanOf = m => m.to == null ? 'all' : (m.from === ctx.G.me ? m.to : m.from);
const inChan = ch => msgs().filter(m => chanOf(m) === ch);
const draft = () => drafts[cur] || (drafts[cur] = { text: '', marks: [] });
const chName = ch => ch === 'all' ? 'Alle' : pName(ch);
const unread = ch => { const s = seen()[ch] || 0; return inChan(ch).filter(m => m.from !== ctx.G.me && m.id > s).length; };
const isField = (m, f) => m.kind === 'field' && same(m.f, f);

export function init(h) {
  hooks = h;
  $('chat').innerHTML =
    `<div class="panel-head chat-head"><button id="chat-toggle" type="button">💬 Diplomatie <b id="chat-total" class="cbadge" hidden></b></button></div>` +
    `<div id="chat-body"><div id="chat-tabs"></div><div id="chat-msgs"></div>` +
    `<div id="chat-comp"><div id="chat-marks"></div>` +
    `<div class="chat-ac" id="chat-ac" hidden></div>` +
    `<textarea id="chat-text" rows="2" placeholder="Nachricht … (# = Provinz, Alt+Klick = Feld markieren)"></textarea>` +
    `<div class="chat-row"><button id="chat-pin" type="button" title="Felder auf der Karte markieren (Alt+Klick)">📍</button>` +
    `<button id="chat-share" type="button">Zug teilen</button><span class="chat-sp"></span>` +
    `<button id="chat-send" type="button" class="primary">Senden</button></div>` +
    `<div class="chat-pop" id="chat-pop" hidden></div></div></div>`;
  for (const id of ['toggle', 'total', 'body', 'tabs', 'msgs', 'comp', 'marks', 'ac', 'text', 'pin', 'share', 'send', 'pop'])
    el[id] = $('chat-' + id);
  collapsed = store.get('dipl-chat-collapsed', false);
  el.toggle.onclick = () => setCollapsed(!collapsed);
  el.tabs.onclick = e => { const b = e.target.closest('[data-ch]'); if (b) openChannel(b.dataset.ch); };
  el.msgs.onmouseover = e => {
    const m = e.target.closest('.cm'), id = m ? +m.dataset.id : null;
    if (id === hoverId) return;
    hoverId = id; R.showMarks(id == null ? [] : (msgs().find(x => x.id === id) || {}).marks, 'chat');
  };
  el.msgs.onmouseleave = () => { hoverId = null; R.showMarks([], 'chat'); };
  el.msgs.onclick = e => {
    const c = e.target.closest('[data-mi]'); if (!c) return;
    const m = msgs().find(x => x.id === +c.dataset.id), mk = m && m.marks[+c.dataset.mi];
    if (!mk) return;
    R.panTo(mk.kind === 'field' ? mk.f : mk.path[mk.path.length - 1]);
    flash([mk], 2000);
  };
  el.marks.onclick = e => { const a = e.target.closest('[data-rm]'); if (a) { draft().marks.splice(+a.dataset.rm, 1); drawDraft(); } };
  el.pin.onclick = () => setPin(!pin);
  el.share.onclick = toggleShare;
  el.pop.onclick = onPop;
  el.send.onclick = send;
  el.text.oninput = onInput;
  el.text.onkeydown = onKeyDown;
  el.ac.onmousedown = e => { const b = e.target.closest('[data-tok]'); if (b) { e.preventDefault(); pickProvince(b.dataset.tok); } };
  document.addEventListener('click', e => { if (!e.target.closest('#chat-pop,#chat-share')) el.pop.hidden = true; });
  el.body.hidden = collapsed; el.toggle.classList.toggle('collapsed', collapsed);
}

function setCollapsed(c) {
  collapsed = c; store.set('dipl-chat-collapsed', c);
  el.body.hidden = c; el.toggle.classList.toggle('collapsed', c);
  if (c) { setPin(false); R.showMarks([], 'chat-draft'); } else { markSeen(); drawDraft(); }
  sig = ''; render();
}

// ---------- hooks used by game.js / input.js ----------
export const pinning = () => pin;
export function cancelPin() { if (!pin) return false; setPin(false); return true; }
export function toggleMark(f) {
  if (!ctx.G || !ctx.G.me) return;
  if (collapsed) setCollapsed(false);
  const d = draft(), i = d.marks.findIndex(m => isField(m, f));
  if (i >= 0) d.marks.splice(i, 1); else d.marks.push({ kind: 'field', f: [f[0], f[1]] });
  drawDraft();
}
export function openChannel(ch, field) {
  if (ch !== 'all' && !(ctx.G.players[ch] && ch !== ctx.G.me)) ch = 'all';
  drafts[cur] = { text: el.text.value, marks: draft().marks };
  cur = ch; sig = '';
  el.text.value = draft().text;
  if (field && !draft().marks.some(m => isField(m, field))) draft().marks.push({ kind: 'field', f: [field[0], field[1]] });
  if (collapsed) { collapsed = false; store.set('dipl-chat-collapsed', false); el.body.hidden = false; el.toggle.classList.remove('collapsed'); }
  markSeen(); render(); drawDraft(); el.text.focus();
}
export function focusInput() { if (collapsed) setCollapsed(false); el.text.focus(); }

// ---------- state update (called after every new server state) ----------
export function update() {
  if (!el.tabs) return;
  const G = ctx.G, L = msgs(), top = L.length ? L[L.length - 1].id : 0;
  if (cur !== 'all' && !G.players[cur]) cur = 'all';
  if (lastId === null) lastId = top;    // everything present at page load counts as already seen
  else if (top > lastId) {
    const fresh = L.filter(m => m.id > lastId && m.from !== G.me);
    lastId = top;
    const marks = fresh.flatMap(m => m.marks);
    if (marks.length) flash(marks, 4000);
    const closed = fresh.filter(m => collapsed || chanOf(m) !== cur);
    if (closed.length) notify(closed[closed.length - 1]);
  }
  markSeen(); render();
}
function markSeen() {
  if (!ctx.G || collapsed) return;
  const L = inChan(cur); if (!L.length) return;
  const s = seen();
  if ((s[cur] || 0) < L[L.length - 1].id) { s[cur] = L[L.length - 1].id; store.set(seenKey(), s); }
}
function flash(marks, ms) {
  R.showMarks(marks, 'chat-flash');
  clearTimeout(flashT); flashT = setTimeout(() => R.showMarks([], 'chat-flash'), ms);
}
function notify(m) {
  let t = $('chat-toast');
  if (!t) { t = document.createElement('div'); t.id = 'chat-toast'; document.body.appendChild(t); }
  const ch = chanOf(m);
  t.textContent = '✉ Nachricht von ' + pName(m.from) + (ch === 'all' ? ' (Alle)' : ''); t.hidden = false;
  t.onclick = () => { t.hidden = true; openChannel(ch); };
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 6000);
}

// ---------- rendering ----------
function render() {
  const G = ctx.G, chans = ['all', ...others()];
  el.comp.hidden = !G.me;
  const counts = chans.map(unread), total = counts.reduce((a, b) => a + b, 0);
  el.total.textContent = total; el.total.hidden = !total || !collapsed;
  if (collapsed) return;
  el.tabs.innerHTML = chans.map((ch, i) =>
    `<button type="button" class="ctab${ch === cur ? ' on' : ''}" data-ch="${esc(ch)}">` +
    (ch === 'all' ? '' : `<i class="cdot" style="background:${R.colorOf(ch)}"></i>`) + esc(chName(ch)) +
    (counts[i] ? ` <b class="cbadge">${counts[i]}</b>` : '') + `</button>`).join('');
  const L = inChan(cur), s = cur + ':' + L.length + ':' + (L.length ? L[L.length - 1].id : 0) + ':' + G.me;
  if (s === sig) return;
  const box = el.msgs, atEnd = !sig || !sig.startsWith(cur + ':') || box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  sig = s;
  box.innerHTML = L.length ? L.map(msgHtml).join('')
    : `<p class="cempty">${cur === 'all' ? 'Öffentlicher Kanal – alle lesen mit.' : 'Privat zwischen dir und ' + esc(pName(cur)) + '.'}</p>`;
  if (atEnd) box.scrollTop = box.scrollHeight;
}
function markLabel(mk) {
  if (mk.kind === 'field') return '📍 ' + fieldName(mk.f);
  const p = mk.path; return '➜ ' + fieldName(p[0]) + ' → ' + fieldName(p[p.length - 1]);
}
function msgHtml(m) {
  const me = m.from === ctx.G.me;
  return `<div class="cm${me ? ' me' : ''}" data-id="${m.id}"><div class="ch"><b style="color:${R.colorOf(m.from)}">${me ? 'Du' : esc(pName(m.from))}</b> <small>R${m.turn}</small></div>` +
    (m.text ? `<div class="ct">${esc(m.text)}</div>` : '') +
    (m.marks.length ? `<div class="cchips">${m.marks.map((mk, i) => `<span class="cchip" data-id="${m.id}" data-mi="${i}">${esc(markLabel(mk))}</span>`).join('')}</div>` : '') + '</div>';
}
function drawDraft() {
  const d = draft();
  el.marks.innerHTML = d.marks.map((mk, i) => `<span class="cchip">${esc(markLabel(mk))} <a data-rm="${i}" title="Entfernen">✕</a></span>`).join('');
  R.showMarks(d.marks, 'chat-draft');
}
function setPin(on) {
  pin = on; el.pin.classList.toggle('on', on); $('map').classList.toggle('picking', on);
  if (on && collapsed) setCollapsed(false);
}

// ---------- share own moves ----------
function toggleShare() {
  if (!el.pop.hidden) { el.pop.hidden = true; return; }
  const moves = O.book.list.filter(o => o.type === 'move'), armies = Object.values(ctx.G.armies);
  el.pop.innerHTML = moves.length
    ? `<button type="button" data-all="1">Alle ${moves.length} Züge</button>` + moves.map((o, i) => {
      const a = armies.find(x => x.id === o.army);
      return a ? `<button type="button" data-mv="${i}">${esc(o.army)}: ${esc(fieldName(a.field))} → ${esc(fieldName(o.path[o.path.length - 1]))} <small>(${o.count} Div.)</small></button>` : '';
    }).join('')
    : '<span class="cempty">Keine Zugbefehle vorhanden.</span>';
  el.pop.hidden = false;
}
function onPop(e) {
  const b = e.target.closest('button'); if (!b) return;
  const moves = O.book.list.filter(o => o.type === 'move'), armies = Object.values(ctx.G.armies);
  for (const o of b.dataset.all ? moves : [moves[+b.dataset.mv]]) {
    const a = o && armies.find(x => x.id === o.army);
    if (a && o.path && o.path.length) draft().marks.push({ kind: 'arrow', path: [[...a.field], ...o.path.map(f => [...f])] });
  }
  el.pop.hidden = true; drawDraft();
}

// ---------- composer ----------
let acList = [], acIdx = 0;
function onInput() {
  const t = el.text, before = t.value.slice(0, t.selectionStart), m = /#([\p{L}\-]*)$/u.exec(before);
  if (!m) { closeAc(); return; }
  const q = m[1].toLowerCase(), st = p => p.name.toLowerCase().startsWith(q) ? 0 : 1;
  acList = Object.entries(P()).filter(([, p]) => p.name.toLowerCase().includes(q))
    .sort((a, b) => st(a[1]) - st(b[1]) || a[1].name.localeCompare(b[1].name))
    .slice(0, 6).map(([tok, p]) => ({ tok, name: p.name }));
  acIdx = 0; renderAc();
}
function renderAc() {
  el.ac.hidden = !acList.length;
  el.ac.innerHTML = acList.map((a, i) => `<button type="button" class="${i === acIdx ? 'on' : ''}" data-tok="${esc(a.tok)}">#${esc(a.name)}</button>`).join('');
}
const closeAc = () => { acList = []; el.ac.hidden = true; };
function pickProvince(tok) {
  const p = P()[tok], t = el.text, pos = t.selectionStart;
  const before = t.value.slice(0, pos).replace(/#[\p{L}\-]*$/u, ''), after = t.value.slice(pos);
  t.value = before + p.name + ' ' + after; t.selectionStart = t.selectionEnd = before.length + p.name.length + 1;
  const d = draft();
  if (p.capital && !d.marks.some(m => isField(m, p.capital))) d.marks.push({ kind: 'field', f: [...p.capital] });
  closeAc(); drawDraft(); t.focus();
}
function onKeyDown(e) {
  if (!el.ac.hidden) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); acIdx = (acIdx + (e.key === 'ArrowDown' ? 1 : acList.length - 1)) % acList.length; renderAc(); return; }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); pickProvince(acList[acIdx].tok); return; }
    if (e.key === 'Escape') { e.preventDefault(); closeAc(); return; }
  }
  if (e.key === 'Escape') { if (pin) setPin(false); else el.text.blur(); return; }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
}
async function send() {
  const d = draft(), text = el.text.value.trim(), ch = cur;
  if (!text && !d.marks.length) return;
  el.send.disabled = true;
  try {
    const r = await api.chat(ctx.gid, ctx.token, { to: ch === 'all' ? null : ch, text, marks: d.marks });
    if (!ctx.G.chat.some(m => m.id === r.message.id)) ctx.G.chat.push(r.message);
    lastId = Math.max(lastId || 0, r.message.id);
    drafts[ch] = { text: '', marks: [] };
    if (ch === cur) { el.text.value = ''; drawDraft(); }
    markSeen(); render(); hooks.poll();
  } catch (e) { hooks.toast(e.message); }
  el.send.disabled = false;
}
