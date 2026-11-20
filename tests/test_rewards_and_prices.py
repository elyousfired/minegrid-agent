import os
import unittest
from unittest import mock

from minegrid_agent.games import bidgrid
from minegrid_agent.games.eloscape import EloscapeAdapter, from_legacy_cache, parse_epoch
from minegrid_agent.strategy import simulate_outcome

WEI = 10 ** 18


def epoch(elo_total, motherlode):
    return {"roundId": "9589", "status": "settled", "winningBlock": "14", "endTime": "1795209948",
            "deployedTotal": str(int(0.3169508 * WEI)), "winnersDeployed": str(int(0.012638 * WEI)),
            "ethWinnings": str(int(0.2836543 * WEI)),
            "eloRewardTotal": str(int(elo_total * WEI)), "motherlodeAmount": str(int(motherlode * WEI))}


class TestEloscapeJackpot(unittest.TestCase):
    def test_jackpot_not_double_counted(self):
        # Real round 9589: eloRewardTotal 50.6 already includes the 49.6 ELO motherlode.
        r = parse_epoch(epoch(50.6, 49.6))
        self.assertAlmostEqual(r.token_reward, 1.0)
        self.assertAlmostEqual(r.motherlode_paid, 49.6)
        out = simulate_outcome(r, 0.05, EloscapeAdapter.config)
        share = 0.002 / (0.012638 + 0.002)
        self.assertAlmostEqual(out.tokens, share * 50.6, places=6)

    def test_normal_round_unchanged(self):
        r = parse_epoch(epoch(1.0, 0.0))
        self.assertAlmostEqual(r.token_reward, 1.0)
        self.assertEqual(r.motherlode_paid, 0.0)

    def test_legacy_cache_same_rule(self):
        r = from_legacy_cache({"round_id": 378, "deployed_total_hype": 0.3, "winning_block": 3,
                               "elo_reward_total": 76.4, "motherlode_amount": 75.4})
        self.assertAlmostEqual(r.token_reward, 1.0)
        self.assertAlmostEqual(r.motherlode_paid, 75.4)


class TestEloscapeMigration(unittest.TestCase):
    def test_migration_fixes_saved_jackpot_once(self):
        from minegrid_agent import migrations
        from minegrid_agent.paper import PaperWallet
        from minegrid_agent.strategy import Decision
        cfg = EloscapeAdapter.config
        old_round = parse_epoch(epoch(50.6, 49.6))
        old_round.token_reward = 50.6  # as saved by the old parser
        w = PaperWallet()
        w.place(9589, Decision(True, 0.05, 0.3, 0.4, 0.001, ""), cfg)
        w.settle(old_round, cfg, 0.05)
        rounds, state = [old_round], {"token_price_native": 0.05}
        new, done = migrations.apply("eloscape", rounds, w, state, cfg)
        self.assertTrue(done)
        self.assertAlmostEqual(rounds[0].token_reward, 1.0)
        self.assertAlmostEqual(new.tokens_gross, w.tokens_gross * 50.6 / 100.2, places=9)
        self.assertAlmostEqual(new.balance_native, w.balance_native, places=12)
        again, done2 = migrations.apply("eloscape", rounds, new, state, cfg)
        self.assertFalse(done2)
        self.assertIs(again, new)


class TestBidGridPrice(unittest.TestCase):
    def test_override_wins(self):
        with mock.patch.dict(os.environ, {"BIDGRID_SBID_PRICE_SOL": "0.0009"}), \
             mock.patch.object(bidgrid, "dexscreener_price_native") as dex:
            m = bidgrid.BidGridAdapter().fetch_market()
        self.assertAlmostEqual(m.token_price_native, 0.0009)
        dex.assert_not_called()

    def test_live_price_when_unset(self):
        with mock.patch.dict(os.environ, {"BIDGRID_SBID_PRICE_SOL": ""}), \
             mock.patch.object(bidgrid, "dexscreener_price_native", return_value=(0.000562, 67.0)) as dex:
            m = bidgrid.BidGridAdapter().fetch_market()
        self.assertAlmostEqual(m.token_price_native, 0.000562)
        dex.assert_called_once_with(bidgrid.SBID_MINT, "SOL")

    def test_no_price_means_no_market(self):
        with mock.patch.dict(os.environ, {"BIDGRID_SBID_PRICE_SOL": ""}), \
             mock.patch.object(bidgrid, "dexscreener_price_native", side_effect=RuntimeError("down")):
            with self.assertRaises(RuntimeError):
                bidgrid.BidGridAdapter().fetch_market()


if __name__ == "__main__":
    unittest.main()
