// Thin fetch wrappers for the HTTP API (API.md section 8).
async function call(method, url, body) {
  const r = await fetch(url, {
    method, headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await r.json(); } catch (e) { /* no body */ }
  if (!r.ok) {
    let d = data && (data.detail ?? data.error);
    if (d && typeof d !== 'string') d = JSON.stringify(d);
    throw new Error(d || r.statusText);
  }
  return data;
}
const g = id => `/api/games/${encodeURIComponent(id)}`;
const t = tok => `?token=${encodeURIComponent(tok)}`;
export const api = {
  maps: () => call('GET', '/api/maps'),
  createGame: (map, rules) => call('POST', '/api/games', { map, rules: rules || {} }),
  lobby: (id, tok) => call('GET', `${g(id)}/lobby${tok ? t(tok) : ''}`),
  join: (id, body) => call('POST', `${g(id)}/join`, body),
  start: (id, tok) => call('POST', `${g(id)}/start${t(tok)}`),
  state: (id, tok, since) => call('GET', `${g(id)}/state${t(tok)}${since != null ? '&since=' + since : ''}`),
  putOrders: (id, tok, orders) => call('PUT', `${g(id)}/orders${t(tok)}`, { orders }),
  ready: (id, tok, ready) => call('POST', `${g(id)}/ready${t(tok)}`, { ready }),
  chooseNation: (id, tok, nation) => call('POST', `${g(id)}/nation${t(tok)}`, { nation }),
  settings: (id, tok, body) => call('POST', `${g(id)}/settings${t(tok)}`, body),
  assignRandom: (id, tok) => call('POST', `${g(id)}/assign_random${t(tok)}`, {}),
  kick: (id, tok, body) => call('POST', `${g(id)}/kick${t(tok)}`, body),
  pause: (id, tok, paused) => call('POST', `${g(id)}/pause${t(tok)}`, { paused }),
  surrender: (id, tok) => call('POST', `${g(id)}/surrender${t(tok)}`, {}),
  rejoin: (id, body) => call('POST', `${g(id)}/rejoin`, body),
  rejoinStatus: (id, rid) => call('GET', `${g(id)}/rejoin/${encodeURIComponent(rid)}`),
  rejoinAnswer: (id, tok, rid, accept) => call('POST', `${g(id)}/rejoin/${encodeURIComponent(rid)}/answer${t(tok)}`, { accept }),
  saveMap: (name, body) => call('PUT', `/api/maps/${encodeURIComponent(name)}`, body),
  chat: (id, tok, body) => call('POST', `${g(id)}/chat${t(tok)}`, body),
  preview: (id, tok, body) => call('POST', `${g(id)}/preview${t(tok)}`, body),
};
