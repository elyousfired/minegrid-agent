"""
BidGrid (Solana): 5x5 grid, bets in SOL, rewards in SBID.

The public history API has no per-square stakes, so outcomes are approximated
(others assumed spread evenly). The SBID price comes live from DexScreener
(most liquid SBID/SOL pair); BIDGRID_SBID_PRICE_SOL overrides it when set.
"""

from __future__ import annotations

import os

from ..gridmath import GameConfig
from ..http import get_json
from ..models import Round
from ..pricing import dexscreener_price_native
from .base import GameAdapter, MarketState

HISTORY_URL = "https://bidgrid.win/api/history/rounds?limit=30"
SBID_MINT = "9Vyqy9pt9b45mfUAcD32KV9pi3A7qYX9D3za4q6qDKMe"
LAMPORTS = 1e9


def parse_round(item: dict, prev_reserve: float | None = None) -> Round:
    lamports = int(item.get("totalDeployedLamports") or item.get("deployedLamports") or 0)
    reserve = int(item.get("motherlodeReserveRaw") or 0) / LAMPORTS
    hit = bool(item.get("motherlode"))
    return Round(
        round_id=int(item.get("roundId", 0)),
        total_deployed=lamports / LAMPORTS,
        winning_square=item.get("winningSquare"),
        token_reward=float((os.environ.get("BIDGRID_TOKENS_PER_ROUND") or "4")),
        motherlode_paid=(prev_reserve or 0.0) if hit else 0.0,
        motherlode_reserve=reserve,
        miners=int(item.get("totalMiners") or 0),
    )


class BidGridAdapter(GameAdapter):
    config = GameConfig(
        name="bidgrid",
        native_symbol="SOL",
        token_symbol="SBID",
        house_edge_override=0.10,
        tokens_per_round=float((os.environ.get("BIDGRID_TOKENS_PER_ROUND") or "4")),
        motherlode_prob=float((os.environ.get("BIDGRID_MOTHERLODE_PROB") or "0")),
        tx_cost_native=float((os.environ.get("BIDGRID_TX_COST_SOL") or "0.00001")),
        min_stake=float((os.environ.get("BIDGRID_MIN_STAKE") or "0.01")),  # raised by the 2026-11-22 upgrade
        max_stake=float((os.environ.get("BIDGRID_MAX_STAKE") or "0.03")),
        exact_outcomes=False,
    )

    def __init__(self) -> None:
        self._last_reserve: float | None = None

    def fetch_new_rounds(self, last_known_id: int) -> list[Round]:
        items = get_json(HISTORY_URL).get("rounds", [])
        items = sorted(items, key=lambda x: int(x.get("roundId", 0)))
        out: list[Round] = []
        prev_reserve: float | None = None  # reserve of the previous round in this batch
        for item in items:
            if item.get("winningSquare") is None:
                continue
            r = parse_round(item, prev_reserve)
            prev_reserve = r.motherlode_reserve
            self._last_reserve = r.motherlode_reserve
            if r.round_id > last_known_id:
                out.append(r)
        return out

    def fetch_market(self) -> MarketState:
        """SBID price in SOL: BIDGRID_SBID_PRICE_SOL if set (manual override), else live from DexScreener."""
        override = os.environ.get("BIDGRID_SBID_PRICE_SOL")
        if override:
            price, native_usd = float(override), None
        else:
            price, native_usd = dexscreener_price_native(SBID_MINT, "SOL")  # raises -> no signal this loop
        return MarketState(token_price_native=price, native_usd=native_usd,
                           motherlode_reserve=self._last_reserve or 0.0)
