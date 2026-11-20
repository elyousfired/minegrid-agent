"""Paper wallet: records every decision as if real money were used, then settles it on real results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .gridmath import GameConfig
from .models import Round
from .strategy import Decision, simulate_outcome

MAX_LOG = 500


@dataclass
class PaperWallet:
    start_native: float = 1.0
    balance_native: float = 1.0
    tokens_gross: float = 0.0
    staked: float = 0.0
    returned: float = 0.0
    tx_costs: float = 0.0
    bets: int = 0
    voided: int = 0
    peak_equity: float = 1.0
    max_drawdown: float = 0.0
    pending: dict = field(default_factory=dict)   # str(round_id) -> bet info
    log: list = field(default_factory=list)

    # -- lifecycle -------------------------------------------------------------
    def place(self, round_id: int, decision: Decision, cfg: GameConfig) -> bool:
        key = str(round_id)
        cost = decision.stake + cfg.tx_cost_native
        if key in self.pending or decision.stake <= 0 or self.balance_native < cost:
            return False
        self.balance_native -= cost
        self.staked += decision.stake
        self.tx_costs += cfg.tx_cost_native
        self.pending[key] = {"stake": decision.stake, "predicted_pool": decision.predicted_pool,
                             "expected_profit": decision.expected_profit}
        return True

    def settle(self, rnd: Round, cfg: GameConfig, token_price_native: float) -> Optional[dict]:
        bet = self.pending.pop(str(rnd.round_id), None)
        if bet is None:
            return None
        out = simulate_outcome(rnd, bet["stake"], cfg)
        self.balance_native += out.native_back
        self.returned += out.native_back
        self.tokens_gross += out.tokens
        self.bets += 1
        token_value = out.tokens * cfg.token_net_factor * token_price_native
        pnl = out.native_back - bet["stake"] - cfg.tx_cost_native + token_value
        entry = {
            "round_id": rnd.round_id,
            "stake": round(bet["stake"], 8),
            "predicted_pool": round(bet["predicted_pool"], 6),
            "actual_pool": round(rnd.total_deployed, 6),
            "native_back": round(out.native_back, 8),
            "tokens": round(out.tokens, 8),
            "pnl_native_eq": round(pnl, 8),
        }
        self.log.append(entry)
        del self.log[:-MAX_LOG]
        self._update_drawdown(token_price_native, cfg)
        return entry

    def void_stale(self, newest_id: int, keep_last: int = 3) -> int:
        """Refund bets on rounds that never showed up in the history (data gaps)."""
        n = 0
        for key in list(self.pending):
            if int(key) < newest_id - keep_last:
                bet = self.pending.pop(key)
                self.balance_native += bet["stake"]
                self.staked -= bet["stake"]
                self.voided += 1
                n += 1
        return n

    # -- reporting -------------------------------------------------------------
    def equity(self, token_price_native: float, cfg: GameConfig) -> float:
        locked = sum(b["stake"] for b in self.pending.values())
        return self.balance_native + locked + self.tokens_gross * cfg.token_net_factor * token_price_native

    def _update_drawdown(self, token_price_native: float, cfg: GameConfig) -> None:
        eq = self.equity(token_price_native, cfg)
        self.peak_equity = max(self.peak_equity, eq)
        if self.peak_equity > 0:
            self.max_drawdown = max(self.max_drawdown, (self.peak_equity - eq) / self.peak_equity)

    def summary(self, token_price_native: float, cfg: GameConfig) -> dict:
        eq = self.equity(token_price_native, cfg)
        pnl = eq - self.start_native
        return {
            "bets": self.bets,
            "pending": len(self.pending),
            "voided": self.voided,
            "staked": self.staked,
            "native_pnl": self.returned - (self.staked - sum(b["stake"] for b in self.pending.values())) - self.tx_costs,
            "tokens_gross": self.tokens_gross,
            "equity_native_eq": eq,
            "pnl_native_eq": pnl,
            "roi_pct": (pnl / self.staked * 100.0) if self.staked > 0 else 0.0,
            "max_drawdown_pct": self.max_drawdown * 100.0,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PaperWallet":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields})
