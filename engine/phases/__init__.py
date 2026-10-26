"""Resolution phases. Each module has run(state, parsed_orders, events). PHASES maps the name in rules['phases']."""
from . import movement, recruitment, transfers

PHASES = {
    "transfers": transfers.run,
    "recruitment": recruitment.run,
    "movement": movement.run,
}
