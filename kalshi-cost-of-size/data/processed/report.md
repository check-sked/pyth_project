# Block diagnostics

These tables are written by `src/07_block_diagnostics.py` from the block tape, the 7 Nov 2026 depth snapshot, and candlesticks pulled for this run. A blank that the code could not fill is the words NOT AVAILABLE.

## 1. Data availability

- Block tape: 52 prints, 32 markets, 2026-06-04 14:48:20.976058+00:00 through 2026-11-06 22:25:45.318292+00:00. Files: block_trades_historical.csv, block_trades_historical_2026-02-10_2026-04-10.csv, block_trades_historical_2026-04-10_2026-06-10.csv, block_trades_historical_2026-06-10_2026-07-15.csv, block_trades_historical_2026-07-15_2026-08-20.csv, block_trades_live.csv, block_trades_live_2026-09-08_2026-09-25.csv, block_trades_live_2026-09-25_2026-10-11.csv.
- Test 1 pre/post mids: 1-minute candlestick bid/ask. Usable minute = two-sided, ask above bid, spread under 50¢ (the rule in `src/03_block_vs_screen.py`). If that window has no usable minute, the pre-block reference is the VWAP of trades the API does not flag as blocks.
- Pre-block source mix: median_minute_mid 27, missing 25.
- +60 min mid available for 29 of 52. Next weekday 16:00 ET mid available for 20 of 52.
- A horizon quote is the last usable minute ending at or up to 60 seconds after the target. It is kept only if that minute is at most 90 seconds old at +1 minute, and at most 5 minutes old at +15, +60, and the next 16:00 ET. A quieter book than that is NOT AVAILABLE at that horizon, not a carried-forward guess.
- Taker outcome side is present on every row of the tape, so the signed gap uses that side. It is not inferred from the book.
- Test 2 historical depth: NOT AVAILABLE: the repo has no order book at block time. `data/processed/orderbook_depth.csv` is a top-of-book-and-depth snapshot of 60 markets, timestamps 2026-11-07 17:08:39+00:00 to 2026-11-07 17:08:39+00:00, depth capped at 100 levels by the script that built it. Candlesticks have the best bid and ask only.
- Test 3 book weight: NOT AVAILABLE: candlesticks do not carry size at the bid or ask, and the historical book is not stored. Design (b) is a weighted median of earlier block prices only. The print being scored is not included. Design (c) uses the book when no earlier print was inside the quote.
- Recency half-life is 15 minutes, Kalshi's reporting window. It is an assumption, not a fitted number.

## 2. Tables

### Test 1. Retained fraction of the block-minus-pre-mid gap

Retained = (post mid − pre mid) / (block YES price − pre mid). Pre mid is the median usable 1-minute mid in the prior 30 minutes. Class at +60 min: reverted if retained < 25%, partial if 25% to 75% inclusive, persistent if retained > 75%. Negative retained counts as reverted.

| slice | n | n classified +60 | reverted | partial | persistent | median retained +1 % | +15 % | +60 % | next 16:00 ET % | n next close | median abs mid move +60, cents |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all blocks | 52 | 21 | 13 | 4 | 4 | 0.00 | 0.00 | 15.38 | -16.67 | 20 | 1.00 |
| outside bid-ask at the print | 25 | 16 | 10 | 4 | 2 | 0.00 | 0.00 | 15.38 | -16.67 | 8 | 1.00 |
| inside the spread at the print | 20 | 5 | 3 | 0 | 2 | 0.00 | 0.00 | 0.00 | 0.00 | 9 | 0.00 |
| no usable quote at the print | 7 | 0 | 0 | 0 | 0 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | -80.00 | 3 | NOT AVAILABLE |
| before 19 Aug 2026 | 19 | 5 | 5 | 0 | 0 | 11.11 | 26.50 | 15.38 | 0.00 | 12 | 1.00 |
| on/after 19 Aug 2026 | 33 | 16 | 8 | 4 | 4 | 0.00 | 0.00 | 21.72 | -37.93 | 8 | 1.00 |
| category: Climate and Weather | 1 | 0 | 0 | 0 | 0 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | 1 | NOT AVAILABLE |
| category: Commodities | 5 | 2 | 2 | 0 | 0 | 11.11 | 22.22 | 11.11 | 23.33 | 2 | 0.50 |
| category: Economics | 6 | 2 | 2 | 0 | 0 | 57.69 | 30.77 | 15.38 | NOT AVAILABLE | 3 | 1.00 |
| category: Elections | 11 | 11 | 6 | 3 | 2 | 0.00 | 0.00 | 0.00 | -40.00 | 3 | 1.00 |
| category: Exotics | 4 | 0 | 0 | 0 | 0 | 0.00 | -0.38 | NOT AVAILABLE | NOT AVAILABLE | 0 | NOT AVAILABLE |
| category: Financials | 2 | 0 | 0 | 0 | 0 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | -80.00 | 2 | NOT AVAILABLE |
| category: Politics | 4 | 3 | 1 | 1 | 1 | 42.86 | 68.57 | 57.14 | NOT AVAILABLE | 0 | 2.00 |
| category: Sports | 19 | 3 | 2 | 0 | 1 | 1.72 | 0.00 | 3.45 | 16.67 | 9 | 0.05 |
| |block − pre mid| ≥ 1¢ | 21 | 15 | 9 | 4 | 2 | 1.72 | 11.11 | 15.38 | -33.33 | 7 | 1.00 |

