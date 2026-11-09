"""Shared paths, HTTP helper, symbol map and annualisation constants.

Not run on its own. Every fetcher writes one long-format funding table per venue to
data/raw/<venue>/funding.parquet with the columns

    venue, asset, time (UTC, end of the accrual period), rate (fraction, per print),
    interval_h (hours the print accrues over)

Sign convention everywhere: positive = longs pay shorts.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUTPUT = ROOT / "output"
for _p in (RAW, PROCESSED, OUTPUT):
    _p.mkdir(parents=True, exist_ok=True)

# Analysis window. Binance's public archive publishes funding by calendar month, so the
# last complete month is the end of the common sample.
SAMPLE_START = pd.Timestamp("2025-11-01", tz="UTC")
SAMPLE_END = pd.Timestamp("2026-10-31 23:59:59", tz="UTC")

HOURS_PER_YEAR = 24 * 365

ASSETS = ["BTC", "ETH", "SOL", "NVDA", "TSLA"]
CRYPTO = ["BTC", "ETH", "SOL"]
EQUITY = ["NVDA", "TSLA"]

# venue -> asset -> venue symbol
SYMBOLS: dict[str, dict[str, str]] = {
    "hyperliquid": {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL", "NVDA": "xyz:NVDA", "TSLA": "xyz:TSLA"},
    "binance": {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "NVDA": "NVDAUSDT", "TSLA": "TSLAUSDT"},
    "bybit": {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "NVDA": "NVDAUSDT", "TSLA": "TSLAUSDT"},
    "okx": {"BTC": "BTC-USDT-SWAP", "ETH": "ETH-USDT-SWAP", "SOL": "SOL-USDT-SWAP", "NVDA": "NVDA-USDT-SWAP", "TSLA": "TSLA-USDT-SWAP"},
    "gate": {"BTC": "BTC_USDT", "ETH": "ETH_USDT", "SOL": "SOL_USDT", "NVDA": "NVDA_USDT", "TSLA": "TSLA_USDT"},
    "lighter": {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL", "NVDA": "NVDA", "TSLA": "TSLA"},
}

VENUES = ["hyperliquid", "binance", "bybit", "okx", "gate", "lighter"]

# Composite columns in hourly_wide_<ASSET>.csv (built in 08_normalize.py).
#   comp_oi        uncapped OI-weighted mean
#   comp_oi_cap30  OI-weighted, each venue's weight capped at 30% (excess redistributed pro rata)
#   comp_oi_cap20  same with a 20% cap
#   comp_median    median across venues with data
COMPOSITES = ["comp_oi", "comp_oi_cap30", "comp_oi_cap20", "comp_median"]
CAPS = {"comp_oi_cap30": 0.30, "comp_oi_cap20": 0.20}
# Composite the comparison in src/14 settles on.
CHOSEN_COMPOSITE = "comp_oi_cap30"


def capped_weights(w: "pd.Series", cap: float) -> "pd.Series":
    """Normalise weights to sum 1, then cap each at `cap`, redistributing the excess pro rata to
    the uncapped venues until no venue exceeds the cap. If the cap is infeasible (fewer than
    1/cap venues present) every venue gets an equal weight, the closest feasible allocation."""
    w = w[w > 0].astype(float)
    if w.empty:
        return w
    if len(w) * cap < 1 - 1e-12:
        return pd.Series(1.0 / len(w), index=w.index)
    w = w / w.sum()
    capped = pd.Series(False, index=w.index)
    for _ in range(len(w) + 1):
        over = (w > cap + 1e-12) & ~capped
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        capped |= over
        free = ~capped
        if free.any():
            w[free] += excess * w[free] / w[free].sum()
    return w

_session = requests.Session()
_session.headers["User-Agent"] = "perps-funding-benchmark/0.1 (research; public endpoints only)"


def get(url: str, params: dict | None = None, retries: int = 6, pause: float = 0.25, timeout: int = 30) -> Any:
    """GET with retry and backoff. Returns parsed JSON. Raises on final failure.
    A geo-block (HTTP 403/451 or Binance's code 0 'restricted location') raises GeoBlocked."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code in (403, 451):
                raise GeoBlocked(f"HTTP {r.status_code} from {url}: {r.text[:200].strip()}")
            if r.status_code == 429:
                time.sleep(min(60, 5 * 2**attempt))
                continue
            r.raise_for_status()
            time.sleep(pause)
            js = r.json()
            if isinstance(js, dict) and js.get("code") == 0 and "restricted location" in str(js.get("msg", "")):
                raise GeoBlocked(f"{url}: {js['msg'][:160]}")
            return js
        except GeoBlocked:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} {params} failed: {last}")


def post_json(url: str, payload: dict, retries: int = 8, pause: float = 0.6, timeout: int = 30) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = _session.post(url, json=payload, timeout=timeout)
            if r.status_code == 429:
                time.sleep(min(60, 5 * 2**attempt))
                continue
            r.raise_for_status()
            time.sleep(pause)
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"POST {url} {payload} failed: {last}")


class GeoBlocked(RuntimeError):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return now_utc().strftime("%Y-%m-%dT%H%MZ")


def write_funding(venue: str, rows: list[dict]) -> pd.DataFrame:
    """rows: dicts with asset, time (pd.Timestamp UTC), rate (float), interval_h (float)."""
    out = RAW / venue
    out.mkdir(exist_ok=True)
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["venue", "asset", "time", "rate", "interval_h"])
    else:
        df["venue"] = venue
        df = df[["venue", "asset", "time", "rate", "interval_h"]].sort_values(["asset", "time"])
        df = df.drop_duplicates(["asset", "time"], keep="last").reset_index(drop=True)
    df.to_parquet(out / "funding.parquet", index=False)
    return df


def write_json(venue: str, name: str, obj: Any) -> Path:
    out = RAW / venue
    out.mkdir(exist_ok=True)
    p = out / name
    p.write_text(json.dumps(obj, indent=1, default=str))
    return p


def load_wide(asset: str) -> pd.DataFrame:
    """Hourly annualised rates (fractions) per venue + comp_oi, comp_median, n_venues."""
    df = pd.read_csv(PROCESSED / f"hourly_wide_{asset}.csv", index_col="hour", parse_dates=["hour"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def load_prints() -> pd.DataFrame:
    """Native prints: venue, asset, time, rate, interval_h, source."""
    return pd.read_parquet(PROCESSED / "prints_long.parquet")


def pct(x: float) -> float:
    """fraction -> percentage points, rounded for tables."""
    return round(float(x) * 100, 2)


def log_status(venue: str, status: dict) -> None:
    """Record what the fetch saw (first/last timestamp, row counts, errors) so a
    NOT AVAILABLE claim in the report is reproducible."""
    status["fetched_at_utc"] = now_utc().isoformat()
    write_json(venue, "fetch_status.json", status)
    print(json.dumps(status, indent=1, default=str))
