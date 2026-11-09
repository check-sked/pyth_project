"""Step 2: snapshot the Kalshi market universe.

- All series (ticker -> category/title/tags)           -> data/raw/series.csv
- All open, non-combo markets with volume/OI/top-of-book -> data/raw/markets_open.csv

Used to (a) classify block trades into categories, (b) measure how thin the
public screen is (displayed size at best bid/ask) relative to block sizes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import kalshi  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

MARKET_COLS = ["ticker", "event_ticker", "title", "subtitle", "status", "market_type", "open_time", "close_time",
               "last_price_dollars", "previous_price_dollars", "yes_bid_dollars", "yes_ask_dollars",
               "yes_bid_size_fp", "yes_ask_size_fp", "volume_fp", "volume_24h_fp", "open_interest_fp",
               "notional_value_dollars", "price_level_structure", "can_close_early"]


def pull_series() -> pd.DataFrame:
    rows = []
    for s in kalshi.paginate("/series", {}, "series", limit=1000):
        rows.append({"series_ticker": s["ticker"], "category": s.get("category"), "series_title": s.get("title"),
                     "tags": "|".join(s.get("tags") or []), "fee_type": s.get("fee_type"),
                     "settlement_sources": "|".join(x.get("name", "") for x in (s.get("settlement_sources") or []))})
    df = pd.DataFrame(rows)
    df.to_csv(RAW / "series.csv", index=False)
    print(f"series: {len(df)} rows; categories: {df.category.value_counts().to_dict()}", file=sys.stderr)
    return df


def pull_open_markets() -> pd.DataFrame:
    rows = []
    for i, m in enumerate(kalshi.markets(status="open", mve_filter="exclude")):
        rows.append({c: m.get(c) for c in MARKET_COLS})
        if i % 5000 == 0:
            print(f"  {i} markets...", file=sys.stderr)
    df = pd.DataFrame(rows)
    df["series_ticker"] = df.ticker.map(kalshi.series_ticker_of)
    df.to_csv(RAW / "markets_open.csv", index=False)
    print(f"open non-combo markets: {len(df)}", file=sys.stderr)
    return df


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    pull_series()
    pull_open_markets()
