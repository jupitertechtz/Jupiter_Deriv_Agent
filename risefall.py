"""Rise/Fall (CALL/PUT) on any market that offers it: forex, commodities, stock indices, crypto
(where Deriv offers options on it) and synthetic indices.

Contracts that end within MAX_WAIT_SECONDS are waited on and settled inside the run. Longer
contracts (common on forex, often minutes) are bought and tracked: they settle on Deriv and
appear in results later. Until then their stake counts as a potential loss against the daily
loss limit, using the account's open positions.
"""
import asyncio
import contextlib
import dataclasses

from config import LIVE_CONFIRM_PHRASE, Settings
from deriv_client import DerivAPIError, DerivClient
from direction import (DIRECTION_STRATEGIES, DirectionEngine, backtest_direction, params_from_settings,
                       simple_direction)
from markets import check_risefall_duration, find, get_catalog, to_seconds
from risk import RiskManager
from services import FATAL_CODES, _account_info, pick_market

APP_TYPES = ("CALL", "PUT", "DIGITMATCH")


def _label(duration: int, unit: str) -> str:
    return f"{duration} {dict(t='tick', s='second', m='minute', h='hour')[unit]}{'' if duration == 1 else 's'}"


async def resolve(s: Settings, symbol: str, duration: int, unit: str, need_open: bool = True) -> dict:
    cat = await get_catalog(s)
    market = find(cat, symbol)
    if market is None or not market["risefall"]:
        raise ValueError(f"'{symbol}' does not offer Rise/Fall on this account.")
    check_risefall_duration(market, duration, unit)
    if need_open and not market["open"]:
        raise ValueError(f"{market['name']} is closed right now (financial markets close outside trading hours "
                         f"and at weekends).")
    return market


async def auto_markets(s: Settings, duration: int, unit: str) -> list[dict]:
    cat = await get_catalog(s)
    out = []
    for m in cat["markets"]:
        if not (m["risefall"] and m["open"]):
            continue
        try:
            check_risefall_duration(m, duration, unit)
            out.append(m)
        except ValueError:
            pass
    return out


async def _payout(client, s, symbol, duration, unit):
    try:
        prop = await client.proposal("CALL", symbol, s.stake, s.currency, duration, unit)
        return float(prop["payout"])
    except DerivAPIError:
        return None


async def _history(client: DerivClient, s: Settings, symbol: str, duration: int, unit: str):
    """Enough history for the engine to reach its minimum number of non-overlapping predictions."""
    times, prices, pip = await client.tick_prices(symbol, s.direction_history)
    if len(times) > 1:
        interval = max(0.2, (times[-1] - times[0]) / (len(times) - 1))
        per_pred = (duration + 2) if unit == "t" else to_seconds(duration, unit) / interval + 2
        needed = min(30000, int(s.direction_min_samples * per_pred * 1.3))
        if needed > len(times):
            times, prices, pip = await client.tick_prices(symbol, needed)
    return times, prices


async def direction_report(s: Settings, symbol: str, duration: int, unit: str) -> dict:
    market = await resolve(s, symbol, duration, unit, need_open=False)
    async with DerivClient(s.app_id, s.api_token or None, s.api_base, s.account_type) as client:
        (times, prices), payout = await asyncio.gather(_history(client, s, symbol, duration, unit),
                                                       _payout(client, s, symbol, duration, unit))
    breakeven = s.stake / payout if payout else 0.5
    ev = DirectionEngine(duration, unit, params_from_settings(s)).fit(times, prices, breakeven).evaluate(breakeven)
    ev.update({"symbol": symbol, "name": market["name"], "category": market["category"], "open": market["open"],
               "payout": payout, "stake": s.stake, "ticks": len(prices), "duration": _label(duration, unit),
               "breakeven_known": bool(payout)})
    return ev


async def backtest_risefall(s: Settings, symbol: str, duration: int, unit: str, ticks: int) -> dict:
    market = await resolve(s, symbol, duration, unit, need_open=False)
    async with DerivClient(s.app_id, s.api_token or None, s.api_base, s.account_type) as client:
        times, prices, _ = await client.tick_prices(symbol, ticks)
        payout = await _payout(client, s, symbol, duration, unit)
    if not payout:
        raise ValueError(f"Deriv gave no Rise/Fall payout for {market['name']} at {_label(duration, unit)} "
                         f"(the market may be closed).")
    p = params_from_settings(s)
    results = [backtest_direction(times, prices, "adaptive", duration, unit, s.stake, payout, p, gated=True),
               backtest_direction(times, prices, "adaptive", duration, unit, s.stake, payout, p, gated=False)]
    results += [backtest_direction(times, prices, x, duration, unit, s.stake, payout, p)
                for x in ("momentum", "reversal", "random")]
    return {"contract": "risefall", "symbol": symbol, "name": market["name"], "ticks": len(prices),
            "duration": _label(duration, unit), "stake": s.stake, "payout": payout,
            "breakeven_rate": s.stake / payout, "chance": 0.5, "results": results}