Baseline: 50 usable random minutes out of 136 attempts, drawn from 51999 five-minute slots in the same markets, seed 42, excluding the 60 minutes on either side of a block on that ticker. Median |mid(t+60) − pre mid| = 0.00¢. Share with no move: 54%. 75th percentile: 0.69¢. The baseline has no block price, so it has no retained fraction.

Of 25 prints outside the usable bid-ask, 4 have a taker side that does not match the side of the YES book they crossed. The signed gap follows the taker side anyway. Median signed gap, all blocks with a pre mid: 2.50¢.

### Test 2. Block gap versus the 7 Nov slippage curve (proxy)

Historical depth at the print: NOT AVAILABLE. The comparison below is a proxy. Gap = |block YES price − pre mid| in cents. Slippage is the 7 Nov walk-the-book number, in cents versus that day's mid, on the taker's YES side (buy if the taker bought YES, sell if the taker bought NO). The size bin is the smallest published size at or above the block (25k, 100k, 250k, 1M). A block above 1M is not compared.

| comparison | n | cheaper than the curve | dearer than the curve | median gap ¢ | median curve slippage ¢ |
| --- | --- | --- | --- | --- | --- |
| same ticker, curve fully fills the bin | 0 | 0 | 0 | NOT AVAILABLE | NOT AVAILABLE |
| same category only, curve fully fills the bin | 16 | 9 | 7 | 2.50 | 15.13 |
| no comparison | 36 | — | — | — | — |

### Test 3. Mark versus the book mid 60 minutes later

Back-test markets are the July Fed decision (`KXFEDDECISION-26JUL-H25`), Texas governor (`GOVPARTYTX-26-R`), Brazil (`KXBRPRES-26-LULA`), and every block market in the Commodities category. Mean absolute error is in cents, unweighted across prints that have both a mark and a +60 mid.

Design (b) does not include the book, and it does not include the print being scored. Design (c) is that median of earlier prints that were inside the book, and it uses the book when none exist. It is not a blend. A size-weighted blend of the book and the blocks is NOT AVAILABLE.

| slice | n (a) | MAE book ¢ | n (b) | MAE earlier-blocks median ¢ | n (c) | MAE inside-prints or book ¢ |
| --- | --- | --- | --- | --- | --- | --- |
| all back-test prints | 15 | 4.13 | 9 | 16.44 | 15 | 9.63 |
| Brazil president | 3 | 0.33 | 2 | 1.50 | 3 | 0.33 |
| July Fed decision | 2 | 0.50 | 1 | 5.50 | 2 | 0.50 |
| Texas governor | 7 | 7.35 | 6 | 23.24 | 7 | 19.14 |
| commodity hub | 3 | 2.83 | 0 | NOT AVAILABLE | 3 | 2.83 |
| Texas Governor \| GOVPARTYTX-26-R | 7 | 7.35 | 6 | 23.24 | 7 | 19.14 |
| SMM CIF Rotterdam 88.5% APT \| KXAPTROT-26DEC1708-T2250 | 1 | 8.50 | 0 | NOT AVAILABLE | 1 | 8.50 |
| Brent Monthly \| KXBRENTMON-26JUN3017-T90.99 | 1 | 0.00 | 0 | NOT AVAILABLE | 1 | 0.00 |
| Brent Monthly \| KXBRENTMON-26JUN3017-T94.99 | 1 | 0.00 | 0 | NOT AVAILABLE | 1 | 0.00 |
| Brazil Presidency \| KXBRPRES-26-LULA | 3 | 0.33 | 2 | 1.50 | 3 | 0.33 |
| Fed meeting \| KXFEDDECISION-26JUL-H25 | 2 | 0.50 | 1 | 5.50 | 2 | 0.50 |

