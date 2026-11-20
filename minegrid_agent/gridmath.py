"""
Shared math for ORE-style 5x5 grid mining games (ORE, Eloscape, BidGrid, ...).

Model (all amounts in the game's native coin, e.g. HYPE or SOL):
  D  = stake deployed by everyone else in the round
  s  = our stake, spread evenly over all squares
  V  = net value of the round's token reward (emission + expected jackpot),
       after claim/sell fees, converted to native coin
  h  = house edge on a stake spread over all squares

  E[profit](s) = V * s / (D + s) - h * s

  * Break-even pool: the first unit of stake is +EV only while D < V / h.
  * Optimal stake:   s* = sqrt(V * D / h) - D   (when D < V / h)
  * Max profit:      (sqrt(V) - sqrt(h * D))^2
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class GameConfig:
    name: str
    native_symbol: str
    token_symbol: str
    squares: int = 25
    winner_fee: float = 0.01         # share of the winning square's stake kept by the protocol
    loser_fee: float = 0.109         # share of losing squares' stakes kept by the protocol
    house_edge_override: Optional[float] = None
    claim_fee: float = 0.0           # fee when claiming token rewards
    sell_fee: float = 0.0            # DEX tax + pool fee when selling the token
    tokens_per_round: float = 1.0    # token emission paid to the winning square
    motherlode_prob: float = 0.0     # chance per round that the jackpot hits
    tx_cost_native: float = 0.0      # gas / priority fee per bet
    min_stake: float = 0.0
    max_stake: float = float("inf")
    exact_outcomes: bool = True      # False when history lacks per-square data

    @property
    def house_edge(self) -> float:
        """Expected loss per unit staked evenly over all squares."""
        if self.house_edge_override is not None:
            return self.house_edge_override
        n = self.squares
        return self.winner_fee / n + self.loser_fee * (n - 1) / n

    @property
    def token_net_factor(self) -> float:
        return (1.0 - self.claim_fee) * (1.0 - self.sell_fee)


def ore_fees(admin: float, protocol: float) -> dict:
    """ORE-style fees: `admin` on every square, then `protocol` on what is left of losing squares."""
    return {"winner_fee": admin, "loser_fee": admin + (1.0 - admin) * protocol}


def reward_value(cfg: GameConfig, token_price_native: float, motherlode_reserve: float = 0.0,
                 tokens_per_round: float | None = None) -> float:
    """Net native value V of one round's token rewards (emission + expected jackpot)."""
    per_round = cfg.tokens_per_round if tokens_per_round is None else tokens_per_round
    expected_tokens = per_round + motherlode_reserve * cfg.motherlode_prob
    return expected_tokens * token_price_native * cfg.token_net_factor


def expected_profit(stake: float, others: float, value: float, edge: float, tx_cost: float = 0.0) -> float:
    if stake <= 0:
        return 0.0
    return value * stake / (others + stake) - edge * stake - tx_cost


def expected_profit_scenarios(stake: float, scenarios: Sequence[float], value: float, edge: float,
                              tx_cost: float = 0.0) -> float:
    """Average expected profit when the others' pool is uncertain (one scenario per past round)."""
    if stake <= 0 or not scenarios:
        return 0.0
    share = sum(stake / (d + stake) for d in scenarios) / len(scenarios)
    return value * share - edge * stake - tx_cost


def breakeven_pool(value: float, edge: float) -> float:
    """Largest pool of others for which entering can still be +EV."""
    return value / edge if edge > 0 else float("inf")


def optimal_stake(others: float, value: float, edge: float) -> float:
    """Stake that maximises expected profit for a known pool of others (0 if no +EV stake)."""
    if value <= 0 or edge <= 0:
        return 0.0
    if others <= 0:
        return 0.0  # empty round: any tiny stake wins everything; caller applies min_stake
    s = math.sqrt(value * others / edge) - others
    return max(0.0, s)


def optimal_stake_scenarios(scenarios: Sequence[float], value: float, edge: float,
                            lo: float, hi: float, tx_cost: float = 0.0) -> float:
    """Maximise average expected profit over scenarios on [lo, hi] (the function is concave)."""
    if hi <= lo:
        return lo
    a, b = lo, hi
    phi = (math.sqrt(5) - 1) / 2
    c, d = b - phi * (b - a), a + phi * (b - a)
    f = lambda x: expected_profit_scenarios(x, scenarios, value, edge, tx_cost)
    fc, fd = f(c), f(d)
    for _ in range(80):
        if fc < fd:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = f(d)
        else:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = f(c)
    return (a + b) / 2
