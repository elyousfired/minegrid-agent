"""
ORE-family games on Solana, read directly from on-chain accounts (exact outcomes).

Layouts come from the open-source programs:
  ORE  https://github.com/regolith-labs/ore      (api/src/state/{board,round,treasury}.rs)
  GODL https://github.com/zenx-labs/godl-program (api/src/state/{board,round,treasury,config}.rs)
Every account starts with an 8-byte discriminator.
"""

from __future__ import annotations

import logging
import os
import struct
from dataclasses import dataclass
from typing import Callable, Optional

from ..gridmath import GameConfig, ore_fees
from ..models import Round
from ..pricing import dexscreener_price_native
from ..solana import SolanaRPC, find_program_address, u64
from .base import GameAdapter, MarketState

log = logging.getLogger("minegrid.solana")
LAMPORTS = 1e9
HDR = 8  # account discriminator


def _rng(entropy: bytes) -> Optional[int]:
    if entropy == b"\x00" * 32 or entropy == b"\xff" * 32:
        return None
    r = 0
    for i in range(4):
        r ^= struct.unpack_from("<Q", entropy, i * 8)[0]
    return r


@dataclass(frozen=True)
class Layout:
    round_size: int
    parse_round: Callable[[bytes, float], Optional[Round]]
    treasury_motherlode_offset: int


# --- ORE: Round { id, sol[25], mass[25], miners[25], entropy[32], closes_at, motherlode,
#                  rent_payer, rewards[25], protocol_fee, total_returned, unique_miners, winner }
def parse_ore_round(d: bytes, one_token: float) -> Optional[Round]:
    o = HDR
    sol = struct.unpack_from("<25Q", d, o + 8)
    entropy = d[o + 608:o + 640]
    r = _rng(entropy)
    if r is None:
        return None
    ws = r % 25
    rewards = struct.unpack_from("<25Q", d, o + 688)
    return Round(
        round_id=u64(d, o),
        total_deployed=sum(sol) / LAMPORTS,
        winning_square=ws,
        end_time=u64(d, o + 640),
        winners_deployed=sol[ws] / LAMPORTS,
        payout_total=u64(d, o + 896) / LAMPORTS,
        token_reward=sum(rewards) / one_token,
        motherlode_paid=u64(d, o + 648) / one_token,
        miners=u64(d, o + 904),
    )


# --- GODL: Round { id, deployed[25], slot_hash[32], count[25], expires_at, motherlode, rent_payer,
#                   top_miner, top_miner_reward, total_deployed, total_vaulted, total_winnings }
def parse_godl_round(d: bytes, one_token: float) -> Optional[Round]:
    o = HDR
    deployed = struct.unpack_from("<25Q", d, o + 8)
    r = _rng(d[o + 208:o + 240])
    if r is None:
        return None
    ws = r % 25
    winnings = u64(d, o + 544)
    return Round(
        round_id=u64(d, o),
        total_deployed=u64(d, o + 528) / LAMPORTS,
        winning_square=ws,
        end_time=u64(d, o + 440),
        winners_deployed=deployed[ws] / LAMPORTS,
        payout_total=(deployed[ws] + winnings) / LAMPORTS,  # winners keep their stake + share of losers
        token_reward=u64(d, o + 520) / one_token,
        motherlode_paid=u64(d, o + 448) / one_token,
        miners=sum(struct.unpack_from("<25Q", d, o + 240)),
    )


ORE_LAYOUT = Layout(round_size=HDR + 944, parse_round=parse_ore_round, treasury_motherlode_offset=HDR)
GODL_LAYOUT = Layout(round_size=HDR + 552, parse_round=parse_godl_round, treasury_motherlode_offset=HDR + 8)


