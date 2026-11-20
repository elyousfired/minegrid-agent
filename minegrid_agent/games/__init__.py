from .base import GameAdapter, MarketState
from .bidgrid import BidGridAdapter
from .eloscape import EloscapeAdapter
from .solana_grid import GodlAdapter, OreAdapter

# Grid games (ORE family): shared EV engine + paper trading.
GAMES: dict[str, type[GameAdapter]] = {
    "eloscape": EloscapeAdapter,
    "bidgrid": BidGridAdapter,
    "ore": OreAdapter,
    "godl": GodlAdapter,
}


def get_game(name: str) -> GameAdapter:
    try:
        return GAMES[name]()
    except KeyError:
        raise SystemExit(f"Unknown game {name!r}. Available: {', '.join(GAMES)}")
