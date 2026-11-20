"""
Periodic push of data/<game>/ to the repo while the agent runs (GitHub Actions only),
so the latest paper-wallet state can be read from GitHub at any time.
Enabled by MINEGRID_SYNC_MINUTES (0 or unset = off). Never raises.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger("minegrid.gitsync")


class GitSync:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.every = float(os.environ.get("MINEGRID_SYNC_MINUTES") or 0) * 60
        self.last = time.time()

    def _git(self, *args: str) -> int:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=60).returncode

    def maybe_push(self, force: bool = False) -> None:
        if self.every <= 0 or (not force and time.time() - self.last < self.every):
            return
        self.last = time.time()
        try:
            self._git("add", str(self.folder))
            if self._git("diff", "--staged", "--quiet") == 0:
                return
            self._git("-c", "user.name=minegrid-agent", "-c", "user.email=actions@users.noreply.github.com",
                      "commit", "-q", "-m", f"chore(agent): {self.folder.name} state [skip ci]")
            for _ in range(3):
                if self._git("pull", "-q", "--rebase") == 0 and self._git("push", "-q") == 0:
                    log.info("State pushed to GitHub")
                    return
                time.sleep(5)
            log.warning("State push failed (will retry next interval)")
        except Exception as exc:
            log.warning("State push error: %s", exc)
