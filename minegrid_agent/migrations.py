"""
One-time, idempotent fixes of saved data, applied when an agent starts.
Each fix is recorded in agent_state["migrations"] so it never runs twice.
"""

from __future__ import annotations

import logging

from .gridmath import GameConfig
from .models import Round
from .paper import PaperWallet
from .strategy import Decision

log = logging.getLogger("minegrid.migrations")

ELO_JACKPOT_FIX = "eloscape_jackpot_double_count_v1"


def fix_eloscape_rounds(rounds: list[Round]) -> int:
    """Old parser stored eloRewardTotal (emission + motherlode) as token_reward. Remove the motherlode part."""
    n = 0
    for r in rounds:
        if r.motherlode_paid > 0 and r.token_reward >= r.motherlode_paid + 0.5:
            r.token_reward -= r.motherlode_paid
            n += 1
    return n


def replay_wallet(old: PaperWallet, rounds: list[Round], cfg: GameConfig, price: float) -> PaperWallet:
    """Rebuild a wallet by re-settling every logged bet on the (fixed) rounds, then re-placing pending bets."""
    by_id = {r.round_id: r for r in rounds}
    w = PaperWallet(start_native=old.start_native, balance_native=old.start_native,
                    peak_equity=old.start_native)
    for e in old.log:
        r = by_id.get(e["round_id"])
        if r is None:
            raise RuntimeError(f"round {e['round_id']} missing from history; cannot replay")
        w.place(r.round_id, Decision(True, e["stake"], e["predicted_pool"], 0.0, 0.0, ""), cfg)
        w.settle(r, cfg, price)
    for key, bet in old.pending.items():
        w.place(int(key), Decision(True, bet["stake"], bet["predicted_pool"], 0.0,
                                   bet.get("expected_profit", 0.0), ""), cfg)
    w.voided = old.voided
    return w


def apply(game_name: str, rounds: list[Round], wallet: PaperWallet, agent_state: dict,
          cfg: GameConfig) -> tuple[PaperWallet, bool]:
    done = agent_state.setdefault("migrations", [])
    if game_name != "eloscape" or ELO_JACKPOT_FIX in done:
        return wallet, False
    fixed = fix_eloscape_rounds(rounds)
    price = agent_state.get("token_price_native", 0.0)
    new_wallet = replay_wallet(wallet, rounds, cfg, price) if wallet.log else wallet
    log.info("Migration %s: fixed %d jackpot rounds; tokens %.4f -> %.4f, balance %.6f -> %.6f",
             ELO_JACKPOT_FIX, fixed, wallet.tokens_gross, new_wallet.tokens_gross,
             wallet.balance_native, new_wallet.balance_native)
    done.append(ELO_JACKPOT_FIX)
    return new_wallet, True
