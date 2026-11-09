"""Step 4: how much can the public screen actually absorb?

For the top-N most active open, non-sports markets (by 24h volume) we snapshot
the live order book and compute the dollars of risk that can be traded
without moving the YES mid by more than 1c / 2c / 5c / 10c, on each side.

Kalshi books list YES bids and NO bids. A NO bid at price q is a YES offer at
1-q, so the YES ask side is derived from the NO bids.

Output: data/processed/orderbook_depth.csv (one row per market per snapshot)
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import kalshi  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
SPORTS = {"Sports", "Esports"}
BANDS = [0.01, 0.02, 0.05, 0.10]
WALK_SIZES = [25_000, 100_000, 250_000, 1_000_000]  # contracts; 25k = Kalshi block minimum


def pick_markets(n: int, live_price_only: bool = True) -> pd.DataFrame:
    """Top-n open non-sports markets by 24h volume. With live_price_only, restrict to
    markets whose last price is between 5c and 95c, i.e. where price discovery is still
    happening (post-event markets pinned at 1c/99c dominate raw volume rankings)."""
    mk = pd.read_csv(RAW / "markets_open.csv")
    se = pd.read_csv(RAW / "series.csv")
    mk = mk.merge(se[["series_ticker", "category", "series_title"]], on="series_ticker", how="left")
    mk = mk[~mk.category.isin(SPORTS)].copy()
    mk["volume_24h_fp"] = pd.to_numeric(mk.volume_24h_fp, errors="coerce").fillna(0)
    mk["last_price_dollars"] = pd.to_numeric(mk.last_price_dollars, errors="coerce")
    if live_price_only:
        mk = mk[mk.last_price_dollars.between(0.05, 0.95)]
    return mk.sort_values("volume_24h_fp", ascending=False).head(n)


def depth_metrics(ob: dict) -> dict:
    yes_bids = sorted(((float(p), float(q)) for p, q in ob.get("yes_dollars", [])), reverse=True)
    yes_asks = sorted(((1 - float(p), float(q)) for p, q in ob.get("no_dollars", [])))
    out = {}
    if not yes_bids or not yes_asks:
        return {"best_bid": yes_bids[0][0] if yes_bids else None, "best_ask": yes_asks[0][0] if yes_asks else None}
    bb, ba = yes_bids[0][0], yes_asks[0][0]
    mid = (bb + ba) / 2
    out.update({"best_bid": bb, "best_ask": ba, "mid": mid, "spread": ba - bb,
                "bid_size_top": yes_bids[0][1], "ask_size_top": yes_asks[0][1],
                "bid_usd_top": yes_bids[0][0] * yes_bids[0][1], "ask_usd_top": yes_asks[0][0] * yes_asks[0][1]})
    for band in BANDS:
        # dollars (YES-price-weighted) resting within `band` of the mid on each side
        bid_usd = sum(p * q for p, q in yes_bids if p >= mid - band)
        ask_usd = sum(p * q for p, q in yes_asks if p <= mid + band)
        bid_ct = sum(q for p, q in yes_bids if p >= mid - band)
        ask_ct = sum(q for p, q in yes_asks if p <= mid + band)
        out[f"bid_usd_within_{int(band*100)}c"] = bid_usd
        out[f"ask_usd_within_{int(band*100)}c"] = ask_usd
        out[f"bid_contracts_within_{int(band*100)}c"] = bid_ct
        out[f"ask_contracts_within_{int(band*100)}c"] = ask_ct
    # total displayed
    out["bid_contracts_total"] = sum(q for _, q in yes_bids)
    out["ask_contracts_total"] = sum(q for _, q in yes_asks)
    # walk the book: average fill price vs mid for a marketable order of N contracts
    for n in WALK_SIZES:
        for side, levels in (("buy", yes_asks), ("sell", yes_bids)):
            filled, cost = 0.0, 0.0
            for p, q in levels:
                take = min(q, n - filled)
                filled += take
                cost += take * p
                if filled >= n:
                    break
            avg = cost / filled if filled else None
            out[f"{side}_{n}_fill_frac"] = filled / n
            out[f"{side}_{n}_slippage_c"] = (abs(avg - mid) * 100) if avg is not None else None
    return out


def main(n: int = 40):
    PROC.mkdir(parents=True, exist_ok=True)
    mk = pick_markets(n)
    snap_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for _, m in mk.iterrows():
        try:
            ob = kalshi.get(f"/markets/{m.ticker}/orderbook", {"depth": 100})["orderbook_fp"]
            d = depth_metrics(ob)
        except Exception as e:
            d = {"error": str(e)[:120]}
        d.update({"snapshot_ts": snap_ts, "ticker": m.ticker, "title": m.title, "category": m.category,
                  "series_title": m.series_title, "volume_24h_fp": m.volume_24h_fp,
                  "open_interest_fp": m.open_interest_fp, "last_price_dollars": m.last_price_dollars})
        rows.append(d)
        time.sleep(0.15)
    df = pd.DataFrame(rows)
    out = PROC / "orderbook_depth.csv"
    if out.exists():
        df = pd.concat([pd.read_csv(out), df])
    df.to_csv(out, index=False)
    print(f"wrote {len(rows)} rows -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
