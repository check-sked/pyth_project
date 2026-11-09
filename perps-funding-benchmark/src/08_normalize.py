"""Normalise every venue's funding prints to an annualised rate per hour of accrual on a
common hourly UTC grid, attach open-interest weights, and build the composites.

Method
  * A print of `rate` (fraction) at time T with accrual interval k hours settles the k hourly
    periods ending at T. Each of those hours gets rate/k, annualised as rate/k x 8760.
    Hourly venues (Hyperliquid, Lighter) are therefore rate x 8760; 8h venues rate x 1095.
  * Hour label = the hour at which the payment is made (end of the accrual hour). Prints that
    land a few ms after the hour were floored in the fetchers.
  * Sign: positive = longs pay shorts, on every venue.
  * Sources: `primary` = the venue's own public API / archive. `archive` = Pendle's Boros
    historical-data archive, used for Bybit (API geo-blocked) and to backfill Gate before
    2026-05-14 and OKX before 2026-08-06. Where primary and archive overlap, the archive is
    checked print-by-print and the result written to data/processed/archive_validation.csv.
  * Weights: current USD open interest per venue (snapshot 2026-11-08/09), held fixed over the
    sample. Only Binance, OKX and Gate publish OI history; Hyperliquid and Lighter publish a
    snapshot only; Bybit's OI is unreachable. Bybit is therefore absent from the OI-weighted
    composite and present in the median composite.
  * Composites per asset-hour: `comp_oi` = OI-weighted mean over venues with data at that hour
    (weights renormalised, >= 2 venues); `comp_oi_cap30` / `comp_oi_cap20` = the same with each
    venue's weight capped at 30% / 20%, excess redistributed pro rata (equal weights when fewer
    than 1/cap venues are present); `comp_median` = median over venues with data (>= 2).

Reads  data/raw/<venue>/funding.parquet, data/raw/boros/archive_funding.parquet, OI files
Writes data/processed/hourly_panel.parquet   long: asset, hour, venue, ann_rate, source
       data/processed/hourly_wide_<ASSET>.csv  one column per venue + composites
       data/processed/coverage.csv, oi_weights.csv, archive_validation.csv, sign_check.csv
Rerun: python src/08_normalize.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json

import numpy as np
import pandas as pd

from common import ASSETS, CAPS, HOURS_PER_YEAR, PROCESSED, RAW, SAMPLE_END, SAMPLE_START, VENUES, capped_weights

BACKFILL = {"gate", "okx"}  # venues whose primary history is short; archive fills earlier dates


def load_primary() -> pd.DataFrame:
    out = []
    for v in VENUES:
        p = RAW / v / "funding.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if not df.empty:
                df["source"] = "archive" if v == "bybit" else "primary"
                out.append(df)
    return pd.concat(out, ignore_index=True)


def load_archive() -> pd.DataFrame:
    a = pd.read_parquet(RAW / "boros" / "archive_funding.parquet")
    a = a[(a.time >= SAMPLE_START - pd.Timedelta(days=1)) & (a.time <= SAMPLE_END + pd.Timedelta(hours=8))]
    a["source"] = "archive"
    return a[["venue", "asset", "time", "rate", "interval_h", "source", "annualizedFundingRate"]]


def validate_archive(primary: pd.DataFrame, archive: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (v, a), g in archive.groupby(["venue", "asset"]):
        p = primary[(primary.venue == v) & (primary.asset == a) & (primary.source == "primary")]
        if p.empty:
            rows.append({"venue": v, "asset": a, "overlap_prints": 0, "note": "no primary series to compare"})
            continue
        m = p.merge(g, on=["venue", "asset", "time"], suffixes=("_p", "_a"))
        if m.empty:
            rows.append({"venue": v, "asset": a, "overlap_prints": 0, "note": "no overlapping print times"})
            continue
        ann_p = m.rate_p / m.interval_h_p * HOURS_PER_YEAR
        ann_a = m.annualizedFundingRate
        d = (ann_p - ann_a).abs()
        rows.append({"venue": v, "asset": a, "overlap_prints": int(len(m)),
                     "overlap_first": m.time.min().isoformat(), "overlap_last": m.time.max().isoformat(),
                     "share_within_0.01pp_annualised": float((d < 1e-4).mean()),
                     "share_within_0.1pp_annualised": float((d < 1e-3).mean()),
                     "mean_abs_diff_pp": float(d.mean() * 100), "max_abs_diff_pp": float(d.max() * 100),
                     "corr": float(np.corrcoef(ann_p, ann_a)[0, 1]) if len(m) > 2 else np.nan})
    return pd.DataFrame(rows)


def expand_hourly(prints: pd.DataFrame) -> pd.DataFrame:
    """Spread each print evenly over the hours it settles."""
    parts = []
    for k, g in prints.groupby("interval_h"):
        k = int(round(k))
        for i in range(k):
            h = g[["venue", "asset", "time", "rate", "source"]].copy()
            h["hour"] = h["time"] - pd.Timedelta(hours=i)
            h["ann_rate"] = h["rate"] / k * HOURS_PER_YEAR
            h["interval_h"] = float(k)
            parts.append(h.drop(columns=["time", "rate"]))
    out = pd.concat(parts, ignore_index=True)
    out = out[(out.hour >= SAMPLE_START) & (out.hour <= SAMPLE_END)]
    # primary wins where both exist for the same hour
    out["pri"] = (out.source == "primary").astype(int)
    out = out.sort_values(["venue", "asset", "hour", "pri"]).drop_duplicates(["venue", "asset", "hour"], keep="last")
    return out.drop(columns="pri").reset_index(drop=True)


def oi_weights() -> pd.DataFrame:
    rows = []
    hl = json.loads((RAW / "hyperliquid" / "oi_snapshot.json").read_text())
    for a, d in hl.items():
        rows.append({"venue": "hyperliquid", "asset": a, "oi_usd": d["oi_usd"], "as_of": d["snapshot_utc"], "oi_source": "metaAndAssetCtxs openInterest x markPx"})
    b = pd.read_csv(RAW / "binance" / "oi_daily.csv")
    for a, g in b.groupby("asset"):
        g = g.sort_values("date")
        rows.append({"venue": "binance", "asset": a, "oi_usd": float(g.oi_usd_last.iloc[-1]), "as_of": g.last_row_time.iloc[-1],
                     "oi_source": "data.binance.vision daily metrics sum_open_interest_value (last row)",
                     "oi_usd_30d_mean": float(g.tail(30).oi_usd_mean.mean())})
    ok = json.loads((RAW / "okx" / "oi_snapshot.json").read_text())
    okh = pd.read_csv(RAW / "okx" / "oi_daily.csv")
    for a, d in ok.items():
        rows.append({"venue": "okx", "asset": a, "oi_usd": d["oi_usd"], "as_of": d["ts"], "oi_source": "/public/open-interest oiUsd",
                     "oi_usd_30d_mean": float(okh[okh.asset == a].oi_usd.mean())})
    gc = json.loads((RAW / "gate" / "contracts.json").read_text())
    gh = pd.read_csv(RAW / "gate" / "oi_daily.csv")
    for a, d in gc.items():
        rows.append({"venue": "gate", "asset": a, "oi_usd": float(d["position_size"]) * float(d["quanto_multiplier"]) * float(d["mark_price"]),
                     "as_of": json.loads((RAW / "gate" / "fetch_status.json").read_text())["fetched_at_utc"],
                     "oi_source": "/contracts position_size x quanto_multiplier x mark_price",
                     "oi_usd_30d_mean": float(gh[gh.asset == a].oi_usd.mean())})
    lm = json.loads((RAW / "lighter" / "markets.json").read_text())
    for a, d in lm.items():
        rows.append({"venue": "lighter", "asset": a, "oi_usd": d["oi_usd"], "as_of": d["snapshot_utc"], "oi_source": "orderBookDetails open_interest x last_trade_price"})
    for a in ASSETS:
        rows.append({"venue": "bybit", "asset": a, "oi_usd": np.nan, "as_of": None, "oi_source": "NOT AVAILABLE: api.bybit.com geo-blocked (HTTP 403)"})
    w = pd.DataFrame(rows)
    w["weight"] = w.groupby("asset").oi_usd.transform(lambda s: s / s.sum())
    return w.sort_values(["asset", "venue"])


def main() -> None:
    primary = load_primary()
    archive = load_archive()
    validation = validate_archive(primary, archive)
    validation.to_csv(PROCESSED / "archive_validation.csv", index=False)
    print(validation.to_string())

    # assemble prints: primary, plus archive backfill for Gate/OKX before their primary start
    pieces = [primary]
    for v in BACKFILL:
        for a in ASSETS:
            p = primary[(primary.venue == v) & (primary.asset == a)]
            if p.empty:
                continue
            first = p.time.min()
            back = archive[(archive.venue == v) & (archive.asset == a) & (archive.time < first)]
            if not back.empty:
                pieces.append(back[["venue", "asset", "time", "rate", "interval_h", "source"]])
    prints = pd.concat(pieces, ignore_index=True)
    prints = prints.sort_values(["venue", "asset", "time"]).drop_duplicates(["venue", "asset", "time"], keep="first")
    prints.to_parquet(PROCESSED / "prints_long.parquet", index=False)

    panel = expand_hourly(prints)
    panel.to_parquet(PROCESSED / "hourly_panel.parquet", index=False)

    # coverage table
    cov = []
    for (v, a), g in prints[(prints.time >= SAMPLE_START) & (prints.time <= SAMPLE_END)].groupby(["venue", "asset"]):
        src = g.groupby("source").time.agg(["min", "max", "size"])
        cov.append({"venue": v, "asset": a, "first": g.time.min().isoformat(), "last": g.time.max().isoformat(),
                    "native_interval_h": "/".join(str(int(x)) for x in sorted(g.interval_h.unique())),
                    "n_prints": int(len(g)), "days": round((g.time.max() - g.time.min()).total_seconds() / 86400, 1),
                    "sources": "; ".join(f"{s}: {r['min'].date()}..{r['max'].date()} ({r['size']} prints)" for s, r in src.iterrows())})
    cov = pd.DataFrame(cov).sort_values(["asset", "venue"])
    cov.to_csv(PROCESSED / "coverage.csv", index=False)
    print(cov.to_string())

    w = oi_weights()
    w.to_csv(PROCESSED / "oi_weights.csv", index=False)
    print(w.to_string())

    # sign check: hourly venues vs Hyperliquid, and every venue vs Hyperliquid at daily resolution
    sc = []
    for a in ASSETS:
        pa = panel[panel.asset == a].pivot_table(index="hour", columns="venue", values="ann_rate")
        if "hyperliquid" not in pa:
            continue
        daily = pa.resample("D").mean()
        for v in pa.columns:
            if v == "hyperliquid":
                continue
            both = daily[["hyperliquid", v]].dropna()
            sc.append({"asset": a, "venue": v, "days_overlap": int(len(both)),
                       "corr_daily_vs_hyperliquid": float(both.corr().iloc[0, 1]) if len(both) > 2 else np.nan,
                       "mean_ann_pct_venue": float(both[v].mean() * 100), "mean_ann_pct_hyperliquid": float(both["hyperliquid"].mean() * 100)})
    sc = pd.DataFrame(sc)
    sc.to_csv(PROCESSED / "sign_check.csv", index=False)
    print(sc.to_string())

    # wide tables with composites
    for a in ASSETS:
        pa = panel[panel.asset == a].pivot_table(index="hour", columns="venue", values="ann_rate")
        grid = pd.date_range(SAMPLE_START, SAMPLE_END, freq="h", tz="UTC")
        pa = pa.reindex(grid)
        wa = w[w.asset == a].dropna(subset=["oi_usd"]).set_index("venue").oi_usd
        cols = [c for c in pa.columns if c in wa.index]
        W = pa[cols].notna().mul(wa[cols], axis=1)
        num = (pa[cols].fillna(0) * W).sum(axis=1)
        den = W.sum(axis=1)
        n_oi = pa[cols].notna().sum(axis=1)
        pa["comp_oi"] = (num / den).where(n_oi >= 2)
        # capped OI weights: one weight vector per availability pattern (set of venues with data)
        avail = pa[cols].notna()
        for name, cap in CAPS.items():
            out = pd.Series(np.nan, index=pa.index)
            for pattern, idx in avail.groupby(list(cols)).groups.items():
                present = [c for c, p in zip(cols, pattern) if p]
                if len(present) < 2:
                    continue
                cw = capped_weights(wa[present], cap)
                out.loc[idx] = (pa.loc[idx, present] * cw).sum(axis=1)
            pa[name] = out
        n_all = pa[[c for c in pa.columns if c in VENUES]].notna().sum(axis=1)
        pa["comp_median"] = pa[[c for c in pa.columns if c in VENUES]].median(axis=1).where(n_all >= 2)
        pa["n_venues"] = n_all
        pa.index.name = "hour"
        pa.to_csv(PROCESSED / f"hourly_wide_{a}.csv")
        print(a, {c: int(pa[c].notna().sum()) for c in pa.columns})


if __name__ == "__main__":
    main()
