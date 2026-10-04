# Deriv Matches Agent (demo-first)

Streams Deriv volatility-index ticks, analyzes last-digit statistics, and places fixed **$0.50 DIGITMATCH** contracts with hard risk stops. Every trade is logged and scored against pure chance.

> Deriv volatility indices use an audited RNG: each digit has a 10% chance every tick. The payout sits below fair odds, so every strategy here has negative expected value. The analyzer and backtester exist to let you verify that on real data before risking money. Not financial advice.

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env      # paste your DEMO account API token (scopes: Read + Trade)
```
Create the token in Deriv: Account settings → API token. Use the token for your **virtual (VRTC…) account**. Register your own app_id on Deriv's API dashboard for anything long-running.

## Commands
| Command | What it does |
|---|---|
| `python cli.py analyze` | Digit distribution + chi-square test for all 10 volatility markets, ranked, with a multiple-comparison correction. No token needed. |
| `python cli.py backtest --symbol R_100 --ticks 20000` | Replays real history against every strategy using Deriv's live payout; shows break-even win rate. |
| `python cli.py trade` | Runs the agent on the symbols/strategy in `.env`. |
| `python cli.py summary` | Win rate, P&L, break-even rate and luck probability from `trades.csv`. |

## Strategies (`STRATEGY=`)
`coldest` (least frequent digit), `hottest`, `repeat_last`, `random` (baseline). If nothing beats `random` over thousands of trades, nothing has an edge.

## Risk controls
Fixed stake (no martingale), daily loss cap (UTC day), optional session take-profit, max trades per session, stop after N consecutive losses or API errors, one open contract at a time, halt on insufficient balance or token errors.

**Real-money guard:** the agent refuses to trade a non-virtual account unless `LIVE_TRADING_CONFIRM` is set to the exact phrase in `config.py`.

## Web app (Vercel)
`app.py` is a FastAPI app Vercel deploys automatically. It serves a dashboard at `/` and:

| Endpoint | Auth | What it does |
|---|---|---|
| `GET /api/analyze` | none | Digit distribution for all markets |
| `GET /api/backtest?symbol=R_100` | none | Backtest every strategy |
| `POST /api/session` | `X-Session-Key` | Places up to `SESSION_MAX_TRADES` demo trades, then stops |
| `GET /api/results` | `X-Session-Key` | Win rate and P&L from your Deriv profit table |
| `GET /api/cron` | `Bearer CRON_SECRET` | Same as a session, for a Vercel cron job |

Set these in Vercel → Project → Settings → Environment Variables, then redeploy: `DERIV_API_TOKEN` (demo token), `SESSION_KEY`, optionally `CRON_SECRET` and any setting from `.env.example`. Daily caps are rebuilt from your Deriv history on every call, so they hold across runs. `MAX_TRADES_PER_SESSION` acts as a daily trade cap on the web app.

To schedule runs, add to `vercel.json`: `{"crons":[{"path":"/api/cron","schedule":"*/15 * * * *"}]}`. Hobby plans allow only daily crons.

Local: `uvicorn app:app --reload`.

## Always-on worker
The CLI `trade` command holds a WebSocket open, so run it on a VPS, Railway/Fly.io, or Docker:
```bash
docker build -t deriv-matches-agent .
docker run --env-file .env -v $PWD/trades.csv:/app/trades.csv deriv-matches-agent
```
To surface results in the Signal Lab dashboard, have the FastAPI app read `trades.csv` (or swap `Journal` for a database writer).

## Files
`deriv_client.py` WebSocket API client · `analyzer.py` digit stats + strategies · `risk.py` stops · `journal.py` log + stats · `stats.py` chi-square/binomial maths · `agent.py` always-on loop · `services.py` web sessions · `app.py` + `dashboard.py` web layer · `backtest.py` replay · `cli.py` CLI
