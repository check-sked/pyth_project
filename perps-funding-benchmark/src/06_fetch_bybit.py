"""Bybit funding history attempt. Records the outcome so the report's availability claim is reproducible.

Source tried:
  GET https://api.bybit.com/v5/market/funding/history?category=linear&symbol=..&limit=200
  GET https://api.bytick.com/...  (alternate host)
  Docs: https://bybit-exchange.github.io/docs/v5/market/history-fund-rate
Also checks https://public.bybit.com/ (bulk archive). It lists premium_index klines but no
funding-rate prints, so funding cannot be read from the archive without re-deriving it.

Writes data/raw/bybit/funding.parquet (possibly empty), fetch_status.json
Rerun: python src/06_fetch_bybit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import re

import pandas as pd
import requests

from common import GeoBlocked, SYMBOLS, get, log_status, write_funding

HOSTS = ["https://api.bybit.com", "https://api.bytick.com"]


def main() -> None:
    status: dict = {"hosts": {}}
    rows = []
    ok_host = None
    for h in HOSTS:
        try:
            d = get(f"{h}/v5/market/funding/history", {"category": "linear", "symbol": "BTCUSDT", "limit": 5})
            status["hosts"][h] = f"ok retCode={d.get('retCode')}"
            ok_host = h
            break
        except GeoBlocked as e:
            status["hosts"][h] = f"GEO-BLOCKED: {e}"
        except Exception as e:  # noqa: BLE001
            status["hosts"][h] = f"error: {e}"
    if ok_host:
        for asset, sym in SYMBOLS["bybit"].items():
            end = None
            got = []
            for _ in range(60):
                p = {"category": "linear", "symbol": sym, "limit": 200}
                if end:
                    p["endTime"] = end
                d = get(f"{ok_host}/v5/market/funding/history", p)
                lst = d.get("result", {}).get("list", [])
                if not lst:
                    break
                got.extend(lst)
                end = int(lst[-1]["fundingRateTimestamp"]) - 1
            times = sorted(int(x["fundingRateTimestamp"]) for x in got)
            gaps = pd.Series(times).diff().dropna() / 3.6e6
            interval = float(gaps.round().mode().iloc[0]) if len(gaps) else 8.0
            for x in got:
                rows.append({"asset": asset, "time": pd.Timestamp(int(x["fundingRateTimestamp"]), unit="ms", tz="UTC").floor("h"),
                             "rate": float(x["fundingRate"]), "interval_h": interval})
            status[asset] = {"symbol": sym, "rows": len(got)}
    try:
        r = requests.get("https://public.bybit.com/", timeout=20)
        status["public_archive_root"] = {"http": r.status_code, "dirs": re.findall(r'href="([^"]+/)"', r.text)}
    except Exception as e:  # noqa: BLE001
        status["public_archive_root"] = f"error: {e}"
    write_funding("bybit", rows)
    status["result"] = "funding history fetched" if rows else "NOT AVAILABLE: REST API geo-blocked from this machine; public archive has no funding prints"
    log_status("bybit", status)


if __name__ == "__main__":
    main()
