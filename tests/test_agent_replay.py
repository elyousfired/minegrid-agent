"""End-to-end: the live loop replays real Eloscape rounds through a fake API (no network)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from minegrid_agent import agent as agent_mod
from minegrid_agent.games.base import MarketState
from minegrid_agent.games.eloscape import EloscapeAdapter
from minegrid_agent.storage import Store
from minegrid_agent.strategy import StrategyParams

REPO_DATA = Path(__file__).resolve().parent.parent / "data"


class ReplayEloscape(EloscapeAdapter):
    def __init__(self, rounds, step=3):
        self.all, self.step, self.cursor = rounds, step, 0

    def fetch_new_rounds(self, last_known_id):
        self.cursor = min(len(self.all), self.cursor + self.step)
        return [r for r in self.all[: self.cursor] if r.round_id > last_known_id]

    def fetch_market(self):
        return MarketState(token_price_native=0.06, motherlode_reserve=0.0)


class TestAgentReplay(unittest.TestCase):
    def test_replay_places_and_settles_paper_bets(self):
        rounds = Store(REPO_DATA, "eloscape").load_rounds()[-400:]
        self.assertGreater(len(rounds), 100)
        fake = ReplayEloscape(rounds)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(agent_mod, "get_game", return_value=fake), \
                mock.patch.object(agent_mod.time, "sleep", lambda s: None):
            clock = iter(range(0, 10**7, 1))
            with mock.patch.object(agent_mod.time, "time", lambda: next(clock)):
                agent_mod.run_agent("eloscape", Path(tmp), max_minutes=60, poll_seconds=0,
                                    params=StrategyParams(), start_native=1.0)
            wallet, state = Store(Path(tmp), "eloscape").load_state(1.0)
            self.assertGreater(wallet.bets, 10)
            self.assertLessEqual(len(wallet.pending), 1)
            self.assertEqual(state["last_round"], rounds[-1].round_id)


if __name__ == "__main__":
    unittest.main()
