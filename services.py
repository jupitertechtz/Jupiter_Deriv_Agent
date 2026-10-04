"""Short, stateless operations for the web app (Vercel functions can't hold a loop open).

Risk state is rebuilt from the account's own Deriv profit table on every call,
so daily caps hold across separate requests without a database.
"""
import asyncio
import contextlib
import dataclasses
from datetime import datetime, timezone

from analyzer import STRATEGIES, DigitAnalyzer
from config import LIVE_CONFIRM_PHRASE, Settings
from deriv_client import VOLATILITY_SYMBOLS, DerivAPIError, DerivClient, last_digit
from journal import stats_from_rows, verdict
from risk import RiskManager
from stats import chisquare_uniform

FATAL_CODES = {"InsufficientBalance", "InvalidToken", "AuthorizationRequired", "PermissionDenied"}


def _start_of_utc_day() -> int:
    now = datetime.now(timezone.utc)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def _for_account(s: Settings, account_type: str | None) -> Settings:
    """Settings for the requested account. Real money needs the server-side confirmation phrase."""
    account_type = account_type or s.account_type
    if account_type not in ("demo", "real"):
        raise ValueError("Account must be 'demo' or 'real'.")
    if account_type == "real" and s.live_trading_confirm != LIVE_CONFIRM_PHRASE:
        raise PermissionError("Live trading is switched off on the server. To allow it, set the Vercel environment "
                              "variable LIVE_TRADING_CONFIRM to the exact phrase in config.py and redeploy.")
    return dataclasses.replace(s, account_type=account_type)


def with_overrides(s: Settings, stake: float | None = None, daily_loss_limit: float | None = None,
                   max_losses_in_row: int | None = None, max_trades_per_day: int | None = None) -> Settings:
    """Apply dashboard-chosen limits, within the server's ceilings."""
    changes = {}
    if stake is not None:
        stake = round(float(stake), 2)
        if not s.min_stake <= stake <= s.max_stake:
            raise ValueError(f"Stake must be between {s.min_stake:.2f} and {s.max_stake:.2f}.")
        changes["stake"] = stake
    if daily_loss_limit is not None:
        daily_loss_limit = round(float(daily_loss_limit), 2)
        if not 0 < daily_loss_limit <= s.max_daily_loss_ceiling:
            raise ValueError(f"Daily loss limit must be above 0 and at most {s.max_daily_loss_ceiling:,.2f}.")
        changes["max_daily_loss"] = daily_loss_limit
    if max_losses_in_row is not None:
        if not 1 <= int(max_losses_in_row) <= s.max_losses_in_row_ceiling:
            raise ValueError(f"Losses in a row must be between 1 and {s.max_losses_in_row_ceiling:,}.")
        changes["max_consecutive_losses"] = int(max_losses_in_row)
    if max_trades_per_day is not None:
        if not 1 <= int(max_trades_per_day) <= s.max_trades_per_day_ceiling:
            raise ValueError(f"Trades per day must be between 1 and {s.max_trades_per_day_ceiling:,}.")
        changes["max_trades_per_session"] = int(max_trades_per_day)
    return dataclasses.replace(s, **changes) if changes else s


def counting_start(count_since: int | None) -> int:
    """Counters run from midnight UTC, or from a later reset the user made today."""
    day = _start_of_utc_day()
    return max(day, int(count_since)) if count_since else day


def _losses_in_row(rows_newest_first) -> int:
    n = 0
    for r in rows_newest_first:
        if r["profit"] > 0:
            break
        n += 1
    return n


async def match_probability(s: Settings, symbol: str, stake: float | None = None) -> dict:
    """What the agent would bet on right now, and the honest odds and payout for that bet."""
    s = with_overrides(s, stake=stake)
    token = s.api_token or None
    async with DerivClient(s.app_id, token, s.api_base, s.account_type) as client:
        digits, _ = await client.tick_history(symbol, s.window)
        analyzer = DigitAnalyzer(s.window)
        analyzer.extend(digits)
        digit = STRATEGIES[s.strategy](analyzer)
        payout = None
        with contextlib.suppress(DerivAPIError):
            payout = float((await client.matches_proposal(symbol, digit, s.stake, s.currency))["payout"])
    freqs = analyzer.frequencies()
    out = {
        "symbol": symbol, "strategy": s.strategy, "digit": digit, "ticks": analyzer.n,
        "frequencies": freqs, "recent_frequency": freqs[digit], "probability": 0.10,
        "uniformity_p": analyzer.uniformity_p_value(), "stake": s.stake, "payout": payout,
    }
    if payout:
        out.update({
            "profit_if_win": round(payout - s.stake, 2),
            "breakeven_rate": s.stake / payout,
            "expected_per_trade": round(0.10 * payout - s.stake, 4),
            "expected_per_100": round(100 * (0.10 * payout - s.stake), 2),
        })
    return out


