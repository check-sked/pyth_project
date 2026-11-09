"""OKX perpetual-swap funding history, caps, and open interest.

Source:
  GET https://www.okx.com/api/v5/public/funding-rate-history?instId=..&limit=100[&after=ts]
      -> realizedRate / fundingRate per fundingTime; pages back with `after`.
      The API stops after about three months (checked 2026-11-08: ETH-USDT-SWAP pages back to 2026-08-06).
  GET https://www.okx.com/api/v5/public/funding-rate?instId=..        -> current rate, maxFundingRate, minFundingRate
  GET https://www.okx.com/api/v5/public/open-interest?instId=..        -> current oi, oiCcy, oiUsd
  GET https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?instId=..&period=1D&limit=30
      -> daily OI history [ts, oi, oiCcy, oiUsd]
Docs: https://www.okx.com/docs-v5/en/#public-data-rest-api-get-funding-rate-history
Positive = longs pay (https://www.okx.com/help/introduction-to-perpetual-swap-funding-fee)

Writes data/raw/okx/funding.parquet, funding_params.json, oi_snapshot.json, oi_daily.csv, fetch_status.json
Rerun: python src/03_fetch_okx.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import RAW, SAMPLE_START, SYMBOLS, get, log_status, write_funding, write_json

BASE = "https://www.okx.com/api/v5"
OUT = RAW / "okx"
OUT.mkdir(exist_ok=True)


def history(inst: str) -> list[dict]:
    out, after = [], None
    while True:
        p = {"instId": inst, "limit": 100}
        if after:
            p["after"] = after
        d = get(f"{BASE}/public/funding-rate-history", p)
        rows = d.get("data", [])
        if not rows:
            break
        out.extend(rows)
        after = rows[-1]["fundingTime"]
        if int(after) < SAMPLE_START.timestamp() * 1000:
            break
    return out


def main() -> None:
    rows, status, params, snap, oi_rows = [], {}, {}, {}, []
    for asset, inst in SYMBOLS["okx"].items():
        hist = history(inst)
        times = sorted(int(r["fundingTime"]) for r in hist)
        # detect interval from spacing between consecutive prints
        if len(times) > 1:
            gaps = pd.Series(times).diff().dropna() / 3.6e6
            interval = float(gaps.round().mode().iloc[0])
        else:
            interval = 8.0
        for r in hist:
            rate = r.get("realizedRate") or r.get("fundingRate")
            rows.append({"asset": asset, "time": pd.Timestamp(int(r["fundingTime"]), unit="ms", tz="UTC").floor("h"),
                         "rate": float(rate), "interval_h": interval,
                         "method": r.get("method"), "formulaType": r.get("formulaType")})
        status[asset] = {"instId": inst, "rows": len(hist), "interval_h_detected": interval,
                         "first": pd.Timestamp(times[0], unit="ms", tz="UTC").isoformat() if times else None,
                         "last": pd.Timestamp(times[-1], unit="ms", tz="UTC").isoformat() if times else None}
        print(asset, status[asset])
        cur = get(f"{BASE}/public/funding-rate", {"instId": inst})["data"]
        params[asset] = cur[0] if cur else None
        oi = get(f"{BASE}/public/open-interest", {"instId": inst})["data"]
        if oi:
            snap[asset] = {"instId": inst, "oi_contracts": float(oi[0]["oi"]), "oi_coins": float(oi[0]["oiCcy"]),
                           "oi_usd": float(oi[0]["oiUsd"]), "ts": pd.Timestamp(int(oi[0]["ts"]), unit="ms", tz="UTC").isoformat()}
        h = get(f"{BASE}/rubik/stat/contracts/open-interest-history", {"instId": inst, "period": "1D", "limit": 30})["data"]
        for ts, oi_c, oi_ccy, oi_usd in h:
            oi_rows.append({"asset": asset, "instId": inst, "date": pd.Timestamp(int(ts), unit="ms", tz="UTC").strftime("%Y-%m-%d"),
                            "oi_coins": float(oi_ccy), "oi_usd": float(oi_usd)})
    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_parquet(OUT / "funding_with_method.parquet", index=False)
    write_funding("okx", rows)
    write_json("okx", "funding_params.json", params)
    write_json("okx", "oi_snapshot.json", snap)
    pd.DataFrame(oi_rows).to_csv(OUT / "oi_daily.csv", index=False)
    status["oi_snapshot"] = snap
    status["funding_params"] = {a: {k: v for k, v in (p or {}).items() if k in ("fundingRate", "maxFundingRate", "minFundingRate", "interestRate", "premium", "settFundingRate", "fundingTime", "nextFundingTime")} for a, p in params.items()}
    log_status("okx", status)


if __name__ == "__main__":
    main()
