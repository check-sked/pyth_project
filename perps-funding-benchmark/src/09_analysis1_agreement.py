"""Analysis 1: do venues agree? Pairwise annualised spreads on the hourly grid.

For each asset and venue pair (A, B): spread_h = ann_rate_A,h - ann_rate_B,h in percentage
points. Hourly stats: n, mean, median, p5, p95, std. Daily stats: the daily mean of the
hourly spread, and the share of days with |daily spread| > 5 pp and > 10 pp. The daily figure
is the fair comparison when one leg prints hourly and the other every 8 hours; the hourly
figure also carries the hourly leg's intra-window noise. The hourly share above 5/10 pp is
reported too.

Reads  data/processed/hourly_wide_<ASSET>.csv
Writes data/processed/a1_pairwise_spreads.csv, a1_daily_by_venue.csv
Rerun: python src/09_analysis1_agreement.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from common import ASSETS, CHOSEN_COMPOSITE, PROCESSED, load_wide

PAIRS_REQUESTED = [("hyperliquid", "binance"), ("hyperliquid", "bybit"), ("binance", "okx"), ("hyperliquid", "gate")]
PAIRS_EXTRA = [("hyperliquid", "okx"), ("hyperliquid", "lighter"), ("binance", "bybit"), ("binance", "gate"),
               ("hyperliquid", "comp_oi"), ("binance", "comp_oi"), ("comp_oi", "comp_median"),
               ("hyperliquid", CHOSEN_COMPOSITE), ("binance", CHOSEN_COMPOSITE), (CHOSEN_COMPOSITE, "comp_median"),
               (CHOSEN_COMPOSITE, "comp_oi"), ("hyperliquid", "comp_oi_cap20"), ("binance", "comp_oi_cap20")]


def main() -> None:
    rows, daily_all = [], []
    for asset in ASSETS:
        w = load_wide(asset) * 100  # pp
        w["n_venues"] = w["n_venues"] / 100
        daily = w.drop(columns="n_venues").resample("D").mean()
        d = daily.copy()
        d["asset"] = asset
        daily_all.append(d)
        for a, b in PAIRS_REQUESTED + PAIRS_EXTRA:
            tag = "requested" if (a, b) in PAIRS_REQUESTED else "extra"
            if a not in w or b not in w:
                rows.append({"asset": asset, "pair": f"{a}-{b}", "set": tag, "n_hours": 0, "note": f"NOT AVAILABLE: no series for {a if a not in w else b}"})
                continue
            s = (w[a] - w[b]).dropna()
            if s.empty:
                rows.append({"asset": asset, "pair": f"{a}-{b}", "set": tag, "n_hours": 0, "note": "no overlapping hours"})
                continue
            ds = (daily[a] - daily[b]).dropna()
            rows.append({
                "asset": asset, "pair": f"{a}-{b}", "set": tag,
                "first": s.index.min().date().isoformat(), "last": s.index.max().date().isoformat(),
                "n_hours": int(len(s)), "mean_pp": round(s.mean(), 2), "median_pp": round(s.median(), 2),
                "p5_pp": round(s.quantile(0.05), 2), "p95_pp": round(s.quantile(0.95), 2), "std_pp": round(s.std(), 2),
                "hours_abs_gt5_pct": round((s.abs() > 5).mean() * 100, 1), "hours_abs_gt10_pct": round((s.abs() > 10).mean() * 100, 1),
                "n_days": int(len(ds)), "daily_mean_pp": round(ds.mean(), 2), "daily_median_pp": round(ds.median(), 2),
                "daily_p5_pp": round(ds.quantile(0.05), 2), "daily_p95_pp": round(ds.quantile(0.95), 2),
                "days_abs_gt5_pct": round((ds.abs() > 5).mean() * 100, 1), "days_abs_gt10_pct": round((ds.abs() > 10).mean() * 100, 1),
                "corr_daily": round(float(daily[[a, b]].dropna().corr().iloc[0, 1]), 3) if len(ds) > 2 else np.nan,
            })
    out = pd.DataFrame(rows)
    out.to_csv(PROCESSED / "a1_pairwise_spreads.csv", index=False)
    pd.concat(daily_all).reset_index().to_csv(PROCESSED / "a1_daily_by_venue.csv", index=False)
    pd.set_option("display.width", 250)
    print(out[out.set == "requested"].drop(columns=["set"]).to_string())
    print(out[out.set == "extra"].drop(columns=["set"]).to_string())


if __name__ == "__main__":
    main()
