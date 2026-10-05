"""Lightweight account snapshot for the dashboard's live balance card (polled every few seconds)."""
import contextlib
import dataclasses
import time

from deriv_client import DerivAPIError, DerivClient
from services import _start_of_utc_day

APP_TYPES = ("DIGITMATCH", "CALL", "PUT")
TYPE_NAMES = {"DIGITMATCH": "Matches", "CALL": "Rise", "PUT": "Fall"}


async def live_snapshot(s, account_type: str = "demo", since: int | None = None) -> dict:
    if account_type not in ("demo", "real"):
        raise ValueError("Account must be 'demo' or 'real'.")
    s = dataclasses.replace(s, account_type=account_type)        # read-only view, no trading
    since = int(since) if since else _start_of_utc_day()
    async with DerivClient(s.app_id, s.api_token, s.api_base, s.account_type) as client:
        acct = client.account
        bal = await client.request({"balance": 1})
        balance = float(bal["balance"]["balance"])
        currency = bal["balance"].get("currency") or acct.get("currency")
        open_contracts = []
        with contextlib.suppress(DerivAPIError):
            open_contracts = [c for c in await client.portfolio() if c.get("contract_type") in APP_TYPES]
        settled = await client.matches_history(since_epoch=since, limit=100)
    now = int(time.time())
    return {
        "time": now, "account": {"loginid": acct.get("loginid"), "is_virtual": bool(acct.get("is_virtual")),
                                 "currency": currency},
        "balance": round(balance, 2),
        "open": {
            "count": len(open_contracts),
            "stake": round(sum(float(c.get("buy_price") or 0) for c in open_contracts), 2),
            "contracts": [{"symbol": c.get("underlying_symbol"), "type": TYPE_NAMES.get(c.get("contract_type")),
                           "stake": float(c.get("buy_price") or 0),
                           "seconds_left": max(0, int(c.get("expiry_time") or now) - now)}
                          for c in open_contracts[:10]],
        },
        "settled": {
            "since": since, "count": len(settled), "wins": sum(r["profit"] > 0 for r in settled),
            "pnl": round(sum(r["profit"] for r in settled), 2),
            "latest": [{"time": r["purchase_time"], "symbol": r["symbol"],
                        "type": TYPE_NAMES.get(r.get("contract_type"), r.get("contract_type")),
                        "bet": r["predicted"], "profit": r["profit"]} for r in settled[:8]],
        },
    }
