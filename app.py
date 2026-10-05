"""FastAPI web layer for Vercel: dashboard + short, capped trading sessions.

Contracts:
  matches   Digit Matches on synthetic indices that offer digits (Adaptive Digit Engine or simple strategies)
  risefall  Rise/Fall on forex, commodities, stock indices, crypto (where offered) and synthetics
            (Adaptive Direction Engine or simple strategies)
"""
import hmac

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import HTMLResponse

from analyzer import STRATEGIES
from backtest import BACKTEST_STRATEGIES, run_backtest, run_backtest_best_payout
from config import LIVE_CONFIRM_PHRASE, Settings
from dashboard import DASHBOARD_HTML
from deriv_client import DerivAPIError
from direction import DIRECTION_STRATEGIES
from markets import find, get_catalog
from live import live_snapshot
import tuning
from risefall import backtest_risefall, direction_report, run_risefall_session
from services import (AUTO_GROUPS, DIGIT_STRATEGIES, SESSION_STRATEGIES, _for_account, account_results,
                      analyze_markets, counting_start, digit_symbols, engine_report, engine_scan, market_payouts,
                      match_probability, run_session, with_overrides)

app = FastAPI(title="Jupiter Deriv Agent", docs_url="/api/docs", openapi_url="/api/openapi.json")
BASE = Settings()


def cfg(x_tuning: str | None = Header(None)) -> Settings:
    """Settings for this request: Vercel environment defaults plus the dashboard's validated adjustments."""
    try:
        return tuning.apply(BASE, x_tuning)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"Settings: {exc}") from exc
UNITS = "^(t|s|m|h)$"


async def _digit_symbol(symbol: str, settings: Settings) -> str:
    cat = await get_catalog(settings)
    m = find(cat, symbol)
    if m is None or not m["digits"]:
        raise HTTPException(400, f"'{symbol}' does not offer Digit Matches. Digit contracts exist only on "
                                 f"synthetic indices; use Rise/Fall for forex, commodities, stock indices and crypto.")
    return symbol


def _require_key(key: str | None) -> None:
    settings = BASE
    if not settings.session_key:
        raise HTTPException(503, "SESSION_KEY is not set in the Vercel project's environment variables.")
    if not key or not hmac.compare_digest(key, settings.session_key):
        raise HTTPException(401, "Session key is missing or wrong.")


def _require_token() -> None:
    if not BASE.api_token:
        raise HTTPException(503, "DERIV_API_TOKEN is not set in the Vercel project's environment variables.")


def _stake(stake, settings: Settings):
    try:
        return with_overrides(settings, stake=stake)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


async def _call(coro):
    try:
        return await coro
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except DerivAPIError as exc:
        raise HTTPException(502, f"Deriv API error {exc}") from exc
    except (ConnectionError, OSError, TimeoutError) as exc:
        raise HTTPException(502, f"Could not reach Deriv: {exc}") from exc


@app.get("/", response_class=HTMLResponse)
async def dashboard(settings: Settings = Depends(cfg)):
    return DASHBOARD_HTML


@app.get("/api/health")
async def health(settings: Settings = Depends(cfg)):
    s = settings
    return {
        "token_configured": bool(s.api_token), "app_id_configured": bool(s.app_id),
        "session_key_configured": bool(s.session_key), "account_type": s.account_type,
        "live_enabled": s.live_trading_confirm == LIVE_CONFIRM_PHRASE,
        "cron_configured": bool(s.cron_secret), "symbols": list(s.symbols),
        "strategy": s.strategy, "strategies": list(DIGIT_STRATEGIES), "digit_strategies": list(DIGIT_STRATEGIES),
        "direction_strategies": list(DIRECTION_STRATEGIES), "stake": s.stake,
        "min_stake": s.min_stake, "max_stake": s.max_stake, "max_daily_loss_ceiling": s.max_daily_loss_ceiling,
        "max_losses_in_row_ceiling": s.max_losses_in_row_ceiling, "max_trades_per_day_ceiling": s.max_trades_per_day_ceiling,
        "max_wait_seconds": s.max_wait_seconds,
        "engine": {"history": s.adaptive_history, "min_samples": s.adaptive_min_samples, "max_p": s.adaptive_max_p,
                   "min_edge": s.adaptive_min_edge, "max_entropy": s.adaptive_max_entropy,
                   "persistence": s.adaptive_persistence},
        "limits": {"max_daily_loss": s.max_daily_loss, "max_trades_per_day": s.max_trades_per_session,
                   "max_consecutive_losses": s.max_consecutive_losses, "trades_per_run": s.session_max_trades},
    }


