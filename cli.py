"""Deriv Matches agent CLI.

  python cli.py analyze                 # digit stats for all volatility markets (no token needed)
  python cli.py backtest --symbol R_100 # replay history against every strategy
  python cli.py trade                   # run the agent (demo account unless explicitly overridden)
  python cli.py summary                 # stats from trades.csv
"""
import argparse
import asyncio
import logging

from analyzer import STRATEGIES, DigitAnalyzer, rank_markets
from backtest import format_backtest, run_backtest
from config import Settings
from deriv_client import VOLATILITY_SYMBOLS, DerivClient
from journal import summarize


async def analyze(settings: Settings, symbols: list[str], ticks: int) -> None:
    results = {}
    async with DerivClient(settings.app_id, endpoint=settings.ws_url) as client:
        for sym in symbols:
            digits, _ = await client.tick_history(sym, ticks)
            a = DigitAnalyzer(window=len(digits) or 1)
            a.extend(digits)
            results[sym] = a
    print(f"Last-digit distribution over the most recent {ticks} ticks (expected: 10.0% each)\n")
    print(rank_markets(results))


def main() -> None:
    parser = argparse.ArgumentParser(description="Deriv Matches analyzer and demo-first trading agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_an = sub.add_parser("analyze", help="digit statistics per market")
    p_an.add_argument("--ticks", type=int, default=5000)
    p_an.add_argument("--symbols", default=",".join(VOLATILITY_SYMBOLS))

    p_bt = sub.add_parser("backtest", help="replay tick history against strategies")
    p_bt.add_argument("--symbol", default="R_100")
    p_bt.add_argument("--ticks", type=int, default=20000)
    p_bt.add_argument("--strategies", default=",".join(STRATEGIES))
    p_bt.add_argument("--payout", type=float, default=None, help="override payout per stake")

    sub.add_parser("trade", help="run the trading agent")
    sub.add_parser("summary", help="summarize the trade log")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    settings = Settings()

    if args.cmd == "analyze":
        asyncio.run(analyze(settings, [s.strip() for s in args.symbols.split(",")], args.ticks))
    elif args.cmd == "backtest":
        names = [s.strip() for s in args.strategies.split(",")]
        print(format_backtest(asyncio.run(run_backtest(settings, args.symbol, args.ticks, names, args.payout))))
    elif args.cmd == "trade":
        from agent import MatchesAgent
        try:
            asyncio.run(MatchesAgent(settings).run())
        except KeyboardInterrupt:
            print("\nStopped by user.")
            print(summarize(settings.trade_log))
    elif args.cmd == "summary":
        print(summarize(settings.trade_log))


if __name__ == "__main__":
    main()