### Test 4. Sample

| fact | value |
| --- | --- |
| blocks | 52 |
| markets | 32 |
| first block (UTC) | 2026-06-04 14:48:20.976058+00:00 |
| last block (UTC) | 2026-11-06 22:25:45.318292+00:00 |
| notional, contracts × $1 | $52,243,493.56 |
| dollars paid, taker's price × contracts | $7,584,486.50 |
| dollars paid, cheaper side × contracts (the column the rest of this repo calls premium_usd) | $6,416,970.90 |
| before 19 Aug 2026 | 19 |
| on or after 19 Aug 2026 | 33 |
| equal window before 19 Aug (2026-05-31 to 2026-08-19, open at the end) | 19 |
| equal window from 19 Aug through the last print (2026-08-19 to 2026-11-06) | 33 |
| sports prints | 19 |
| sports minimum contracts observed | 40,000.00 |
| non-sports minimum contracts observed | 25,000.00 |
| sports prints under 50,000 contracts | 2 |

Blocks by month:

| month | n |
| --- | --- |
| 2026-06 | 4 |
| 2026-07 | 8 |
| 2026-08 | 7 |
| 2026-09 | 8 |
| 2026-10 | 9 |
| 2026-11 | 16 |

By category, sports included. Dollars paid use the taker's price.

| category | n | notional $ | taker paid $ | smallest print, contracts |
| --- | --- | --- | --- | --- |
| Exotics | 4 | 19,363,317 | 1,625,000 | 934,579 |
| Sports | 19 | 16,974,728 | 1,584,887 | 40,000 |
| Elections | 11 | 10,586,949 | 3,294,800 | 214,286 |
| Economics | 6 | 3,818,000 | 493,600 | 50,000 |
| Commodities | 5 | 750,500 | 352,700 | 83,500 |
| Politics | 4 | 650,000 | 177,000 | 50,000 |
| Financials | 2 | 75,000 | 50,000 | 25,000 |
| Climate and Weather | 1 | 25,000 | 6,500 | 25,000 |

By category, sports removed.

| category | n | notional $ | taker paid $ | smallest print, contracts |
| --- | --- | --- | --- | --- |
| Exotics | 4 | 19,363,317 | 1,625,000 | 934,579 |
| Elections | 11 | 10,586,949 | 3,294,800 | 214,286 |
| Economics | 6 | 3,818,000 | 493,600 | 50,000 |
| Commodities | 5 | 750,500 | 352,700 | 83,500 |
| Politics | 4 | 650,000 | 177,000 | 50,000 |
| Financials | 2 | 75,000 | 50,000 | 25,000 |
| Climate and Weather | 1 | 25,000 | 6,500 | 25,000 |

No usable quote at the print (no bid/ask, crossed, or spread ≥ 50¢): 7 of 52.

| ticker | category | time UTC | bid | ask | YES price |
| --- | --- | --- | --- | --- | --- |
| KXMVESPORTSMULTIGAMEEXTENDED-S202637D6E1B4F28-CC2208F8F90 | Exotics | 2026-06-05 21:39:43.517802+00:00 | 0.0 | 1.0 | 0.04 |
| KXMVESPORTSMULTIGAMEEXTENDED-S202637D6E1B4F28-CC2208F8F90 | Exotics | 2026-06-05 21:39:58.115471+00:00 | 0.0 | 1.0 | 0.04 |
| KXHOBBYTEMP-26SEP01 | Climate and Weather | 2026-07-27 19:49:07.315944+00:00 | 0.0 | 0.99 | 0.26 |
| KXFLYCANCJFK-JFK-ALL-26OCT21-T50 | Economics | 2026-07-27 20:14:32.291798+00:00 | 0.0 | 0.99 | 0.004 |
| KXCAGOAT-26SEP30 | Politics | 2026-08-04 19:37:00.774808+00:00 | 0.0 | 0.0 | 0.9 |
| KXCCAPRICEICE-26AUG48 | Financials | 2026-08-18 20:25:29.687778+00:00 | 0.0 | 0.88 | 0.2 |
| KXSONORACATTLE-31MAR27-T90 | Economics | 2026-11-06 22:25:45.318292+00:00 | 0.01 | 0.99 | 0.2 |

### July Fed meeting, recomputed

