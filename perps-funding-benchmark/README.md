# perps-funding-benchmark

Twelve months of perpetual-funding prints, and the tables computed from them, for a market-wide funding rate.

- Findings, rendered from the processed tables: [`output/report_tables.md`](output/report_tables.md)
- Machine-readable tables: `data/processed/`
- Sources, with URLs and quoted wording: [`data/raw/research/sources.md`](data/raw/research/sources.md)

Sample window: **2025-11-01 00:00 – 2026-10-31 23:59 UTC** (12 months; Binance's archive publishes complete months only). Data were pulled on 2026-11-08/09 UTC. OI weights are a snapshot from the same dates.

## Data sources

All public, no API keys. "Primary" = read from the venue. "Archive" = Pendle's Boros historical-data archive, which republishes venue funding prints; used only where the venue blocks this machine, and validated print-by-print against primary data wherever both exist (`data/processed/archive_validation.csv`: 100% of Binance/Hyperliquid/Gate/OKX overlap prints identical; Lighter 99.8–99.99% within 0.01 pp annualised, the remainder is Lighter's 4-decimal rounding).

| Venue | Funding history | Interval | OI used for weights | Caps / params | Status from this machine |
|---|---|---|---|---|---|
| Hyperliquid | `POST https://api.hyperliquid.xyz/info` `{"type":"fundingHistory"}` (dex `xyz` for NVDA/TSLA) | 1h | `metaAndAssetCtxs` openInterest × markPx (default + `xyz` dex) | docs https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding (0.5 %/h cap) | OK |
| Binance USDⓈ-M | `https://data.binance.vision/data/futures/um/monthly/fundingRate/<SYM>/` monthly zips (S3 listing `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=...`) | 8h (NVDA 1h/8h, TSLA 4h/8h; interval column in archive) | `data/futures/um/daily/metrics/<SYM>/` (5-min `sum_open_interest_value`), last 35 days | `/fapi/v1/fundingInfo` geo-blocked; BTC/ETH ±0.3 % per third-party read https://safearbitrage.com/en/blog/funding-rate-cap-and-floor/ | REST `fapi.binance.com` HTTP 451 (restricted location); archive OK |
| OKX | `GET https://www.okx.com/api/v5/public/funding-rate-history` (paging with `after` stops after ≈3 months: primary from 2026-08-06 for all five instruments); archive before for BTC/ETH/SOL, none for NVDA/TSLA | 8h | `/api/v5/public/open-interest` (oiUsd) + `/api/v5/rubik/stat/contracts/open-interest-history` 30d | `/api/v5/public/funding-rate` `maxFundingRate` | OK |
| Gate | `GET https://api.gateio.ws/api/v4/futures/usdt/funding_rate` (primary from 2026-05-14 = 179-day retention); archive before | 8h | `/futures/usdt/contract_stats` 1d, `open_interest_usd` | `/futures/usdt/contracts/<c>` `funding_rate_limit`, `interest_rate` | OK |
| Lighter | `GET https://mainnet.zklighter.elliot.ai/api/v1/fundings` (750/page); `rate` is % per hour, unsigned, `direction` gives sign | 1h | `/api/v1/orderBookDetails` open_interest × last_trade_price | same endpoint: `funding_clamp_big` 4 %/8h = 0.5 %/h | OK |
| Bybit | `https://api.bybit.com/v5/market/funding/history`, `api.bytick.com` mirror | 8h | NOT AVAILABLE | NOT AVAILABLE (cap = f(IMR, MMR) per symbol, https://www.bybit.com/en/help-center/article/Introduction-to-Funding-Rate) | **HTTP 403 (CloudFront country block)** on both hosts; `public.bybit.com` has no funding files. Funding series taken from the Boros archive (second-hand), marked `Bybit*` everywhere |
| Pendle Boros archive | `https://historical-data.boros.finance/files.json` → `funding-rate/<Exchange>-<Asset>.ndjson.zip`, `market-data/<id>-<EXCHANGE>-<SYMBOL>-<MATURITY>/` | native | – | – | OK |
| Pyth Pro symbology | `https://pyth.dourolabs.app/v1/symbols?asset_type=funding-rate` / `interest-rate` / `rates` (docs https://docs.pyth.network/pro/symbology-reference) | – | – | – | OK (`rates` returns 0 feeds; `crypto-redemption-rate` filter HTTP 400) |

Bybit OI in the Boros Data Board (BTC $5.22B on 2026-11-08, https://boros-data-dashboard.pendle.finance/funding-rates) is JS-rendered and not machine-readable; it was not used.

## Method

- **Normalisation.** A print `rate` at payment time T with interval k hours is spread evenly over the k hourly periods ending at T: each hour gets `rate/k`, annualised × 8760 (so 8h venues × 1095/print, 1h venues × 8760/print). Hour label = payment hour (end of accrual). Positive = longs pay. Units everywhere: annualised %, differences in percentage points (pp).
- **Composites per asset-hour.** `comp_oi` = OI-weighted mean over venues with data that hour (weights renormalised; ≥2 venues required); `comp_oi_cap30` and `comp_oi_cap20` = the same with each venue's weight capped at 30% and 20%, excess redistributed pro rata (equal weights when the cap cannot sum to 1); `comp_median` = median over venues with data (≥2). Bybit* is excluded from the OI composites (no OI) but included in `comp_median`. `src/14_composite_cap.py` compares them. `comp_oi_cap30` is the composite that comparison settles on.
- **OI weights** = single USD OI snapshot (2026-11-07/09, `data/processed/oi_weights.csv`), held fixed over the whole year. 30-day mean OI is recorded where available (Binance, OKX, Gate) for comparison but not used.
- **Outliers** = |z| > 4 vs the trailing 30-day mean/std of the same venue's own prints (shifted, ≥20 prints).
- **Swap cost** = receive-floating P&L on $1M notional over rolling 30-day (720 h) windows ending 23:00 UTC: Σ w_h/8760 × $1M, venue minus composite.

## Rerun

```bash
cd perps-funding-benchmark
python3.13 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
for s in src/0*.py src/1*.py; do python "$s"; done
```

Scripts run in numeric order; each is idempotent and overwrites its outputs.

| Script | Writes |
|---|---|
| `01_fetch_hyperliquid.py` | `data/raw/hyperliquid/funding.parquet`, `funding_with_premium.parquet`, `oi_snapshot.json` |
| `02_fetch_binance.py` | `data/raw/binance/funding.parquet`, `oi_daily.csv` |
| `03_fetch_okx.py` | `data/raw/okx/funding.parquet`, `funding_params.json`, `oi_snapshot.json`, `oi_daily.csv` |
| `04_fetch_gate.py` | `data/raw/gate/funding.parquet`, `contracts.json`, `oi_daily.csv` |
| `05_fetch_lighter.py` | `data/raw/lighter/funding.parquet`, `markets.json` |
| `06_fetch_bybit.py` | `data/raw/bybit/fetch_status.json` (+ empty parquet when blocked) |
| `07_fetch_boros_archive.py` | `data/raw/boros/archive_funding.parquet`, `boros_markets_from_archive.csv`; fills `data/raw/bybit/funding.parquet` if empty |
| `08_normalize.py` | `data/processed/prints_long.parquet`, `hourly_panel.parquet`, `hourly_wide_<ASSET>.csv`, `coverage.csv`, `oi_weights.csv`, `archive_validation.csv`, `sign_check.csv` |
| `09_analysis1_agreement.py` | `a1_pairwise_spreads.csv`, `a1_daily_by_venue.csv` |
| `10_analysis2_fragility.py` | `a2_outliers_caps.csv`, `a2_volatility.csv`, `a2_outliers_hourly_grid.csv`, `a2_spike_episode.csv` |
| `11_analysis3_swap_cost.py` | `a3_swap_cost.csv`, `a3_rolling_pnl_<ASSET>.csv` |
| `12_analysis4_equity.py` | `a4_equity_pairs.csv`, `a4_equity_volatility.csv`, `a4_equity_session.csv`, `a4_equity_swap_cost.csv` |
| `13_fetch_pyth_catalog.py` | `data/raw/pyth/symbols_*.json`, `data/processed/a5_pyth_feeds.csv` |
| `14_composite_cap.py` | `data/processed/a6_composite_comparison.csv`, `a6_composite_weights.csv` (uncapped vs 30% cap vs 20% cap vs median) |
| `15_report_tables.py` | `output/report_tables.md` |

Rerunning on a later date moves the Gate (179-day) and OKX (≈3-month) primary windows forward; the archive backfill keeps the full year as long as Pendle's archive stays up. Rerunning from a non-US location will also make Binance REST and Bybit reachable; `06_fetch_bybit.py` then writes primary Bybit data and `07` leaves it alone.

## Known gaps (marked NOT AVAILABLE where a number could not be filled)

- Bybit: no primary data, no OI weight, no cap; nothing for NVDA/TSLA (Bybit lists no such contracts in the archive).
- Binance caps for SOL/NVDA/TSLA; `fundingInfo` geo-blocked.
- Binance funding archive ends 2026-10-31 16:00 (last 8h print of the month), so the final 7 hours of the window lack Binance.
- OKX SOL before 2026-03-23 (archive starts there); OKX NVDA & TSLA before 2026-08-06 (API retention, no archive series); Gate NVDA & TSLA before 2026-09-02 (contract `create_time`).
- Boros volume/OI figures: only what public pages state (see `sources.md`); no API.
- OI weights are a single snapshot, not time-varying.
