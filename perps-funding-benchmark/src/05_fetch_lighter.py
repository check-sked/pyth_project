"""Lighter hourly funding history and open interest.

Source:
  GET https://mainnet.zklighter.elliot.ai/api/v1/orderBookDetails
      -> market_id per symbol, open_interest (coins), last_trade_price, funding_clamp_big/small, base_interest_rate
  GET https://mainnet.zklighter.elliot.ai/api/v1/fundings?market_id=..&resolution=1h&start_timestamp=..&end_timestamp=..&count_back=750
      -> at most 750 rows per call (docs: https://docs.lighter.xyz/api/funding/fundings), paged back by end_timestamp.
      Row: {timestamp (s), value, rate, direction in {long, short}}.
Units: `rate` is a percent per hour. Checks (2026-11-08): the default print when the premium
  is inside the small clamp is InterestRate/8 = 0.01%/8 = 0.00125%/h and shows as "0.0012";
  `value` ~= mark price x rate/100 (NVDA: 181.3 x 0.0132/100 = 0.0239 vs value 0.02393).
  `rate` is unsigned; `direction` = "long" is read as longs pay (positive), "short" as shorts pay.
  Docs on mechanics and sign: https://docs.lighter.xyz/trading/funding
  (hourly, BigClamp 4% per 8h = 0.5%/h, positive = longs pay). The sign reading is verified
  against Hyperliquid in 07_normalize.py (correlation must be positive).

Writes data/raw/lighter/funding.parquet, markets.json, fetch_status.json
Rerun: python src/05_fetch_lighter.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import time

import pandas as pd

from common import SAMPLE_START, SYMBOLS, get, log_status, write_funding, write_json

BASE = "https://mainnet.zklighter.elliot.ai/api/v1"


def history(market_id: int) -> list[dict]:
    end = int(time.time())
    floor = int(SAMPLE_START.timestamp()) - 86400
    out = []
    while end > floor:
        d = get(f"{BASE}/fundings", {"market_id": market_id, "resolution": "1h",
                                     "start_timestamp": floor * 1000, "end_timestamp": end * 1000, "count_back": 750})
        f = d.get("fundings", [])
        if not f:
            break
        out.extend(f)
        oldest = min(x["timestamp"] for x in f)
        if oldest >= end:
            break
        end = oldest - 1
    return out


def main() -> None:
    books = get(f"{BASE}/orderBookDetails")["order_book_details"]
    by_sym = {b["symbol"]: b for b in books}
    rows, status, markets = [], {}, {}
    for asset, sym in SYMBOLS["lighter"].items():
        b = by_sym.get(sym)
        if not b:
            status[asset] = {"error": f"symbol {sym} not in orderBookDetails"}
            continue
        mid = b["market_id"]
        markets[asset] = {k: b.get(k) for k in ("symbol", "market_id", "status", "open_interest", "last_trade_price",
                                                 "daily_quote_token_volume", "funding_clamp_big", "funding_clamp_small",
                                                 "base_interest_rate", "market_type", "funding_interval")}
        markets[asset]["oi_usd"] = float(b["open_interest"]) * float(b["last_trade_price"])
        markets[asset]["snapshot_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
        hist = history(mid)
        for r in hist:
            sign = 1.0 if r["direction"] == "long" else -1.0
            rows.append({"asset": asset, "time": pd.Timestamp(int(r["timestamp"]), unit="s", tz="UTC").floor("h"),
                         "rate": sign * float(r["rate"]) / 100.0,  # percent/hour -> fraction/hour
                         "interval_h": 1.0, "value": float(r["value"]), "direction": r["direction"]})
        ts = sorted(int(r["timestamp"]) for r in hist)
        status[asset] = {"market_id": mid, "rows": len(hist),
                         "first": pd.Timestamp(ts[0], unit="s", tz="UTC").isoformat() if ts else None,
                         "last": pd.Timestamp(ts[-1], unit="s", tz="UTC").isoformat() if ts else None,
                         "oi_usd_now": markets[asset]["oi_usd"]}
        print(asset, status[asset])
    write_funding("lighter", rows)
    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_parquet(Path(__file__).resolve().parents[1] / "data" / "raw" / "lighter" / "funding_with_direction.parquet", index=False)
    write_json("lighter", "markets.json", markets)
    log_status("lighter", status)


if __name__ == "__main__":
    main()