async def scan_payouts(client: DerivClient, s: Settings) -> list[dict]:
    """Live Matches payout for every Volatility index at the current stake, best first.

    Every digit has a 1-in-10 chance on every market; payout is the only real difference."""
    async def one(sym):
        try:
            prop = await client.matches_proposal(sym, 5, s.stake, s.currency)
            payout = float(prop["payout"])
            return {"symbol": sym, "payout": payout, "breakeven_rate": s.stake / payout,
                    "expected_per_trade": round(0.10 * payout - s.stake, 4)}
        except DerivAPIError as exc:
            return {"symbol": sym, "payout": None, "error": str(exc)}
    rows = await asyncio.gather(*(one(sym) for sym in VOLATILITY_SYMBOLS))
    return sorted(rows, key=lambda r: -(r["payout"] or 0))


def pick_market(scan: list[dict], previous: str | None) -> str | None:
    """Highest payout wins. Markets tied at the top payout take turns, in list order."""
    paying = [r for r in scan if r.get("payout")]
    if not paying:
        return None
    top = max(r["payout"] for r in paying)
    tied = [r["symbol"] for r in paying if r["payout"] >= top - 0.005]
    tied.sort(key=VOLATILITY_SYMBOLS.index)
    if previous in tied:
        return tied[(tied.index(previous) + 1) % len(tied)]
    return tied[0]


async def market_payouts(s: Settings, stake: float | None = None) -> dict:
    s = with_overrides(s, stake=stake)
    async with DerivClient(s.app_id, s.api_token or None, s.api_base, s.account_type) as client:
        rows = await scan_payouts(client, s)
    paying = [r["payout"] for r in rows if r.get("payout")]
    top = max(paying) if paying else None
    for r in rows:
        r["best"] = bool(top and r.get("payout") and r["payout"] >= top - 0.005)
    return {"stake": s.stake, "markets": rows, "all_equal": bool(paying) and max(paying) - min(paying) < 0.005}


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


async def account_results(s: Settings, limit: int = 500, account_type: str | None = None,
                          count_since: int | None = None) -> dict:
    account_type = account_type or s.account_type
    if account_type not in ("demo", "real"):
        raise ValueError("Account must be 'demo' or 'real'.")
    s = dataclasses.replace(s, account_type=account_type)  # viewing real results is read-only, no phrase needed
    async with DerivClient(s.app_id, s.api_token, s.api_base, s.account_type) as client:
        account = _account_info(client.account)
        rows = await client.matches_history(limit=limit)
        since = counting_start(count_since)
        today = await client.matches_history(since_epoch=since, limit=500)
    st = stats_from_rows(rows)
    if st["trades"]:
        st["verdict"] = verdict(st)
    return {"account": account, "stats": st,
            "today": {"trades": len(today), "pnl": round(sum(r["profit"] for r in today), 2),
                      "losses_in_row": _losses_in_row(today), "counting_since": since},
            "recent": rows[:50]}


