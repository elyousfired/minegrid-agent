"""GitSync.push_folder: concurrent jobs on shallow clones never lose state or get stuck."""
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from minegrid_agent.gitsync import GitSync


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("git"), "git not installed")
class TestGitSync(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        seed = self.tmp / "seed"
        seed.mkdir()
        git(seed, "init", "-q", "-b", "main")
        for g in ("ore", "godl", "eloscape"):
            (seed / "data" / g).mkdir(parents=True)
            (seed / "data" / g / "state.json").write_text("{}")
        git(seed, "add", "-A")
        git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")
        git(self.tmp, "clone", "-q", "--bare", str(seed), "remote.git")
        self.clones = {}
        for g in ("ore", "godl", "eloscape"):
            git(self.tmp, "clone", "-q", "--depth=1", f"file://{self.tmp}/remote.git", g)
            self.clones[g] = self.tmp / g

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def push(self, g, text):
        folder = self.clones[g] / "data" / g
        (folder / "state.json").write_text(text)
        return GitSync(folder).push_folder()

    def remote_file(self, g):
        return git(self.tmp / "remote.git", "show", f"main:data/{g}/state.json").stdout

    def test_concurrent_pushes_all_land(self):
        for round_ in range(3):
            results = {}
            threads = [threading.Thread(target=lambda g=g: results.__setitem__(g, self.push(g, f"{g}{round_}")))
                       for g in self.clones]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertTrue(all(results.values()), results)
            for g in self.clones:
                self.assertEqual(self.remote_file(g), f"{g}{round_}")

    def test_recovers_from_stuck_rebase_and_detached_head(self):
        self.assertTrue(self.push("eloscape", "e1"))
        ore = self.clones["ore"]
        git(ore, "checkout", "-q", "--detach")
        (ore / "data" / "eloscape" / "state.json").write_text("stale local copy")  # unrelated dirt
        self.assertTrue(self.push("ore", "o1"))
        self.assertEqual(self.remote_file("ore"), "o1")
        self.assertEqual(self.remote_file("eloscape"), "e1")  # never overwritten by ore's job


if __name__ == "__main__":
    unittest.main()
