// Cinematic turn replay: banner, then every order step by step (look in replay.css, drawing in render.js).
// Starts from last_turn.before and applies each order group's "snap" (API.md section 5).
import * as R from './render.js';
import { $, esc, ctx, P, nName, pName } from './ctx.js';

const MS_HEX = 250, SPEEDS = [1, 2, 4];
const STOP = { stop: true };
const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const ls = {
  get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};

let hooks = {}, ui = null, run = null, speed = 1, seenMem = null;

export const active = () => !!run;
export const canReplay = lt => !!(lt && lt.before && lt.events && lt.events.length);
export function init(h) { hooks = h || {}; document.addEventListener('keydown', onKey); }

// Called after every state update: auto-play a turn that arrives while the page is open, once per player.
export function maybeAuto(G) {
  const lt = G.last_turn, key = 'dip_replay_seen_' + ctx.gid;
  if (!lt) return;
  const seen = Math.max(seenMem == null ? -1 : seenMem, Number(ls.get(key)) || 0);
  if (seenMem == null) { seenMem = lt.turn; ls.set(key, String(lt.turn)); return; } // first load: never replay an old turn
  if (lt.turn > seen && !run && canReplay(lt)) { seenMem = lt.turn; ls.set(key, String(lt.turn)); start(lt); }
  else if (lt.turn > seenMem) seenMem = lt.turn;
}

