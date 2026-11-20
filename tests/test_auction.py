import unittest

from minegrid_agent.auction.glazecorp import parse_fund
from minegrid_agent.auction.model import (Slot, breakeven_minute, evaluate, profit_at_minute, realized_usdg,
                                          settle_takeover, token_value)


def slot(**kw):
    base = dict(coin="0xabc", symbol="TST", epoch=5, init_price=2.0, auction_started_at=0, tps=0.01,
                last_price=1.0, p_token=1.0, r_usdg=1000.0, swap_fee=0.01)
    base.update(kw)
    return Slot(**base)


class TestAuctionModel(unittest.TestCase):
    def test_cpmm_slippage(self):
        self.assertAlmostEqual(realized_usdg(10, 1000, 0.0), 1000 * 10 / 1010)
        self.assertLess(realized_usdg(100, 100, 0.01), 100)

    def test_dutch_price_decays_linearly(self):
        s = slot()
        self.assertAlmostEqual(s.price_now(0), 2.0)
        self.assertAlmostEqual(s.price_now(1800), 1.0)
        self.assertEqual(s.price_now(4000), 0.0)

    def test_breakeven_minute_is_consistent(self):
        s = slot(tps=0.0005)
        be = breakeven_minute(s, 1.5)
        self.assertGreater(be, 0)
        self.assertGreaterEqual(profit_at_minute(s, 1.5, be - 0.01), 0)
        if be < 60:
            self.assertLess(profit_at_minute(s, 1.5, be + 0.5), 0)

    def test_cheap_slot_with_big_mining_is_safe(self):
        s = slot(init_price=0.05, tps=0.01)
        self.assertEqual(evaluate(s, now=1800).kind, "safe")
        self.assertEqual(evaluate(slot(r_usdg=0.1), now=0).kind, "illiquid")

    def test_settle_takeover_uses_real_takeover(self):
        s0 = slot()
        entry = {"epoch": 5, "entered_at": 100.0, "p_in": 1.0, "slot": s0.__dict__}
        after = slot(epoch=6, auction_started_at=700, last_price=1.5)
        pnl = settle_takeover(entry, after)
        self.assertAlmostEqual(pnl, 0.8 * 1.5 + token_value(s0, 600) - 1.0)

    def test_parse_subgraph_fund(self):
        f = {"coin": "0xABC", "symbol": "WSM", "swapFee": "10000",
             "pool": {"quoteIsUsdg": True, "reserveBaseRaw": str(500 * 10**18), "reserveQuoteRaw": str(250 * 10**6)},
             "miningSlots": [{"epoch": "3", "initialPriceRaw": str(4 * 10**6), "auctionStartedAt": "1000",
                              "tpsRaw": str(2 * 10**16), "lastPriceRaw": str(2 * 10**6)}]}
        s = parse_fund(f)
        self.assertEqual((s.coin, s.epoch), ("0xabc", 3))
        self.assertAlmostEqual(s.p_token, 0.5)
        self.assertAlmostEqual(s.tps, 0.02)
        self.assertAlmostEqual(s.init_price, 4.0)


if __name__ == "__main__":
    unittest.main()
