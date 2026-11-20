from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Round:
    """A settled round, normalised across games. Amounts in native coin / whole tokens."""
    round_id: int
    total_deployed: float
    winning_square: Optional[int]
    end_time: int = 0
    winners_deployed: Optional[float] = None   # stake on the winning square (exact games only)
    payout_total: Optional[float] = None       # native paid back to winners (exact games only)
    token_reward: float = 0.0                  # emission paid this round
    motherlode_paid: float = 0.0               # jackpot paid this round
    motherlode_reserve: Optional[float] = None
    miners: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Round":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields})


@dataclass
class Outcome:
    native_back: float
    tokens: float
    won: bool
