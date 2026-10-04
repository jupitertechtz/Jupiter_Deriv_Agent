"""Minimal async client for the Deriv WebSocket API (v3).

Authenticates with an API token (never a password). Every request carries a
req_id; Deriv echoes it on responses and on every subscription update, which
is how messages are routed back to the right caller.
"""
import asyncio
import contextlib
import itertools
import json
import logging

import websockets

log = logging.getLogger("deriv")

VOLATILITY_SYMBOLS = [
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
]


class DerivAPIError(Exception):
    def __init__(self, error: dict):
        self.code = error.get("code")
        super().__init__(f"{self.code}: {error.get('message')}")


def last_digit(quote, pip_size: int) -> int:
    """Last digit of a quote at the market's display precision (2.50 -> 0, not 5)."""
    return int(f"{float(quote):.{int(pip_size)}f}"[-1])


def _infer_pip_size(prices) -> int:
    # Fallback if the API omits pip_size: floats drop trailing zeros, so take the max.
    return max((len(repr(float(p)).split(".")[1]) for p in prices), default=2)


def _parse_shortcode(shortcode: str) -> tuple[str, str]:
    # e.g. DIGITMATCH_R_100_4.75_1759550000_1T_5_0 -> ("R_100", "5")
    try:
        parts = shortcode.split("_", 1)[1].split("_")
        return "_".join(parts[:-5]), parts[-2]
    except (IndexError, ValueError):
        return "", ""


class DerivClient:
    def __init__(self, app_id: str, token: str | None = None,
                 endpoint: str = "wss://ws.derivws.com/websockets/v3"):
        self.url = f"{endpoint}?app_id={app_id}"
        self.token = token
        self.ws = None
        self.account: dict | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._streams: dict[int, asyncio.Queue] = {}
        self._reader: asyncio.Task | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # ---------- connection ----------
    async def connect(self):
        self.ws = await websockets.connect(self.url, ping_interval=20, ping_timeout=20, max_size=2**23)
        self._reader = asyncio.create_task(self._read_loop())
        if self.token:
            self.account = (await self.request({"authorize": self.token}))["authorize"]
        return self.account

    async def close(self):
        if self.ws is not None:
            await self.ws.close()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader

    async def _read_loop(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                rid = msg.get("req_id")
                stream = self._streams.get(rid)
                if stream is not None:
                    stream.put_nowait(msg)
                    continue
                fut = self._pending.pop(rid, None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        except websockets.ConnectionClosed as exc:
            log.warning("Deriv connection closed: %s", exc)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("Deriv connection closed"))
            self._pending.clear()
            for q in self._streams.values():
                q.put_nowait(None)

    # ---------- primitives ----------
    async def request(self, payload: dict, timeout: float = 30) -> dict:
        rid = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self.ws.send(json.dumps({**payload, "req_id": rid}))
        try:
            msg = await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rid, None)
        if "error" in msg:
            raise DerivAPIError(msg["error"])
        return msg

    async def subscribe(self, payload: dict):
        """Async generator yielding every update of a subscription until closed."""
        rid = next(self._ids)
        queue: asyncio.Queue = asyncio.Queue()
        self._streams[rid] = queue
        sub_id = None
        await self.ws.send(json.dumps({**payload, "subscribe": 1, "req_id": rid}))
        try:
            while True:
                msg = await queue.get()
                if msg is None:
                    raise ConnectionError("Deriv connection closed")
                if "error" in msg:
                    raise DerivAPIError(msg["error"])
                sub_id = (msg.get("subscription") or {}).get("id", sub_id)
                yield msg
        finally:
            self._streams.pop(rid, None)
            if sub_id:
                with contextlib.suppress(Exception):
                    await self.request({"forget": sub_id}, timeout=5)

    # ---------- market data ----------
    async def tick_history(self, symbol: str, count: int) -> tuple[list[int], int]:
        """Last digits of the most recent `count` ticks (pages 5000 at a time)."""
        prices: list = []
        end, pip = "latest", None
        while len(prices) < count:
            n = min(5000, count - len(prices))
            resp = await self.request({"ticks_history": symbol, "count": n, "end": end, "style": "ticks"})
            hist = resp["history"]
            pip = resp.get("pip_size", pip)
            if not hist["prices"]:
                break
            prices = hist["prices"] + prices
            end = int(hist["times"][0]) - 1
            if len(hist["prices"]) < n:
                break
        if pip is None:
            pip = _infer_pip_size(prices)
        return [last_digit(p, pip) for p in prices], int(pip)

    # ---------- trading ----------
    async def balance(self) -> float:
        return float((await self.request({"balance": 1}))["balance"]["balance"])

    async def matches_history(self, since_epoch: int | None = None, limit: int = 500) -> list[dict]:
        """Settled DIGITMATCH contracts from the account's profit table, newest first."""
        req = {"profit_table": 1, "description": 1, "limit": limit, "sort": "DESC",
               "contract_type": ["DIGITMATCH"]}
        if since_epoch is not None:
            req["date_from"] = int(since_epoch)
        rows = []
        for t in (await self.request(req))["profit_table"].get("transactions", []):
            symbol, barrier = _parse_shortcode(t.get("shortcode", ""))
            buy, sell = float(t["buy_price"]), float(t.get("sell_price") or 0)
            rows.append({
                "contract_id": t["contract_id"], "purchase_time": int(t["purchase_time"]),
                "symbol": symbol, "predicted": barrier, "stake": buy,
                "payout": float(t["payout"]), "profit": round(sell - buy, 2),
            })
        return rows

    async def matches_proposal(self, symbol: str, digit: int, stake: float, currency: str) -> dict:
        resp = await self.request({
            "proposal": 1, "amount": stake, "basis": "stake",
            "contract_type": "DIGITMATCH", "currency": currency,
            "duration": 1, "duration_unit": "t",
            "symbol": symbol, "barrier": str(digit),
        })
        return resp["proposal"]

    async def buy(self, proposal: dict) -> dict:
        # price = max we are willing to pay; equals the stake for basis=stake.
        resp = await self.request({"buy": proposal["id"], "price": proposal["ask_price"]})
        return resp["buy"]

    async def wait_for_settlement(self, contract_id: int, timeout: float = 60) -> dict:
        gen = self.subscribe({"proposal_open_contract": 1, "contract_id": contract_id})

        async def _wait():
            async for msg in gen:
                poc = msg["proposal_open_contract"]
                if poc.get("is_sold"):
                    return poc

        try:
            return await asyncio.wait_for(_wait(), timeout)
        finally:
            await gen.aclose()
