"""Gate USDT-settled perpetual funding history, contract parameters and open interest.

Source:
  GET https://api.gateio.ws/api/v4/futures/usdt/funding_rate?contract=..&limit=1000&from=..&to=..
      -> [{r, t}] with t = funding time (s). `from` may not be older than 180 days
      ("from time exceeds 180-day limit", checked 2026-11-08). Fetched in 30-day windows.
  GET https://api.gateio.ws/api/v4/futures/usdt/contracts/<contract>
      -> funding_interval (s), funding_cap_ratio, position_size (OI in contracts), quanto_multiplier, mark_price
  GET https://api.gateio.ws/api/v4/futures/usdt/contract_stats?contract=..&interval=1d&limit=30
      -> daily open_interest, open_interest_usd
Docs: https://www.gate.com/docs/developers/apiv4/#funding-rate-history
Positive = longs pay (https://www.gate.com/help/futures/perpetual/22139/what-is-funding-rate)

Writes data/raw/gate/funding.parquet, contracts.json, oi_daily.csv, fetch_status.json
Rerun: python src/04_fetch_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import time

import pandas as pd

from common import RAW, SYMBOLS, get, log_status, write_funding, write_json

BASE = "https://api.gateio.ws/api/v4/futures/usdt"
OUT = RAW / "gate"
OUT.mkdir(exist_ok=True)


def history(contract: str) -> list[dict]:
    now = int(time.time())
    start = now - 179 * 86400  # API limit
    out = []
    lo = start
    while lo < now:
        hi = min(lo + 30 * 86400, now)
        d = get(f"{BASE}/funding_rate", {"contract": contract, "limit": 1000, "from": lo, "to": hi})
        if isinstance(d, dict):
            raise RuntimeError(f"gate funding_rate {contract}: {d}")
        out.extend(d)
        lo = hi + 1
    return out


def main() -> None:
    rows, status, contracts, oi_rows = [], {}, {}, []
    for asset, c in SYMBOLS["gate"].items():
        info = get(f"{BASE}/contracts/{c}")
        contracts[asset] = info
        interval_h = float(info["funding_interval"]) / 3600.0
        hist = history(c)
        for r in hist:
            rows.append({"asset": asset, "time": pd.Timestamp(int(r["t"]), unit="s", tz="UTC").floor("h"),
                         "rate": float(r["r"]), "interval_h": interval_h})
        ts = sorted(int(r["t"]) for r in hist)
        status[asset] = {"contract": c, "rows": len(hist), "interval_h": interval_h,
                         "funding_cap_ratio": info.get("funding_cap_ratio"),
                         "create_time": pd.Timestamp(int(info["create_time"]), unit="s", tz="UTC").isoformat() if info.get("create_time") else None,
                         "first": pd.Timestamp(ts[0], unit="s", tz="UTC").isoformat() if ts else None,
                         "last": pd.Timestamp(ts[-1], unit="s", tz="UTC").isoformat() if ts else None,
                         "oi_usd_now": float(info["position_size"]) * float(info["quanto_multiplier"]) * float(info["mark_price"])}
        print(asset, status[asset])
        stats = get(f"{BASE}/contract_stats", {"contract": c, "interval": "1d", "limit": 30})
        for s in stats:
            oi_rows.append({"asset": asset, "contract": c, "date": pd.Timestamp(int(s["time"]), unit="s", tz="UTC").strftime("%Y-%m-%d"),
                            "oi_contracts": s["open_interest"], "oi_usd": s["open_interest_usd"],
                            "last_funding_rate": s.get("last_funding_rate")})
    write_funding("gate", rows)
    write_json("gate", "contracts.json", contracts)
    pd.DataFrame(oi_rows).to_csv(OUT / "oi_daily.csv", index=False)
    log_status("gate", status)


if __name__ == "__main__":
    main()
