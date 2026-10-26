// Hex-grid helpers (flat-top, odd columns raised half a field). No colours, no drawing.
export const neighbours = (c, r) => c % 2
  ? [[c, r - 1], [c, r + 1], [c - 1, r - 1], [c - 1, r], [c + 1, r - 1], [c + 1, r]]
  : [[c, r - 1], [c, r + 1], [c - 1, r], [c - 1, r + 1], [c + 1, r], [c + 1, r + 1]];
export const parseGrid = rows => rows.map(l => l.trim().split(/\s+/));
export const key = f => f[0] + ',' + f[1];
