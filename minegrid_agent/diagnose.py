"""One-shot on-chain diagnostic for Solana grid games: prints what the adapter sees."""
from __future__ import annotations

from .games import get_game
from .solana import u64


def diagnose(name: str) -> None:
    ad = get_game(name)
    print(f"program {ad.program_id}\nboard {ad.board}")
    board = ad.rpc.get_accounts([ad.board])[0]
    if board is None:
        print("BOARD MISSING: program id or seed is wrong")
        return
    print(f"board len {len(board)} words {[u64(board, o) for o in range(8, min(len(board), 48), 8)]}")
    live = u64(board, 8)
    ids = list(range(live - 4, live + 1))
    for rid, data in zip(ids, ad.rpc.get_accounts([ad.round_address(i) for i in ids])):
        if data is None:
            print(f"round {rid}: MISSING ({ad.round_address(rid)})")
            continue
        parsed = ad.layout.parse_round(data, 10 ** ad.token_decimals)
        print(f"round {rid}: len {len(data)} disc {data[:8].hex()} id@8 {u64(data, 8)} "
              f"head {[u64(data, o) for o in range(16, 64, 8)]} parsed {parsed}")
    try:
        print("market", ad.fetch_market())
    except Exception as exc:
        print("market error", exc)