@app.get("/api/settings")
async def settings_schema():
    """Adjustable settings: label, help, allowed range, default (from the Vercel environment), and
    whether lowering or raising the value loosens the evidence gate."""
    return {"fields": tuning.schema(BASE), "presets": tuning.PRESETS, "gate_keys": list(tuning.GATE_KEYS)}


@app.get("/api/markets")
async def markets(refresh: bool = False, settings: Settings = Depends(cfg)):
    """Every market on this account with what it offers: Digit Matches and/or Rise/Fall (with durations)."""
    cat = await get_catalog(settings, refresh=refresh)
    return {"source": cat["source"], "built": cat["built"], "markets": cat["markets"]}


@app.get("/api/analyze")
async def analyze(ticks: int = Query(2000, ge=100, le=5000), symbols: str | None = None,
                  group: str = Query("all", pattern="^(all|volatility)$"),
                  settings: Settings = Depends(cfg)):
    syms = [await _digit_symbol(x.strip(), settings) for x in symbols.split(",")] if symbols else \
        await digit_symbols(settings, group)
    return await _call(analyze_markets(settings, syms, ticks))


@app.get("/api/backtest")
async def backtest(symbol: str = "R_100", ticks: int = Query(10000, ge=1000, le=20000),
                   strategies: str | None = None, stake: float | None = None,
                   contract: str = Query("matches", pattern="^(matches|risefall)$"),
                   duration: int = Query(5, ge=1), unit: str = Query("t", pattern=UNITS),
                  settings: Settings = Depends(cfg)):
    """Backtest the one market you selected (Digit Matches or Rise/Fall)."""
    s = _stake(stake, settings)
    if contract == "risefall":
        return await _call(backtest_risefall(s, symbol, duration, unit, ticks))
    names = [x.strip() for x in strategies.split(",")] if strategies else list(BACKTEST_STRATEGIES)
    return await _call(run_backtest(s, await _digit_symbol(symbol, settings), ticks, names))


@app.get("/api/backtest/best-payout")
async def backtest_best_payout(ticks: int = Query(5000, ge=1000, le=10000), strategies: str | None = None,
                               stake: float | None = None, group: str = Query("all", pattern="^(all|volatility)$"),
                  settings: Settings = Depends(cfg)):
    """Digit Matches: find the highest-payout market(s) now and backtest every digit market at its own payout."""
    s = _stake(stake, settings)
    names = [x.strip() for x in strategies.split(",")] if strategies else list(BACKTEST_STRATEGIES)
    ticks = min(ticks, 5000) if group == "all" else ticks
    return await _call(run_backtest_best_payout(s, ticks, names, await digit_symbols(s, group)))


@app.get("/api/probability")
async def probability(symbol: str = "R_100", stake: float | None = None, settings: Settings = Depends(cfg)):
    return await _call(match_probability(settings, await _digit_symbol(symbol, settings), stake))


@app.get("/api/payouts")
async def payouts(stake: float | None = None, group: str = Query("all", pattern="^(all|volatility)$"),
                  settings: Settings = Depends(cfg)):
    return await _call(market_payouts(settings, stake, group))


@app.get("/api/engine")
async def engine(symbol: str = "R_100", ticks: int | None = Query(None, ge=1500, le=10000), stake: float | None = None, settings: Settings = Depends(cfg)):
    """Adaptive Digit Engine v2 walk-forward report for one digit market."""
    return await _call(engine_report(settings, await _digit_symbol(symbol, settings), ticks, stake))


@app.get("/api/engine/scan")
async def engine_scan_all(ticks: int | None = Query(None, ge=1500, le=5000), stake: float | None = None,
                          group: str = Query("all", pattern="^(all|volatility)$"),
                  settings: Settings = Depends(cfg)):
    """Adaptive Digit Engine v2 decision for every digit market, MATCH first then by score."""
    return await _call(engine_scan(settings, ticks, stake, group))


