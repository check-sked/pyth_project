"""Analysis 4: equity perps (NVDA, TSLA) across Hyperliquid xyz, Lighter, Binance, Gate, OKX.

Assembles the equity rows of analyses 1-3 into one table set and adds two things the crypto
tables do not need:
  * share of prints equal to exactly zero per venue (Gate/OKX/Binance equity perps run a
    zero interest-rate component, so a zero print means "premium inside the clamp")
  * volatility split by US cash session (weekdays 13:30-21:00 UTC, covering EDT and EST
    regular hours) vs. off-session hours, since the underlying does not trade off-session

Reads  data/processed/hourly_wide_NVDA.csv, hourly_wide_TSLA.csv, a1/a2/a3 tables
Writes data/processed/a4_equity_pairs.csv, a4_equity_volatility.csv, a4_equity_session.csv, a4_equity_swap_cost.csv
Rerun: python src/12_analysis4_equity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from common import CHOSEN_COMPOSITE, COMPOSITES, EQUITY, PROCESSED, VENUES, load_wide

PAIRS = [("hyperliquid", "lighter"), ("hyperliquid", "binance"), ("hyperliquid", "gate"), ("hyperliquid", "okx"),
         ("binance", "okx"), ("binance", "gate"), ("lighter", "binance"), ("hyperliquid", "comp_oi"), ("comp_oi", "comp_median"), ("hyperliquid", CHOSEN_COMPOSITE), (CHOSEN_COMPOSITE, "comp_median")]


def main() -> None:
    rows, vol, sess = [], [], []
    for a in EQUITY:
        w = load_wide(a).drop(columns="n_venues") * 100
        daily = w.resample("D").mean()
        for x, y in PAIRS:
            if x not in w or y not in w:
                rows.append({"asset": a, "pair": f"{x}-{y}", "n_hours": 0, "note": "NOT AVAILABLE"})
                continue
            s = (w[x] - w[y]).dropna()
            ds = (daily[x] - daily[y]).dropna()
            if s.empty:
                rows.append({"asset": a, "pair": f"{x}-{y}", "n_hours": 0, "note": "no overlap"})
                continue
            rows.append({"asset": a, "pair": f"{x}-{y}", "first": s.index.min().date().isoformat(), "last": s.index.max().date().isoformat(),
                         "n_hours": int(len(s)), "mean_pp": round(s.mean(), 2), "median_pp": round(s.median(), 2),
                         "p5_pp": round(s.quantile(0.05), 2), "p95_pp": round(s.quantile(0.95), 2), "std_pp": round(s.std(), 2),
                         "n_days": int(len(ds)), "days_abs_gt5_pct": round((ds.abs() > 5).mean() * 100, 1),
                         "days_abs_gt10_pct": round((ds.abs() > 10).mean() * 100, 1),
                         "corr_daily": round(float(daily[[x, y]].dropna().corr().iloc[0, 1]), 3) if len(ds) > 2 else np.nan})
        cols = [c for c in w.columns if c in VENUES] + COMPOSITES
        common = w[cols].dropna()
        for c in cols:
            vol.append({"asset": a, "series": c, "n_hours_own": int(w[c].notna().sum()), "mean_pp": round(w[c].mean(), 2),
                        "std_hourly_pp_own": round(w[c].std(), 2), "std_hourly_pp_common": round(common[c].std(), 2), "n_hours_common": int(len(common)),
                        "std_daily_pp": round(daily[c].std(), 2), "p1_pp": round(w[c].quantile(0.01), 1), "p99_pp": round(w[c].quantile(0.99), 1),
                        "share_hours_zero_pct": round(float((w[c] == 0).mean() * 100), 1)})
        idx = w.index
        in_sess = (idx.dayofweek < 5) & (((idx.hour == 13) & (idx.minute >= 30)) | ((idx.hour >= 14) & (idx.hour < 21)))
        for c in cols:
            sess.append({"asset": a, "series": c,
                         "std_pp_session": round(w.loc[in_sess, c].std(), 2), "n_session": int(w.loc[in_sess, c].notna().sum()),
                         "std_pp_off_session": round(w.loc[~in_sess, c].std(), 2), "n_off": int(w.loc[~in_sess, c].notna().sum()),
                         "mean_pp_session": round(w.loc[in_sess, c].mean(), 2), "mean_pp_off_session": round(w.loc[~in_sess, c].mean(), 2)})
    pairs = pd.DataFrame(rows)
    pairs.to_csv(PROCESSED / "a4_equity_pairs.csv", index=False)
    vol = pd.DataFrame(vol)
    vol.to_csv(PROCESSED / "a4_equity_volatility.csv", index=False)
    sess = pd.DataFrame(sess)
    sess.to_csv(PROCESSED / "a4_equity_session.csv", index=False)
    a3 = pd.read_csv(PROCESSED / "a3_swap_cost.csv")
    a3[a3.asset.isin(EQUITY)].to_csv(PROCESSED / "a4_equity_swap_cost.csv", index=False)
    pd.set_option("display.width", 250)
    print(pairs.to_string())
    print(vol.to_string())
    print(sess.to_string())


if __name__ == "__main__":
    main()
