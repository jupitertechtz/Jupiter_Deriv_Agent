"""Hard stops for the agent. Stake is fixed; nothing here ever increases it."""
from datetime import datetime, timezone


class RiskManager:
    def __init__(self, settings):
        self.s = settings
        self.day = self._today()
        self.daily_pnl = 0.0
        self.session_pnl = 0.0
        self.session_trades = 0
        self.session_wins = 0
        self.consecutive_losses = 0
        self.consecutive_errors = 0
        self.halt_reason: str | None = None

    @staticmethod
    def _today():
        return datetime.now(timezone.utc).date()

    def _roll_day(self) -> None:
        today = self._today()
        if today != self.day:
            self.day, self.daily_pnl = today, 0.0

    def can_trade(self) -> tuple[bool, str]:
        self._roll_day()
        s = self.s
        checks = [
            (self.halt_reason is not None, self.halt_reason or ""),
            (self.daily_pnl - s.stake < -s.max_daily_loss,
             f"daily loss limit: P&L {self.daily_pnl:+.2f}, one more loss would exceed -{s.max_daily_loss:.2f}"),
            (s.session_take_profit > 0 and self.session_pnl >= s.session_take_profit,
             f"session take-profit reached ({self.session_pnl:+.2f})"),
            (self.session_trades >= s.max_trades_per_session,
             f"max trades per session reached ({self.session_trades})"),
            (self.consecutive_losses >= s.max_consecutive_losses,
             f"{self.consecutive_losses} losses in a row"),
            (self.consecutive_errors >= s.max_consecutive_errors,
             f"{self.consecutive_errors} API errors in a row"),
        ]
        for tripped, reason in checks:
            if tripped:
                return False, reason
        return True, ""

    def record(self, profit: float) -> None:
        self._roll_day()
        self.daily_pnl += profit
        self.session_pnl += profit
        self.session_trades += 1
        self.consecutive_errors = 0
        if profit > 0:
            self.session_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

    def record_error(self, fatal_reason: str | None = None) -> None:
        self.consecutive_errors += 1
        if fatal_reason:
            self.halt_reason = fatal_reason
