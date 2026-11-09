"""Analysis 3: what does the choice of settlement reference cost a funding swap?

A receive-floating funding swap on $1M notional pays the holder the realised funding over the
tenor: P&L = 1e6 x sum over hours of (annualised rate_h / 8760). For every 30-day window
starting at 00:00 UTC (daily steps, 720 hours), per asset and venue:
    diff = P&L settled on the venue's own prints - P&L settled on the composite
Reported per asset x venue: number of windows, median and p95 of |diff| (vs comp_oi and
vs comp_median), the signed mean diff, the largest |diff| and its window, and the median
P&L of the venue leg and the composite leg for scale. A window counts only when the venue and
the composite both have all 720 hours.

Reads  data/processed/hourly_wide_<ASSET>.csv
Writes data/processed/a3_swap_cost.csv, a3_rolling_pnl_<ASSET>.csv
Rerun: python src/11_analysis3_swap_cost.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from common import ASSETS, COMPOSITES, HOURS_PER_YEAR, PROCESSED, VENUES, load_wide

NOTIONAL = 1_000_000
TENOR_H = 30 * 24


def main() -> None:
    rows = []
    for a in ASSETS:
        w = load_wide(a).drop(columns="n_venues")
        pnl_h = w / HOURS_PER_YEAR * NOTIONAL  # $ accrued per hour per $1M
        # rolling 720h sums, complete windows only
        roll = pnl_h.rolling(TENOR_H, min_periods=TENOR_H).sum()
        roll = roll[roll.index.hour == 23]  # windows ending at 23:00 -> started 00:00 30 days earlier
        roll.index.name = "window_end_hour"
        roll.round(2).to_csv(PROCESSED / f"a3_rolling_pnl_{a}.csv")
        for v in [c for c in w.columns if c in VENUES]:
            for comp in COMPOSITES:
                d = (roll[v] - roll[comp]).dropna()
                if d.empty:
                    rows.append({"asset": a, "venue": v, "composite": comp, "n_windows": 0, "note": "no complete 30-day windows"})
                    continue
                rows.append({
                    "asset": a, "venue": v, "composite": comp, "n_windows": int(len(d)),
                    "first_window_end": d.index.min().date().isoformat(), "last_window_end": d.index.max().date().isoformat(),
                    "median_abs_diff_usd": round(d.abs().median(), 0), "p95_abs_diff_usd": round(d.abs().quantile(0.95), 0),
                    "max_abs_diff_usd": round(d.abs().max(), 0), "max_abs_diff_window_end": d.abs().idxmax().date().isoformat(),
                    "mean_signed_diff_usd": round(d.mean(), 0),
                    "median_venue_pnl_usd": round(roll.loc[d.index, v].median(), 0), "median_composite_pnl_usd": round(roll.loc[d.index, comp].median(), 0),
                    "p5_venue_pnl_usd": round(roll.loc[d.index, v].quantile(0.05), 0), "p95_venue_pnl_usd": round(roll.loc[d.index, v].quantile(0.95), 0),
                    "median_abs_diff_bp_of_notional": round(d.abs().median() / NOTIONAL * 1e4, 1),
                    "p95_abs_diff_bp_of_notional": round(d.abs().quantile(0.95) / NOTIONAL * 1e4, 1),
                })
    out = pd.DataFrame(rows)
    out.to_csv(PROCESSED / "a3_swap_cost.csv", index=False)
    pd.set_option("display.width", 250)
    print(out[out.composite == "comp_oi"].drop(columns=["composite"]).to_string())
    print(out[out.composite == "comp_median"][["asset", "venue", "n_windows", "median_abs_diff_usd", "p95_abs_diff_usd"]].to_string())


if __name__ == "__main__":
    main()
