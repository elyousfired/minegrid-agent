"""
Audit a Solana program: when it was last upgraded, by whom, the upgrade transactions,
and the current size and first fields of its board / round accounts.

  python -m minegrid_agent.program_audit <program_id>
"""

from __future__ import annotations

import base64
import json
import struct
import sys
from datetime import datetime, timezone

from .solana import SolanaRPC, b58encode, find_program_address

LOADER_V3 = "BPFLoaderUpgradeab1e11111111111111111111111"


def ts(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if t else "?"


def main(program_id: str) -> None:
    rpc = SolanaRPC()
    acc = rpc._call("getAccountInfo", [program_id, {"encoding": "base64"}])["value"]
    print(f"program {program_id} owner {acc['owner']} executable {acc['executable']}")
    raw = base64.b64decode(acc["data"][0])
    if acc["owner"] != LOADER_V3:
        print("not an upgradeable program")
        return
    pdata = b58encode(raw[4:36])
    head = rpc._call("getAccountInfo", [pdata, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 45}}])["value"]
    h = base64.b64decode(head["data"][0])
    slot = struct.unpack_from("<Q", h, 4)[0]
    auth = b58encode(h[13:45]) if h[12] == 1 else "NONE (immutable)"
    t = rpc._call("getBlockTime", [slot])
    print(f"programdata {pdata}\nlast deploy slot {slot} at {ts(t)}\nupgrade authority {auth}")
    print(f"programdata size {head.get('space') or '?'} bytes, lamports {head['lamports'] / 1e9:.4f} SOL")

    print("\n== recent transactions touching programdata (upgrades / extends)")
    for s in rpc._call("getSignaturesForAddress", [pdata, {"limit": 15}]):
        print(f"{ts(s.get('blockTime'))} slot {s['slot']} err {s.get('err')} {s['signature']}")
    sigs = rpc._call("getSignaturesForAddress", [pdata, {"limit": 3}])
    for s in sigs:
        tx = rpc._call("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if not tx:
            continue
        msg = tx["transaction"]["message"]
        print(f"\n-- tx {s['signature'][:20]}… at {ts(tx.get('blockTime'))} fee {tx['meta']['fee']}")
        print("   signers:", [k["pubkey"] for k in msg["accountKeys"] if k.get("signer")])
        for ins in msg["instructions"]:
            p = ins.get("parsed")
            print("   ix", ins.get("programId"), json.dumps(p)[:300] if p else (ins.get("data") or "")[:60])
        for line in (tx["meta"].get("logMessages") or [])[:12]:
            print("   log", line[:160])

    print("\n== game accounts")
    board_addr = find_program_address([b"board"], program_id)[0]
    board = rpc.get_accounts([board_addr])[0]
    if board is None:
        print("no board account")
        return
    live = struct.unpack_from("<Q", board, 8)[0]
    print(f"board {board_addr} len {len(board)} words {[struct.unpack_from('<Q', board, o)[0] for o in range(8, len(board) - 7, 8)][:8]}")
    ids = [live - 3, live - 2, live - 1, live]
    addrs = [find_program_address([b"round", struct.pack("<Q", i)], program_id)[0] for i in ids]
    for rid, data in zip(ids, rpc.get_accounts(addrs)):
        if data is None:
            print(f"round {rid}: missing")
            continue
        words = [struct.unpack_from("<Q", data, o)[0] for o in range(0, len(data) - 7, 8)]
        print(f"round {rid}: len {len(data)} disc {data[:8].hex()}")
        print("   u64 words:", words[:60])
        if len(data) >= 332:
            print(f"   old radar offsets: deployed@316 {words[316 // 8] / 1e9} SOL, miners@324 {words[324 // 8]}")


if __name__ == "__main__":
    main(sys.argv[1])
