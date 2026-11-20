from .base import GameAdapter, MarketState
from .bidgrid import BidGridAdapter
from .eloscape import EloscapeAdapter

GAMES: dict[str, type[GameAdapter]] = {
    "eloscape": EloscapeAdapter,
    "bidgrid": BidGridAdapter,
}


def get_game(name: str) -> GameAdapter:
    try:
        return GAMES[name]()
    except KeyError:
        raise SystemExit(f"Unknown game {name!r}. Available: {', '.join(GAMES)}")
