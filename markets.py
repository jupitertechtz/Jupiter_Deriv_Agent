"""Live market catalog: every Deriv market, what it offers, and its duration limits.

Built from the API's active_symbols and contracts_for, so it follows whatever Deriv
offers on the account (markets and contract types differ by region and change over time).

Capabilities this app can trade:
  digits    Digit Matches (DIGITMATCH). Offered on synthetic indices.
  risefall  Rise/Fall (CALL/PUT with no barrier). Offered on synthetics and most
            financial markets (forex, commodities, stock indices; crypto where offered).
"""
import asyncio
import re
import time

from deriv_client import VOLATILITY_SYMBOLS, DerivAPIError, DerivClient

CATEGORY_NAMES = {
    "synthetic_index": "Derived / synthetic indices", "forex": "Forex", "commodities": "Commodities",
    "indices": "Stock indices", "cryptocurrency": "Cryptocurrencies", "stocks": "Stocks", "etf": "ETFs",
}
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
CACHE_TTL = 900
_cache: dict = {}


def parse_duration(text: str, expiry_type: str = "") -> tuple[int, str] | None:
    """'5t' -> (5, 't'); '15m' -> (15, 'm'); '5' on a tick expiry -> (5, 't')."""
    m = re.fullmatch(r"\s*(\d+)\s*([tsmhd]?)\s*", str(text or ""))
    if not m:
        return None
    unit = m.group(2) or ("t" if expiry_type == "tick" else "s")
    return int(m.group(1)), unit


def to_seconds(value: int, unit: str, tick_seconds: float = 2.0) -> float:
    return value * (tick_seconds if unit == "t" else UNIT_SECONDS[unit])


def _capabilities(available: list[dict]) -> dict:
    caps: dict = {"digits": None, "risefall": []}
    for c in available:
        ctype, expiry = c.get("contract_type"), c.get("expiry_type", "")
        lo = parse_duration(c.get("min_contract_duration"), expiry)
        hi = parse_duration(c.get("max_contract_duration"), expiry)
        if ctype == "DIGITMATCH" and lo and hi:
            caps["digits"] = {"min": lo[0], "max": hi[0], "unit": "t"}
        if ctype == "CALL" and int(c.get("barriers") or 0) == 0 and expiry != "daily" and lo and hi:
            rng = {"expiry_type": expiry, "min": list(lo), "max": list(hi)}
            if rng not in caps["risefall"]:
                caps["risefall"].append(rng)
    caps["risefall"].sort(key=lambda r: to_seconds(*r["min"]))
    return caps


async def build_catalog(client: DerivClient) -> list[dict]:
    symbols = [s for s in await client.active_symbols() if not s.get("is_trading_suspended")]
    sem = asyncio.Semaphore(10)

    async def one(sym):
        async with sem:
            try:
                return await client.contracts_for(sym["underlying_symbol"])
            except DerivAPIError:
                return []

    contracts = await asyncio.gather(*(one(s) for s in symbols))
    out = []
    for sym, avail in zip(symbols, contracts):
        caps = _capabilities(avail)
        if not caps["digits"] and not caps["risefall"]:
            continue
        out.append({
            "symbol": sym["underlying_symbol"], "name": sym.get("underlying_symbol_name") or sym["underlying_symbol"],
            "market": sym.get("market", ""), "category": CATEGORY_NAMES.get(sym.get("market", ""), sym.get("market", "")),
            "submarket": sym.get("submarket", ""), "open": bool(sym.get("exchange_is_open", 1)),
            "pip_size": sym.get("pip_size"), "digits": caps["digits"], "risefall": caps["risefall"],
        })
    out.sort(key=lambda m: (list(CATEGORY_NAMES).index(m["market"]) if m["market"] in CATEGORY_NAMES else 99,
                            m["submarket"], m["name"]))
    return out


def _fallback() -> list[dict]:
    names = {"R_10": "Volatility 10 Index", "R_25": "Volatility 25 Index", "R_50": "Volatility 50 Index",
             "R_75": "Volatility 75 Index", "R_100": "Volatility 100 Index", "1HZ10V": "Volatility 10 (1s) Index",
             "1HZ25V": "Volatility 25 (1s) Index", "1HZ50V": "Volatility 50 (1s) Index",
             "1HZ75V": "Volatility 75 (1s) Index", "1HZ100V": "Volatility 100 (1s) Index"}
    return [{"symbol": s, "name": names[s], "market": "synthetic_index", "category": CATEGORY_NAMES["synthetic_index"],
             "submarket": "random_index", "open": True, "pip_size": None,
             "digits": {"min": 1, "max": 10, "unit": "t"},
             "risefall": [{"expiry_type": "tick", "min": [1, "t"], "max": [10, "t"]}]} for s in VOLATILITY_SYMBOLS]


async def get_catalog(settings, refresh: bool = False) -> dict:
    """Cached catalog for this account type. Falls back to the ten Volatility indices if discovery fails."""
    key = settings.account_type
    hit = _cache.get(key)
    if hit and not refresh and time.time() - hit["built"] < CACHE_TTL:
        return hit
    try:
        async with DerivClient(settings.app_id, settings.api_token or None, settings.api_base,
                               settings.account_type) as client:
            markets = await build_catalog(client)
        if not markets:
            raise ValueError("empty catalog")
        entry = {"markets": markets, "built": time.time(), "source": "live"}
    except Exception as exc:  # network/API trouble: keep trading the known digit markets
        entry = {"markets": _fallback(), "built": time.time(), "source": f"fallback ({exc})"}
    _cache[key] = entry
    return entry


def find(catalog: dict, symbol: str) -> dict | None:
    return next((m for m in catalog["markets"] if m["symbol"] == symbol), None)


def check_risefall_duration(market: dict, duration: int, unit: str) -> None:
    """Raise ValueError unless (duration, unit) fits one of the market's Rise/Fall ranges."""
    if unit not in ("t", "s", "m", "h"):
        raise ValueError("Duration unit must be ticks, seconds, minutes or hours.")
    for r in market["risefall"]:
        (lo, lu), (hi, hu) = r["min"], r["max"]
        if unit == "t" and lu == "t" and lo <= duration <= hi:
            return
        if unit != "t" and lu != "t" and to_seconds(lo, lu) <= to_seconds(duration, unit) <= to_seconds(hi, hu):
            return
    allowed = "; ".join(f"{r['min'][0]}{r['min'][1]} to {r['max'][0]}{r['max'][1]}" for r in market["risefall"])
    raise ValueError(f"{market['name']} allows Rise/Fall durations of {allowed or 'none'}.")
