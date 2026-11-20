"""
Walk-forward backtest. For round i the strategy only sees rounds[:i] (strictly causal),
our own stake is added to the pool, and house edge, claim/sell fees and tx costs are paid.

Limitation: the token price is held constant (historical ELO/SBID prices are not stored),
so the report also gives the token price at which the run breaks even.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .gridmath import GameConfig, reward_value
from .models import Round
from .strategy import Decision, StrategyParams, decide, simulate_outcome


@dataclass
class BacktestResult:
    label: str
    rounds: int
    entered: int
    staked: float
    native_pnl: float
    tokens_net: float
    token_value: float
    net_pnl: float
    roi_pct: float
    max_drawdown: float
    breakeven_token_price: float

    def row(self, native: str) -> str:
        be = f"{self.breakeven_token_price:.6f}" if self.breakeven_token_price != float("inf") else "-"
        return (f"{self.label:<28} rounds={self.rounds:>5} entered={self.entered:>5} "
                f"staked={self.staked:>9.4f} native={self.native_pnl:>+9.4f} tokens={self.tokens_net:>8.3f} "
                f"net={self.net_pnl:>+9.4f} {native} ROI={self.roi_pct:>+7.2f}% maxDD={self.max_drawdown:>8.4f} "
                f"BE_price={be}")


def run_backtest(rounds: Sequence[Round], cfg: GameConfig, token_price_native: float,
                 params: StrategyParams, warmup: int = 20, label: str | None = None,
                 always_on_stake: float | None = None) -> BacktestResult:
    """Simulate the strategy (or a fixed always-on stake if `always_on_stake` is set)."""
    value = reward_value(cfg, token_price_native)
    entered = 0
    staked = native_pnl = tokens = 0.0
    equity = peak = max_dd = 0.0

    for i in range(warmup, len(rounds)):
        if always_on_stake is not None:
            stake = always_on_stake
        else:
            dec: Decision = decide(rounds[:i], cfg, value, params)
            if not dec.enter:
                continue
            stake = dec.stake
        out = simulate_outcome(rounds[i], stake, cfg)
        entered += 1
        staked += stake
        native = out.native_back - stake - cfg.tx_cost_native
        native_pnl += native
        tokens += out.tokens * cfg.token_net_factor
        equity += native + out.tokens * cfg.token_net_factor * token_price_native
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    token_value = tokens * token_price_native
    net = native_pnl + token_value
    be_price = (-native_pnl / tokens) if tokens > 0 else float("inf")
    return BacktestResult(
        label=label or f"{params.predictor} (lb={params.lookback}, m={params.safety_margin})",
        rounds=max(0, len(rounds) - warmup), entered=entered, staked=staked,
        native_pnl=native_pnl, tokens_net=tokens, token_value=token_value, net_pnl=net,
        roi_pct=(net / staked * 100.0) if staked > 0 else 0.0,
        max_drawdown=max_dd, breakeven_token_price=be_price,
    )


def compare(rounds: Sequence[Round], cfg: GameConfig, token_price_native: float,
            warmup: int = 20) -> list[BacktestResult]:
    """Baseline vs every predictor, on the full history and on each half (stability check)."""
    results: list[BacktestResult] = []
    halves = {"all": rounds, "1st half": rounds[: len(rounds) // 2], "2nd half": rounds[len(rounds) // 2:]}
    for name, part in halves.items():
        results.append(run_backtest(part, cfg, token_price_native, StrategyParams(), warmup,
                                    label=f"[{name}] always-on min", always_on_stake=cfg.min_stake))
        for p in ("last", "median", "scenario"):
            results.append(run_backtest(part, cfg, token_price_native, StrategyParams(predictor=p), warmup,
                                        label=f"[{name}] {p}"))
    return results
