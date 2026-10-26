// Mini-map thumbnails for start/join/lobby (render layer: colours only from theme.json).
import { parseGrid } from './hex.js';

const S = 10, SQ3 = Math.sqrt(3), NS = 'http://www.w3.org/2000/svg';
const hexPath = (c, r) => {
  const x = c * 1.5 * S + S, y = (r + (c % 2 ? 0 : 0.5)) * SQ3 * S + S;
  return 'M' + [0, 1, 2, 3, 4, 5].map(i => (x + S * Math.cos(i * Math.PI / 3)).toFixed(1) + ' ' + (y + S * Math.sin(i * Math.PI / 3)).toFixed(1)).join('L') + 'z';
};
const mk = (tag, attrs, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
};

// opts: { joined: Set|array|object of nation codes drawn in colour (default: all), highlight: nation code }
// Returned element has .update(opts) to recolour without rebuilding.
export function thumbnail(map, theme, opts = {}) {
  const grid = parseGrid(map.grid), provs = map.provinces || {}, terr = theme.terrain || {};
  const groups = {};
  grid.forEach((row, r) => row.forEach((tok, c) => {
    if (tok === '..') return;
    const k = provs[tok] ? provs[tok].owner || '' : tok;
    (groups[k] ||= []).push(hexPath(c, r));
  }));
  const cols = Math.max(...grid.map(r => r.length));
  const svg = mk('svg', { viewBox: `0 0 ${(cols * 1.5 + 1) * S + S} ${(grid.length + 1) * SQ3 * S + S}`, class: 'minimap', role: 'img', 'aria-label': map.name || 'Karte' });
  const paths = {};
  for (const k in groups) paths[k] = mk('path', { d: groups[k].join('') }, svg);
  svg.update = (o = {}) => {
    const on = o.joined == null ? null : new Set(o.joined instanceof Set || Array.isArray(o.joined) ? o.joined : Object.keys(o.joined));
    for (const k in paths) {
      const nation = (map.nations || {})[k] !== undefined;
      let fill;
      if (nation) fill = !on || on.has(k) ? (theme.nation_colors || {})[k] || theme.neutral_color : theme.neutral_color;
      else fill = (terr[k] || {}).fill || (k === '' ? theme.neutral_color : theme.background);
      paths[k].setAttribute('fill', fill || '#888');
      paths[k].setAttribute('opacity', nation && o.highlight && o.highlight !== k ? 0.35 : 1);
      paths[k].setAttribute('stroke', nation && o.highlight === k ? theme.province_border || '#fff' : 'none');
      paths[k].setAttribute('stroke-width', 1.5);
    }
  };
  svg.update(opts);
  return svg;
}
