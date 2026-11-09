"""Render the findings tables (markdown) from the processed CSVs.

Reads  data/processed/*.csv
Writes output/report_tables.md
Rerun: python src/15_report_tables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import OUTPUT, PROCESSED

NAME = {"hyperliquid": "Hyperliquid", "binance": "Binance", "bybit": "Bybit*", "okx": "OKX", "gate": "Gate", "lighter": "Lighter",
        "comp_oi": "OI-weighted", "comp_oi_cap30": "OI-weighted, 30% cap", "comp_oi_cap20": "OI-weighted, 20% cap",
        "comp_median": "Median"}


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join("" if pd.isna(v) else (f"{v:,.0f}" if isinstance(v, float) and abs(v) >= 100 else str(v)) for v in r.values) + " |")
    return "\n".join(out)


def main() -> None:
    parts = []

    cov = pd.read_csv(PROCESSED / "coverage.csv")
    cov["venue"] = cov.venue.map(NAME)
    cov["first"] = cov["first"].str[:10]
    cov["last"] = cov["last"].str[:10]
    cov = cov.rename(columns={"native_interval_h": "interval (h)", "n_prints": "prints"})
    parts.append("## Coverage\n\n" + md(cov[["asset", "venue", "first", "last", "interval (h)", "prints", "days", "sources"]]))

    w = pd.read_csv(PROCESSED / "oi_weights.csv")
    w["venue"] = w.venue.map(NAME)
    w["oi_usd_m"] = (w.oi_usd / 1e6).round(1)
    w["oi_30d_mean_usd_m"] = (w.oi_usd_30d_mean / 1e6).round(1)
    w["weight_pct"] = (w.weight * 100).round(1)
    parts.append("## OI weights\n\n" + md(w[["asset", "venue", "oi_usd_m", "oi_30d_mean_usd_m", "weight_pct", "as_of"]]))

    val = pd.read_csv(PROCESSED / "archive_validation.csv")
    val["venue"] = val.venue.map(NAME)
    parts.append("## Archive validation\n\n" + md(val[["venue", "asset", "overlap_prints", "share_within_0.01pp_annualised", "mean_abs_diff_pp", "max_abs_diff_pp", "corr", "note"]]))

    sc = pd.read_csv(PROCESSED / "sign_check.csv")
    sc["venue"] = sc.venue.map(NAME)
    parts.append("## Sign check (daily, vs Hyperliquid)\n\n" + md(sc.round(2)))

    a1 = pd.read_csv(PROCESSED / "a1_pairwise_spreads.csv")
    a1["pair"] = (a1.pair.str.replace("hyperliquid", "HL").str.replace("binance", "Binance").str.replace("bybit", "Bybit*")
                 .str.replace("okx", "OKX").str.replace("gate", "Gate").str.replace("lighter", "Lighter")
                 .str.replace("comp_oi_cap30", "Composite(30% cap)").str.replace("comp_oi_cap20", "Composite(20% cap)")
                 .str.replace("comp_oi", "Composite(OI)").str.replace("comp_median", "Composite(median)"))
    cols = ["asset", "pair", "first", "last", "n_hours", "n_days", "mean_pp", "median_pp", "p5_pp", "p95_pp", "days_abs_gt5_pct", "days_abs_gt10_pct", "hours_abs_gt5_pct", "hours_abs_gt10_pct", "corr_daily", "note"]
    parts.append("## A1 requested pairs\n\n" + md(a1[a1.set == "requested"][cols]))
    parts.append("## A1 extra pairs\n\n" + md(a1[a1.set == "extra"][cols]))

    a2 = pd.read_csv(PROCESSED / "a2_outliers_caps.csv")
    a2["venue"] = a2.venue.map(NAME)
    a2["max_at"] = a2.max_at.str[:13]
    a2["min_at"] = a2.min_at.str[:13]
    parts.append("## A2 outliers and caps\n\n" + md(a2[["asset", "venue", "n_prints", "interval_h", "outliers_abs_z_gt4", "outliers_per_1000_prints", "max_ann_pct", "max_at", "min_ann_pct", "min_at", "cap_per_print_pct", "share_prints_at_cap_pct", "modal_print_ann_pct", "share_prints_at_modal_pct", "share_prints_zero_pct"]]))
    parts.append("## A2 cap sources\n\n" + md(a2[["asset", "venue", "cap_source"]].drop_duplicates(["venue", "cap_source"])[["venue", "cap_source"]]))

    v = pd.read_csv(PROCESSED / "a2_volatility.csv")
    v["series"] = v.series.map(NAME)
    parts.append("## A2 volatility\n\n" + md(v[["asset", "series", "mean_pp_own_hours", "std_hourly_pp_own_hours", "n_hours_own", "std_hourly_pp_common_hours", "n_hours_common", "std_daily_pp", "n_days", "p1_pp", "p99_pp"]]))

    hz = pd.read_csv(PROCESSED / "a2_outliers_hourly_grid.csv")
    hz["series"] = hz.series.map(NAME)
    parts.append("## A2 outliers on hourly grid\n\n" + md(hz.pivot(index="asset", columns="series", values="outliers_per_1000_hours").reset_index()))

    a3 = pd.read_csv(PROCESSED / "a3_swap_cost.csv")
    a3["venue"] = a3.venue.map(NAME)
    for comp in ("comp_oi", "comp_oi_cap30", "comp_oi_cap20", "comp_median"):
        t = a3[a3.composite == comp][["asset", "venue", "n_windows", "first_window_end", "last_window_end", "median_abs_diff_usd", "p95_abs_diff_usd", "max_abs_diff_usd", "mean_signed_diff_usd", "median_venue_pnl_usd", "median_composite_pnl_usd", "median_abs_diff_bp_of_notional", "p95_abs_diff_bp_of_notional"]]
        parts.append(f"## A3 swap cost vs {NAME[comp]}\n\n" + md(t))

    a4 = pd.read_csv(PROCESSED / "a4_equity_pairs.csv")
    a4["pair"] = (a4.pair.str.replace("hyperliquid", "HL").str.replace("binance", "Binance")
                 .str.replace("okx", "OKX").str.replace("gate", "Gate").str.replace("lighter", "Lighter")
                 .str.replace("comp_oi_cap30", "Composite(30% cap)").str.replace("comp_oi_cap20", "Composite(20% cap)")
                 .str.replace("comp_oi", "Composite(OI)").str.replace("comp_median", "Composite(median)"))
    parts.append("## A4 equity pairs\n\n" + md(a4))
    a4v = pd.read_csv(PROCESSED / "a4_equity_volatility.csv")
    a4v["series"] = a4v.series.map(NAME)
    parts.append("## A4 equity volatility\n\n" + md(a4v))
    a4s = pd.read_csv(PROCESSED / "a4_equity_session.csv")
    a4s["series"] = a4s.series.map(NAME)
    parts.append("## A4 equity session split\n\n" + md(a4s))

    a6 = pd.read_csv(PROCESSED / "a6_composite_comparison.csv")
    a6["composite"] = a6.composite.map(NAME)
    parts.append("## A6 composite comparison\n\n" + md(a6))
    w6 = pd.read_csv(PROCESSED / "a6_composite_weights.csv")
    w6["composite"] = w6.composite.map(NAME)
    w6["venue"] = w6.venue.map(NAME)
    w6["weight_all_venues_present"] = (w6.weight_all_venues_present * 100).round(1)
    parts.append("## A6 weights when every OI venue is present, %\n\n" + md(w6))

    py = pd.read_csv(PROCESSED / "a5_pyth_feeds.csv")
    parts.append("## A5 Pyth funding-rate feeds\n\n" + md(py[py.asset_type == "funding-rate"][["symbol", "state", "interval", "min_publishers"]]))
    ir = py[(py.asset_type == "interest-rate")]
    parts.append("## A5 Pyth interest-rate feeds (stable)\n\n" + ", ".join(ir[ir.state == "stable"].symbol.tolist()) + f"\n\n({len(ir)} feeds total: {ir.state.value_counts().to_dict()})")

    bm = pd.read_csv(PROCESSED.parent / "raw" / "boros" / "boros_markets_from_archive.csv")
    live = bm[pd.to_datetime(bm.maturity_date) >= pd.Timestamp("2026-11-08")]
    parts.append("## A5 Boros markets with maturity >= 2026-11-08 (from archive directory names)\n\n" + md(live[["market_id", "exchange", "symbol", "maturity", "first_month"]]))
    parts.append("## A5 Boros market counts by exchange (all time, from archive)\n\n" + md(bm.exchange.value_counts().rename_axis("exchange").reset_index(name="markets")))
    parts.append("## A5 Boros equity/index/RWA markets (from archive)\n\n" + md(bm[bm.symbol.str.startswith("xyz") | bm.symbol.str.contains("SKHYNIX|NVDA", regex=True)][["market_id", "exchange", "symbol", "maturity", "first_month", "last_month"]]))

    (OUTPUT / "report_tables.md").write_text("\n\n".join(parts) + "\n")
    print((OUTPUT / "report_tables.md").read_text())


if __name__ == "__main__":
    main()
