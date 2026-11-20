"""
Live agent loop: sync settled rounds -> settle paper bets -> decide for the next round ->
record paper bet -> alert on Discord when the signal changes. Never signs transactions.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from . import migrations
from .games import get_game
from .gitsync import GitSync
from .gridmath import reward_value
from .notify import BLUE, GREEN, RED, Notifier, field
from .storage import Store
from .strategy import StrategyParams, decide

log = logging.getLogger("minegrid.agent")


def run_agent(game_name: str, data_dir: Path, max_minutes: float, poll_seconds: float,
              params: StrategyParams, start_native: float, summary_every_min: float = 60.0) -> None:
    game = get_game(game_name)
    cfg = game.config
    store = Store(data_dir, game_name)
    rounds = store.load_rounds()
    wallet, agent_state = store.load_state(start_native)
    wallet, migrated = migrations.apply(game_name, rounds, wallet, agent_state, cfg)
    if migrated:
        store.save_rounds(rounds)
        store.save_state(wallet, agent_state)
    notifier = Notifier()
    sync = GitSync(store.dir)
    last_signal = agent_state.get("last_signal")
    last_summary = time.time()
    deadline = time.time() + max_minutes * 60
    price = agent_state.get("token_price_native", 0.0)

    log.info("Agent %s started: %d rounds in history, paper balance %.6f %s, Discord %s",
             game_name, len(rounds), wallet.balance_native, cfg.native_symbol,
             "ON" if notifier.enabled else "OFF")

    while time.time() < deadline:
        try:
            last_id = rounds[-1].round_id if rounds else 0
            new = game.fetch_new_rounds(last_id)
            if new:
                market = game.fetch_market()
                price = market.token_price_native
                value = reward_value(cfg, price, market.motherlode_reserve, market.tokens_per_round)

                for r in new:
                    rounds.append(r)
                    settled = wallet.settle(r, cfg, price)
                    if settled:
                        log.info("Settled paper bet #%d: stake %.5f -> native %.5f + %.4f %s (pnl %+.6f)",
                                 r.round_id, settled["stake"], settled["native_back"], settled["tokens"],
                                 cfg.token_symbol, settled["pnl_native_eq"])
                newest = rounds[-1].round_id
                wallet.void_stale(newest)

                target = newest + 1
                if market.live_round_id and market.live_round_id > target:
                    target = market.live_round_id
                dec = decide(rounds, cfg, value, params)
                placed = dec.enter and wallet.place(target, dec, cfg)
                signal = "ENTER" if dec.enter else "WAIT"
                log.info("Round #%d -> %s | pool pred %.4f / BE %.4f | stake %.5f | EV %+.6f | %s",
                         target, signal, dec.predicted_pool, dec.breakeven_pool, dec.stake,
                         dec.expected_profit, "paper bet placed" if placed else dec.reason)

                if signal != last_signal:
                    _alert(notifier, cfg, target, dec, signal)
                    last_signal = signal

                agent_state.update(last_signal=signal, token_price_native=price, last_round=newest,
                                   updated=int(time.time()))
                store.save_rounds(rounds)
                store.save_state(wallet, agent_state)
                sync.maybe_push()

            if time.time() - last_summary >= summary_every_min * 60:
                _summary(notifier, cfg, wallet.summary(price, cfg))
                last_summary = time.time()
        except Exception as exc:  # keep running through API hiccups
            log.warning("Loop error: %s", exc)
        time.sleep(poll_seconds)

    store.save_rounds(rounds)
    store.save_state(wallet, agent_state)
    log.info("Agent stopped. Summary: %s", wallet.summary(price, cfg))


def _alert(notifier: Notifier, cfg, target: int, dec, signal: str) -> None:
    n = cfg.native_symbol
    if signal == "ENTER":
        notifier.send(
            f"🟢 {cfg.name.upper()} — دخل ف round #{target}",
            f"الـpool المتوقع **{dec.predicted_pool:.4f} {n}** تحت الـbreak-even **{dec.breakeven_pool:.4f} {n}**.\n"
            f"حط **{dec.stake:.5f} {n}** موزعة على 25 مربع ({dec.stake / cfg.squares:.6f} لكل مربع).",
            GREEN,
            [field("الربح المتوقع", f"{dec.expected_profit:+.6f} {n}"),
             field("Stake", f"{dec.stake:.5f} {n}")],
        )
    else:
        notifier.send(
            f"🔴 {cfg.name.upper()} — تسنى",
            f"{dec.reason}.\nما تدخلش حتى يجيك signal أخضر.",
            RED,
        )


def _summary(notifier: Notifier, cfg, s: dict) -> None:
    n = cfg.native_symbol
    notifier.send(
        f"📊 {cfg.name.upper()} — ملخص الـpaper wallet",
        f"الرهانات: **{s['bets']}** | الربح الصافي: **{s['pnl_native_eq']:+.6f} {n}** (ROI {s['roi_pct']:+.2f}%)",
        BLUE,
        [field("Native PnL", f"{s['native_pnl']:+.6f} {n}"),
         field(f"{cfg.token_symbol} مجموع", f"{s['tokens_gross']:.4f}"),
         field("Max drawdown", f"{s['max_drawdown_pct']:.2f}%")],
    )
