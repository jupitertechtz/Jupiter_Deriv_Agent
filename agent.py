"""The trading agent: stream ticks, analyze digits, place fixed-stake Matches trades."""
import asyncio
import logging

from analyzer import STRATEGIES, DigitAnalyzer
from config import LIVE_CONFIRM_PHRASE, Settings
from deriv_client import DerivAPIError, DerivClient, last_digit
from journal import Journal, summarize
from risk import RiskManager

log = logging.getLogger("agent")

FATAL_CODES = {"InsufficientBalance", "InvalidToken", "AuthorizationRequired", "PermissionDenied"}


class MatchesAgent:
    def __init__(self, settings: Settings):
        if settings.strategy not in STRATEGIES:
            raise SystemExit(f"Unknown STRATEGY '{settings.strategy}'. Options: {', '.join(STRATEGIES)}")
        self.s = settings
        self.client = DerivClient(settings.app_id, settings.api_token, settings.api_base, settings.account_type)
        self.risk = RiskManager(settings)
        self.journal = Journal(settings.trade_log)
        self.strategy = STRATEGIES[settings.strategy]
        self.analyzers = {sym: DigitAnalyzer(settings.window) for sym in settings.symbols}
        self.stop = asyncio.Event()
        self.busy = False          # one open contract at a time
        self.loginid = None
        self.currency = settings.currency
        self._tasks: set = set()

    async def run(self) -> None:
        if not self.s.api_token:
            raise SystemExit("Set DERIV_API_TOKEN (a Read + Trade token) in your .env first.")
        acct = await self.client.connect()
        try:
            self._check_account(acct)
            await self._warm_up()
            watchers = [asyncio.create_task(self._watch(sym)) for sym in self.s.symbols]
            await self.stop.wait()
            while self.busy:                       # let an open contract settle
                await asyncio.sleep(0.5)
            for t in watchers:
                t.cancel()
            await asyncio.gather(*watchers, return_exceptions=True)
        finally:
            await self.client.close()
            print("\n=== Session summary ===")
            print(summarize(self.s.trade_log, account=self.loginid))

    def _check_account(self, acct: dict) -> None:
        self.loginid = acct["loginid"]
        self.currency = acct.get("currency") or self.s.currency
        virtual = bool(acct.get("is_virtual"))
        log.info("Authorized %s (%s account) balance %.2f %s",
                 self.loginid, "DEMO" if virtual else "REAL", float(acct.get("balance", 0)), self.currency)
        if not virtual:
            if self.s.live_trading_confirm != LIVE_CONFIRM_PHRASE:
                raise SystemExit(
                    "Refusing to trade a REAL-money account. Run on your demo (VRTC) token first. "
                    f"To override, set LIVE_TRADING_CONFIRM=\"{LIVE_CONFIRM_PHRASE}\"."
                )
            log.warning("LIVE MODE: real money at risk. Daily loss cap %.2f %s.", self.s.max_daily_loss, self.currency)

    async def _warm_up(self) -> None:
        for sym in self.s.symbols:
            digits, _ = await self.client.tick_history(sym, self.s.window)
            self.analyzers[sym].extend(digits)
            log.info("Warm-up  %s", self.analyzers[sym].summary(sym))

    async def _watch(self, symbol: str) -> None:
        analyzer = self.analyzers[symbol]
        seen = 0
        gen = self.client.subscribe({"ticks": symbol})
        try:
            async for msg in gen:
                if self.stop.is_set():
                    break
                tick = msg["tick"]
                analyzer.add(last_digit(tick["quote"], tick["pip_size"]))
                seen += 1
                if seen % 500 == 0:
                    log.info("Stats    %s", analyzer.summary(symbol))
                if seen % self.s.trade_every_n_ticks or self.busy:
                    continue
                ok, reason = self.risk.can_trade()
                if not ok:
                    log.warning("Stopping: %s", reason)
                    self.stop.set()
                    break
                self.busy = True
                task = asyncio.create_task(self._trade(symbol, self.strategy(analyzer)))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except (DerivAPIError, ConnectionError) as exc:
            log.error("Tick stream for %s failed: %s", symbol, exc)
            self.stop.set()
        finally:
            await gen.aclose()

    async def _trade(self, symbol: str, digit: int) -> None:
        try:
            proposal = await self.client.matches_proposal(symbol, digit, self.s.stake, self.currency)
            bought = await self.client.buy(proposal)
            poc = await self.client.wait_for_settlement(bought["contract_id"])
            profit = float(poc["profit"])
            exit_val = poc.get("exit_spot")
            exit_digit = last_digit(exit_val, self.client.pip_sizes.get(symbol, 2)) if exit_val is not None else ""
            self.risk.record(profit)
            self.journal.write(
                account=self.loginid, symbol=symbol, strategy=self.s.strategy, predicted=digit,
                exit_digit=exit_digit, stake=bought["buy_price"], payout=bought["payout"],
                profit=f"{profit:.2f}", status=poc.get("status"), contract_id=bought["contract_id"],
            )
            r = self.risk
            log.info("%-7s bet %d, exit %s -> %-4s %+.2f | session %+.2f over %d trades (%d won)",
                     symbol, digit, exit_digit, poc.get("status"), profit,
                     r.session_pnl, r.session_trades, r.session_wins)
        except DerivAPIError as exc:
            log.error("Trade failed on %s: %s", symbol, exc)
            self.risk.record_error(fatal_reason=str(exc) if exc.code in FATAL_CODES else None)
        except asyncio.TimeoutError:
            log.error("Contract did not settle in time on %s. Check your Deriv statement.", symbol)
            self.risk.record_error()
        except ConnectionError as exc:
            log.error("Connection lost during trade: %s", exc)
            self.risk.record_error(fatal_reason="connection lost")
            self.stop.set()
        finally:
            self.busy = False
