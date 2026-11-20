import math
import unittest

from minegrid_agent.backtest import run_backtest
from minegrid_agent.gridmath import (
    GameConfig,
    breakeven_pool,
    expected_profit,
    optimal_stake,
    optimal_stake_scenarios,
    reward_value,
)
from minegrid_agent.models import Round
from minegrid_agent.paper import PaperWallet
from minegrid_agent.strategy import Decision, StrategyParams, decide, simulate_outcome

ELO = GameConfig(name="t", native_symbol="H", token_symbol="T", admin_fee=0.01, loser_fee=0.10,
                 claim_fee=0.10, sell_fee=0.04, tokens_per_round=1.0, min_stake=0.001, max_stake=1.0)


def rnd(i, pool, exact=True):
    w = pool / 25
    return Round(round_id=i, total_deployed=pool, winning_square=i % 25,
                 winners_deployed=w if exact else None,
                 payout_total=(0.99 * w + 0.891 * (pool - w)) if exact else None,
                 token_reward=1.0)


class TestMath(unittest.TestCase):
    def test_house_edge_matches_eloscape(self):
        self.assertAlmostEqual(ELO.house_edge, 0.10504, places=10)

    def test_breakeven_and_optimum(self):
        v, h = 0.03, 0.10
        self.assertAlmostEqual(breakeven_pool(v, h), 0.3)
        d = 0.05
        s = optimal_stake(d, v, h)
        self.assertAlmostEqual(s, math.sqrt(v * d / h) - d)
        # optimum beats neighbours
        self.assertGreater(expected_profit(s, d, v, h), expected_profit(s * 1.2, d, v, h))
        self.assertGreater(expected_profit(s, d, v, h), expected_profit(s * 0.8, d, v, h))
        self.assertAlmostEqual(expected_profit(s, d, v, h), (math.sqrt(v) - math.sqrt(h * d)) ** 2)
        self.assertEqual(optimal_stake(0.5, v, h), 0.0)  # above break-even

    def test_scenario_optimum_equals_closed_form_for_single_scenario(self):
        v, h, d = 0.03, 0.10, 0.05
        s = optimal_stake_scenarios([d], v, h, 0.0, 1.0)
        self.assertAlmostEqual(s, optimal_stake(d, v, h), places=5)

    def test_reward_value_applies_fees_and_jackpot(self):
        cfg = GameConfig(name="x", native_symbol="H", token_symbol="T", claim_fee=0.1, sell_fee=0.04,
                         tokens_per_round=1.0, motherlode_prob=1 / 500)
        self.assertAlmostEqual(reward_value(cfg, 2.0, motherlode_reserve=100), 1.2 * 2.0 * 0.9 * 0.96)


class TestStrategy(unittest.TestCase):
    def test_waits_when_pools_are_big(self):
        hist = [rnd(i, 5.0) for i in range(20)]
        self.assertFalse(decide(hist, ELO, value=0.03, params=StrategyParams()).enter)

    def test_enters_when_pools_are_small(self):
        hist = [rnd(i, 0.05) for i in range(20)]
        d = decide(hist, ELO, value=0.03, params=StrategyParams())
        self.assertTrue(d.enter)
        self.assertGreater(d.expected_profit, 0)

    def test_decision_is_causal(self):
        """Changing a FUTURE round must not change the decision for the current one."""
        hist = [rnd(i, 0.05 + 0.01 * (i % 3)) for i in range(30)]
        a = decide(hist[:25], ELO, 0.03, StrategyParams())
        hist[27] = rnd(27, 999.0)
        b = decide(hist[:25], ELO, 0.03, StrategyParams())
        self.assertEqual(a, b)

    def test_exact_and_approx_outcomes_agree_for_even_pools(self):
        cfg_approx = GameConfig(**{**ELO.__dict__, "exact_outcomes": False})
        e = simulate_outcome(rnd(1, 0.5), 0.01, ELO)
        a = simulate_outcome(rnd(1, 0.5, exact=False), 0.01, cfg_approx)
        self.assertAlmostEqual(e.native_back, a.native_back, places=10)
        self.assertAlmostEqual(e.tokens, a.tokens, places=10)


class TestPaperAndBacktest(unittest.TestCase):
    def test_paper_wallet_round_trip(self):
        w = PaperWallet(start_native=1.0, balance_native=1.0, peak_equity=1.0)
        dec = Decision(True, 0.01, 0.05, 0.3, 0.001, "")
        self.assertTrue(w.place(7, dec, ELO))
        self.assertFalse(w.place(7, dec, ELO))  # no double bet
        self.assertAlmostEqual(w.balance_native, 0.99)
        entry = w.settle(rnd(7, 0.05), ELO, token_price_native=0.03)
        self.assertIsNotNone(entry)
        self.assertEqual(w.bets, 1)
        self.assertEqual(w.pending, {})

    def test_void_stale_refunds(self):
        w = PaperWallet()
        w.place(3, Decision(True, 0.01, 0, 0, 0, ""), ELO)
        self.assertEqual(w.void_stale(newest_id=10), 1)
        self.assertAlmostEqual(w.balance_native, 1.0)

    def test_backtest_profitable_only_when_reward_is_worth_it(self):
        hist = [rnd(i, 0.05) for i in range(200)]
        rich = run_backtest(hist, ELO, token_price_native=0.05, params=StrategyParams())
        poor = run_backtest(hist, ELO, token_price_native=0.0001, params=StrategyParams())
        self.assertGreater(rich.net_pnl, 0)
        self.assertEqual(poor.entered, 0)


if __name__ == "__main__":
    unittest.main()
