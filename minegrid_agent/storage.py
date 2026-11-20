from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Round
from .paper import PaperWallet

MAX_ROUNDS = 50_000


def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, data_dir: Path, game: str) -> None:
        self.dir = Path(data_dir) / game
        self.rounds_path = self.dir / "rounds.json"
        self.state_path = self.dir / "state.json"

    def load_rounds(self) -> list[Round]:
        if not self.rounds_path.exists():
            return []
        rows = json.loads(self.rounds_path.read_text(encoding="utf-8"))
        rounds = {int(r["round_id"]): Round.from_dict(r) for r in rows}
        return [rounds[k] for k in sorted(rounds)]

    def save_rounds(self, rounds: list[Round]) -> None:
        _atomic_write(self.rounds_path, [r.to_dict() for r in rounds[-MAX_ROUNDS:]])

    def load_state(self, start_native: float) -> tuple[PaperWallet, dict]:
        if not self.state_path.exists():
            return PaperWallet(start_native=start_native, balance_native=start_native,
                               peak_equity=start_native), {}
        d = json.loads(self.state_path.read_text(encoding="utf-8"))
        return PaperWallet.from_dict(d.get("wallet", {})), d.get("agent", {})

    def save_state(self, wallet: PaperWallet, agent: dict) -> None:
        _atomic_write(self.state_path, {"wallet": wallet.to_dict(), "agent": agent})
