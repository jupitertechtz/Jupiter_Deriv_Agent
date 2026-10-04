"""Settings for the Deriv Matches agent, loaded from environment / .env."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# A real-money account is only traded if LIVE_TRADING_CONFIRM equals this exact phrase.
LIVE_CONFIRM_PHRASE = "I understand this has negative expected value"


def _f(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def _symbols() -> tuple:
    raw = os.getenv("SYMBOLS", "R_100")
    return tuple(s.strip() for s in raw.split(",") if s.strip())


@dataclass(frozen=True)
class Settings:
    # Connection
    api_token: str = field(default_factory=lambda: os.getenv("DERIV_API_TOKEN", ""))
    app_id: str = field(default_factory=lambda: os.getenv("DERIV_APP_ID", ""))  # from developers.deriv.com
    api_base: str = field(default_factory=lambda: os.getenv("DERIV_API_BASE", "https://api.derivws.com"))
    account_type: str = field(default_factory=lambda: os.getenv("ACCOUNT_TYPE", "demo"))  # demo | real

    # Trading
    symbols: tuple = field(default_factory=_symbols)
    stake: float = field(default_factory=lambda: _f("STAKE", "0.5"))
    currency: str = field(default_factory=lambda: os.getenv("CURRENCY", "USD"))
    strategy: str = field(default_factory=lambda: os.getenv("STRATEGY", "coldest"))
    window: int = field(default_factory=lambda: _i("ANALYSIS_WINDOW", "500"))
    trade_every_n_ticks: int = field(default_factory=lambda: _i("TRADE_EVERY_N_TICKS", "10"))

    # Risk controls (stake is always fixed: no martingale)
    max_daily_loss: float = field(default_factory=lambda: _f("MAX_DAILY_LOSS", "5"))
    session_take_profit: float = field(default_factory=lambda: _f("SESSION_TAKE_PROFIT", "0"))  # 0 = off
    max_trades_per_session: int = field(default_factory=lambda: _i("MAX_TRADES_PER_SESSION", "100"))
    max_consecutive_losses: int = field(default_factory=lambda: _i("MAX_CONSECUTIVE_LOSSES", "25"))
    max_consecutive_errors: int = field(default_factory=lambda: _i("MAX_CONSECUTIVE_ERRORS", "5"))

    # Safety + logging
    live_trading_confirm: str = field(default_factory=lambda: os.getenv("LIVE_TRADING_CONFIRM", ""))
    trade_log: str = field(default_factory=lambda: os.getenv("TRADE_LOG", "trades.csv"))

    # Web / Vercel sessions (short, capped bursts instead of an always-on loop)
    session_key: str = field(default_factory=lambda: os.getenv("SESSION_KEY", ""))
    cron_secret: str = field(default_factory=lambda: os.getenv("CRON_SECRET", ""))
    session_max_trades: int = field(default_factory=lambda: _i("SESSION_MAX_TRADES", "10"))
    session_time_budget: float = field(default_factory=lambda: _f("SESSION_TIME_BUDGET", "50"))
    session_trade_every_n_ticks: int = field(default_factory=lambda: _i("SESSION_TRADE_EVERY_N_TICKS", "1"))
