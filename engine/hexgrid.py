"""Hex grid helpers: flat-top hexes, odd columns raised half a field. Fields are (column, row)."""


def neighbours(c, r):
    """The six fields next to (c, r)."""
    if c % 2:
        return [(c, r - 1), (c, r + 1), (c - 1, r - 1), (c - 1, r), (c + 1, r - 1), (c + 1, r)]
    return [(c, r - 1), (c, r + 1), (c - 1, r), (c - 1, r + 1), (c + 1, r), (c + 1, r + 1)]


def tup(field):
    """Turn a [c, r] list into a (c, r) tuple."""
    return (field[0], field[1])


def is_adjacent(a, b):
    """True if the two fields touch."""
    return tup(b) in neighbours(*tup(a))


def parse_grid(grid):
    """Map.json grid rows -> {(c, r): token}."""
    cells = {}
    for r, line in enumerate(grid):
        for c, token in enumerate(line.split()):
            cells[(c, r)] = token
    return cells