@app.get("/api/direction")
async def direction(symbol: str, duration: int = Query(5, ge=1), unit: str = Query("t", pattern=UNITS),
                    stake: float | None = None, settings: Settings = Depends(cfg)):
    """Adaptive Direction Engine walk-forward report for Rise/Fall on one market."""
    return await _call(direction_report(_stake(stake, settings), symbol, duration, unit))


@app.get("/api/live")
async def live(account: str = Query("demo", pattern="^(demo|real)$"), since: int | None = None,
               x_session_key: str | None = Header(None), settings: Settings = Depends(cfg)):
    """Balance, open contracts and trades settled since `since` (epoch), for the live balance card."""
    _require_key(x_session_key)
    _require_token()
    return await _call(live_snapshot(settings, account, since))


@app.get("/api/results")
async def results(account: str = Query("demo", pattern="^(demo|real)$"), since: int | None = None,
                  x_session_key: str | None = Header(None),
                  settings: Settings = Depends(cfg)):
    _require_key(x_session_key)
    _require_token()
    return await _call(account_results(settings, account_type=account, count_since=since))


class SessionRequest(BaseModel):
    symbol: str | None = None
    max_trades: int | None = None
    account: str = "demo"   # "demo" or "real"
    stake: float | None = None
    daily_loss_limit: float | None = None
    max_losses_in_row: int | None = None
    max_trades_per_day: int | None = None
    count_since: int | None = None   # epoch seconds of the user's last counter reset
    last_symbol: str | None = None   # auto mode: market used last, so rotation continues across runs
    strategy: str | None = None
    contract: str = "matches"        # "matches" or "risefall"
    duration: int = 5                # Rise/Fall only
    unit: str = "t"                  # Rise/Fall only: t, s, m, h


@app.post("/api/session")
async def session(body: SessionRequest | None = None, x_session_key: str | None = Header(None), settings: Settings = Depends(cfg)):
    _require_key(x_session_key)
    _require_token()
    body = body or SessionRequest()
    if body.account not in ("demo", "real"):
        raise HTTPException(400, "Account must be 'demo' or 'real'.")
    last = body.last_symbol if body.last_symbol and len(body.last_symbol) <= 40 else None

    if body.contract == "risefall":
        if body.unit not in ("t", "s", "m", "h") or body.duration < 1:
            raise HTTPException(400, "Duration must be a whole number of ticks, seconds, minutes or hours.")
        try:
            s = with_overrides(_for_account(settings, body.account), stake=body.stake,
                               daily_loss_limit=body.daily_loss_limit, max_losses_in_row=body.max_losses_in_row,
                               max_trades_per_day=body.max_trades_per_day, strategy=body.strategy)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(403 if isinstance(exc, PermissionError) else 400, str(exc)) from exc
        symbol = body.symbol or "auto"
        max_trades = max(1, min(body.max_trades or s.session_max_trades, 50))
        return await _call(run_risefall_session(s, symbol, body.duration, body.unit, max_trades,
                                                counting_start(body.count_since), last))
    if body.contract != "matches":
        raise HTTPException(400, "Contract must be 'matches' or 'risefall'.")
    symbol = None
    if body.symbol:
        symbol = body.symbol if body.symbol in AUTO_GROUPS else await _digit_symbol(body.symbol, settings)
    return await _call(run_session(settings, symbol, body.max_trades, body.account,
                                   body.stake, body.daily_loss_limit, body.max_losses_in_row,
                                   body.max_trades_per_day, body.count_since, last, body.strategy))


@app.get("/api/cron")
async def cron(authorization: str | None = Header(None), settings: Settings = Depends(cfg)):
    """For a Vercel cron job: Vercel sends 'Authorization: Bearer <CRON_SECRET>'. Runs Digit Matches defaults."""
    if not settings.cron_secret:
        raise HTTPException(503, "CRON_SECRET is not set, so scheduled sessions are off.")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {settings.cron_secret}"):
        raise HTTPException(401, "Unauthorized.")
    _require_token()
    return await _call(run_session(settings))
