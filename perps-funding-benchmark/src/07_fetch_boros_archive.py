"""Pendle's public Boros historical-data archive: market list, and exchange funding series
used (a) as the only reachable Bybit source and (b) to cross-check the primary venue pulls.

Source: https://historical-data.boros.finance/  (static site; file index at /files.json)
  funding-rate/<Exchange>-<Asset>.ndjson.zip   rows {timestamp (s), datetime, annualizedFundingRate}
      Schema text on the index page: "Historical underlying funding rates sourced from exchanges."
      annualizedFundingRate = per-print rate x prints per year (Bybit 8h: 0.0001 -> 0.1095).
  market-data/<id>-<EXCHANGE>-<SYMBOL>-<MATURITY>/<YYYY-MM>.ndjson.zip
      directory names enumerate every Boros market ever listed (id, exchange, symbol, maturity).

Bybit's own API is geo-blocked from this machine (see 06_fetch_bybit.py). The Bybit series
here is second-hand (collected by Pendle), so the report labels it "Bybit via Boros archive",
and the same archive's Binance/Hyperliquid/OKX/Gate/Lighter series are compared with the
primary pulls in 08_normalize.py to show the archive reproduces exchange prints.

Writes data/raw/boros/files.json, boros_markets_from_archive.csv, archive_funding.parquet
       data/raw/bybit/funding.parquet (only if 06 left it empty), updates bybit/fetch_status.json
Rerun: python src/07_fetch_boros_archive.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import io
import json
import re
import zipfile

import pandas as pd
import requests

from common import RAW, SAMPLE_START, log_status, write_funding

BASE = "https://historical-data.boros.finance"
OUT = RAW / "boros"
OUT.mkdir(exist_ok=True)

ARCHIVE_SERIES = {  # archive name -> (venue, asset)
    "Bybit-BTC": ("bybit", "BTC"), "Bybit-ETH": ("bybit", "ETH"), "Bybit-SOL": ("bybit", "SOL"),
    "Binance-BTC": ("binance", "BTC"), "Binance-ETH": ("binance", "ETH"), "Binance-SOL": ("binance", "SOL"),
    "Hyperliquid-BTC": ("hyperliquid", "BTC"), "Hyperliquid-ETH": ("hyperliquid", "ETH"), "Hyperliquid-SOL": ("hyperliquid", "SOL"),
    "Hyperliquid-NVDA": ("hyperliquid", "NVDA"),
    "OKX-BTC": ("okx", "BTC"), "OKX-ETH": ("okx", "ETH"), "OKX-SOL": ("okx", "SOL"),
    "Gate-BTC": ("gate", "BTC"), "Gate-ETH": ("gate", "ETH"), "Gate-SOL": ("gate", "SOL"),
    "Lighter-BTC": ("lighter", "BTC"), "Lighter-ETH": ("lighter", "ETH"), "Lighter-SOL": ("lighter", "SOL"),
}


def read_ndjson_zip(path: str) -> pd.DataFrame:
    r = requests.get(f"{BASE}/{path}", timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    rows = []
    for name in z.namelist():
        for line in z.open(name).read().decode().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def main() -> None:
    files = requests.get(f"{BASE}/files.json", timeout=30).json()
    (OUT / "files.json").write_text(json.dumps(files))

    # Boros market list from directory names
    mk = {}
    for f in files:
        m = re.match(r"market-data/(\d+)-([A-Z]+)-(.+)-(\d{1,2}[A-Z]{3}\d{4})/(\d{4}-\d{2})\.ndjson\.zip", f["path"])
        if m:
            mid, ex, sym, mat, month = m.groups()
            d = mk.setdefault(int(mid), {"market_id": int(mid), "exchange": ex, "symbol": sym, "maturity": mat, "months": []})
            d["months"].append(month)
    rows = []
    for d in sorted(mk.values(), key=lambda x: x["market_id"]):
        rows.append({**{k: v for k, v in d.items() if k != "months"},
                     "first_month": min(d["months"]), "last_month": max(d["months"]),
                     "maturity_date": pd.to_datetime(d["maturity"], format="%d%b%Y").date()})
    markets = pd.DataFrame(rows)
    markets.to_csv(OUT / "boros_markets_from_archive.csv", index=False)
    print(f"Boros markets in archive: {len(markets)}; exchanges: {markets.exchange.value_counts().to_dict()}")

    # exchange funding series
    out = []
    status = {}
    for name, (venue, asset) in ARCHIVE_SERIES.items():
        try:
            df = read_ndjson_zip(f"funding-rate/{name}.ndjson.zip")
        except Exception as e:  # noqa: BLE001
            status[name] = f"error: {e}"
            continue
        df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df = df.sort_values("time")
        # The archive's sampling cadence changes over time (e.g. Binance-ETH is hourly until
        # 2025Q4 and 8h after), so the accrual interval is taken per row from the gap to the
        # previous print, clipped to the venue's possible intervals {1, 4, 8} h.
        gaps = (df["time"].diff().dt.total_seconds() / 3600).round()
        gaps = gaps.bfill().clip(lower=1, upper=8)
        gaps = gaps.where(gaps.isin([1, 2, 4, 8]), 8)
        df["venue"], df["asset"], df["interval_h"] = venue, asset, gaps.astype(float)
        df["rate"] = df["annualizedFundingRate"] * df["interval_h"] / 8760.0  # back to per-print fraction
        out.append(df[["venue", "asset", "time", "rate", "interval_h", "annualizedFundingRate"]])
        recent = df[df["time"] >= SAMPLE_START]
        status[name] = {"rows": int(len(df)), "interval_h_mode_in_sample": float(recent["interval_h"].mode().iloc[0]) if len(recent) else None,
                        "first": df["time"].min().isoformat(), "last": df["time"].max().isoformat()}
        print(name, status[name])
    arch = pd.concat(out, ignore_index=True)
    arch.to_parquet(OUT / "archive_funding.parquet", index=False)

    # Bybit fallback
    bybit_path = RAW / "bybit" / "funding.parquet"
    existing = pd.read_parquet(bybit_path) if bybit_path.exists() else pd.DataFrame()
    if existing.empty:
        b = arch[(arch.venue == "bybit") & (arch.time >= SAMPLE_START - pd.Timedelta(days=1))]
        write_funding("bybit", b[["asset", "time", "rate", "interval_h"]].to_dict("records"))
        st_path = RAW / "bybit" / "fetch_status.json"
        st = json.loads(st_path.read_text()) if st_path.exists() else {}
        st["fallback_source"] = "https://historical-data.boros.finance/funding-rate/Bybit-<ASSET>.ndjson.zip (Pendle-collected)"
        st["fallback_rows"] = {a: int(n) for a, n in b.groupby("asset").size().items()}
        st["result"] = "Bybit API geo-blocked; funding taken from Pendle's Boros historical-data archive (second-hand)"
        st_path.write_text(json.dumps(st, indent=1, default=str))
    status["markets_in_archive"] = int(len(markets))
    log_status("boros", status)


if __name__ == "__main__":
    main()
