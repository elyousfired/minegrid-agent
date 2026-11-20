"""
GlazeCorp agent: scan every fund's mining slot, alert on "safe" entries, paper-buy them,
and settle each paper position when the slot changes hands (real takeover data).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from pathlib import Path

from ..notify import BLUE, GREEN, Notifier, field
from ..storage import _atomic_write
from .glazecorp import fetch_slots
from .model import Slot, evaluate, settle_takeover, token_value

log = logging.getLogger("minegrid.glazecorp")
MAX_HOLD_SECONDS = 6 * 3600


def _load(path: Path, start_usd: float) -> dict:
    import json
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"start_usd": start_usd, "balance_usd": start_usd, "positions": {}, "closed": [],
            "entries": 0, "pnl_usd": 0.0, "alerted": {}}


def run_glazecorp_agent(data_dir: Path, max_minutes: float, poll_seconds: float,
                        start_usd: float, max_entry_usd: float) -> None:
    path = Path(data_dir) / "glazecorp" / "state.json"
    st = _load(path, start_usd)
    notifier = Notifier()
    deadline = time.time() + max_minutes * 60
    log.info("GlazeCorp agent started: balance $%.2f, %d open positions", st["balance_usd"], len(st["positions"]))

    while time.time() < deadline:
        try:
            now = time.time()
            slots = {s.coin: s for s in fetch_slots()}

            # 1) settle paper positions whose slot changed hands (or timed out)
            for coin, pos in list(st["positions"].items()):
                s = slots.get(coin)
                if s is None:
                    continue
                if s.epoch > pos["epoch"] or now - pos["entered_at"] > MAX_HOLD_SECONDS:
                    if s.epoch > pos["epoch"]:
                        pnl = settle_takeover(pos, s)
                    else:  # nobody took over: keep the mined tokens, no refund
                        held = Slot(**{**pos["slot"], "p_token": s.p_token, "r_usdg": s.r_usdg})
                        pnl = token_value(held, now - pos["entered_at"]) - pos["p_in"]
                    st["balance_usd"] += pos["p_in"] + pnl
                    st["pnl_usd"] += pnl
                    st["closed"] = (st["closed"] + [{"coin": coin, "symbol": pos["slot"]["symbol"],
                                                     "p_in": pos["p_in"], "pnl": pnl}])[-300:]
                    del st["positions"][coin]
                    log.info("Closed %s: pnl %+.4f USDG", pos["slot"]["symbol"], pnl)

            # 2) new entries
            for s in slots.values():
                sig = evaluate(s, now)
                if sig.kind != "safe" or s.coin in st["positions"]:
                    continue
                if 0 < sig.p_in <= min(max_entry_usd, st["balance_usd"]):
                    st["balance_usd"] -= sig.p_in
                    st["entries"] += 1
                    st["positions"][s.coin] = {"epoch": s.epoch, "entered_at": now, "p_in": sig.p_in,
                                               "slot": asdict(s)}
                    log.info("Paper entry %s at $%.4f (safe price $%.4f)", s.symbol, sig.p_in, sig.safe_price)
                if st["alerted"].get(s.coin) != s.epoch:
                    st["alerted"][s.coin] = s.epoch
                    notifier.send(
                        f"🟢 GLAZECORP — {s.symbol}",
                        f"{sig.label}.\nالثمن دابا **${sig.p_in:.4f}**، والثمن الآمن **${sig.safe_price:.4f}**.",
                        GREEN,
                        [field("Epoch", str(s.epoch)), field("TPS", f"{s.tps:.4f}")],
                    )
            _atomic_write(path, st)
        except Exception as exc:
            log.warning("Loop error: %s", exc)
        time.sleep(poll_seconds)

    _atomic_write(path, st)
    notifier.send("📊 GLAZECORP — ملخص الـpaper wallet",
                  f"دخلات: **{st['entries']}** | الربح المحقق: **{st['pnl_usd']:+.4f} USDG** | "
                  f"مفتوحين: {len(st['positions'])}", BLUE)
