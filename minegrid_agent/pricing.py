"""Token prices from the public DexScreener API (no key needed)."""

from __future__ import annotations

from .http import get_json

NATIVE_ALIASES = {
    "SOL": {"SOL", "WSOL"},
    "ETH": {"ETH", "WETH"},
    "BNB": {"BNB", "WBNB"},
    "HYPE": {"HYPE", "WHYPE"},
}


def dexscreener_price_native(token_address: str, native_symbol: str) -> tuple[float, float | None]:
    """
    Price of `token_address` in the native coin, from its most liquid pair against that coin.
    Returns (price_native, native_usd). Raises if no usable pair exists.
    """
    data = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{token_address}")
    aliases = NATIVE_ALIASES.get(native_symbol.upper(), {native_symbol.upper()})
    best = None
    for pair in data.get("pairs") or []:
        if (pair.get("baseToken", {}).get("address", "").lower() != token_address.lower()
                or (pair.get("quoteToken", {}).get("symbol") or "").upper() not in aliases):
            continue
        liq = float((pair.get("liquidity") or {}).get("usd") or 0)
        if best is None or liq > best[0]:
            best = (liq, pair)
    if best is None:
        raise RuntimeError(f"No {native_symbol} pair on DexScreener for {token_address}")
    pair = best[1]
    price_native = float(pair.get("priceNative") or 0)
    price_usd = float(pair.get("priceUsd") or 0)
    native_usd = (price_usd / price_native) if price_native > 0 and price_usd > 0 else None
    return price_native, native_usd
