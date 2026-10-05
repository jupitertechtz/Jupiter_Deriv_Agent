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
import urllib.error
import urllib.request

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
    """Deriv API (2026): REST for accounts + one-time-password WebSocket login.

    With a token: GET /trading/v1/options/accounts picks the demo (or real) account,
    POST .../{account_id}/otp returns an authenticated WebSocket URL.
    Without a token: the public WebSocket (market data only).
    """

    def __init__(self, app_id: str = "", token: str | None = None,
                 endpoint: str = "https://api.derivws.com", account_type: str = "demo"):
        self.base = endpoint.rstrip("/")
        self.app_id = app_id
        self.token = token
        self.account_type = account_type
        self.ws = None
        self.account: dict | None = None
        self.pip_sizes: dict[str, int] = {}
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._streams: dict[int, asyncio.Queue] = {}
        self._reader: asyncio.Task | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # ---------- REST ----------
    def _rest_sync(self, method: str, path: str) -> dict:
        req = urllib.request.Request(self.base + path, method=method, data=b"" if method == "POST" else None,
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Deriv-App-ID": self.app_id,
                                              "Accept": "application/json",
                                              "User-Agent": "jupiter-deriv-agent/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            code = "InvalidToken" if exc.code in (401, 403) else f"HTTP{exc.code}"
            raise DerivAPIError({"code": code, "message": f"{method} {path} -> {exc.code}: {body}"}) from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Could not reach {self.base}: {exc.reason}") from exc

    async def _rest(self, method: str, path: str) -> dict:
        return await asyncio.to_thread(self._rest_sync, method, path)

    # ---------- connection ----------
    async def connect(self):
        if self.token:
            if not self.app_id:
                raise DerivAPIError({"code": "AppIdRequired",
                                     "message": "DERIV_APP_ID must be the App ID registered on developers.deriv.com."})
            accounts = (await self._rest("GET", "/trading/v1/options/accounts")).get("data", [])
            active = [a for a in accounts if a.get("status", "active") == "active"]
            chosen = next((a for a in active if a.get("account_type") == self.account_type), None)
            if chosen is None:
                raise DerivAPIError({"code": "NoAccount",
                                     "message": f"No active {self.account_type} options account for this token."})
            otp = await self._rest("POST", f"/trading/v1/options/accounts/{chosen['account_id']}/otp")
            ws_url = otp["data"]["url"]
            self.account = {"loginid": chosen["account_id"], "is_virtual": chosen["account_type"] == "demo",
                            "currency": chosen.get("currency"), "balance": chosen.get("balance", 0)}
        else:
            ws_url = self.base.replace("https://", "wss://").replace("http://", "ws://") + "/trading/v1/options/ws/public"
        self.ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=20, max_size=2**23)
        self._reader = asyncio.create_task(self._read_loop())
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
    async def tick_prices(self, symbol: str, count: int) -> tuple[list[int], list[float], int]:
        """(epoch times, prices, pip size) for the most recent `count` ticks (pages 5000 at a time)."""
        prices: list = []
        times: list = []
        end, pip = "latest", None
        while len(prices) < count:
            n = min(5000, count - len(prices))
            resp = await self.request({"ticks_history": symbol, "count": n, "end": end, "style": "ticks"})
            hist = resp["history"]
            pip = resp.get("pip_size", pip)
            if not hist["prices"]:
                break
            prices = [float(p) for p in hist["prices"]] + prices
            times = [int(t) for t in hist["times"]] + times
            end = int(hist["times"][0]) - 1
            if len(hist["prices"]) < n:
                break
        if pip is None:
            pip = _infer_pip_size(prices)
        self.pip_sizes[symbol] = int(pip)
        return times, prices, int(pip)

    async def tick_history(self, symbol: str, count: int) -> tuple[list[int], int]:
        """Last digits of the most recent `count` ticks."""
        _, prices, pip = await self.tick_prices(symbol, count)
        return [last_digit(p, pip) for p in prices], pip

    async def active_symbols(self) -> list[dict]:
        return (await self.request({"active_symbols": "brief"}))["active_symbols"]

    async def contracts_for(self, symbol: str) -> list[dict]:
        return (await self.request({"contracts_for": symbol}))["contracts_for"].get("available", [])

    # ---------- trading ----------
    async def balance(self) -> float:
        return float((await self.request({"balance": 1}))["balance"]["balance"])

    async def matches_history(self, since_epoch: int | None = None, limit: int = 500,
                              contract_types: tuple = ("DIGITMATCH", "CALL", "PUT")) -> list[dict]:
        """Settled contracts this app trades (Matches, Rise, Fall) from the profit table, newest first."""
        req = {"profit_table": 1, "description": 1, "limit": limit, "sort": "DESC",
               "contract_type": list(contract_types)}
        if since_epoch is not None:
            req["date_from"] = str(int(since_epoch))
        rows = []
        for t in (await self.request(req))["profit_table"].get("transactions", []):
            sc_symbol, barrier = _parse_shortcode(t.get("shortcode", ""))
            symbol = t.get("underlying_symbol") or sc_symbol
            buy, sell = float(t["buy_price"]), float(t.get("sell_price") or 0)
            rows.append({
                "contract_id": t["contract_id"], "purchase_time": int(t["purchase_time"]),
                "symbol": symbol, "predicted": barrier if t.get("contract_type", "DIGITMATCH") == "DIGITMATCH"
                else {"CALL": "Rise", "PUT": "Fall"}.get(t.get("contract_type"), t.get("contract_type")),
                "contract_type": t.get("contract_type", "DIGITMATCH"), "stake": buy,
                "payout": float(t["payout"]), "profit": round(sell - buy, 2),
            })
        return rows

    async def proposal(self, contract_type: str, symbol: str, stake: float, currency: str,
                       duration: int, duration_unit: str, barrier: str | None = None) -> dict:
        req = {"proposal": 1, "amount": stake, "basis": "stake", "contract_type": contract_type,
               "currency": currency, "duration": int(duration), "duration_unit": duration_unit,
               "underlying_symbol": symbol}
        if barrier is not None:
            req["barrier"] = str(barrier)
        return (await self.request(req))["proposal"]

    async def portfolio(self) -> list[dict]:
        return (await self.request({"portfolio": 1}))["portfolio"].get("contracts", [])

    async def matches_proposal(self, symbol: str, digit: int, stake: float, currency: str) -> dict:
        resp = await self.request({
            "proposal": 1, "amount": stake, "basis": "stake",
            "contract_type": "DIGITMATCH", "currency": currency,
            "duration": 1, "duration_unit": "t",
            "underlying_symbol": symbol, "barrier": str(digit),
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
