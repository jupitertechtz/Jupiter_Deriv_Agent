"""FastAPI web layer for Vercel: dashboard + short, capped demo-trading sessions."""
import hmac

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from analyzer import STRATEGIES
from backtest import run_backtest
from config import LIVE_CONFIRM_PHRASE, Settings
from dashboard import DASHBOARD_HTML
from deriv_client import VOLATILITY_SYMBOLS, DerivAPIError
from services import account_results, analyze_markets, market_payouts, match_probability, run_session

app = FastAPI(title="Jupiter Deriv Agent", docs_url="/api/docs", openapi_url="/api/openapi.json")
settings = Settings()


def _check_symbol(symbol: str) -> str:
    if symbol not in VOLATILITY_SYMBOLS:
        raise HTTPException(400, f"Unknown market '{symbol}'. Use one of: {', '.join(VOLATILITY_SYMBOLS)}")
    return symbol


def _require_key(key: str | None) -> None:
    if not settings.session_key:
        raise HTTPException(503, "SESSION_KEY is not set in the Vercel project's environment variables.")
    if not key or not hmac.compare_digest(key, settings.session_key):
        raise HTTPException(401, "Session key is missing or wrong.")


def _require_token() -> None:
    if not settings.api_token:
        raise HTTPException(503, "DERIV_API_TOKEN is not set in the Vercel project's environment variables.")


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
async def dashboard():
    return DASHBOARD_HTML


@app.get("/api/health")
async def health():
    s = settings
    return {
        "token_configured": bool(s.api_token), "app_id_configured": bool(s.app_id),
        "session_key_configured": bool(s.session_key), "account_type": s.account_type,
        "live_enabled": s.live_trading_confirm == LIVE_CONFIRM_PHRASE,
        "cron_configured": bool(s.cron_secret), "symbols": list(s.symbols), "all_symbols": VOLATILITY_SYMBOLS,
        "strategy": s.strategy, "strategies": list(STRATEGIES), "stake": s.stake,
        "min_stake": s.min_stake, "max_stake": s.max_stake, "max_daily_loss_ceiling": s.max_daily_loss_ceiling,
        "max_losses_in_row_ceiling": s.max_losses_in_row_ceiling, "max_trades_per_day_ceiling": s.max_trades_per_day_ceiling,
        "limits": {"max_daily_loss": s.max_daily_loss, "max_trades_per_day": s.max_trades_per_session,
                   "max_consecutive_losses": s.max_consecutive_losses,
                   "trades_per_run": s.session_max_trades},
    }


@app.get("/api/analyze")
async def analyze(ticks: int = Query(2000, ge=100, le=5000), symbols: str | None = None):
    syms = [_check_symbol(x.strip()) for x in symbols.split(",")] if symbols else VOLATILITY_SYMBOLS
    return await _call(analyze_markets(settings, syms, ticks))


@app.get("/api/backtest")
async def backtest(symbol: str = "R_100", ticks: int = Query(10000, ge=1000, le=20000),
                   strategies: str | None = None):
    names = [x.strip() for x in strategies.split(",")] if strategies else list(STRATEGIES)
    return await _call(run_backtest(settings, _check_symbol(symbol), ticks, names))


@app.get("/api/probability")
async def probability(symbol: str = "R_100", stake: float | None = None):
    return await _call(match_probability(settings, _check_symbol(symbol), stake))


@app.get("/api/payouts")
async def payouts(stake: float | None = None):
    return await _call(market_payouts(settings, stake))


@app.get("/api/results")
async def results(account: str = Query("demo", pattern="^(demo|real)$"), since: int | None = None,
                  x_session_key: str | None = Header(None)):
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


@app.post("/api/session")
async def session(body: SessionRequest | None = None, x_session_key: str | None = Header(None)):
    _require_key(x_session_key)
    _require_token()
    body = body or SessionRequest()
    symbol = None if not body.symbol else ("auto" if body.symbol == "auto" else _check_symbol(body.symbol))
    if body.account not in ("demo", "real"):
        raise HTTPException(400, "Account must be 'demo' or 'real'.")
    return await _call(run_session(settings, symbol, body.max_trades, body.account,
                                   body.stake, body.daily_loss_limit, body.max_losses_in_row,
                                   body.max_trades_per_day, body.count_since))


@app.get("/api/cron")
async def cron(authorization: str | None = Header(None)):
    """For a Vercel cron job: Vercel sends 'Authorization: Bearer <CRON_SECRET>'."""
    if not settings.cron_secret:
        raise HTTPException(503, "CRON_SECRET is not set, so scheduled sessions are off.")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {settings.cron_secret}"):
        raise HTTPException(401, "Unauthorized.")
    _require_token()
    return await _call(run_session(settings))
