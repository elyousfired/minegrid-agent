"""
Compare a program's instructions before and after a moment (e.g. an upgrade):
instruction names from logs, data discriminators, account counts, SOL moved.

  python -m minegrid_agent.ix_compare <program_id> <split_unix_time>
"""
from __future__ import annotations

import base64
import collections
import sys
from datetime import datetime, timezone

from .solana import SolanaRPC, b58decode


def ts(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%m-%d %H:%M:%S") if t else "?"


def main(program: str, split: int) -> None:
    rpc = SolanaRPC()
    sigs, before = [], None
    while True:
        opts = {"limit": 1000}
        if before:
            opts["before"] = before
        page = rpc._call("getSignaturesForAddress", [program, opts])
        if not page:
            break
        sigs += page
        before = page[-1]["signature"]
        if (page[-1].get("blockTime") or 0) < split - 6 * 3600 or len(sigs) > 6000:
            break
    after = [s for s in sigs if (s.get("blockTime") or 0) >= split and not s.get("err")]
    prior = [s for s in sigs if (s.get("blockTime") or 0) < split and not s.get("err")]
    print(f"{len(sigs)} signatures, {len(prior)} ok before, {len(after)} ok after; "
          f"oldest {ts(sigs[-1].get('blockTime'))}")
    for label, group in (("BEFORE", prior[:25]), ("AFTER", after[-25:])):
        names, shapes, signers = collections.Counter(), collections.Counter(), collections.Counter()
        for s in group:
            tx = rpc._call("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
            if not tx:
                continue
            msg = tx["transaction"]["message"]
            keys = msg["accountKeys"]
            signers[keys[0]] += 1
            for ins in msg["instructions"]:
                if keys[ins["programIdIndex"]] != program:
                    continue
                data = b58decode(ins["data"]) if ins["data"] else b""
                shapes[(data[:8].hex(), len(data), len(ins["accounts"]))] += 1
            for line in tx["meta"].get("logMessages") or []:
                if "Instruction:" in line:
                    names[line.split("Instruction:")[1].strip()] += 1
            pre, post = tx["meta"]["preBalances"], tx["meta"]["postBalances"]
            if label == "AFTER" and len(group) and s is group[-1]:
                print("  last tx logs:", [l[:120] for l in (tx["meta"].get("logMessages") or [])][:15])
        print(f"\n== {label} ({len(group)} txs, {ts(group[0].get('blockTime')) if group else '-'}..)")
        print("  instruction names:", dict(names))
        print("  (discriminator, data len, n accounts):", dict(shapes))
        print("  fee payers:", dict(signers.most_common(8)))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
