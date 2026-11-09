"""Compare the four composites (uncapped OI, OI capped 30%, OI capped 20%, median) on BTC/ETH/SOL.

Per asset x composite: effective max venue weight (at the hours where every OI-weighted venue
is present, and the max over all hours), hourly std (pp, common hours), |z|>4 outliers per
1,000 hours (from a2_outliers_hourly_grid.csv), the composite value at the 25 Aug 2026 SOL
spike hour (from a2_spike_episode.csv), and the ETH $1M 30-day swap gap (median / p95) for
Hyperliquid and Binance vs that composite (from a3_swap_cost.csv).

Reads  data/processed/hourly_wide_<ASSET>.csv, oi_weights.csv, a2_*.csv, a3_swap_cost.csv
Writes data/processed/a6_composite_comparison.csv, a6_composite_weights.csv
Rerun: python src/14_composite_cap.py   (after 08, 10, 11)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import CAPS, CHOSEN_COMPOSITE, COMPOSITES, CRYPTO, PROCESSED, VENUES, capped_weights, load_wide


def main() -> None:
    w = pd.read_csv(PROCESSED / "oi_weights.csv")
    hz = pd.read_csv(PROCESSED / "a2_outliers_hourly_grid.csv")
    a3 = pd.read_csv(PROCESSED / "a3_swap_cost.csv")
    ep = pd.read_csv(PROCESSED / "a2_spike_episode.csv", parse_dates=["hour"])
    spike_hour = pd.Timestamp(ep.spike_hour.iloc[0])
    spike = ep[ep.hour == spike_hour].iloc[0]

    weights_rows, rows = [], []
    for a in CRYPTO:
        wide = load_wide(a)
        wa = w[(w.asset == a)].dropna(subset=["oi_usd"]).set_index("venue").oi_usd
        full = wa / wa.sum()
        for comp in COMPOSITES:
            if comp == "comp_median":
                full_w = pd.Series(dtype=float)
                max_full = float("nan")
            else:
                full_w = capped_weights(wa, CAPS[comp]) if comp in CAPS else full
                max_full = float(full_w.max())
            for v, x in full_w.items():
                weights_rows.append({"asset": a, "composite": comp, "venue": v, "weight_all_venues_present": round(float(x), 4)})
            # max weight over all hours: recompute per availability pattern
            cols = [c for c in wide.columns if c in wa.index]
            avail = wide[cols].notna()
            max_any = float("nan")
            if comp != "comp_median":
                mx = []
                for pattern, idx in avail.groupby(list(cols)).groups.items():
                    present = [c for c, p in zip(cols, pattern) if p]
                    if len(present) < 2:
                        continue
                    cw = capped_weights(wa[present], CAPS[comp]) if comp in CAPS else wa[present] / wa[present].sum()
                    mx.append((float(cw.max()), len(idx)))
                max_any = max(m for m, _ in mx)
            common = wide[[c for c in wide.columns if c in VENUES] + COMPOSITES].dropna()
            o = hz[(hz.asset == a) & (hz.series == comp)]
            row = {
                "asset": a, "composite": comp,
                "max_venue_weight_all_present_pct": round(max_full * 100, 1) if comp != "comp_median" else "n/a",
                "max_venue_weight_any_hour_pct": round(max_any * 100, 1) if comp != "comp_median" else "n/a",
                "std_hourly_pp_common_hours": round(float(common[comp].std() * 100), 2), "n_hours_common": int(len(common)),
                "std_hourly_pp_own_hours": round(float(wide[comp].std() * 100), 2),
                "outliers_per_1000_hours": float(o.outliers_per_1000_hours.iloc[0]) if len(o) else float("nan"),
            }
            if a == "SOL":
                row["spike_value_pct"] = round(float(spike[comp]), 1)
                row["spike_hour"] = spike_hour.isoformat()
                row["spike_lighter_pct"] = round(float(spike.lighter), 1)
            if a == "ETH":
                for v in ("hyperliquid", "binance"):
                    r = a3[(a3.asset == "ETH") & (a3.venue == v) & (a3.composite == comp)].iloc[0]
                    row[f"eth_swap_{v}_median_usd"] = float(r.median_abs_diff_usd)
                    row[f"eth_swap_{v}_p95_usd"] = float(r.p95_abs_diff_usd)
                    row[f"eth_swap_{v}_n_windows"] = int(r.n_windows)
            rows.append(row)
    out = pd.DataFrame(rows)
    out["chosen"] = out.composite == CHOSEN_COMPOSITE
    out.to_csv(PROCESSED / "a6_composite_comparison.csv", index=False)
    pd.DataFrame(weights_rows).to_csv(PROCESSED / "a6_composite_weights.csv", index=False)
    pd.set_option("display.width", 250)
    print(out.to_string())
    print(pd.DataFrame(weights_rows).pivot_table(index=["asset", "venue"], columns="composite", values="weight_all_venues_present").to_string())


if __name__ == "__main__":
    main()