class SolanaGridAdapter(GameAdapter):
    program_id: str
    token_mint: str
    token_decimals: int = 11
    layout: Layout
    backfill: int = 300

    def __init__(self) -> None:
        self.rpc = SolanaRPC()
        self.board = find_program_address([b"board"], self.program_id)[0]
        self.treasury = find_program_address([b"treasury"], self.program_id)[0]
        self._live_id: Optional[int] = None

    def round_address(self, round_id: int) -> str:
        return find_program_address([b"round", struct.pack("<Q", round_id)], self.program_id)[0]

    def fetch_new_rounds(self, last_known_id: int) -> list[Round]:
        board = self.rpc.get_accounts([self.board])[0]
        if not board:
            raise RuntimeError(f"{self.config.name}: board account not found")
        self._live_id = u64(board, HDR)
        start = max(last_known_id + 1, self._live_id - self.backfill)
        ids = list(range(start, self._live_id))
        if not ids:
            return []
        one = 10 ** self.token_decimals
        out = []
        for rid, data in zip(ids, self.rpc.get_accounts([self.round_address(i) for i in ids])):
            if data is None:
                continue  # closed or never created
            if len(data) < self.layout.round_size:
                raise RuntimeError(f"{self.config.name}: round account is {len(data)} bytes, expected "
                                   f"{self.layout.round_size}. The program layout changed.")
            r = self.layout.parse_round(data, one)
            if r is not None and r.round_id == rid:
                out.append(r)
        return out

    def market_extras(self) -> dict:
        return {}

    def fetch_market(self) -> MarketState:
        treasury = self.rpc.get_accounts([self.treasury])[0]
        reserve = u64(treasury, self.layout.treasury_motherlode_offset) / 10 ** self.token_decimals if treasury else 0.0
        price, native_usd = dexscreener_price_native(self.token_mint, self.config.native_symbol)
        return MarketState(token_price_native=price, native_usd=native_usd, motherlode_reserve=reserve,
                           live_round_id=self._live_id, **self.market_extras())


def _stake(env: str, default: str) -> float:
    return float(os.environ.get(env) or default)


class OreAdapter(SolanaGridAdapter):
    program_id = "oreV3EG1i9BEgiAJ8b177Z2S2rMarzak4NMv1kULvWv"
    token_mint = "oreoU2P8bN6jkk3jbaiVxYnG1dCXcYxwhwyK9jSybcp"
    layout = ORE_LAYOUT
    config = GameConfig(
        name="ore", native_symbol="SOL", token_symbol="ORE",
        **ore_fees(admin=0.01, protocol=0.10),
        claim_fee=0.10,                # 10% fee on unrefined ORE
        sell_fee=_stake("ORE_SELL_FEE", "0.01"),
        tokens_per_round=1.0,
        motherlode_prob=1.0 / 500.0,
        tx_cost_native=_stake("ORE_TX_COST_SOL", "0.00002"),
        min_stake=_stake("ORE_MIN_STAKE", "0.005"),
        max_stake=_stake("ORE_MAX_STAKE", "0.25"),
    )


class GodlAdapter(SolanaGridAdapter):
    program_id = "mineWsRs2Rmw2jPMkVbgAbDjV1E23yQ8TEodaX3iza4"
    token_mint = "GodL6KZ9uuUoQwELggtVzQkKmU1LfqmDokPibPeDKkhF"
    layout = GODL_LAYOUT
    config = GameConfig(
        name="godl", native_symbol="SOL", token_symbol="GODL",
        winner_fee=0.0,                         # winners keep their whole stake
        loser_fee=1 - (1 - 0.015) * 0.90,       # 0.5% admin + 1% SOL jackpot, then 10% vault
        claim_fee=0.10,
        sell_fee=_stake("GODL_SELL_FEE", "0.01"),
        tokens_per_round=1.0,                   # replaced live by config.godl_per_round
        motherlode_prob=0.9 / 625.0,            # 1/625 chance, pays 90% of the pot
        tx_cost_native=_stake("GODL_TX_COST_SOL", "0.00002"),
        min_stake=_stake("GODL_MIN_STAKE", "0.005"),
        max_stake=_stake("GODL_MAX_STAKE", "0.1"),
    )

    def __init__(self) -> None:
        super().__init__()
        self.config_pda = find_program_address([b"config"], self.program_id)[0]

    def market_extras(self) -> dict:
        cfg = self.rpc.get_accounts([self.config_pda])[0]
        if not cfg:
            return {}
        return {"tokens_per_round": u64(cfg, HDR + 32) / 10 ** self.token_decimals}
