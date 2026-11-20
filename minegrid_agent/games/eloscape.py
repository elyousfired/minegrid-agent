"""Eloscape (HyperEVM): 5x5 grid, bets in HYPE, rewards in ELO."""

from __future__ import annotations

import os

from ..gridmath import GameConfig, ore_fees
from ..http import get_json
from ..models import Round
from .base import GameAdapter, MarketState

BASE_URL = "https://eloscape.com"
WEI = 1e18


def parse_epoch(item: dict) -> Round:
    return Round(
        round_id=int(item["roundId"]),
        total_deployed=int(item.get("deployedTotal") or 0) / WEI,
        winning_square=int(item["winningBlock"]) if item.get("winningBlock") is not None else None,
        end_time=int(item.get("endTime") or 0),
        winners_deployed=int(item.get("winnersDeployed") or 0) / WEI,
        payout_total=int(item.get("ethWinnings") or item.get("totalWinnings") or 0) / WEI,
        token_reward=int(item.get("eloRewardTotal") or 0) / WEI,
        motherlode_paid=int(item.get("motherlodeAmount") or 0) / WEI,
    )


def from_legacy_cache(row: dict) -> Round:
    """Convert a row of eloscape-quant-dashboard/data/epochs_cache.json."""
    return Round(
        round_id=int(row["round_id"]),
        total_deployed=float(row["deployed_total_hype"]),
        winning_square=row.get("winning_block"),
        end_time=int(row.get("end_time") or 0),
        winners_deployed=float(row.get("winners_deployed_hype") or 0.0),
        payout_total=float(row.get("eth_winnings_hype") or 0.0),
        token_reward=float(row.get("elo_reward_total") or 0.0),
        motherlode_paid=float(row.get("motherlode_amount") or 0.0),
    )


class EloscapeAdapter(GameAdapter):
    config = GameConfig(
        name="eloscape",
        native_symbol="HYPE",
        token_symbol="ELO",
        **ore_fees(admin=0.01, protocol=0.10),
        claim_fee=0.10,
        sell_fee=0.04,
        tokens_per_round=1.0,
        motherlode_prob=1.0 / 500.0,
        tx_cost_native=float((os.environ.get("ELOSCAPE_TX_COST_HYPE") or "0.00002")),
        min_stake=float((os.environ.get("ELOSCAPE_MIN_STAKE") or "0.0025")),
        max_stake=float((os.environ.get("ELOSCAPE_MAX_STAKE") or "0.05")),
    )

    def fetch_new_rounds(self, last_known_id: int) -> list[Round]:
        found: dict[int, Round] = {}
        for page in range(50):
            data = get_json(f"{BASE_URL}/api/lab/game/overview/epochs?page={page}&limit=12&sort=roundId&order=desc",
                            timeout=20).get("epochs", {})
            items = data.get("items", [])
            if not items:
                break
            stop = False
            for item in items:
                if item.get("status") != "settled" or item.get("winningBlock") is None:
                    continue
                r = parse_epoch(item)
                if r.round_id <= last_known_id:
                    stop = True
                    continue
                found[r.round_id] = r
            if stop or last_known_id == 0:
                break
        return [found[k] for k in sorted(found)]

    def fetch_market(self) -> MarketState:
        prices = get_json(f"{BASE_URL}/api/prices")
        hype_usd = float(prices.get("hypeUsd") or prices.get("usd") or 0.0)
        elo_usd = float(prices.get("eloUsd") or 0.0)
        reserve = 0.0
        live_id = None
        try:
            header = get_json(f"{BASE_URL}/api/lab/game/overview/header").get("header", {})
            reserve = int(header.get("totals", {}).get("motherlode") or 0) / WEI
            live_id = int(header.get("currentRoundId") or 0) or None
        except RuntimeError:
            pass
        return MarketState(
            token_price_native=(elo_usd / hype_usd) if hype_usd > 0 else 0.0,
            native_usd=hype_usd,
            motherlode_reserve=reserve,
            live_round_id=live_id,
        )
