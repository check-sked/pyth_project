"""Binance USD-M funding history and open interest from the public data archive.

The REST API (https://fapi.binance.com/fapi/v1/fundingRate, /openInterestHist) answers
`{"code":0,"msg":"Service unavailable from a restricted location ..."}` from this machine
(US IP, checked 2026-11-08). The archive bucket is not geo-fenced:

  https://data.binance.vision/data/futures/um/monthly/fundingRate/<SYMBOL>/<SYMBOL>-fundingRate-YYYY-MM.zip
      columns: calc_time (ms), funding_interval_hours, last_funding_rate
      Published per complete calendar month, so the series ends at the last month-end.
  https://data.binance.vision/data/futures/um/daily/metrics/<SYMBOL>/<SYMBOL>-metrics-YYYY-MM-DD.zip
      5-minute rows: sum_open_interest (coins), sum_open_interest_value (USDT) -> OI history
  Bucket listing: https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=...
Archive docs: https://github.com/binance/binance-public-data

Writes data/raw/binance/funding.parquet, oi_daily.csv, fetch_status.json
Rerun: python src/02_fetch_binance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import io
import re
import zipfile

import pandas as pd
import requests

from common import GeoBlocked, RAW, SAMPLE_END, SAMPLE_START, SYMBOLS, get, log_status, write_funding

BASE = "https://data.binance.vision/data/futures/um"
LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
OUT = RAW / "binance"
OUT.mkdir(exist_ok=True)


def list_keys(prefix: str) -> list[str]:
    r = requests.get(LIST, params={"delimiter": "/", "prefix": prefix}, timeout=30)
    r.raise_for_status()
    return re.findall(r"<Key>([^<]+\.zip)</Key>", r.text)


def read_zip_csv(url: str) -> pd.DataFrame | None:
    r = requests.get(url, timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = z.namelist()[0]
    return pd.read_csv(z.open(name))


def main() -> None:
    status: dict = {"rest_api": None}
    try:
        get("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": "BTCUSDT", "limit": 1})
        status["rest_api"] = "reachable"
    except GeoBlocked as e:
        status["rest_api"] = f"GEO-BLOCKED: {e}"
    except Exception as e:  # noqa: BLE001
        status["rest_api"] = f"error: {e}"

    rows = []
    months = pd.period_range(SAMPLE_START.to_period("M"), SAMPLE_END.to_period("M"), freq="M")
    for asset, sym in SYMBOLS["binance"].items():
        keys = list_keys(f"data/futures/um/monthly/fundingRate/{sym}/")
        avail = sorted({re.search(r"fundingRate-(\d{4}-\d{2})\.zip", k).group(1) for k in keys if k.endswith(".zip")})
        n = 0
        for m in months:
            tag = m.strftime("%Y-%m")
            if tag not in avail:
                continue
            df = read_zip_csv(f"{BASE}/monthly/fundingRate/{sym}/{sym}-fundingRate-{tag}.zip")
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                rows.append({
                    "asset": asset,
                    # calc_time is the funding timestamp (a few ms after the hour); the print
                    # settles the interval that ends there
                    "time": pd.Timestamp(int(r["calc_time"]), unit="ms", tz="UTC").floor("h"),
                    "rate": float(r["last_funding_rate"]),
                    "interval_h": float(r["funding_interval_hours"]),
                })
                n += 1
        status[asset] = {"symbol": sym, "rows": n, "archive_months_available": f"{avail[0]}..{avail[-1]}" if avail else None,
                         "months_used": [m.strftime("%Y-%m") for m in months if m.strftime("%Y-%m") in avail]}
        print(asset, status[asset])
    df = write_funding("binance", rows)
    for asset, g in df.groupby("asset"):
        status[asset]["first"] = g["time"].min().isoformat()
        status[asset]["last"] = g["time"].max().isoformat()
        status[asset]["interval_hours_seen"] = sorted(g["interval_h"].unique().tolist())

    # Open interest: last 35 daily metrics files (5-minute rows) -> daily mean + last value
    oi_rows = []
    days = pd.date_range(pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=35), pd.Timestamp.now(tz="UTC").normalize(), freq="D")
    for asset, sym in SYMBOLS["binance"].items():
        for d in days:
            tag = d.strftime("%Y-%m-%d")
            df = read_zip_csv(f"{BASE}/daily/metrics/{sym}/{sym}-metrics-{tag}.zip")
            if df is None or df.empty:
                continue
            oi_rows.append({"asset": asset, "symbol": sym, "date": tag,
                            "oi_coins_mean": df["sum_open_interest"].astype(float).mean(),
                            "oi_usd_mean": df["sum_open_interest_value"].astype(float).mean(),
                            "oi_usd_last": float(df["sum_open_interest_value"].astype(float).iloc[-1]),
                            "last_row_time": str(df["create_time"].iloc[-1])})
    oi = pd.DataFrame(oi_rows)
    oi.to_csv(OUT / "oi_daily.csv", index=False)
    status["oi_daily"] = {a: {"days": int(len(g)), "first": g["date"].min(), "last": g["date"].max()} for a, g in oi.groupby("asset")} if not oi.empty else {}
    log_status("binance", status)


if __name__ == "__main__":
    main()
