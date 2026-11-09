"""Step 6: how good is the public screen as a *mark*?

Uses the trade tape for the largest non-sports markets (05_pull_trades.py) to
measure four things a fund administrator or risk desk cares about:

A. Size concentration: what share of volume prints in large trades?
B. Impact of large on-book prints: how far do they move the last price, and
   does the move revert (temporary impact = the screen does not reflect size)?
C. Mark dispersion: at hourly snapshots, how far is `last trade` from a 1h
   and 24h VWAP? (Different reasonable marks give different numbers.)
D. Staleness: at a daily 4pm ET valuation snapshot, how long since the last
   trade, and how much open interest sits in markets with a stale last price?
E. Month-end case study: dollar value of open interest under alternative marks.

Outputs: data/processed/mark_*.csv and a printed summary, also saved to output/mark_quality.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
SIZE_BUCKETS = [0, 100, 1_000, 5_000, 10_000, 50_000, np.inf]
SIZE_LABELS = ["<100", "100-1k", "1k-5k", "5k-10k", "10k-50k", ">=50k"]
LARGE = 5_000  # contracts


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    tr = pd.read_parquet(RAW / "trades_top_oi.parquet").sort_values(["ticker", "created_time"])
    mk = pd.read_csv(RAW / "trades_top_oi_markets.csv")
    tr["px"] = tr.yes_price_dollars
    tr["qty"] = tr.count_fp
    tr["notional"] = tr.qty  # each contract pays $1
    return tr, mk


# A -------------------------------------------------------------------------
def size_concentration(tr: pd.DataFrame) -> pd.DataFrame:
    tr = tr.copy()
    tr["bucket"] = pd.cut(tr.qty, SIZE_BUCKETS, labels=SIZE_LABELS, right=False)
    g = tr.groupby("bucket", observed=False).agg(trades=("qty", "size"), contracts=("qty", "sum"))
    g["share_trades"] = g.trades / g.trades.sum()
    g["share_contracts"] = g.contracts / g.contracts.sum()
    g["cum_share_contracts_from_top"] = g.share_contracts[::-1].cumsum()[::-1]
    return g


# B -------------------------------------------------------------------------
def large_print_impact(tr: pd.DataFrame, horizon_min: int = 30) -> pd.DataFrame:
    rows = []
    for t, g in tr.groupby("ticker"):
        g = g.reset_index(drop=True)
        # merge same-timestamp fills (one aggressor sweeping several levels)
        g["ts_key"] = g.created_time.dt.floor("s")
        agg = g.groupby("ts_key").agg(qty=("qty", "sum"), px=("px", lambda s: np.average(s, weights=g.loc[s.index, "qty"])),
                                      is_block=("is_block_trade", "max")).reset_index()
        agg["prev_px"] = agg.px.shift(1)
        agg["prev_ts"] = agg.ts_key.shift(1)
        big = agg[(agg.qty >= LARGE) & ~agg.is_block & agg.prev_px.notna()]
        for _, r in big.iterrows():
            later = agg[(agg.ts_key > r.ts_key + pd.Timedelta(minutes=horizon_min))]
            px_later = later.px.iloc[0] if not later.empty else np.nan
            rows.append({"ticker": t, "ts": r.ts_key, "qty": r.qty, "px": r.px, "prev_px": r.prev_px,
                         "impact": r.px - r.prev_px, "px_later": px_later,
                         "reversal": (px_later - r.px) if not np.isnan(px_later) else np.nan,
                         "gap_min_since_prev": (r.ts_key - r.prev_ts).total_seconds() / 60})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["abs_impact"] = df.impact.abs()
        # fraction of impact that reverts within the horizon (signed, clipped to [0,1] per obs)
        with np.errstate(divide="ignore", invalid="ignore"):
            df["reverted_frac"] = np.where(df.impact != 0, (-df.reversal / df.impact).clip(-1, 1), np.nan)
    return df


# C -------------------------------------------------------------------------
def mark_dispersion(tr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t, g in tr.groupby("ticker"):
        s = g.set_index("created_time")
        hourly_last = s.px.resample("1h").last().ffill()
        pv = (s.px * s.qty).resample("1h").sum()
        v = s.qty.resample("1h").sum()
        vwap1 = (pv / v)
        vwap24 = pv.rolling(24, min_periods=1).sum() / v.rolling(24, min_periods=1).sum()
        df = pd.DataFrame({"last": hourly_last, "vwap1h": vwap1, "vwap24h": vwap24, "vol1h": v})
        df = df[df.vwap24h.notna()]
        df["ticker"] = t
        rows.append(df.reset_index().rename(columns={"created_time": "hour"}))
    out = pd.concat(rows, ignore_index=True)
    out["last_minus_vwap24"] = out["last"] - out.vwap24h
    out["last_minus_vwap1"] = out["last"] - out.vwap1h
    return out


# D -------------------------------------------------------------------------
def staleness(tr: pd.DataFrame, mk: pd.DataFrame, hour_utc: int = 21) -> pd.DataFrame:
    rows = []
    days = pd.date_range(tr.created_time.min().normalize() + pd.Timedelta(days=1),
                         tr.created_time.max().normalize(), freq="D", tz="UTC")
    oi = mk.set_index("ticker").open_interest_fp
    for t, g in tr.groupby("ticker"):
        ts = g.created_time.dt.tz_convert("UTC").dt.tz_localize(None).values
        for d in days:
            snap = d + pd.Timedelta(hours=hour_utc)
            snap_naive = snap.tz_convert("UTC").tz_localize(None)
            idx = np.searchsorted(ts, np.datetime64(snap_naive)) - 1
            if idx < 0:
                continue
            age_min = (snap_naive - pd.Timestamp(ts[idx])).total_seconds() / 60
            # volume in the 24h before the snapshot
            lo = np.searchsorted(ts, np.datetime64(snap_naive - pd.Timedelta(hours=24)))
            rows.append({"ticker": t, "snapshot": snap, "minutes_since_last_trade": age_min,
                         "trades_prev_24h": idx + 1 - lo, "contracts_prev_24h": g.qty.values[lo:idx + 1].sum(),
                         "open_interest_now": oi.get(t, np.nan)})
    return pd.DataFrame(rows)


# E -------------------------------------------------------------------------
def oi_as_of(when: pd.Timestamp, fallback: pd.Series) -> pd.Series:
    """Open interest per ticker at the end of `when`'s date, from daily candles (05b);
    falls back to the market snapshot OI if the candle file is missing."""
    p = RAW / "daily_candles_top_oi.parquet"
    if not p.exists():
        return fallback
    dc = pd.read_parquet(p)
    day = dc[dc.date == when.normalize()]
    return day.set_index("ticker").open_interest_fp.reindex(fallback.index).fillna(fallback)


def month_end(tr: pd.DataFrame, mk: pd.DataFrame, when: pd.Timestamp) -> pd.DataFrame:
    rows = []
    oi = oi_as_of(when, mk.set_index("ticker").open_interest_fp)
    for t, g in tr.groupby("ticker"):
        before = g[g.created_time <= when]
        if before.empty:
            continue
        last = before.px.iloc[-1]
        w1 = before[before.created_time > when - pd.Timedelta(hours=1)]
        w24 = before[before.created_time > when - pd.Timedelta(hours=24)]
        vwap1 = np.average(w1.px, weights=w1.qty) if not w1.empty else np.nan
        vwap24 = np.average(w24.px, weights=w24.qty) if not w24.empty else np.nan
        rows.append({"ticker": t, "as_of": when, "last": last, "vwap1h": vwap1, "vwap24h": vwap24,
                     "minutes_since_last_trade": (when - before.created_time.iloc[-1]).total_seconds() / 60,
                     "open_interest": oi.get(t, np.nan)})
    df = pd.DataFrame(rows)
    df["last_minus_vwap24"] = df["last"] - df.vwap24h
    df["last_minus_vwap1"] = df["last"] - df.vwap1h
    df["usd_diff_on_oi"] = df.last_minus_vwap24.abs() * df.open_interest
    # range across the three candidate marks, in dollars on the open interest
    df["mark_range"] = df[["last", "vwap1h", "vwap24h"]].max(axis=1) - df[["last", "vwap1h", "vwap24h"]].min(axis=1)
    df["usd_range_on_oi"] = df.mark_range * df.open_interest
    return df


def main():
    PROC.mkdir(parents=True, exist_ok=True)
    tr, mk = load()
    print(f"{len(tr):,} trades, {tr.ticker.nunique()} markets, {tr.created_time.min():%Y-%m-%d} -> {tr.created_time.max():%Y-%m-%d}")
    print(f"block trades in sample: {int(tr.is_block_trade.sum())}")

    print("\n== A. size concentration (pooled) ==")
    a = size_concentration(tr)
    a.to_csv(PROC / "mark_A_size_concentration.csv")
    print(a.round(4).to_string())

    print("\n== B. large (>=5k contracts) on-book prints: impact and 30-min reversal ==")
    b = large_print_impact(tr)
    b.to_csv(PROC / "mark_B_large_print_impact.csv", index=False)
    if not b.empty:
        print(f"n={len(b)}; median |impact| {b.abs_impact.median()*100:.1f}c; mean {b.abs_impact.mean()*100:.1f}c; "
              f"share |impact|>=1c {(b.abs_impact>=0.01).mean():.0%}; >=3c {(b.abs_impact>=0.03).mean():.0%}")
        nz = b[(b.abs_impact >= 0.01) & b.reversal.notna()]
        print(f"of prints that moved >=1c (n={len(nz)}): median reverted fraction in 30m {nz.reverted_frac.median():.2f}; "
              f"share reverting >=50% {(nz.reverted_frac>=0.5).mean():.0%}")

    print("\n== C. hourly mark dispersion: last trade vs 24h VWAP ==")
    c = mark_dispersion(tr)
    c.to_csv(PROC / "mark_C_hourly_dispersion.csv", index=False)
    d_abs = c.last_minus_vwap24.abs()
    print(f"n hours={len(c):,}; median |last-vwap24| {d_abs.median()*100:.2f}c; p75 {d_abs.quantile(.75)*100:.2f}c; "
          f"p90 {d_abs.quantile(.9)*100:.2f}c; share >=1c {(d_abs>=0.01).mean():.0%}; >=2c {(d_abs>=0.02).mean():.0%}; >=5c {(d_abs>=0.05).mean():.0%}")

    print("\n== D. staleness at daily 4pm ET snapshot ==")
    d = staleness(tr, mk)
    d.to_csv(PROC / "mark_D_staleness.csv", index=False)
    print(f"n market-days={len(d):,}; median minutes since last trade {d.minutes_since_last_trade.median():.0f}; "
          f"share >60m {(d.minutes_since_last_trade>60).mean():.0%}; >6h {(d.minutes_since_last_trade>360).mean():.0%}; >24h {(d.minutes_since_last_trade>1440).mean():.0%}")
    stale = d[d.minutes_since_last_trade > 60]
    print(f"OI-weighted share of market-days with last trade >60m old: "
          f"{stale.open_interest_now.sum()/d.open_interest_now.sum():.0%}")

    print("\n== E. month-end valuation: 2026-09-30 and 2026-10-31 at 4pm ET ==")
    es = []
    for when in [pd.Timestamp("2026-09-30 21:00", tz="UTC"), pd.Timestamp("2026-10-31 21:00", tz="UTC")]:
        e = month_end(tr, mk, when)
        es.append(e)
        print(f"{when:%Y-%m-%d}: markets={len(e)}, OI as of date=${e.open_interest.sum()/1e6:.1f}M notional; "
              f"median |last-vwap24h| {e.last_minus_vwap24.abs().median()*100:.2f}c; max {e.last_minus_vwap24.abs().max()*100:.1f}c; "
              f"sum |last-vwap24h| x OI = ${e.usd_diff_on_oi.sum()/1e3:,.0f}K; "
              f"sum (max-min of last/vwap1h/vwap24h) x OI = ${e.usd_range_on_oi.sum()/1e3:,.0f}K; "
              f"markets with last trade >1h old: {(e.minutes_since_last_trade>60).mean():.0%}")
    pd.concat(es).to_csv(PROC / "mark_E_month_end.csv", index=False)


class _Tee:
    """Write the printed summary to output/mark_quality.md as well as the terminal."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file, self.term = open(path, "w"), sys.stdout

    def write(self, s):
        self.file.write(s)
        self.term.write(s)

    def flush(self):
        self.file.flush()
        self.term.flush()


if __name__ == "__main__":
    sys.stdout = _Tee(ROOT / "output" / "mark_quality.md")
    main()
    sys.stdout.file.close()
