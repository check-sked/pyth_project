"""Step 5: pull the full public trade tape (live window) for the largest
non-sports markets by open interest.

Open interest is the right lens for a valuation product: it is the stock of
positions that must be marked. We take the top-N open, non-sports markets
with a live price (5c-95c), excluding intraday crypto/gas series, and pull
every trade since the live/historical cutoff (currently 2026-09-08).

Output: data/raw/trades_top_oi.parquet, data/raw/trades_top_oi_markets.csv
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import kalshi  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SPORTS = {"Sports", "Esports"}
INTRADAY = "15M|BTCD|ETHD|SOLD|XRPD|AAAGASD"


def pick(n: int) -> pd.DataFrame:
    mk = pd.read_csv(RAW / "markets_open.csv")
    se = pd.read_csv(RAW / "series.csv")
    mk = mk.merge(se[["series_ticker", "category", "series_title"]], on="series_ticker", how="left")
    for c in ["volume_fp", "volume_24h_fp", "open_interest_fp", "last_price_dollars"]:
        mk[c] = pd.to_numeric(mk[c], errors="coerce")
    mk = mk[~mk.category.isin(SPORTS) & mk.last_price_dollars.between(0.05, 0.95)]
    mk = mk[~mk.series_ticker.str.contains(INTRADAY)]
    return mk.sort_values("open_interest_fp", ascending=False).head(n)


def main(n: int = 40):
    cutoff = kalshi.get("/historical/cutoff")["trades_created_ts"]
    min_ts = int(datetime.fromisoformat(cutoff.replace("Z", "+00:00")).timestamp())
    mk = pick(n)
    mk.to_csv(RAW / "trades_top_oi_markets.csv", index=False)
    frames = []
    for i, t in enumerate(mk.ticker):
        rows = list(kalshi.trades(ticker=t, min_ts=min_ts))
        df = pd.DataFrame(rows)
        if not df.empty:
            df["ticker"] = t
            frames.append(df)
        print(f"  [{i+1}/{len(mk)}] {t}: {len(rows)} trades", file=sys.stderr)
        time.sleep(0.2)
    out = pd.concat(frames, ignore_index=True)
    out["created_time"] = pd.to_datetime(out.created_time, utc=True)
    for c in ["count_fp", "yes_price_dollars", "no_price_dollars"]:
        out[c] = pd.to_numeric(out[c])
    out.to_parquet(RAW / "trades_top_oi.parquet", index=False)
    print(f"wrote {len(out)} trades for {out.ticker.nunique()} markets", file=sys.stderr)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
