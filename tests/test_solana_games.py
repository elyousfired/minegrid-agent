"""
ORE / GODL plugins: build account bytes exactly like the Rust structs, parse them, and check
that our simulated payout equals the programs' own reset arithmetic with our stake added.
"""
import random
import struct
import unittest

from minegrid_agent.games.solana_grid import GodlAdapter, OreAdapter, parse_godl_round, parse_ore_round
from minegrid_agent.solana import b58decode, b58encode, find_program_address
from minegrid_agent.strategy import simulate_outcome

ONE = 10**11
LAMPORTS = 10**9


def entropy_for(square: int) -> bytes:
    # rng = xor of 4 u64 -> make first word = square, others 0 (non-zero entropy)
    return struct.pack("<4Q", 25 * 7 + square, 0, 0, 0)


def ore_payout(sol: list[int], ws: int) -> int:
    """ore/api/src/state/round.rs::calculate_fees + reset.rs total_returned."""
    admin = protocol = 0
    for i, d in enumerate(sol):
        if d > 0:
            a = max(d // 100, 1)
            admin += a
            if i != ws:
                protocol += max((d - a) // 10, 1)
    return sum(sol) - admin - protocol


def godl_payout(dep: list[int], ws: int) -> int:
    """godl reset_permissionless.rs: winners keep stake + 90% of losers after 1.5% fees."""
    losers = sum(d for i, d in enumerate(dep) if i != ws)
    winnings = losers - losers * 150 // 10_000
    return dep[ws] + winnings - winnings // 10


def ore_account(rid, sol, ws, rewards_total, motherlode=0):
    body = struct.pack("<Q", rid) + struct.pack("<25Q", *sol) + bytes(200) + bytes(200)
    body += entropy_for(ws) + struct.pack("<QQ", 1_700_000_000, motherlode) + bytes(32)
    rewards = [rewards_total] + [0] * 24
    body += struct.pack("<25Q", *rewards) + struct.pack("<QQQ", 0, ore_payout(sol, ws), 9) + bytes(32)
    assert len(body) == 944
    return bytes(8) + body


def godl_account(rid, dep, ws, reward):
    body = struct.pack("<Q", rid) + struct.pack("<25Q", *dep) + entropy_for(ws) + struct.pack("<25Q", *[1] * 25)
    body += struct.pack("<QQ", 1_700_000_000, 0) + bytes(64)
    losers = sum(d for i, d in enumerate(dep) if i != ws)
    winnings = losers - losers * 150 // 10_000
    body += struct.pack("<QQQQ", reward, sum(dep), winnings // 10, winnings - winnings // 10)
    assert len(body) == 552
    return bytes(8) + body


class TestSolanaHelpers(unittest.TestCase):
    def test_pda_matches_ore_published_addresses(self):
        pid = OreAdapter.program_id
        self.assertEqual(find_program_address([b"board"], pid)[0], "BrcSxdp1nXFzou1YyDnQJcPNBNHgoypZmTsyKBSLLXzi")
        self.assertEqual(find_program_address([b"treasury"], pid)[0], "45db2FSR4mcXdSVVZbKbwojU6uYDpMyhpEi7cC8nHaWG")

    def test_base58_roundtrip(self):
        for s in (OreAdapter.program_id, GodlAdapter.token_mint, "11111111111111111111111111111111"):
            self.assertEqual(b58encode(b58decode(s)), s)


class TestParsers(unittest.TestCase):
    def setUp(self):
        rnd = random.Random(7)
        self.sol = [rnd.randrange(0, 40_000_000) for _ in range(25)]

    def test_ore_parse_and_exact_payout(self):
        ws = 13
        r = parse_ore_round(ore_account(42, self.sol, ws, ONE, motherlode=3 * ONE), ONE)
        self.assertEqual((r.round_id, r.winning_square), (42, ws))
        self.assertAlmostEqual(r.total_deployed, sum(self.sol) / LAMPORTS)
        self.assertAlmostEqual(r.token_reward, 1.0)
        self.assertAlmostEqual(r.motherlode_paid, 3.0)

        stake = 25 * 400_000  # 0.01 SOL over 25 squares
        with_us = [d + stake // 25 for d in self.sol]
        expected = (stake // 25) / with_us[ws] * ore_payout(with_us, ws) / LAMPORTS
        got = simulate_outcome(r, stake / LAMPORTS, OreAdapter.config).native_back
        self.assertAlmostEqual(got, expected, delta=2e-8)

    def test_godl_parse_and_exact_payout(self):
        ws = 4
        r = parse_godl_round(godl_account(7, self.sol, ws, 20 * ONE), ONE)
        self.assertEqual((r.round_id, r.winning_square), (7, ws))
        self.assertAlmostEqual(r.token_reward, 20.0)
        stake = 25 * 400_000
        with_us = [d + stake // 25 for d in self.sol]
        expected = (stake // 25) / with_us[ws] * godl_payout(with_us, ws) / LAMPORTS
        got = simulate_outcome(r, stake / LAMPORTS, GodlAdapter.config).native_back
        self.assertAlmostEqual(got, expected, delta=2e-8)

    def test_unsettled_round_is_skipped(self):
        data = bytearray(ore_account(1, self.sol, 0, ONE))
        data[8 + 608:8 + 640] = bytes(32)  # no entropy yet
        self.assertIsNone(parse_ore_round(bytes(data), ONE))


class FakeRPC:
    def __init__(self, accounts):
        self.accounts = accounts

    def get_accounts(self, addrs):
        return [self.accounts.get(a) for a in addrs]


class TestAdapterSync(unittest.TestCase):
    def test_fetch_new_rounds_reads_board_then_rounds(self):
        ad = OreAdapter()
        sol = [1_000_000] * 25
        accounts = {ad.board: bytes(8) + struct.pack("<QQQQ", 105, 0, 0, 0)}
        for rid in range(100, 105):
            accounts[ad.round_address(rid)] = ore_account(rid, sol, rid % 25, ONE)
        ad.rpc = FakeRPC(accounts)
        got = ad.fetch_new_rounds(last_known_id=101)
        self.assertEqual([r.round_id for r in got], [102, 103, 104])


if __name__ == "__main__":
    unittest.main()


class TestOreAgentLoop(unittest.TestCase):
    def test_live_loop_on_fake_chain(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from minegrid_agent import agent as agent_mod
        from minegrid_agent.games import solana_grid
        from minegrid_agent.storage import Store
        from minegrid_agent.strategy import StrategyParams

        ad = OreAdapter()
        rnd = random.Random(3)
        accounts = {ad.treasury: bytes(8) + struct.pack("<Q", 50 * ONE)}
        for rid in range(1, 400):
            sol = [rnd.randrange(0, 3_000_000) for _ in range(25)]  # tiny pools -> should enter
            accounts[ad.round_address(rid)] = ore_account(rid, sol, rnd.randrange(25), ONE)
        live = {"id": 50}

        class Chain(FakeRPC):
            def get_accounts(self, addrs):
                live["id"] = min(live["id"] + 2, 399)
                accounts[ad.board] = bytes(8) + struct.pack("<QQQQ", live["id"], 0, 0, 0)
                return super().get_accounts(addrs)

        ad.rpc = Chain(accounts)
        clock = iter(range(10**7))
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(agent_mod, "get_game", return_value=ad), \
                mock.patch.object(solana_grid, "dexscreener_price_native", return_value=(0.5, 150.0)), \
                mock.patch.object(agent_mod.time, "sleep", lambda s: None), \
                mock.patch.object(agent_mod.time, "time", lambda: next(clock)):
            agent_mod.run_agent("ore", Path(tmp), max_minutes=30, poll_seconds=0,
                                params=StrategyParams(), start_native=1.0)
            wallet, state = Store(Path(tmp), "ore").load_state(1.0)
        self.assertGreater(wallet.bets, 20)
        self.assertEqual(state["last_signal"], "ENTER")
