from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..gridmath import GameConfig
from ..models import Round


@dataclass
class MarketState:
    token_price_native: float          # price of one reward token in native coin
    native_usd: Optional[float] = None
    motherlode_reserve: float = 0.0    # current jackpot size in tokens
    live_round_id: Optional[int] = None


class GameAdapter:
    """One plugin per game. Subclasses only talk to the game's API; all math is shared."""

    config: GameConfig

    def fetch_new_rounds(self, last_known_id: int) -> list[Round]:
        """Settled rounds with round_id > last_known_id, ascending."""
        raise NotImplementedError

    def fetch_market(self) -> MarketState:
        raise NotImplementedError
