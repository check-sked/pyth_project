"""Step 3: compare each block print with the public screen around it.

For each block trade we fetch 1-minute candlesticks for the market from
60 minutes before to 60 minutes after the print and record:

- screen bid/ask/mid at the minute the block printed (close of the prior candle)
- last on-book trade price before the block
- where the block printed relative to the spread (inside / at / outside)
- the block's size as a multiple of the market's on-book volume in the
  surrounding +-60 minutes and of the market's open interest at the time
- the on-book price 60 min after the block (did the screen follow the block?)

Output: data/processed/block_context.csv
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
import kalshi  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
WINDOW_MIN = 60


def load_blocks() -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in RAW.glob("block_trades*.csv") if p.stat().st_size > 0]
    df = pd.concat(frames).drop_duplicates("trade_id")
    df["created_time"] = pd.to_datetime(df.created_time, utc=True)
    # Timestamp.timestamp() is seconds either way. astype("int64")//1e9 is not:
    # pandas stores datetimes as microseconds on some builds, and that division
    # lands in 1970, so every screen comparison comes back empty.
    df["ts"] = df.created_time.map(lambda t: int(pd.Timestamp(t).timestamp()))
    return df.sort_values("created_time").reset_index(drop=True)


def f(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _g(obj: dict, key: str):
    """Live candles use `<key>_dollars` / `*_fp`; archived (historical) candles use bare keys."""
    return obj.get(f"{key}_dollars", obj.get(key))


def candles_df(series_ticker: str, ticker: str, start_ts: int, end_ts: int) -> pd.DataFrame:
    rows = []
    cs = []
    for historical in (False, True):
        try:
            path = (f"/historical/markets/{ticker}/candlesticks" if historical
                    else f"/series/{series_ticker}/markets/{ticker}/candlesticks")
            d = kalshi.get(path, {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 1}, retries=2)
            cs = d.get("candlesticks", [])
            if cs:
                break
        except (RuntimeError, requests.HTTPError):
            cs = []
    for c in cs:
        rows.append({
            "end_ts": c["end_period_ts"],
            "bid": f(_g(c["yes_bid"], "close")), "ask": f(_g(c["yes_ask"], "close")),
            "bid_open": f(_g(c["yes_bid"], "open")), "ask_open": f(_g(c["yes_ask"], "open")),
            "px_open": f(_g(c["price"], "open")), "px_close": f(_g(c["price"], "close")),
            "px_prev": f(_g(c["price"], "previous")), "px_mean": f(_g(c["price"], "mean")),
            "px_high": f(_g(c["price"], "high")), "px_low": f(_g(c["price"], "low")),
            "vol": f(c.get("volume_fp", c.get("volume"))), "oi": f(c.get("open_interest_fp", c.get("open_interest"))),
        })
    return pd.DataFrame(rows)


def context_for(block: pd.Series, all_blocks: pd.DataFrame) -> dict:
    ticker, ts = block.ticker, int(block.ts)
    series_ticker = kalshi.series_ticker_of(ticker)
    cs = candles_df(series_ticker, ticker, ts - WINDOW_MIN * 60, ts + WINDOW_MIN * 60)
    out = {"trade_id": block.trade_id, "n_candles": len(cs)}
    if cs.empty:
        return out
    # candlestick volume includes block prints; strip *other* blocks on this ticker in the window
    others = all_blocks[(all_blocks.ticker == ticker) & (all_blocks.trade_id != block.trade_id)
                        & (all_blocks.ts >= ts - WINDOW_MIN * 60) & (all_blocks.ts <= ts + WINDOW_MIN * 60)]
    other_pre = float(others[others.ts <= ts].count_fp.sum())
    other_post = float(others[others.ts > ts].count_fp.sum())
    px = float(block.yes_price_dollars)
    before = cs[cs.end_ts <= ts]
    after = cs[cs.end_ts > ts]
    # the candle containing the block: first candle ending after ts
    cur = after.iloc[0] if not after.empty else None
    prev = before.iloc[-1] if not before.empty else None
    # screen at the moment of the block = open of the containing candle (falls back to close of prior candle)
    bid = (cur.bid_open if cur is not None and cur.bid_open is not None else (prev.bid if prev is not None else None))
    ask = (cur.ask_open if cur is not None and cur.ask_open is not None else (prev.ask if prev is not None else None))
    last = (cur.px_prev if cur is not None and cur.px_prev is not None else (prev.px_close if prev is not None else None))
    mid = (bid + ask) / 2 if bid is not None and ask is not None else None
    qty = float(block.count_fp)
    vol_pre = max(float(before.vol.sum()) - other_pre, 0.0)
    vol_post = max(float(after.vol.sum()) - qty - other_post, 0.0)
    out.update({
        "screen_bid": bid, "screen_ask": ask, "screen_mid": mid, "screen_spread": (ask - bid) if mid is not None else None,
        "last_onbook_px": last,
        "block_minus_mid": (px - mid) if mid is not None else None,
        "block_minus_last": (px - last) if last is not None else None,
        "inside_spread": (bid < px < ask) if mid is not None else None,
        "outside_spread": (px < bid or px > ask) if mid is not None else None,
        "cents_outside_spread": (max(0.0, bid - px, px - ask)) if mid is not None else None,
        # effectively unquoted market: no quotes, a >=50c wide spread, or a degenerate 0/0 book
        "no_screen": (mid is None) or (ask - bid >= 0.5) or (ask <= bid) or (ask == 0),
        "onbook_vol_pre60": vol_pre,
        "onbook_vol_post60_ex_block": vol_post,
        "block_x_onbook_vol_pre60": (qty / vol_pre) if vol_pre > 0 else None,
        "oi_before": float(prev.oi) if prev is not None else None,
        "block_pct_of_oi": (qty / float(prev.oi)) if prev is not None and prev.oi and prev.oi > 0 else None,
        "px_close_post60": f(after.px_close.dropna().iloc[-1]) if not after.px_close.dropna().empty else None,
        "mid_post60": ((after.iloc[-1].bid + after.iloc[-1].ask) / 2
                       if not after.empty and after.iloc[-1].bid is not None and after.iloc[-1].ask is not None else None),
        "minutes_since_last_onbook_trade": (
            (ts - int(before[before.vol > 0].end_ts.iloc[-1])) / 60 if (before.vol > 0).any() else None),
    })
    return out


def main():
    PROC.mkdir(parents=True, exist_ok=True)
    blocks = load_blocks()
    print(f"{len(blocks)} block trades", file=sys.stderr)
    rows = []
    for i, b in blocks.iterrows():
        try:
            rows.append(context_for(b, blocks))
        except Exception as e:  # keep going; record failure
            rows.append({"trade_id": b.trade_id, "error": str(e)[:200]})
        if i % 10 == 0:
            print(f"  {i}/{len(blocks)}", file=sys.stderr)
    ctx = pd.DataFrame(rows)
    merged = blocks.merge(ctx, on="trade_id", how="left")
    # category via series metadata (02_market_universe.py)
    se = pd.read_csv(RAW / "series.csv")[["series_ticker", "category", "series_title"]]
    merged["series_ticker"] = merged.ticker.map(kalshi.series_ticker_of)
    merged = merged.merge(se, on="series_ticker", how="left")
    merged["premium_usd"] = merged.count_fp * merged[["yes_price_dollars", "no_price_dollars"]].min(axis=1)
    merged["notional_usd"] = merged.count_fp  # $1 payout per contract
    merged.to_csv(PROC / "block_context.csv", index=False)
    print(f"wrote {PROC / 'block_context.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
