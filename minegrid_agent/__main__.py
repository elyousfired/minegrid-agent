"""
CLI:
  python -m minegrid_agent run      --game eloscape --max-minutes 330
  python -m minegrid_agent run      --game glazecorp
  python -m minegrid_agent backtest --game eloscape --token-price 0.012
  python -m minegrid_agent status   --game eloscape
  python -m minegrid_agent import-eloscape-cache path/to/epochs_cache.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .backtest import compare
from .games import GAMES, get_game
from .storage import Store
from .strategy import PREDICTORS, StrategyParams

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data"
ALL_GAMES = list(GAMES) + ["glazecorp"]


def main() -> None:
    ap = argparse.ArgumentParser(prog="minegrid_agent")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="live agent (signals + paper trading)")
    run.add_argument("--game", choices=ALL_GAMES, required=True)
    run.add_argument("--max-minutes", type=float, default=330)
    run.add_argument("--poll", type=float, default=4.0)
    run.add_argument("--predictor", choices=PREDICTORS, default="scenario")
    run.add_argument("--lookback", type=int, default=10)
    run.add_argument("--margin", type=float, default=0.15)
    run.add_argument("--start-balance", type=float, default=1.0)
    run.add_argument("--summary-every", type=float, default=60.0, help="minutes")
    run.add_argument("--max-entry-usd", type=float, default=5.0, help="glazecorp: max paper entry price")

    bt = sub.add_parser("backtest", help="walk-forward backtest on stored history")
    bt.add_argument("--game", choices=list(GAMES), required=True)
    bt.add_argument("--token-price", type=float, required=True,
                    help="reward token price in native coin (e.g. ELO/HYPE)")
    bt.add_argument("--warmup", type=int, default=20)

    st = sub.add_parser("status", help="print paper wallet summary")
    st.add_argument("--game", choices=ALL_GAMES, required=True)

    imp = sub.add_parser("import-eloscape-cache", help="seed Eloscape history from the old dashboard cache")
    imp.add_argument("path", type=Path)

    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd == "run" and args.game == "glazecorp":
        from .auction.agent import run_glazecorp_agent
        start = args.start_balance if args.start_balance != 1.0 else 100.0
        run_glazecorp_agent(args.data_dir, args.max_minutes, max(args.poll, 15.0), start, args.max_entry_usd)

    elif args.cmd == "run":
        from .agent import run_agent
        params = StrategyParams(predictor=args.predictor, lookback=args.lookback, safety_margin=args.margin)
        run_agent(args.game, args.data_dir, args.max_minutes, args.poll, params,
                  args.start_balance, args.summary_every)

    elif args.cmd == "backtest":
        cfg = get_game(args.game).config
        rounds = Store(args.data_dir, args.game).load_rounds()
        if len(rounds) <= args.warmup:
            raise SystemExit(f"Not enough history ({len(rounds)} rounds) in {args.data_dir / args.game}")
        print(f"{cfg.name}: {len(rounds)} rounds | house edge {cfg.house_edge:.4%} | "
              f"token price {args.token_price} {cfg.native_symbol}")
        for res in compare(rounds, cfg, args.token_price, args.warmup):
            print(res.row(cfg.native_symbol))

    elif args.cmd == "status" and args.game == "glazecorp":
        path = args.data_dir / "glazecorp" / "state.json"
        st = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        print(json.dumps({k: st.get(k) for k in ("balance_usd", "pnl_usd", "entries")}
                         | {"open_positions": len(st.get("positions", {}))}, indent=2))

    elif args.cmd == "status":
        cfg = get_game(args.game).config
        wallet, agent = Store(args.data_dir, args.game).load_state(1.0)
        price = agent.get("token_price_native", 0.0)
        print(json.dumps({"agent": agent, "wallet": wallet.summary(price, cfg)}, indent=2, ensure_ascii=False))

    elif args.cmd == "import-eloscape-cache":
        from .games.eloscape import from_legacy_cache
        rows = json.loads(args.path.read_text(encoding="utf-8"))
        rounds = [from_legacy_cache(r) for r in rows
                  if r.get("status") == "settled" and r.get("winning_block") is not None]
        store = Store(args.data_dir, "eloscape")
        store.save_rounds(sorted(rounds, key=lambda r: r.round_id))
        print(f"Imported {len(rounds)} Eloscape rounds into {store.rounds_path}")


if __name__ == "__main__":
    main()
