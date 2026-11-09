"""Step 5b: daily candlesticks (volume, open interest, bid/ask close) for the
top-OI markets, so month-end valuations use the open interest *as of* the date
rather than today's OI.

Output: data/raw/daily_candles_top_oi.parquet
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import kalshi  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def main():
    mk = pd.read_csv(RAW / "trades_top_oi_markets.csv")
    start = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
    end = int(time.time())
    frames = []
    for t in mk.ticker:
        cs = kalshi.candlesticks(kalshi.series_ticker_of(t), t, start, end, period_interval=1440)
        rows = [{"ticker": t, "date": pd.Timestamp(c["end_period_ts"], unit="s", tz="UTC").normalize(),
                 "volume_fp": float(c["volume_fp"]), "open_interest_fp": float(c["open_interest_fp"]),
                 "bid_close": c["yes_bid"].get("close_dollars"), "ask_close": c["yes_ask"].get("close_dollars"),
                 "px_close": c["price"].get("close_dollars"), "px_mean": c["price"].get("mean_dollars")}
                for c in cs]
        frames.append(pd.DataFrame(rows))
        time.sleep(0.1)
    df = pd.concat(frames, ignore_index=True)
    for c in ["bid_close", "ask_close", "px_close", "px_mean"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.to_parquet(RAW / "daily_candles_top_oi.parquet", index=False)
    print(f"wrote {len(df)} daily candles for {df.ticker.nunique()} markets", file=sys.stderr)


if __name__ == "__main__":
    main()
