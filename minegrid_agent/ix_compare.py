"""
Compare a program's instructions before and after a moment (e.g. an upgrade):
instruction names from logs, data discriminators, account counts, SOL moved.

  python -m minegrid_agent.ix_compare <program_id> <split_unix_time>
"""
from __future__ import annotations

import base64
import collections
import sys
import time
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
        if (page[-1].get("blockTime") or 0) < split - 3600 or len(sigs) > 15000:
            break
    errs = collections.Counter(str(x.get("err")) for x in sigs if x.get("err"))
    print("errors in signatures:", dict(errs.most_common(6)))
    failed = [x for x in sigs if x.get("err")]
    after = [s for s in sigs if (s.get("blockTime") or 0) >= split and not s.get("err")]
    prior = [s for s in sigs if (s.get("blockTime") or 0) < split and not s.get("err")]
    print(f"{len(sigs)} signatures, {len(prior)} ok before, {len(after)} ok after; "
          f"oldest {ts(sigs[-1].get('blockTime'))}")
    def get_tx(sig):
        for i in range(5):
            try:
                time.sleep(1.2)
                return rpc._call("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
            except Exception:
                time.sleep(5 * (i + 1))
        return None

    for label, group in (("BEFORE", prior[:10]), ("AFTER ok", after[-10:]), ("FAILED", failed[:12])):
        names, shapes, signers = collections.Counter(), collections.Counter(), collections.Counter()
        for s in group:
            tx = get_tx(s["signature"])
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
            if s is group[0] and label != "BEFORE":
                print(f"  {label} sample logs:", [l[:140] for l in (tx["meta"].get("logMessages") or [])][:14])
        print(f"\n== {label} ({len(group)} txs, {ts(group[0].get('blockTime')) if group else '-'}..)")
        print("  instruction names:", dict(names))
        print("  (discriminator, data len, n accounts):", dict(shapes))
        print("  fee payers:", dict(signers.most_common(8)))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
