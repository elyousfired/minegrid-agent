"""GlazeCorp (Robinhood Chain) mining slots, read from the public Goldsky subgraph."""

from __future__ import annotations

import json
import os
import urllib.request

from .model import Slot

SUBGRAPH_URL = os.environ.get("GLAZECORP_SUBGRAPH_URL") or (
    "https://api.goldsky.com/api/public/project_cmtlwofwa17hz01u26caa9ev9/subgraphs/glazecorp-zero-rpc/0.3.0/gn"
)

QUERY = """
{
  fundInstances(first: 200, orderBy: liquidityUsdgRaw, orderDirection: desc) {
    coin symbol swapFee liquidityUsdgRaw priceUsdgWad
    pool { quoteIsUsdg reserveBaseRaw reserveQuoteRaw }
    miningSlots { epoch initialPriceRaw auctionStartedAt tpsRaw lastPriceRaw }
  }
}
"""


def parse_fund(f: dict) -> Slot | None:
    slots = f.get("miningSlots") or []
    if not slots:
        return None
    s = slots[0]
    pool = f.get("pool") or {}
    r_base = int(pool.get("reserveBaseRaw") or 0) / 1e18
    r_quote = int(pool.get("reserveQuoteRaw") or 0) / 1e6
    quote_is_usdg = bool(pool.get("quoteIsUsdg", True))
    if quote_is_usdg and r_base > 0 and r_quote > 0:
        p_token, r_usdg = r_quote / r_base, r_quote
    else:
        p_token = int(f.get("priceUsdgWad") or 0) / 1e18
        r_usdg = int(f.get("liquidityUsdgRaw") or 0) / 1e6 / 2
    fee = int(f.get("swapFee") or 10_000) / 1e6
    return Slot(
        coin=(f.get("coin") or "").lower(),
        symbol=f.get("symbol") or "???",
        epoch=int(s.get("epoch") or 0),
        init_price=int(s.get("initialPriceRaw") or 0) / 1e6,
        auction_started_at=int(s.get("auctionStartedAt") or 0),
        tps=int(s.get("tpsRaw") or 0) / 1e18,
        last_price=int(s.get("lastPriceRaw") or 0) / 1e6,
        p_token=p_token,
        r_usdg=r_usdg,
        swap_fee=fee if 0 < fee <= 0.2 else 0.01,
    )


def fetch_slots() -> list[Slot]:
    req = urllib.request.Request(
        SUBGRAPH_URL, data=json.dumps({"query": QUERY}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "minegrid-agent"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    if data.get("errors"):
        raise RuntimeError(f"subgraph error: {data['errors']}")
    out = []
    for f in data.get("data", {}).get("fundInstances", []):
        slot = parse_fund(f)
        if slot and slot.tps > 0:
            out.append(slot)
    return out
