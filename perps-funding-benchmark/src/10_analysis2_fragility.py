"""Analysis 2: how fragile is a single-venue rate?

Per venue x asset, on native prints (annualised = rate / interval_h x 8760):
  * outliers: |z| > 4 where z uses the mean and std of the trailing 30 days of prints
    (time-based window, excluding the current print; at least 20 prints in the window)
  * max / min annualised print and their dates
  * share of prints at the venue's documented cap or floor (|rate| >= cap - 1e-9), with the
    cap source; "NOT AVAILABLE" where the cap could not be read from this machine
  * share of prints exactly equal to the venue's default/interest-rate print, and exactly 0
Volatility (hourly grid): std of the hourly annualised rate per venue vs comp_oi vs
  comp_median, on (a) each venue's own hours and (b) the hours where every venue is present.
  Also the std of daily means.
Spike episode: the hour with the largest |venue - comp_median| among BTC/ETH/SOL, with the
  +-72h window written for the chart.

Caps (documented):
  Hyperliquid 0.5%/hour: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding
  Lighter BigClamp 4% per 8h = 0.5%/hour (orderBookDetails funding_clamp_big): https://docs.lighter.xyz/trading/funding
  OKX maxFundingRate/minFundingRate from /public/funding-rate (saved in data/raw/okx/funding_params.json)
  Gate funding_rate_limit from /futures/usdt/contracts (saved in data/raw/gate/contracts.json);
       rule fmax = 0.75 x maintenance_rate: https://www.gate.com/help/futures/futures-logic/27569/funding-rate-and-funding-fee
  Binance cap = 0.75 x maintenance margin ratio at max leverage for >=30x contracts
       (https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031);
       the per-symbol value sits on GET /fapi/v1/fundingInfo, which is geo-blocked here. A third-party
       read of that endpoint on 2026-09-27 reports +-0.3% for BTCUSDT and ETHUSDT
       (https://safearbitrage.com/en/blog/funding-rate-cap-and-floor/). Used for BTC/ETH only, labelled.
  Bybit: formula min((IMR - MMR) x 0.75, MMR) per https://www.bybit.com/en/help-center/article/Introduction-to-Funding-Rate;
       per-symbol values unreachable -> NOT AVAILABLE.

Reads  data/processed/prints_long.parquet, hourly_wide_<ASSET>.csv, raw cap parameters
Writes data/processed/a2_outliers_caps.csv, a2_volatility.csv, a2_spike_episode.csv
Rerun: python src/10_analysis2_fragility.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json

import numpy as np
import pandas as pd

from common import ASSETS, COMPOSITES, CRYPTO, HOURS_PER_YEAR, PROCESSED, RAW, VENUES, load_prints, load_wide


def caps() -> dict[tuple[str, str], tuple[float | None, str]]:
    """(venue, asset) -> (cap as fraction per print, source)."""
    out = {}
    okx = json.loads((RAW / "okx" / "funding_params.json").read_text())
    gate = json.loads((RAW / "gate" / "contracts.json").read_text())
    lighter = json.loads((RAW / "lighter" / "markets.json").read_text())
    for a in ASSETS:
        out[("hyperliquid", a)] = (0.005, "docs: 0.5%/hour")
        big = float(lighter[a]["funding_clamp_big"]) / 100 / 8 if a in lighter else 0.005
        out[("lighter", a)] = (big, f"orderBookDetails funding_clamp_big {lighter[a]['funding_clamp_big']}% per 8h -> {big*100:.2f}%/hour")
        if a in okx and okx[a]:
            out[("okx", a)] = (float(okx[a]["maxFundingRate"]), f"/public/funding-rate maxFundingRate {okx[a]['maxFundingRate']}")
        if a in gate:
            out[("gate", a)] = (float(gate[a]["funding_rate_limit"]), f"/contracts funding_rate_limit {gate[a]['funding_rate_limit']}")
        if a in ("BTC", "ETH"):
            out[("binance", a)] = (0.003, "third-party read of /fapi/v1/fundingInfo 2026-09-27: +-0.3% (endpoint geo-blocked here)")
        else:
            out[("binance", a)] = (None, "NOT AVAILABLE: /fapi/v1/fundingInfo geo-blocked")
        out[("bybit", a)] = (None, "NOT AVAILABLE: Bybit API geo-blocked; cap depends on per-symbol margin tiers")
    return out


def main() -> None:
    prints = load_prints()
    prints["ann"] = prints.rate / prints.interval_h * HOURS_PER_YEAR
    cap_map = caps()
    rows = []
    for (v, a), g in prints.groupby(["venue", "asset"]):
        g = g.sort_values("time").set_index("time")
        s = g["ann"]
        # trailing 30-day distribution, excluding the current print
        roll = s.shift(1).rolling("30D", min_periods=20)
        z = (s - roll.mean()) / roll.std()
        n_z = int((z.abs() > 4).sum())
        cap, src = cap_map.get((v, a), (None, "NOT AVAILABLE"))
        at_cap = float((g.rate.abs() >= cap - 1e-9).mean()) if cap else np.nan
        # default print: the interest-rate-only value (most common print)
        mode = g.rate.round(10).mode()
        mode_val = float(mode.iloc[0]) if len(mode) else np.nan
        rows.append({
            "venue": v, "asset": a, "n_prints": int(len(g)), "interval_h": "/".join(str(int(x)) for x in sorted(g.interval_h.unique())),
            "outliers_abs_z_gt4": n_z, "outliers_per_1000_prints": round(n_z / len(g) * 1000, 2),
            "n_prints_with_z": int(z.notna().sum()),
            "max_ann_pct": round(s.max() * 100, 1), "max_at": s.idxmax().isoformat(),
            "min_ann_pct": round(s.min() * 100, 1), "min_at": s.idxmin().isoformat(),
            "cap_per_print_pct": round(cap * 100, 4) if cap else None, "cap_annualised_pct": round(cap / g.interval_h.iloc[-1] * HOURS_PER_YEAR * 100, 0) if cap else None,
            "share_prints_at_cap_pct": round(at_cap * 100, 3) if cap else "NOT AVAILABLE", "cap_source": src,
            "modal_print": mode_val, "modal_print_ann_pct": round(mode_val / g.interval_h.iloc[-1] * HOURS_PER_YEAR * 100, 2) if not np.isnan(mode_val) else None,
            "share_prints_at_modal_pct": round(float((g.rate.round(10) == round(mode_val, 10)).mean() * 100), 1),
            "share_prints_zero_pct": round(float((g.rate == 0).mean() * 100), 1),
            "share_prints_negative_pct": round(float((g.rate < 0).mean() * 100), 1),
        })
    oc = pd.DataFrame(rows).sort_values(["asset", "venue"])
    oc.to_csv(PROCESSED / "a2_outliers_caps.csv", index=False)
    pd.set_option("display.width", 250)
    print(oc.drop(columns=["cap_source", "max_at", "min_at"]).to_string())

    # volatility
    vol = []
    for a in ASSETS:
        w = load_wide(a).drop(columns="n_venues") * 100
        cols = [c for c in w.columns if c in VENUES] + COMPOSITES
        common = w[cols].dropna()
        daily = w[cols].resample("D").mean()
        for c in cols:
            vol.append({"asset": a, "series": c,
                        "std_hourly_pp_own_hours": round(w[c].std(), 2), "n_hours_own": int(w[c].notna().sum()),
                        "std_hourly_pp_common_hours": round(common[c].std(), 2) if len(common) else np.nan, "n_hours_common": int(len(common)),
                        "std_daily_pp": round(daily[c].std(), 2), "n_days": int(daily[c].notna().sum()),
                        "mean_pp_own_hours": round(w[c].mean(), 2),
                        "p1_pp": round(w[c].quantile(0.01), 1), "p99_pp": round(w[c].quantile(0.99), 1)})
    vol = pd.DataFrame(vol)
    vol.to_csv(PROCESSED / "a2_volatility.csv", index=False)
    print(vol.to_string())

    # outliers on the common hourly grid, so composites can be compared with venues
    hz = []
    for a in ASSETS:
        w = load_wide(a).drop(columns="n_venues")
        for c in [c for c in w.columns if c in VENUES] + COMPOSITES:
            s = w[c].dropna()
            if s.empty:
                continue
            roll = s.shift(1).rolling("30D", min_periods=240)
            z = (s - roll.mean()) / roll.std()
            hz.append({"asset": a, "series": c, "n_hours": int(z.notna().sum()), "outlier_hours_abs_z_gt4": int((z.abs() > 4).sum()),
                       "outliers_per_1000_hours": round((z.abs() > 4).sum() / max(z.notna().sum(), 1) * 1000, 2),
                       "max_abs_z": round(float(z.abs().max()), 1)})
    hz = pd.DataFrame(hz)
    hz.to_csv(PROCESSED / "a2_outliers_hourly_grid.csv", index=False)
    print(hz.pivot(index="asset", columns="series", values="outliers_per_1000_hours").to_string())

    # spike episode: largest |venue - comp_median| among crypto assets
    best = None
    for a in CRYPTO:
        w = load_wide(a) * 100
        for v in [c for c in w.columns if c in VENUES]:
            d = (w[v] - w["comp_median"]).abs()
            if d.notna().any():
                h = d.idxmax()
                if best is None or d.max() > best[0]:
                    best = (d.max(), a, v, h)
    gap, a, v, h = best
    w = load_wide(a) * 100
    ep = w.loc[h - pd.Timedelta(hours=72): h + pd.Timedelta(hours=72)].copy()
    ep["asset"], ep["spike_venue"], ep["spike_hour"] = a, v, h.isoformat()
    ep.to_csv(PROCESSED / "a2_spike_episode.csv")
    print(f"spike: {a} {v} at {h} diverged {gap:.1f} pp (annualised) from the median composite; "
          f"venue={w.loc[h, v]:.1f}%, " + ", ".join(f"{c}={w.loc[h, c]:.1f}%" for c in COMPOSITES))


if __name__ == "__main__":
    main()