async def run_session(s: Settings, symbol: str | None = None, max_trades: int | None = None,
                      account_type: str | None = None, stake: float | None = None,
                      daily_loss_limit: float | None = None, max_losses_in_row: int | None = None,
                      max_trades_per_day: int | None = None, count_since: int | None = None,
                      last_symbol: str | None = None) -> dict:
    """One capped run. symbol="auto" re-checks every market's payout during the run and trades the
    best-paying one, rotating through markets that tie for the best payout."""
    s = with_overrides(_for_account(s, account_type), stake=stake, daily_loss_limit=daily_loss_limit,
                       max_losses_in_row=max_losses_in_row, max_trades_per_day=max_trades_per_day)
    since = counting_start(count_since)
    symbol = symbol or s.symbols[0]
    auto = symbol == "auto"
    max_trades = max(1, min(max_trades or s.session_max_trades, 50))
    strategy = STRATEGIES[s.strategy]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + s.session_time_budget

    async with DerivClient(s.app_id, s.api_token, s.api_base, s.account_type) as client:
        info = _account_info(client.account)
        if not info["is_virtual"] and s.live_trading_confirm != LIVE_CONFIRM_PHRASE:
            raise PermissionError("This token belongs to a REAL-money account. Sessions only run on the demo "
                                  "account unless LIVE_TRADING_CONFIRM is set to the exact phrase in config.py.")
        s = dataclasses.replace(s, currency=info["currency"] or s.currency)

        # Rebuild today's risk state from Deriv, oldest first.
        risk = RiskManager(s)
        for r in reversed(await client.matches_history(since_epoch=since)):
            risk.record(r["profit"])
        trades_before = risk.session_trades
        risk.session_pnl, risk.session_wins = 0.0, 0

        trades, errors, switches = [], [], []
        scan, current = None, (last_symbol if auto else symbol)
        analyzer = DigitAnalyzer(s.window)
        feeder, new_tick = None, asyncio.Event()

        if not auto:
            analyzer.extend((await client.tick_history(symbol, s.window))[0])

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

        stop_reason = f"reached {max_trades} trades for this run"
        attempts = 0
        try:
            while len(trades) < max_trades:
                if deadline - loop.time() < 12:
                    stop_reason = "time budget for this run used up"
                    break
                ok, reason = risk.can_trade()
                if not ok:
                    stop_reason = reason
                    break

                if auto:
                    if scan is None or attempts % max(1, s.auto_rescan_every) == 0:
                        scan = await scan_payouts(client, s)
                    chosen = pick_market(scan, current)
                    if chosen is None:
                        stop_reason = "no market is offering a payout right now"
                        break
                    if chosen != current:
                        switches.append({"to": chosen, "payout": next(r["payout"] for r in scan if r["symbol"] == chosen)})
                    current = chosen
                    # fresh recent digits for the chosen market
                    analyzer = DigitAnalyzer(s.window)
                    analyzer.extend((await client.tick_history(current, s.window))[0])
                else:
                    for _ in range(max(1, s.session_trade_every_n_ticks)):
                        new_tick.clear()
                        await asyncio.wait_for(new_tick.wait(), timeout=10)
                attempts += 1

                digit = strategy(analyzer)
                try:
                    prop = await client.matches_proposal(current, digit, s.stake, s.currency)
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
                trades.append({"contract_id": bought["contract_id"], "symbol": current, "predicted": digit,
                               "exit_digit": last_digit(exit_val, client.pip_sizes.get(current, 2)) if exit_val is not None else None,
                               "stake": float(bought["buy_price"]), "payout": float(bought["payout"]),
                               "profit": round(profit, 2), "status": poc.get("status")})
        except asyncio.TimeoutError:
            stop_reason = "tick stream went quiet"
        finally:
            if feeder:
                feeder.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await feeder
        with contextlib.suppress(Exception):
            info["balance"] = await client.balance()

    used = {}
    for t in trades:
        used[t["symbol"]] = used.get(t["symbol"], 0) + 1
    return {
        "account": info, "symbol": current or symbol, "auto_selected": auto, "market_scan": scan,
        "markets_used": used, "switches": switches,
        "strategy": s.strategy, "stake": s.stake, "stop_reason": stop_reason,
        "can_continue": stop_reason.startswith("reached") or stop_reason.startswith("time budget"),
        "trades": trades, "errors": errors,
        "run": {"trades": len(trades), "wins": sum(t["profit"] > 0 for t in trades),
                "pnl": round(sum(t["profit"] for t in trades), 2)},
        "today": {"trades": trades_before + len(trades), "pnl": round(risk.daily_pnl, 2),
                  "daily_loss_cap": s.max_daily_loss, "daily_trade_cap": s.max_trades_per_session,
                  "losses_in_row": risk.consecutive_losses, "losses_in_row_cap": s.max_consecutive_losses,
                  "counting_since": since},
    }
