"""Short, stateless operations for the web app (Vercel functions can't hold a loop open).

Risk state is rebuilt from the account's own Deriv profit table on every call,
so daily caps hold across separate requests without a database.
"""
import asyncio
import contextlib
from datetime import datetime, timezone

from analyzer import STRATEGIES, DigitAnalyzer
from config import LIVE_CONFIRM_PHRASE, Settings
from deriv_client import DerivAPIError, DerivClient, last_digit
from journal import stats_from_rows, verdict
from risk import RiskManager
from stats import chisquare_uniform

FATAL_CODES = {"InsufficientBalance", "InvalidToken", "AuthorizationRequired", "PermissionDenied"}


def _start_of_utc_day() -> int:
    now = datetime.now(timezone.utc)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def _account_info(acct: dict) -> dict:
    return {"loginid": acct.get("loginid"), "is_virtual": bool(acct.get("is_virtual")),
            "currency": acct.get("currency"), "balance": float(acct.get("balance", 0))}


async def analyze_markets(s: Settings, symbols: list[str], ticks: int) -> dict:
    async with DerivClient(s.app_id, endpoint=s.api_base) as client:
        histories = await asyncio.gather(*(client.tick_history(sym, ticks) for sym in symbols))
    k = len(symbols)
    threshold = 0.05 / max(k, 1)
    markets = []
    for sym, (digits, _) in zip(symbols, histories):
        counts = [0] * 10
        for d in digits:
            counts[d] += 1
        n = len(digits)
        _, p = chisquare_uniform(counts) if n >= 50 else (0, None)
        markets.append({"symbol": sym, "ticks": n,
                        "frequencies": [c / n if n else 0 for c in counts],
                        "p_value": p, "flagged": p is not None and p < threshold})
    markets.sort(key=lambda m: m["p_value"] if m["p_value"] is not None else 1.0)
    return {"markets": markets, "threshold": threshold,
            "chance_of_false_alarm": 1 - 0.95 ** k}


async def account_results(s: Settings, limit: int = 500) -> dict:
    async with DerivClient(s.app_id, s.api_token, s.api_base, s.account_type) as client:
        account = _account_info(client.account)
        rows = await client.matches_history(limit=limit)
        today = await client.matches_history(since_epoch=_start_of_utc_day(), limit=500)
    st = stats_from_rows(rows)
    if st["trades"]:
        st["verdict"] = verdict(st)
    return {"account": account, "stats": st,
            "today": {"trades": len(today), "pnl": round(sum(r["profit"] for r in today), 2)},
            "recent": rows[:50]}


async def run_session(s: Settings, symbol: str | None = None, max_trades: int | None = None) -> dict:
    symbol = symbol or s.symbols[0]
    max_trades = max(1, min(max_trades or s.session_max_trades, 50))
    strategy = STRATEGIES[s.strategy]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + s.session_time_budget

    async with DerivClient(s.app_id, s.api_token, s.api_base, s.account_type) as client:
        acct = client.account
        info = _account_info(acct)
        if not info["is_virtual"] and s.live_trading_confirm != LIVE_CONFIRM_PHRASE:
            raise PermissionError("This token belongs to a REAL-money account. Sessions only run on the demo "
                                  "(VRTC) account unless LIVE_TRADING_CONFIRM is set to the exact phrase in config.py.")
        currency = info["currency"] or s.currency

        # Rebuild today's risk state from Deriv, oldest first.
        risk = RiskManager(s)
        for r in reversed(await client.matches_history(since_epoch=_start_of_utc_day())):
            risk.record(r["profit"])
        trades_before = risk.session_trades
        risk.session_pnl, risk.session_wins = 0.0, 0

        analyzer = DigitAnalyzer(s.window)
        digits, _ = await client.tick_history(symbol, s.window)
        analyzer.extend(digits)
        new_tick = asyncio.Event()

        async def feed():
            gen = client.subscribe({"ticks": symbol})
            try:
                async for msg in gen:
                    analyzer.add(last_digit(msg["tick"]["quote"], msg["tick"]["pip_size"]))
                    new_tick.set()
            finally:
                with contextlib.suppress(Exception):
                    await gen.aclose()

        feeder = asyncio.create_task(feed())
        trades, errors = [], []
        stop_reason = f"reached {max_trades} trades for this run"
        try:
            while len(trades) < max_trades:
                remaining = deadline - loop.time()
                if remaining < 12:
                    stop_reason = "time budget for this run used up"
                    break
                ok, reason = risk.can_trade()
                if not ok:
                    stop_reason = reason
                    break
                for _ in range(max(1, s.session_trade_every_n_ticks)):
                    new_tick.clear()
                    await asyncio.wait_for(new_tick.wait(), timeout=10)
                digit = strategy(analyzer)
                try:
                    prop = await client.matches_proposal(symbol, digit, s.stake, currency)
                    bought = await client.buy(prop)
                    poc = await client.wait_for_settlement(bought["contract_id"],
                                                           timeout=max(5, min(30, deadline - loop.time() - 2)))
                except DerivAPIError as exc:
                    errors.append(str(exc))
                    risk.record_error(fatal_reason=str(exc) if exc.code in FATAL_CODES else None)
                    continue
                except asyncio.TimeoutError:
                    errors.append("A contract did not settle in time; check your Deriv statement.")
                    stop_reason = "contract settlement timed out"
                    break
                profit = float(poc["profit"])
                risk.record(profit)
                exit_val = poc.get("exit_spot")
                trades.append({"contract_id": bought["contract_id"], "symbol": symbol, "predicted": digit,
                               "exit_digit": last_digit(exit_val, client.pip_sizes.get(symbol, 2)) if exit_val is not None else None,
                               "stake": float(bought["buy_price"]), "payout": float(bought["payout"]),
                               "profit": round(profit, 2), "status": poc.get("status")})
        except asyncio.TimeoutError:
            stop_reason = "tick stream went quiet"
        finally:
            feeder.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await feeder
        with contextlib.suppress(Exception):
            info["balance"] = await client.balance()

    return {
        "account": info, "symbol": symbol, "strategy": s.strategy, "stop_reason": stop_reason,
        "trades": trades, "errors": errors,
        "run": {"trades": len(trades), "wins": sum(t["profit"] > 0 for t in trades),
                "pnl": round(sum(t["profit"] for t in trades), 2)},
        "today": {"trades": trades_before + len(trades), "pnl": round(risk.daily_pnl, 2),
                  "daily_loss_cap": s.max_daily_loss, "daily_trade_cap": s.max_trades_per_session},
    }