| time UTC | contracts | YES price | pre bid/ask (last usable minute) | pre mid | pre source | screen at print | +1 bid/ask | +15 bid/ask | +60 bid/ask | retained +60 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-28 17:08:36.278973+00:00 | 400,000 | 0.27 | 0.2000/0.2200 | 0.2050 | median_minute_mid | 0.2/0.22 | 0.25/0.26 | 0.22/0.23 | 0.21/0.22 | 15.38 |
| 2026-07-28 17:09:37.293467+00:00 | 200,000 | 0.27 | 0.2000/0.2200 | 0.2050 | median_minute_mid | 0.2/0.22 | 0.22/0.24 | 0.22/0.23 | 0.21/0.22 | 15.38 |

## 3. Three sentences each

**Test 1.** At 60 minutes, 13 of 21 (62%) classified prints had reverted, 4 were partial, and 4 were persistent. The median retained fraction was 0.00% at +1 min, 0.00% at +15, and 15.38% at +60. Prints outside the bid-ask were 10 of 16 (62%) reverted at +60; prints inside were 3 of 5 (60%) reverted. The class counts use 21 prints with a pre mid, a +60 mid, and a non-zero gap, out of 52 blocks. The median absolute book move at +60 is 1.00¢ on the blocks and 0.00¢ on 50 random minutes in the same markets. A print can look reverted because the 30-minute median mid is not the mid at the handshake, because the public time is up to 15 minutes after the trade, or because a one-cent gap makes the ratio swing on a one-tick book move. Restricted to gaps of at least 1¢, the +60 classes are 9 reverted, 4 partial, 2 persistent, on 15 prints.

**Test 2.** Of 16 blocks with a proxy slippage, 9 had a smaller |price − pre mid| than the 7 Nov curve and 7 had a larger one. 36 blocks have no comparison. The proxy covers 16 of 52 blocks. Same-ticker snapshot rows: 1, of which 0 fully fill the size bin. Category-median comparisons: 16. The curve is one afternoon, 7 Nov 2026, not the book these trades actually lifted, and the size bin is the next published size up rather than the block's own size. A block can look cheap against a thin November book or expensive against a deep one that did not exist on the trade date.

**Test 3.** The closest point estimate on the pooled back-test is book only at 4.13¢ MAE. Book only is 4.13¢ (n=15). The earlier-blocks median, which leaves out the print being scored, is 16.44¢ (n=9). Inside-prints-or-book is 9.63¢ (n=15). On the 9 prints that have an earlier block, the book is 5.66¢ and the earlier-blocks median is 16.44¢. Six of those nine are the Texas governor market. Design (b) ignores the book, and design (c) uses the book when no earlier print was inside the quote. Sixty minutes is a short horizon, and several of these prints are the same event a minute apart, so the errors are not independent.

**Test 4.** The tape has 52 blocks. Dollars paid at the taker's price are not the same object as contracts times the cheaper side; both are in the table. The equal-length windows are 79.9 days. The before window opens on 2026-05-31, after the scan has already started and before the first block, so it contains the same 19 prints as the raw pre-19-Aug count, against 33 from 19 Aug through the last print. Sports prints are in the category table. The smallest sports print in the tape is 40,000 contracts, and 2 sports prints are under 50,000, so this tape does not confirm a 50,000-contract sports minimum.

## 4. Bottom line

- On this tape the gap mostly does not stay in the book: more prints revert than persist or partially stick. Classified at +60: 13 reverted, 4 partial, 4 persistent, out of 21.
- Median retained fraction at +60 is 15.38%. Median |book move| is 1.00¢ after a block and 0.00¢ at 50 random times.
- The closest point estimate on the pooled back-test is book only at 4.13¢ MAE. Book only is 4.13¢ (n=15), the earlier-blocks median is 16.44¢ (n=9), and inside-prints-or-book is 9.63¢ (n=15).
- Against the 7 Nov curve, 9 comparable blocks were inside that curve's slippage and 7 were outside it. This is not the cost of walking the book at the time of the trade.
- A mark that weights the book and the blocks together by size is NOT AVAILABLE: the historical book depth was not stored.

## 5. Files

- `src/07_block_diagnostics.py` — this script.
- `data/processed/block_paths.csv` — one row per block, mids, retained fractions, class.
- `data/processed/baseline_moves.csv` — the random-minute control.
- `data/processed/slippage_proxy.csv` — Test 2.
- `data/processed/mark_scores.csv` — Test 3.
- `data/processed/report.md` — this report.
- `data/cache/` — candlestick and VWAP responses, so a rerun does not refetch. Not committed.

Rerun from inside `kalshi-cost-of-size`:

```
python src/07_block_diagnostics.py
```
