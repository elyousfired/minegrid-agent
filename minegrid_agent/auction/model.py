"""
GlazeCorp mining-slot economics (ported from glazecorp-live-dashboard/index.html).

You buy the slot at the current Dutch-auction price p_in (decays linearly to 0 over 1h).
While you hold it you mine `tps` tokens/second. When someone takes over at minute m, they
pay the next auction price (starts at max(2*p_in, 1), decays over 1h) and you get 80% of it.
Tokens are valued at what you would actually receive selling into the AMM (or NAV, if higher).
"""

from __future__ import annotations

from dataclasses import dataclass

REFUND_SHARE = 0.80
AUCTION_SECONDS = 3600.0


@dataclass
class Slot:
    coin: str
    symbol: str
    epoch: int
    init_price: float        # USDG
    auction_started_at: int  # unix seconds
    tps: float               # tokens per second
    last_price: float        # USDG paid by the current holder
    p_token: float           # USDG per token (spot)
    r_usdg: float            # USDG side of the AMM pool
    swap_fee: float = 0.01
    nav_per_token: float = 0.0

    def price_now(self, now: float) -> float:
        elapsed = max(0.0, now - self.auction_started_at)
        if elapsed >= AUCTION_SECONDS:
            return 0.0
        return self.init_price * (AUCTION_SECONDS - elapsed) / AUCTION_SECONDS


def realized_usdg(paper_usd: float, r_usdg: float, swap_fee: float) -> float:
    """USDG received for selling tokens worth `paper_usd` at spot into a constant-product pool."""
    if r_usdg <= 0 or paper_usd <= 0:
        return 0.0
    eff = paper_usd * (1.0 - swap_fee)
    return r_usdg * eff / (r_usdg + eff)


def token_value(slot: Slot, seconds: float) -> float:
    mined = slot.tps * max(0.0, seconds)
    return max(realized_usdg(mined * slot.p_token, slot.r_usdg, slot.swap_fee), mined * slot.nav_per_token)


def profit_at_minute(slot: Slot, p_in: float, minute: float) -> float:
    next_start = max(2.0 * p_in, 1.0)
    p_next = 0.0 if minute >= 60 else next_start * (1.0 - minute / 60.0)
    return REFUND_SHARE * p_next + token_value(slot, minute * 60.0) - p_in


def breakeven_minute(slot: Slot, p_in: float) -> float:
    """Latest takeover minute that still leaves you whole (60 = profitable at any time)."""
    if p_in <= 0 or profit_at_minute(slot, p_in, 60) >= 0:
        return 60.0
    if profit_at_minute(slot, p_in, 0) < 0:
        return 0.0
    lo, hi = 0.0, 60.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if profit_at_minute(slot, p_in, mid) >= 0:
            lo = mid
        else:
            hi = mid
    return lo


@dataclass
class AuctionSignal:
    coin: str
    symbol: str
    kind: str          # "safe" | "partial" | "wait" | "illiquid"
    p_in: float
    breakeven_min: float
    safe_price: float  # price at or below which entry is profitable for the full hour
    label: str


def evaluate(slot: Slot, now: float, min_liquidity: float = 0.5) -> AuctionSignal:
    p_in = slot.price_now(now)
    be = breakeven_minute(slot, p_in)
    p_safe = token_value(slot, AUCTION_SECONDS)
    if slot.r_usdg < min_liquidity:
        kind, label = "illiquid", "سيولة ميتة"
    elif be >= 59.9 and p_safe > 0.02:
        kind, label = "safe", "رابح واخا يدّيه منك شي حد ف أي دقيقة"
    elif be >= 35.0:
        kind, label = "partial", f"رابح إلا بقا عندك {be:.0f} دقيقة ولا أقل"
    else:
        kind, label = "wait", "تسنى حتى يطيح الثمن"
    return AuctionSignal(slot.coin, slot.symbol, kind, p_in, be, p_safe, label)


def settle_takeover(entry: dict, slot_after: Slot) -> float:
    """
    Realised profit of a paper entry once the slot changed hands.
    The takeover happened when the new auction started; the new holder paid `last_price`.
    """
    held = max(0.0, slot_after.auction_started_at - entry["entered_at"])
    held_slot = Slot(**{**entry["slot"], "p_token": slot_after.p_token, "r_usdg": slot_after.r_usdg})
    refund = REFUND_SHARE * slot_after.last_price
    return refund + token_value(held_slot, held) - entry["p_in"]
