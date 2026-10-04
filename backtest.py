"""Replay real tick history against each strategy, using Deriv's live payout."""
from analyzer import STRATEGIES, DigitAnalyzer
from deriv_client import DerivAPIError, DerivClient
from stats import binom_sf


def backtest_digits(digits, strategy_name: str, window: int, every: int,
                    stake: float, payout: float) -> dict:
    """Bet at tick i on the strategy's digit; the contract settles on tick i+1."""
    strategy = STRATEGIES[strategy_name]
    analyzer = DigitAnalyzer(window)
    n = wins = 0
    for i, d in enumerate(digits[:-1]):
        analyzer.add(d)
        if analyzer.n < window or i % every:
            continue
        n += 1
        wins += digits[i + 1] == strategy(analyzer)
    pnl = wins * (payout - stake) - (n - wins) * stake
    return {
        "strategy": strategy_name, "trades": n, "wins": wins,
        "win_rate": wins / n if n else 0.0, "pnl": round(pnl, 2),
        "luck_p": binom_sf(wins, n, 0.10) if n else 1.0,
    }


async def run_backtest(settings, symbol: str, ticks: int, strategies: list[str],
                       payout: float | None = None) -> dict:
    unknown = [s for s in strategies if s not in STRATEGIES]
    if unknown:
        raise ValueError(f"Unknown strategies: {', '.join(unknown)}")
    async with DerivClient(settings.app_id, endpoint=settings.ws_url) as client:
        digits, _ = await client.tick_history(symbol, ticks)
        if payout is None:
            try:
                prop = await client.matches_proposal(symbol, 5, settings.stake, settings.currency)
                payout = float(prop["payout"])
            except DerivAPIError as exc:
                raise ValueError(f"Could not fetch live payout ({exc}). Pass a payout explicitly.") from exc
    return {
        "symbol": symbol, "ticks": len(digits), "stake": settings.stake, "payout": payout,
        "breakeven_rate": settings.stake / payout,
        "results": [backtest_digits(digits, name, settings.window, settings.trade_every_n_ticks,
                                    settings.stake, payout) for name in strategies],
    }


def format_backtest(bt: dict) -> str:
    out = [f"{bt['symbol']}: {bt['ticks']} ticks, stake {bt['stake']:.2f}, payout {bt['payout']:.2f} "
           f"-> need {bt['breakeven_rate'] * 100:.2f}% wins to break even (chance gives 10.00%)", ""]
    out.append(f"{'strategy':<12}{'trades':>8}{'wins':>7}{'win %':>8}{'P&L':>10}{'luck p':>9}")
    for r in bt["results"]:
        out.append(f"{r['strategy']:<12}{r['trades']:>8}{r['wins']:>7}{r['win_rate'] * 100:>7.2f}%"
                   f"{r['pnl']:>+10.2f}{r['luck_p']:>9.3f}")
    out.append("")
    out.append("If a strategy beats 'random' here, re-run on a different tick range before trusting it.")
    return "\n".join(out)
