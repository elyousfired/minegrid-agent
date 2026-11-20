"""
Entry decision. `decide` is a pure function of PAST settled rounds only, so the same
code drives the live agent and the backtest without lookahead.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from typing import Sequence

from .gridmath import (
    GameConfig,
    breakeven_pool,
    expected_profit,
    expected_profit_scenarios,
    optimal_stake,
    optimal_stake_scenarios,
)
from .models import Outcome, Round

PREDICTORS = ("last", "median", "scenario")


@dataclass
class StrategyParams:
    predictor: str = "scenario"   # how to estimate the next round's pool of others
    lookback: int = 10            # past rounds used by "median" / "scenario"
    safety_margin: float = 0.15   # require predicted pool <= (1 - margin) * break-even
    min_edge_pct: float = 2.0     # require expected profit >= this % of the stake


@dataclass
class Decision:
    enter: bool
    stake: float
    predicted_pool: float
    breakeven_pool: float
    expected_profit: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def predict_pool(history: Sequence[Round], params: StrategyParams) -> tuple[float, list[float]]:
    """Return (point estimate, scenario list) for the next round's pool of others."""
    if not history:
        return float("inf"), []
    recent = [r.total_deployed for r in history[-params.lookback:]]
    if params.predictor == "last":
        return recent[-1], [recent[-1]]
    if params.predictor == "median":
        m = statistics.median(recent)
        return m, [m]
    if params.predictor == "scenario":
        return statistics.median(recent), recent
    raise ValueError(f"unknown predictor {params.predictor!r}")


def decide(history: Sequence[Round], cfg: GameConfig, value: float, params: StrategyParams) -> Decision:
    h = cfg.house_edge
    be = breakeven_pool(value, h)
    point, scenarios = predict_pool(history, params)

    if not scenarios:
        return Decision(False, 0.0, point, be, 0.0, "ما كايناش داتا كافية")
    if value <= 0:
        return Decision(False, 0.0, point, be, 0.0, "قيمة الجائزة صفر (ثمن التوكن ناقص)")
    if point > be * (1.0 - params.safety_margin):
        return Decision(False, 0.0, point, be, 0.0,
                        f"الـpool المتوقع {point:.4f} فوق حد الدخول {be * (1 - params.safety_margin):.4f}")

    hi = cfg.max_stake if cfg.max_stake != float("inf") else max(be, cfg.min_stake * 2, 1e-9)
    if params.predictor == "scenario":
        stake = optimal_stake_scenarios(scenarios, value, h, cfg.min_stake, hi, cfg.tx_cost_native)
        ev = expected_profit_scenarios(stake, scenarios, value, h, cfg.tx_cost_native)
    else:
        stake = min(max(optimal_stake(point, value, h), cfg.min_stake), hi)
        ev = expected_profit(stake, point, value, h, cfg.tx_cost_native)

    if stake <= 0 or ev <= 0 or ev < stake * params.min_edge_pct / 100.0:
        return Decision(False, 0.0, point, be, ev, f"الربح المتوقع {ev:.6f} صغير بزاف")
    return Decision(True, stake, point, be, ev,
                    f"الـpool المتوقع {point:.4f} تحت الـbreak-even {be:.4f}")


def simulate_outcome(rnd: Round, stake: float, cfg: GameConfig) -> Outcome:
    """Native coin and tokens we would have received with `stake` spread over all squares."""
    if stake <= 0 or rnd.winning_square is None:
        return Outcome(0.0, 0.0, False)
    n = cfg.squares
    our_win = stake / n
    our_lose = stake - our_win
    tokens_pool = rnd.token_reward + rnd.motherlode_paid

    if cfg.exact_outcomes and rnd.winners_deployed is not None and rnd.payout_total is not None:
        new_w = rnd.winners_deployed + our_win
        payout = rnd.payout_total + (1 - cfg.winner_fee) * our_win + (1 - cfg.loser_fee) * our_lose
        share = our_win / new_w
        return Outcome(share * payout, share * tokens_pool, True)

    # Approximation when per-square data is missing: others spread evenly over squares.
    total = rnd.total_deployed + stake
    share = stake / total if total > 0 else 1.0
    return Outcome(stake * (1 - cfg.house_edge), share * tokens_pool, True)
