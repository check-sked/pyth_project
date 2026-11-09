"""Hyperliquid hourly funding history + current open interest.

Source: POST https://api.hyperliquid.xyz/info
  {"type":"fundingHistory","coin":..,"startTime":..}  -> 500 hourly rows per page
  {"type":"metaAndAssetCtxs"} and {"type":"metaAndAssetCtxs","dex":"xyz"} -> openInterest (coins), markPx
Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals
Funding mechanics: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding
  (paid hourly, cap 0.5%/hour, rate is the hourly fraction; positive = longs pay)

Writes data/raw/hyperliquid/funding.parquet, oi_snapshot.json, fetch_status.json
Rerun: python src/01_fetch_hyperliquid.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import SAMPLE_END, SAMPLE_START, SYMBOLS, log_status, post_json, write_funding, write_json

INFO = "https://api.hyperliquid.xyz/info"


def funding_history(coin: str, start_ms: int, end_ms: int) -> list[dict]:
    out, cursor = [], start_ms
    while True:
        rows = post_json(INFO, {"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": end_ms})
        if not rows:
            break
        out.extend(rows)
        if len(rows) < 500:
            break
        cursor = rows[-1]["time"] + 1
    return out


def main() -> None:
    start_ms = int((SAMPLE_START - pd.Timedelta(days=1)).timestamp() * 1000)
    end_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    rows, status = [], {}
    for asset, coin in SYMBOLS["hyperliquid"].items():
        hist = funding_history(coin, start_ms, end_ms)
        for r in hist:
            rows.append({
                "asset": asset,
                # prints land a few ms after the hour; the payment covers the hour that ends there
                "time": pd.Timestamp(r["time"], unit="ms", tz="UTC").floor("h"),
                "rate": float(r["fundingRate"]),
                "interval_h": 1.0,
                "premium": float(r["premium"]),
            })
        ts = [r["time"] for r in hist]
        status[asset] = {
            "coin": coin, "rows": len(hist),
            "first": pd.Timestamp(min(ts), unit="ms", tz="UTC").isoformat() if ts else None,
            "last": pd.Timestamp(max(ts), unit="ms", tz="UTC").isoformat() if ts else None,
        }
        print(asset, status[asset])
    write_funding("hyperliquid", rows)
    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_parquet(Path(__file__).resolve().parents[1] / "data" / "raw" / "hyperliquid" / "funding_with_premium.parquet", index=False)

    # open interest snapshot (no public history)
    snap = {}
    for dex in (None, "xyz"):
        payload = {"type": "metaAndAssetCtxs"} | ({"dex": dex} if dex else {})
        meta, ctxs = post_json(INFO, payload)
        for a, c in zip(meta["universe"], ctxs):
            for asset, coin in SYMBOLS["hyperliquid"].items():
                if a["name"] == coin:
                    oi = float(c["openInterest"])
                    px = float(c["markPx"])
                    snap[asset] = {"coin": coin, "openInterest_coins": oi, "markPx": px,
                                   "oi_usd": oi * px, "funding_hourly": float(c["funding"]),
                                   "snapshot_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    write_json("hyperliquid", "oi_snapshot.json", snap)
    status["oi_snapshot"] = snap
    log_status("hyperliquid", status)


if __name__ == "__main__":
    main()
