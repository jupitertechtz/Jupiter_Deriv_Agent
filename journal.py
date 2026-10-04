"""CSV trade log plus a summary that compares results against chance."""
import csv
import os
from datetime import datetime, timezone

from stats import binom_sf

FIELDS = ["time_utc", "account", "symbol", "strategy", "predicted", "exit_digit",
          "stake", "payout", "profit", "status", "contract_id"]


class Journal:
    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writeheader()

    def write(self, **row) -> None:
        row.setdefault("time_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        with open(self.path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow({k: row.get(k, "") for k in FIELDS})


def summarize(path: str, account: str | None = None) -> str:
    if not os.path.exists(path):
        return "No trades logged yet."
    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if account is None or r["account"] == account]
    if not rows:
        return "No trades logged yet" + (f" for {account}." if account else ".")
    return format_stats(stats_from_rows(rows))


def stats_from_rows(rows) -> dict:
    """rows need stake, payout and profit. Returns the numbers behind the summary."""
    n = len(rows)
    if n == 0:
        return {"trades": 0}
    wins = sum(1 for r in rows if float(r["profit"]) > 0)
    pnl = sum(float(r["profit"]) for r in rows)
    staked = sum(float(r["stake"]) for r in rows)
    breakeven = sum(float(r["stake"]) / float(r["payout"]) for r in rows) / n
    return {
        "trades": n, "wins": wins, "win_rate": wins / n, "breakeven_rate": breakeven,
        "staked": round(staked, 2), "pnl": round(pnl, 2), "return_on_stake": pnl / staked if staked else 0.0,
        "luck_p": binom_sf(wins, n, 0.10),
    }


def verdict(st: dict) -> str:
    if st["trades"] < 1000:
        return "Too few trades to judge: under ~1,000 trades, win rates swing several points from luck alone."
    if st["luck_p"] < 0.01:
        return "Win rate is unusually high. Re-test on fresh trades before trusting it."
    return "Result is consistent with random guessing."


def format_stats(st: dict) -> str:
    if not st.get("trades"):
        return "No trades logged yet."
    n, wins, pnl, staked = st["trades"], st["wins"], st["pnl"], st["staked"]
    breakeven, p_value = st["breakeven_rate"], st["luck_p"]
    lines = [
        f"Trades: {n}   Wins: {wins}   Win rate: {wins / n * 100:.2f}%",
        f"Chance rate: 10.00%   Break-even rate at these payouts: {breakeven * 100:.2f}%",
        f"Total staked: {staked:.2f}   Net P&L: {pnl:+.2f}   Return on stake: {pnl / staked * 100:+.2f}%",
        f"Probability of doing this well or better by pure luck: {p_value:.3f}",
    ]
    lines.append(verdict(st))
    return "\n".join(lines)
