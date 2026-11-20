"""
Periodic push of data/<game>/ to the repo while the agent runs (GitHub Actions only),
so the latest paper-wallet state can be read from GitHub at any time.
Enabled by MINEGRID_SYNC_MINUTES (0 or unset = off). Never raises.
"""

from __future__ import annotations

import logging
import os
import random
import subprocess
import time
from pathlib import Path

log = logging.getLogger("minegrid.gitsync")


class GitSync:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder).resolve()
        self.every = float(os.environ.get("MINEGRID_SYNC_MINUTES") or 0) * 60
        # spread the five game jobs over the interval so they don't push at the same moment
        self.last = time.time() - random.uniform(0, self.every)
        self.last_error = ""

    def _git(self, *args: str) -> int:
        self.folder.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", *args], cwd=self.folder, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            log.debug("git %s failed: %s", " ".join(args), (r.stderr or r.stdout).strip()[-300:])
            self.last_error = (r.stderr or r.stdout).strip()[-300:]
        return r.returncode

    def push_folder(self) -> bool:
        """
        Commit only this game's folder on top of the newest origin/main and push it.
        No rebase: HEAD is moved to origin/main with a mixed reset, which keeps our files on disk,
        so a race with another job can never leave a half-done rebase behind.
        """
        self._git("rebase", "--abort")  # clean up a rebase left over by an older version
        for _ in range(8):
            if self._git("fetch", "-q", "origin", "main") != 0:
                time.sleep(random.uniform(2, 15))
                continue
            self._git("reset", "-q", "--mixed", "origin/main")
            self._git("add", "--", ".")
            if self._git("diff", "--staged", "--quiet") == 0:
                return True
            self._git("-c", "user.name=minegrid-agent", "-c", "user.email=actions@users.noreply.github.com",
                      "commit", "-q", "-m", f"chore(agent): {self.folder.name} state [skip ci]")
            if self._git("push", "-q", "origin", "HEAD:main") == 0:
                return True
            time.sleep(random.uniform(2, 15))
        return False

    def maybe_push(self, force: bool = False) -> None:
        if self.every <= 0 or (not force and time.time() - self.last < self.every):
            return
        self.last = time.time()
        try:
            if self.push_folder():
                log.info("State pushed to GitHub")
            else:
                log.warning("State push failed (will retry next interval): %s", self.last_error)
        except Exception as exc:
            log.warning("State push error: %s", exc)
