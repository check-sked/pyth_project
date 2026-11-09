# Product ideas

Two evidence projects for Pyth. `Pyth_Report.pdf` is the two-page note: Cost of Size, then a benchmark funding rate. Each folder has its own virtualenv, `requirements.txt`, and README. Run the scripts from inside that folder. The README there says what each file in `src/` does, what it reads, and what it writes.

Saved pulls are dated November 8th, 2026.

## [kalshi-cost-of-size](kalshi-cost-of-size/)

Evidence for Cost of Size. The Kalshi screen stays the per-contract price. The number beside it is what size costs, walked from the live book and checked against block prints.

All of the data is Kalshi's public Trade API v2. No API key. `src/01` through `src/05b` pull block trades, the screen around each print, order-book depth, and the trade tape. `src/06` and `src/07` write the findings in `output/mark_quality.md` and `data/processed/report.md`.

## [perps-funding-benchmark](perps-funding-benchmark/)

Evidence for a benchmark funding rate: settlement-grade per-venue funding feeds and an hourly open-interest-weighted composite. Twelve months of funding prints from Hyperliquid, Binance (public archive), OKX, Gate, Lighter and Bybit (via the Boros archive), normalised to an hourly annualised grid. `src/01` through `src/07` fetch, `src/08` normalises, `src/09` through `src/12` and `src/14` write the tables, `src/13` saves Pyth's feed catalogue, and `src/15` renders the findings in `output/report_tables.md`.
