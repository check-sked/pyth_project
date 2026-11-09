# Kalshi block trades vs. the public screen

Empirical support for **Cost of Size**: the Kalshi screen stays the per-contract price,
and the feed beside it is what size costs. All data comes from Kalshi's public,
unauthenticated Trade API v2 (no API key, no non-public data).

## Reproduce

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python src/01_scan_block_trades.py 0 live                              # blocks on the live tape (cutoff -> now)
python src/01_scan_block_trades.py 0 historical 2026-02-10 2026-09-08  # blocks on the archived tape (slow; can be split into
                                                                       # several date ranges and run in parallel)
python src/02_market_universe.py        # all series (categories) + all open non-combo markets
python src/03_block_vs_screen.py        # 1-min candles around each block
python src/04_orderbook_depth.py 60     # live book snapshot + walk-the-book for top-60 live-price non-sports markets
python src/05_pull_trades.py 40         # full trade tape since cutoff for top-40 non-sports markets by OI
python src/05b_pull_daily_candles.py    # daily OI/volume for the same 40 markets (as-of OI for month-end)
python src/06_mark_quality.py           # mark-quality statistics -> output/mark_quality.md, data/processed/mark_*.csv
python src/07_block_diagnostics.py      # reversion, baseline, mark scores -> data/processed/, findings in data/processed/report.md
```

Steps 01, 02, 04, 05, and 05b pull from the API and reflect the moment they ran. The raw pulls
used here are committed under `data/raw/`, so steps 03 and later reproduce the same tables. Step 07
pulls 1-minute candlesticks around each block and caches them in `data/cache/` (not committed).
The committed block files are the date-range splits from parallel runs of step 01, and `src/07_block_diagnostics.py` reads every `block_trades*.csv`.

## Scripts

`kalshi.py` is the client. Read-only calls to the public Trade API v2, with retry and backoff. No key. The numbered scripts import it.

`01_scan_block_trades.py` collects every trade with `is_block_trade` set. A scan that runs longer than 10 seconds is aborted by the server, so the script walks the tape in time windows and shrinks the window on timeout. `live` reads the current tape. `historical` takes a start and an end on the archived tape. A window that still fails at one hour is logged and skipped, so the file is a lower bound. Writes `data/raw/block_trades.csv`.

`02_market_universe.py` snapshots the catalogue used to classify those blocks and to compare their size with the screen. All series, with category, title, and tags, go to `data/raw/series.csv`. Every open market that is not a combo, with volume, open interest, and the top of book, goes to `data/raw/markets_open.csv`.

`03_block_vs_screen.py` places each block on the public screen. It fetches one-minute candles from 60 minutes before the print to 60 minutes after, and records the bid, ask, and mid at the print, the last on-book trade before it, whether the print was inside, at, or outside the spread, the block's size against nearby on-book volume and against open interest, and the screen 60 minutes later. Writes `data/processed/block_context.csv`.

`04_orderbook_depth.py` asks how much size the live book can absorb. The argument is how many markets to take. It keeps open non-sports markets whose last price is between 5¢ and 95¢, ranked by 24-hour volume; the run recorded here passed 60. For each book it records the contracts and dollars resting within 1¢, 2¢, 5¢, and 10¢ of the YES mid, and then walks a marketable order of 25,000, 100,000, 250,000, and 1,000,000 contracts: the fraction filled and the average fill versus the mid, in cents. A NO bid at price q is treated as a YES offer at 1−q. The API returns at most 100 levels a side. A rerun appends rows to `data/processed/orderbook_depth.csv` rather than replacing it, and the snapshot time is a column.

`05_pull_trades.py` pulls the full public trade tape, from the live/historical cutoff forward, for the largest open non-sports markets by open interest. The argument is how many. A market needs a live price between 5¢ and 95¢. Intraday crypto and gas series are left out. Writes `data/raw/trades_top_oi.parquet` and `trades_top_oi_markets.csv`.

`05b_pull_daily_candles.py` pulls daily candles for those same markets: volume, open interest, and the closing bid and ask. Month-end figures then use the open interest on that date rather than today's. Writes `data/raw/daily_candles_top_oi.parquet`.

`06_mark_quality.py` tests the public last price as a mark, on the tape from step 05. It writes five tables. `mark_A_size_concentration.csv` is the share of volume that prints in large trades. `mark_B_large_print_impact.csv` is how far a large on-book print moves the last price, and whether the move reverts. `mark_C_hourly_dispersion.csv` is the distance, at each hour, from the last trade to a 1-hour VWAP and a 24-hour VWAP. `mark_D_staleness.csv` is, at a 4pm ET snapshot, how long since the last trade and how much open interest sits in markets whose last trade is stale. `mark_E_month_end.csv` is the dollar value of open interest under those alternative marks. The same numbers are printed and saved to `output/mark_quality.md`.

`07_block_diagnostics.py` asks whether a block price stays in the book, and which mark is closer to the book an hour later. It reads the saved block tape and the order-book snapshot, and pulls one-minute candles for each window it needs. `block_paths.csv` is one row per block: the screen at the print, the mid 1, 15, and 60 minutes later, the share of the gap still in the book, and a class at 60 minutes (reverted, partial, or persistent). `baseline_moves.csv` is the same measurement at random minutes in those markets, away from any block. `slippage_proxy.csv` compares the block's gap with the cost of the same size on the snapshot book, using the market itself when it is in the snapshot and the category median otherwise. `mark_scores.csv` scores three marks against the mid 60 minutes later: the book mid at the print, a size-weighted median of earlier block prices on that ticker (the print being scored is not in the median), and that same median restricted to earlier prints that were inside the quote, with the book used when no such print exists. The write-up of those tables is `data/processed/report.md`.

## Data sources and limits

- **Kalshi Trade API v2** (`https://api.elections.kalshi.com/trade-api/v2`): `/markets/trades`,
  `/historical/trades`, `/markets`, `/series`, `/markets/{ticker}/orderbook`,
  `/series/{s}/markets/{t}/candlesticks`, `/historical/markets/{t}/candlesticks`, `/historical/cutoff`.
  Docs: https://docs.kalshi.com/api-reference.
- Trades before the `trades_created_ts` cutoff (2026-09-08 at time of writing) are only on the
  `/historical/trades` endpoint. Both endpoints abort any scan that takes >10 s server-side, so
  block scans are done in 12-hour windows (shrinking to 1-hour on timeout). A window that fails even at
  1 hour is logged and skipped, so the block list is a lower bound.
- `is_block_trade` flags prints matched off-book under Kalshi's block rule (min 25,000 contracts,
  must be reported within 15 minutes of agreement). RFQ fills that execute *on* the book are not
  flagged and are therefore not in the block sample.
- Candlestick `volume` includes block volume. Scripts subtract known blocks when computing on-book volume.
- The order-book snapshot is a single point in time (timestamp recorded in the CSV); depth is capped at
  100 levels per side by the API.
- "Screen at time of print" is the open of the 1-minute candle containing the block (fallback: close of the
  prior candle). Because blocks can be reported up to 15 minutes after agreement, part of any block-vs-screen
  gap can be reporting lag rather than a price concession; the data cannot separate the two, which is itself
  part of the argument for a time-stamped reference.
- Open interest for month-end valuation is taken from daily candles as of that date.
- Notional = contracts x $1 (max payout). Premium = contracts x price paid by the buyer of the cheaper side.

## Layout

```
src/            numbered scripts, run in order
data/raw/       API pulls (CSV / parquet)
data/processed/ derived tables and the block-diagnostics findings
output/         mark_quality.md
```
