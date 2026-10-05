"""Settings the dashboard may adjust per browser, with safe bounds.

The dashboard sends its overrides as JSON in the X-Tuning header on every request; the
server validates each value against the bounds below and applies them to that request
only. Defaults come from the Vercel environment (config.py). Stake, loss limits and the
real-money switch are handled separately and are not part of this list.
"""
import dataclasses
import json

# key: (group, label, type, min, max, step, help, loosens)
#   loosens = "down" if lowering the value makes the engine trade more readily (riskier),
#             "up" if raising it does, None if neutral.
FIELDS = {
    # ---- Adaptive Digit Engine (Digit Matches)
    "adaptive_history": ("Digit engine", "History replayed per market (ticks)", int, 1000, 20000, 500,
                         "Ticks of past data the engine learns from before deciding. More history gives more "
                         "walk-forward predictions but takes longer.", None),
    "adaptive_min_samples": ("Digit engine", "Walk-forward predictions required", int, 100, 10000, 100,
                             "How many scored predictions the engine needs before its accuracy is trusted. "
                             "Must be below history minus the short window.", "down"),
    "adaptive_max_p": ("Digit engine", "Max luck probability (p)", float, 0.0001, 0.2, 0.001,
                       "Accuracy must be this unlikely to come from pure luck. 0.01 = 1%.", "up"),
    "adaptive_min_edge": ("Digit engine", "Min edge over 10%", float, 0.0, 0.2, 0.005,
                          "How far the chosen digit's probability must exceed 10%.", "down"),
    "adaptive_min_separation": ("Digit engine", "Min lead over 2nd digit", float, 0.0, 0.1, 0.001,
                                "How far ahead of the second-best digit the pick must be.", "down"),
    "adaptive_max_entropy": ("Digit engine", "Max forecast entropy", float, 0.9, 1.0, 0.001,
                             "At or above this the forecast counts as uniform and the engine skips. "
                             "1.0 = perfectly flat.", "up"),
    "adaptive_persistence": ("Digit engine", "Consecutive ticks the gate must hold", int, 1, 500, 1,
                             "Evidence must pass on this many ticks in a row before MATCH.", "down"),
    "adaptive_eta": ("Digit engine", "Learning rate (eta)", float, 0.01, 1.0, 0.01,
                     "How fast model weights move toward the best-performing model.", None),
    "adaptive_short_window": ("Digit engine", "Short window (ticks)", int, 20, 1000, 10,
                              "Ticks used by the short-term frequency model.", None),
    "adaptive_long_window": ("Digit engine", "Long window (ticks)", int, 100, 10000, 100,
                             "Ticks used by the long-term frequency model.", None),
    "adaptive_recency_lambda": ("Digit engine", "Recency decay (lambda)", float, 0.8, 0.999, 0.001,
                                "Weight kept by older ticks in the recency model; lower forgets faster.", None),
    "scan_ticks": ("Digit engine", "History per market in scans (ticks)", int, 1000, 10000, 500,
                   "Used by 'Scan all markets'. Many markets x many ticks takes longer.", None),
    # ---- Adaptive Direction Engine (Rise/Fall)
    "direction_history": ("Direction engine", "History replayed per market (ticks)", int, 1000, 30000, 500,
                          "Fetched automatically higher for long durations.", None),
    "direction_min_samples": ("Direction engine", "Walk-forward predictions required", int, 50, 5000, 50,
                              "Non-overlapping scored predictions needed before accuracy is trusted.", "down"),
    "direction_max_p": ("Direction engine", "Max luck probability (p)", float, 0.0001, 0.2, 0.001,
                        "Accuracy must be this unlikely vs a 50% coin flip.", "up"),
    "direction_min_edge": ("Direction engine", "Min distance from 50%", float, 0.0, 0.3, 0.005,
                           "How far the forecast must be from a coin flip.", "down"),
    "direction_max_entropy": ("Direction engine", "Max forecast entropy", float, 0.9, 1.0, 0.001,
                              "At or above this the forecast counts as 50/50 and the engine skips.", "up"),
    "direction_persistence": ("Direction engine", "Consecutive new predictions the gate must hold", int, 1, 500, 1,
                              "Evidence must pass on this many new resolved predictions in a row.", "down"),
    # ---- Sessions
    "session_time_budget": ("Sessions", "Seconds per run", float, 20, 85, 1,
                            "How long one run may trade. Must stay under the Vercel function limit (90 s).", None),
    "session_trade_every_n_ticks": ("Sessions", "Ticks between trades (simple strategies)", int, 1, 100, 1,
                                    "Spacing between trades for Coldest/Hottest/Repeat/Random on one market.", None),
    "auto_rescan_every": ("Sessions", "Re-check payouts every N trades (auto)", int, 1, 100, 1,
                          "Auto mode re-checks every market's payout this often.", None),
    "max_wait_seconds": ("Sessions", "Wait for contracts up to (seconds)", float, 5, 60, 1,
                         "Rise/Fall contracts longer than this are bought and tracked instead of waited on.", None),
    # ---- Simple strategies and backtests
    "window": ("Simple strategies & backtests", "Analysis window (ticks)", int, 50, 5000, 50,
               "Ticks the Coldest/Hottest strategies look back over.", None),
    "trade_every_n_ticks": ("Simple strategies & backtests", "Ticks between backtest trades", int, 1, 100, 1,
                            "Spacing between simulated trades in backtests.", None),
}


def schema(base) -> list[dict]:
    out = []
    for key, (group, label, typ, lo, hi, step, help_, loosens) in FIELDS.items():
        out.append({"key": key, "group": group, "label": label, "type": typ.__name__, "min": lo, "max": hi,
                    "step": step, "help": help_, "loosens": loosens, "default": getattr(base, key)})
    return out


def apply(base, raw: str | dict | None):
    """Return Settings with validated overrides applied. Raises ValueError on bad input."""
    if not raw:
        return base
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        raise ValueError("saved settings could not be read; open Settings and press 'Reset all to defaults'.") from None
    if not isinstance(data, dict):
        raise ValueError("Settings must be a JSON object.")
    changes = {}
    for key, value in data.items():
        if key not in FIELDS:
            raise ValueError(f"'{key}' is not an adjustable setting.")
        _, label, typ, lo, hi, *_ = FIELDS[key]
        try:
            v = typ(value)
            if typ is int and float(value) != int(v):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"{label} must be a {'whole number' if typ is int else 'number'}.") from None
        if not lo <= v <= hi:
            raise ValueError(f"{label} must be between {lo} and {hi}.")
        changes[key] = v
    s = dataclasses.replace(base, **changes)
    if s.adaptive_min_samples > s.adaptive_history - s.adaptive_short_window:
        raise ValueError(f"Digit engine: walk-forward predictions required ({s.adaptive_min_samples}) can never be "
                         f"reached with {s.adaptive_history} ticks of history; it must be at most history minus the "
                         f"short window ({s.adaptive_history - s.adaptive_short_window}).")
    if s.adaptive_long_window < s.adaptive_short_window:
        raise ValueError("Digit engine: the long window must be at least the short window.")
    return s