export function skip() { if (run) { run.abort = true; run.paused = false; document.getAnimations().forEach(a => { try { a.finish(); } catch (e) { /* infinite */ } }); } }
function onKey(e) {
  if (!run || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
  if (e.key === 'Escape') { e.preventDefault(); skip(); }
  else if (e.key === ' ') { e.preventDefault(); togglePause(); }
}
function togglePause() {
  if (!run) return;
  run.paused = !run.paused;
  const map = $('map');  // freeze only the map animations (caption and banner stay readable)
  document.getAnimations().filter(a => a.effect && a.effect.target && map.contains(a.effect.target))
    .forEach(a => { try { run.paused ? a.pause() : a.play(); } catch (e) { /* ignore */ } });
  ui.pause.textContent = run.paused ? '▶' : '⏸';
  ui.pause.title = run.paused ? 'Weiter (Leertaste)' : 'Pause (Leertaste)';
}

// ---------- overlay ----------
function build() {
  const box = $('mapbox'), el = document.createElement('div');
  el.id = 'rp';
  el.innerHTML = `<div id="rp-dim"></div><div id="rp-banner" hidden></div><div id="rp-toast" hidden></div>
    <div id="rp-bar"><span id="rp-dot"></span><span id="rp-text"></span>
      <span id="rp-ctl"><button id="rp-pause" title="Pause (Leertaste)">⏸</button>
      ${SPEEDS.map(s => `<button class="rp-sp${s === speed ? ' on' : ''}" data-sp="${s}" title="Tempo">${s}×</button>`).join('')}
      <button id="rp-skip" title="Überspringen (Esc)">⏭ Überspringen</button></span></div>`;
  box.appendChild(el);
  ui = { el, dim: el.querySelector('#rp-dim'), banner: el.querySelector('#rp-banner'), toast: el.querySelector('#rp-toast'),
    dot: el.querySelector('#rp-dot'), text: el.querySelector('#rp-text'), pause: el.querySelector('#rp-pause') };
  ui.pause.onclick = togglePause;
  el.querySelector('#rp-skip').onclick = skip;
  el.querySelectorAll('.rp-sp').forEach(b => { b.onclick = () => { speed = +b.dataset.sp; el.querySelectorAll('.rp-sp').forEach(x => x.classList.toggle('on', x === b)); }; });
  el.onwheel = e => e.preventDefault();
}

// ---------- timing ----------
async function wait(ms) {
  let left = ms / speed;
  while (left > 0) {
    if (run.abort) throw STOP;
    await new Promise(r => setTimeout(r, 40));
    if (!run.paused) left -= 40;
  }
  if (run.abort) throw STOP;
}
const chk = () => { if (run.abort) throw STOP; };
const dur = ms => (reduced() ? Math.min(ms, 250) : ms) / speed;

async function showBanner(html, ms, cls = '') {
  const b = ui.banner;
  b.className = cls; b.innerHTML = html; b.hidden = false;
  ui.dim.classList.add('deep');
  void b.offsetWidth;
  b.classList.add('in');
  await wait(ms);
  b.classList.remove('in'); b.classList.add('out');
  await wait(450).catch(e => { throw e; });
  b.hidden = true; ui.dim.classList.remove('deep');
}
async function showToast(html, ms) {
  const t = ui.toast;
  t.innerHTML = html; t.hidden = false; void t.offsetWidth; t.classList.add('in');
  await wait(ms);
  t.classList.remove('in'); t.hidden = true;
}
const colorDot = p => (p ? `background:${R.colorOf(p)}` : 'background:transparent');
function caption(e, dim) {
  ui.dot.style.cssText = colorDot(e.player);
  ui.text.textContent = e.text;
  ui.text.classList.toggle('dim', !!dim);
  ui.text.classList.remove('pop'); void ui.text.offsetWidth; ui.text.classList.add('pop');
}

// ---------- the replay ----------
export async function start(lt) {
  if (run || !canReplay(lt)) return;
  run = { abort: false, paused: false };
  build();
  document.body.classList.add('replaying');
  R.setReplayMode(true);
  const home = R.viewCentre();
  const board = { armies: JSON.parse(JSON.stringify(lt.before.armies)), owners: { ...lt.before.owners } };
  R.drawBoard(board.armies, board.owners);
  try {
    const order = (lt.player_order || ctx.G.player_order || []).map(p =>
      `<span class="rp-chip"><i style="background:${R.colorOf(p)}"></i>${esc(pName(p))}</span>`).join('');
    await showBanner(`<div class="rp-seal"></div><div class="rp-title">Runde ${lt.turn}</div><div class="rp-sub">Die Ereignisse</div>` +
      (order ? `<div class="rp-order">${order}</div>` : ''), reduced() ? 1200 : 2300);
    const { groups, rest } = split(lt.events);
    for (const g of groups) {
      chk();
      try { await playGroup(g, board); } catch (e) { if (e === STOP) throw e; console.error('replay', e); }
      if (g.snap) { board.armies = JSON.parse(JSON.stringify(g.snap.armies)); board.owners = { ...g.snap.owners }; R.drawBoard(board.armies, board.owners); R.clearFx(); }
      await wait(g.events.length === 1 && g.events[0].kind === 'skipped' ? 200 : 450);
    }
    await showBanner(`<div class="rp-seal"></div><div class="rp-title">Runde ${lt.turn + 1} beginnt</div>${incomeLine(rest)}`, reduced() ? 1000 : 2200, 'end');
  } catch (e) { if (e !== STOP) console.error('replay', e); }
  finish(home);
}

function finish(home) {
  R.setReplayMode(false);
  document.body.classList.remove('replaying');
  ui.el.remove(); ui = null; run = null;
  if (hooks.onEnd) hooks.onEnd();
  R.panSmooth(home, 0);
}

// Groups end at the first event with a snap; unknown-order skips stand alone; income/upkeep and the start-of-turn
// block are the rest (shown on the closing banner).
function split(events) {
  const groups = [], econ = []; let cur = [], rest = [];
  events.forEach((e, i) => {
    if (rest.length || e.kind === 'turn_start') { rest.push(e); return; }
    if (e.kind === 'income' || e.kind === 'upkeep') { econ.push(e); return; }
    if (e.kind === 'skipped' && !e.snap) { groups.push({ events: [e], snap: null }); return; }
    cur.push(e);
    if (e.snap) { groups.push({ events: cur, snap: e.snap }); cur = []; }
  });
  if (cur.length) groups.push({ events: cur, snap: null });
  return { groups, rest: econ.concat(rest) };
}
function incomeLine(rest) {
  const me = ctx.G.me, f = k => rest.filter(e => e.kind === k && e.player === me).reduce((s, e) => s + e.amount, 0);
  if (!me || !rest.some(e => e.kind === 'income' && e.player === me)) return '';
  const inc = f('income'), up = f('upkeep');
  return `<div class="rp-sub">Einkommen +${inc} · Unterhalt −${up} · Gold ${ctx.G.my_gold}</div>`;
}

async function panFor(fields) {
  if (reduced() || fields.every(f => R.isVisible(f))) return;
  const pts = fields.map(f => R.centre(f)), n = pts.length;
  await R.panSmooth({ x: pts.reduce((s, p) => s + p.x, 0) / n, y: pts.reduce((s, p) => s + p.y, 0) / n }, dur(650));
}
const sameF = (a, b) => a && b && a[0] === b[0] && a[1] === b[1];

async function playGroup(g, board) {
  const A = board.armies;
  const redraw = id => { if (A[id] && A[id].divisions > 0) R.putToken(A[id]); else { R.removeToken(id); delete A[id]; } };
  for (const e of g.events) {
    chk();
    caption(e, e.kind === 'skipped');
    const ms = n => wait(n);
    switch (e.kind) {
      case 'move': {
        const fields = [e.from, ...e.path];
        await panFor([e.from, e.to]);
        let tok;
        const whole = A[e.army] && sameF(A[e.army].field, e.from);
        if (whole) tok = R.tokenEl(e.army);
        else {
          const src = Object.values(A).find(a => a.owner === e.player && sameF(a.field, e.from));
          A[e.army] = { ...(src || { owner: e.player, forced_march: false }), id: e.army, field: [...e.from], divisions: e.count, fresh: 0, linked: undefined };
          if (src) { src.divisions -= e.count; src.fresh = Math.min(src.fresh || 0, src.divisions); redraw(src.id); }
          tok = R.putToken(A[e.army]);
        }
        const mate = e.with && A[e.with];   // a linked fleet / army sails along
        await Promise.all([R.animateToken(tok, fields, dur(reduced() ? 1 : MS_HEX)),
          mate ? R.animateToken(R.tokenEl(e.with), fields, dur(reduced() ? 1 : MS_HEX)) : null]);
        A[e.army].field = [...e.to];
        if (mate) mate.field = [...e.to];
        await ms(150);
        break;
      }
      case 'fight': {
        await panFor([e.field]);
        await R.effect(e.field, 'fight', ['−' + e.attacker_losses, '−' + e.defender_losses], dur(1100));
        for (const [id, n] of Object.entries(e.losses || {})) if (A[id]) { A[id].divisions -= n; redraw(id); }   // per unit (tank rule)
        await ms(250);
        break;
      }
      case 'conquest': {
        await panFor([e.field]);
        const p = P()[e.province], mover = Object.values(A).find(a => a.owner === e.player && sameF(a.field, e.field));
        if (mover) { mover.divisions -= e.cost; redraw(mover.id); }
        board.owners[e.province] = e.player;
        R.flashProvince(e.province, dur(900));
        const t = showToast(`<b>${esc(nName(e.player))}</b> erobert <b>${esc(p ? p.name : e.province)}</b>`, 1500);
        t.catch(() => {});
        await Promise.all([R.setProvinceFill(e.province, e.player, dur(900)), R.effect(e.field, 'conquest', '', dur(900))]);
        await t;
        break;
      }
      case 'conquest_failed': {
        const mover = Object.values(A).find(a => a.owner === e.player && sameF(a.field, e.field));
        await R.effect(e.field, 'fail', 'Eroberung gescheitert', dur(1000));
        if (mover && e.back_to) {
          await R.animateToken(R.tokenEl(mover.id), [e.field, e.back_to], dur(MS_HEX));
          mover.field = [...e.back_to];
        }
        break;
      }
      case 'merge': {
        const m = A[e.army], into = A[e.into];
        if (m && into) { into.divisions += m.divisions; delete A[e.army]; R.removeToken(e.army); redraw(e.into); }
        await R.effect(e.field, 'merge', '', dur(600));
        break;
      }
      case 'recruit': case 'build_ship': {
        await panFor([e.field]);
        if (A[e.army]) { A[e.army].divisions += e.count; A[e.army].fresh = (A[e.army].fresh || 0) + e.count; }
        else A[e.army] = { id: e.army, owner: e.player, field: [...e.field], divisions: e.count, fresh: e.count, forced_march: false,
          unit: e.kind === 'build_ship' ? ctx.G.rules.sea_unit : ctx.G.rules.land_unit };
        redraw(e.army);
        await R.effect(e.field, 'recruit', '+' + e.count, dur(900));
        break;
      }
      case 'disband': {
        await panFor([e.field]);
        if (A[e.army]) { A[e.army].divisions -= e.count; redraw(e.army); }
        await R.effect(e.field, 'disband', '−' + e.count, dur(900));
        break;
      }
      case 'forced_march': {
        if (A[e.army]) { A[e.army].forced_march = e.on; redraw(e.army); await R.effect(A[e.army].field, 'march', e.on ? '»' : '»×', dur(600)); }
        break;
      }
      case 'give_province': case 'buy': {   // buy: e.to is the buyer
        const p = P()[e.province];
        if (p) await panFor([p.capital]);
        board.owners[e.province] = e.to;
        R.flashProvince(e.province, dur(900));
        await R.setProvinceFill(e.province, e.to, dur(1000));
        break;
      }
      case 'alliance': case 'alliance_end': case 'victory': {   // diplomacy news: caption plus a short banner toast
        const t = showToast(esc(e.text), 1800);
        t.catch(() => {});
        await t;
        break;
      }
      default: // send_gold, no_attack, leave, move_blocked, victory_progress, skipped, ...: caption only
        await ms(e.kind === 'skipped' ? 600 : 1100);
    }
  }
}
