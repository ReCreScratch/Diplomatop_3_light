"""Resolution phases. Each module has run(state, parsed_orders, events). PHASES maps the name in rules['phases']."""
from . import gold, movement, recruitment

PHASES = {
    "recruitment": recruitment.run,
    "gold": gold.run,
    "movement": movement.run,
}