async def run_risefall_session(s: Settings, symbol: str, duration: int, unit: str, max_trades: int,
                               since: int, last_symbol: str | None = None) -> dict:
    if s.strategy not in DIRECTION_STRATEGIES:
        raise ValueError(f"For Rise/Fall choose one of: {', '.join(DIRECTION_STRATEGIES)}.")
    auto = symbol == "auto"
    if auto:
        candidates = await auto_markets(s, duration, unit)
        if not candidates:
            raise ValueError(f"No open market offers Rise/Fall at {_label(duration, unit)} right now.")
    else:
        candidates = [await resolve(s, symbol, duration, unit)]

    loop = asyncio.get_running_loop()
    deadline = loop.time() + s.session_time_budget
    params = params_from_settings(s)

    async with DerivClient(s.app_id, s.api_token, s.api_base, s.account_type) as client:
        info = _account_info(client.account)
        if not info["is_virtual"] and s.live_trading_confirm != LIVE_CONFIRM_PHRASE:
            raise PermissionError("This token belongs to a REAL-money account. Sessions only run on the demo "
                                  "account unless LIVE_TRADING_CONFIRM is set to the exact phrase in config.py.")
        s = dataclasses.replace(s, currency=info["currency"] or s.currency)

        risk = RiskManager(s)
        for r in reversed(await client.matches_history(since_epoch=since)):
            risk.record(r["profit"])
        trades_before = risk.session_trades
        risk.session_pnl, risk.session_wins = 0.0, 0
        exposure = 0.0
        with contextlib.suppress(DerivAPIError):
            exposure = sum(float(c.get("buy_price") or 0) for c in await client.portfolio()
                           if c.get("contract_type") in APP_TYPES)

        # payouts; in auto mode keep the 10 best-paying open markets
        sem = asyncio.Semaphore(10)

        async def lim(coro):
            async with sem:
                return await coro
        pays = await asyncio.gather(*(lim(_payout(client, s, m["symbol"], duration, unit)) for m in candidates))
        priced = sorted(((m, p) for m, p in zip(candidates, pays) if p), key=lambda mp: -mp[1])
        if not priced:
            raise ValueError("No candidate market returned a Rise/Fall payout right now.")
        if auto:
            priced = priced[:10]
        names = {m["symbol"]: m["name"] for m, _ in priced}
        syms = [m["symbol"] for m, _ in priced]
        breakeven = {m["symbol"]: s.stake / p for m, p in priced}
        scan = [{"symbol": m["symbol"], "payout": p} for m, p in priced]

        adaptive = s.strategy == "adaptive"
        hist = await asyncio.gather(*(lim(_history(client, s, x, duration, unit) if adaptive
                                          else client.tick_prices(x, 300)) for x in syms))
        engines = {}
        tick_secs = {}
        for x, h in zip(syms, hist):
            times, prices = h[0], h[1]
            engines[x] = DirectionEngine(duration, unit, params).fit(times, prices, breakeven[x] if adaptive else None)
            tick_secs[x] = max(0.2, (times[-1] - times[0]) / max(1, len(times) - 1)) if len(times) > 1 else 2.0

        tick = asyncio.Event()

        async def feed(x):
            gen = client.subscribe({"ticks": x})
            try:
                async for msg in gen:
                    t = msg["tick"]
                    engines[x].update(float(t.get("epoch") or loop.time()), float(t["quote"]))
                    tick.set()
            finally:
                with contextlib.suppress(Exception):
                    await gen.aclose()

        feeders = [asyncio.create_task(feed(x)) for x in syms]
        trades, errors, skips = [], [], {}
        checks = 0
        current = last_symbol
        stop_reason = f"reached {max_trades} trades for this run"
        try:
            while len(trades) < max_trades:
                if deadline - loop.time() < 12:
                    stop_reason = "time budget for this run used up" + \
                        ("" if trades or not adaptive else ": no market passed the evidence gate")
                    break
                ok, reason = risk.can_trade()
                if ok and risk.daily_pnl - exposure - s.stake < -s.max_daily_loss:
                    ok, reason = False, (f"daily loss limit: settled P&L {risk.daily_pnl:+.2f} plus {exposure:.2f} "
                                         f"still open could exceed -{s.max_daily_loss:.2f}")
                if not ok:
                    stop_reason = reason
                    break
                tick.clear()
                await asyncio.wait_for(tick.wait(), timeout=15)
                checks += 1
                if adaptive:
                    evals = {x: engines[x].evaluate(breakeven[x], fast=True) for x in syms}
                    ready = [x for x in syms if evals[x]["decision"] == "TRADE"]
                    if not ready:
                        top = max(syms, key=lambda x: evals[x]["score"])
                        skips[evals[top]["gate"]] = skips.get(evals[top]["gate"], 0) + 1
                        continue
                    sym = max(ready, key=lambda x: evals[x]["score"])
                    direction = 1 if evals[sym]["direction"] == "RISE" else -1
                else:
                    sym = pick_market(scan, current, syms) if auto else syms[0]
                    direction = simple_direction(s.strategy, engines[sym])
                current = sym
                ctype = "CALL" if direction > 0 else "PUT"
                est = to_seconds(duration, unit, tick_secs[sym])
                wait = est <= s.max_wait_seconds and est + 8 < deadline - loop.time()
                try:
                    prop = await client.proposal(ctype, sym, s.stake, s.currency, duration, unit)
                    bought = await client.buy(prop)
                    poc = await client.wait_for_settlement(
                        bought["contract_id"], timeout=max(5, min(est + 15, deadline - loop.time() - 2))) if wait else None
                except DerivAPIError as exc:
                    errors.append(str(exc))
                    risk.record_error(fatal_reason=str(exc) if exc.code in FATAL_CODES else None)
                    continue
                except asyncio.TimeoutError:
                    errors.append("A contract did not settle in time; it is tracked on Deriv and will appear in results.")
                    exposure += s.stake
                    trades.append({"contract_id": None, "symbol": sym, "direction": "Rise" if direction > 0 else "Fall",
                                   "duration": _label(duration, unit), "stake": s.stake, "payout": None,
                                   "profit": None, "status": "open"})
                    continue
                trade = {"contract_id": bought["contract_id"], "symbol": sym,
                         "direction": "Rise" if direction > 0 else "Fall", "duration": _label(duration, unit),
                         "stake": float(bought["buy_price"]), "payout": float(bought["payout"])}
                if poc is not None:
                    profit = float(poc["profit"])
                    risk.record(profit)
                    trade.update({"profit": round(profit, 2), "status": poc.get("status")})
                else:
                    exposure += float(bought["buy_price"])
                    risk.session_trades += 1          # counts toward the trade limits now; P&L comes later
                    trade.update({"profit": None, "status": "open"})
                trades.append(trade)
        except asyncio.TimeoutError:
            stop_reason = "no new ticks for 15 seconds (the market may have closed)"
        finally:
            for f in feeders:
                f.cancel()
            await asyncio.gather(*feeders, return_exceptions=True)
        final = {x: engines[x].evaluate(breakeven[x]) for x in syms} if adaptive else {}
        with contextlib.suppress(Exception):
            info["balance"] = await client.balance()

    settled = [t for t in trades if t["profit"] is not None]
    used = {}
    for t in trades:
        used[t["symbol"]] = used.get(t["symbol"], 0) + 1
    order = {"TRADE": 0, "WAIT": 1, "SKIP": 2}
    engine = None
    if adaptive:
        engine = {"checks": checks, "skipped_because": skips,
                  "latest": sorted(({"symbol": x, "name": names[x], **{k: final[x][k] for k in (
                      "decision", "gate", "reason", "direction", "p_dir", "walk_forward_accuracy", "samples",
                      "entropy", "luck_p", "score", "breakeven")}} for x in syms),
                      key=lambda r: (order[r["decision"]], -r["score"]))}
    return {
        "contract": "risefall", "account": info, "symbol": trades[-1]["symbol"] if trades else (None if auto else syms[0]),
        "auto_selected": auto, "markets_used": used, "names": names, "strategy": s.strategy, "stake": s.stake,
        "duration": _label(duration, unit), "stop_reason": stop_reason,
        "can_continue": stop_reason.startswith("reached") or stop_reason.startswith("time budget"),
        "trades": trades, "errors": errors, "engine": engine, "open_exposure": round(exposure, 2),
        "run": {"trades": len(trades), "settled": len(settled), "open": len(trades) - len(settled),
                "wins": sum(t["profit"] > 0 for t in settled), "pnl": round(sum(t["profit"] for t in settled), 2)},
        "today": {"trades": trades_before + len(trades), "pnl": round(risk.daily_pnl, 2),
                  "daily_loss_cap": s.max_daily_loss, "daily_trade_cap": s.max_trades_per_session,
                  "losses_in_row": risk.consecutive_losses, "losses_in_row_cap": s.max_consecutive_losses,
                  "counting_since": since, "open_exposure": round(exposure, 2)},
    }
