"""Do block prints persist, and which mark is closer to the later book?

Reads the block tape and the 7 Nov 2026 order-book snapshot already in this
repo. Pulls 1-minute candlesticks from Kalshi's public API for the windows
each test needs. Writes tables to data/processed/.

Rerun from inside kalshi-cost-of-size:

    python src/07_block_diagnostics.py
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "cache"  # candlestick responses; gitignored, rebuilt on a rerun
sys.path.insert(0, str(ROOT / "src"))
import kalshi  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "block_vs_screen", ROOT / "src" / "03_block_vs_screen.py"
)
_bvs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bvs)
load_blocks = _bvs.load_blocks

ET = ZoneInfo("America/New_York")
CANTOR = pd.Timestamp("2026-08-19", tz="UTC")
HALFLIFE_MIN = 15.0  # Kalshi's reporting window. Not fitted.
WALK_SIZES = (25_000, 100_000, 250_000, 1_000_000)
RNG_SEED = 42
HORIZONS = (1, 15, 60)


def f(x):
    try:
        return float(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None
    except (TypeError, ValueError):
        return None


def _g(obj, key):
    if not isinstance(obj, dict):
        return None
    return obj.get(f"{key}_dollars", obj.get(key))


def quote_ok(bid, ask) -> bool:
    """Same usable-book rule as src/03_block_vs_screen.py: a real two-sided quote under 50¢."""
    if bid is None or ask is None:
        return False
    if ask <= bid or ask == 0:
        return False
    if ask - bid >= 0.5:
        return False
    return True


def fetch_candles(ticker: str, start_ts: int, end_ts: int) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{ticker}_{int(start_ts)}_{int(end_ts)}.json"
    if path.exists():
        payload = json.loads(path.read_text())
    else:
        payload = None
        last_err = None
        for historical in (True, False):
            route = (f"/historical/markets/{ticker}/candlesticks" if historical
                     else f"/series/{kalshi.series_ticker_of(ticker)}/markets/{ticker}/candlesticks")
            try:
                d = kalshi.get(route, {"start_ts": int(start_ts), "end_ts": int(end_ts), "period_interval": 1}, retries=3)
                cs = d.get("candlesticks", [])
                if cs:
                    payload = cs
                    break
                payload = []
            except (RuntimeError, requests.HTTPError) as e:
                last_err = str(e)[:180]
                payload = []
        if payload is None:
            payload = []
        path.write_text(json.dumps({"candles": payload, "error": last_err}))
        payload = payload if isinstance(payload, list) else payload
    if isinstance(payload, dict):
        candles = payload.get("candles", [])
    else:
        candles = payload
    rows = []
    for c in candles:
        bid, ask, px = c.get("yes_bid") or {}, c.get("yes_ask") or {}, c.get("price") or {}
        rows.append({
            "end_ts": int(c["end_period_ts"]),
            "bid_open": f(_g(bid, "open")), "bid_high": f(_g(bid, "high")),
            "bid_low": f(_g(bid, "low")), "bid_close": f(_g(bid, "close")),
            "ask_open": f(_g(ask, "open")), "ask_high": f(_g(ask, "high")),
            "ask_low": f(_g(ask, "low")), "ask_close": f(_g(ask, "close")),
            "px_close": f(_g(px, "close")), "px_mean": f(_g(px, "mean")),
            "vol": f(c.get("volume_fp", c.get("volume"))),
        })
    return pd.DataFrame(rows)


def nonblock_vwap(ticker: str, start_ts: int, end_ts: int, block_ids: set[str]) -> float | None:
    """VWAP of trades the API does not flag as blocks, in [start_ts, end_ts)."""
    cache = CACHE / f"vwap_{ticker}_{int(start_ts)}_{int(end_ts)}.json"
    if cache.exists():
        d = json.loads(cache.read_text())
        return d.get("vwap")
    trades = []
    for historical in (True, False):
        try:
            trades = list(kalshi.trades(ticker, min_ts=int(start_ts), max_ts=int(end_ts) - 1,
                                        is_block_trade=False, historical=historical, retries=2, limit=1000))
            if trades:
                break
        except (RuntimeError, requests.HTTPError):
            trades = []
    num = den = 0.0
    for t in trades:
        if t.get("trade_id") in block_ids:
            continue
        px, qty = f(t.get("yes_price_dollars")), f(t.get("count_fp"))
        if px is None or qty is None or qty <= 0:
            continue
        num += px * qty
        den += qty
    vwap = (num / den) if den > 0 else None
    cache.write_text(json.dumps({"vwap": vwap, "n": len(trades)}))
    return vwap


def _range(row, side: str) -> tuple[float | None, float | None]:
    keys = [f"{side}_open", f"{side}_close", f"{side}_high", f"{side}_low"]
    vals = [getattr(row, k) for k in keys if getattr(row, k) is not None and not (isinstance(getattr(row, k), float) and math.isnan(getattr(row, k)))]
    if not vals:
        return None, None
    return min(vals), max(vals)


def screen_at(cs: pd.DataFrame, ts: int) -> tuple[float | None, float | None, str]:
    """Bid/ask at the print: open of the candle that contains ts, else the prior close."""
    if cs.empty:
        return None, None, "no_candles"
    after = cs[cs.end_ts > ts]
    before = cs[cs.end_ts <= ts]
    if not after.empty:
        cur = after.iloc[0]
        if cur.bid_open is not None and cur.ask_open is not None:
            return float(cur.bid_open), float(cur.ask_open), "containing_candle_open"
    if not before.empty:
        prev = before.iloc[-1]
        if prev.bid_close is not None and prev.ask_close is not None:
            return float(prev.bid_close), float(prev.ask_close), "prior_candle_close"
    return None, None, "no_quote"


def pre_reference(cs: pd.DataFrame, ts: int, ticker: str, block_ids: set[str], allow_vwap: bool = True) -> dict:
    """Median usable 1-minute mid in the 30 minutes before ts. Else non-block VWAP."""
    pre = cs[(cs.end_ts > ts - 30 * 60) & (cs.end_ts <= ts)] if not cs.empty else cs
    mids = []
    last_bid = last_ask = None
    if not pre.empty:
        for row in pre.itertuples(index=False):
            if quote_ok(row.bid_close, row.ask_close):
                mids.append((row.bid_close + row.ask_close) / 2)
                last_bid, last_ask = float(row.bid_close), float(row.ask_close)
    if mids:
        return {"pre_mid": float(np.median(mids)), "pre_source": "median_minute_mid",
                "pre_n_minutes": len(mids), "pre_last_bid": last_bid, "pre_last_ask": last_ask}
    if not allow_vwap:
        return {"pre_mid": None, "pre_source": "missing", "pre_n_minutes": 0,
                "pre_last_bid": None, "pre_last_ask": None}
    vwap = nonblock_vwap(ticker, ts - 30 * 60, ts, block_ids)
    return {"pre_mid": vwap, "pre_source": "nonblock_vwap" if vwap is not None else "missing",
            "pre_n_minutes": 0, "pre_last_bid": None, "pre_last_ask": None}


def mid_at(cs: pd.DataFrame, ts: int, horizon_s: int, max_stale_s: int = 300) -> dict:
    """Last usable minute at or up to 60s after ts+horizon, if it is not older than max_stale_s.

    Kalshi omits minutes with no update. A quote that last moved a few minutes
    earlier is still the book. A quote older than max_stale_s is left missing.
    """
    target = ts + horizon_s
    empty = {"mid": None, "bid": None, "ask": None, "end_ts": None, "age_s": None}
    if cs.empty:
        return empty
    hit = cs[cs.end_ts <= target + 60]
    for row in hit.iloc[::-1].itertuples(index=False):
        if not quote_ok(row.bid_close, row.ask_close):
            continue
        age = target - int(row.end_ts)
        if age > max_stale_s:
            return {**empty, "age_s": int(age)}
        return {"mid": (row.bid_close + row.ask_close) / 2, "bid": float(row.bid_close),
                "ask": float(row.ask_close), "end_ts": int(row.end_ts), "age_s": int(age)}
    return empty


def outside_full_window(cs: pd.DataFrame, ts: int, px: float, stand_bid, stand_ask) -> str:
    """True if px sat outside every minute's bid-ask range in the prior 15 minutes.

    Returns 'outside', 'inside', or 'unknown'. A minute with no usable quote is skipped.
    If the window has no usable minute, the standing quote at the print is the book.
    """
    if cs.empty:
        window = cs
    else:
        window = cs[(cs.end_ts > ts - 15 * 60) & (cs.end_ts <= ts)]
    saw = False
    for row in window.itertuples(index=False):
        bid_lo, _ = _range(row, "bid")
        _, ask_hi = _range(row, "ask")
        if not quote_ok(bid_lo, ask_hi):
            continue
        saw = True
        if bid_lo - 1e-9 <= px <= ask_hi + 1e-9:
            return "inside"
    if saw:
        return "outside"
    if quote_ok(stand_bid, stand_ask):
        if stand_bid - 1e-9 <= px <= stand_ask + 1e-9:
            return "inside"
        return "outside"
    return "unknown"


def signed_gap(px, mid, taker) -> tuple[float | None, str]:
    if px is None or mid is None:
        return None, "no_mid"
    if taker == "yes":
        return px - mid, "taker_bought_yes"
    if taker == "no":
        return mid - px, "taker_bought_no"
    return None, "taker_side_missing"


def book_cross(px, bid, ask) -> str:
    if not quote_ok(bid, ask):
        return "no_usable_book"
    if px > ask + 1e-9:
        return "through_offer"
    if px < bid - 1e-9:
        return "through_bid"
    return "inside"


def retained(pre, post, px) -> float | None:
    if pre is None or post is None or px is None:
        return None
    den = px - pre
    if abs(den) < 1e-12:
        return None
    return (post - pre) / den


def classify(r: float | None) -> str | None:
    if r is None or not np.isfinite(r):
        return None
    if r < 0.25:
        return "reverted"
    if r <= 0.75:
        return "partial"
    return "persistent"


def weighted_median(prices: list[float], weights: list[float]) -> float | None:
    pairs = [(p, w) for p, w in zip(prices, weights) if p is not None and w is not None and w > 0 and np.isfinite(p)]
    if not pairs:
        return None
    pairs.sort(key=lambda pw: pw[0])
    total = sum(w for _, w in pairs)
    acc = 0.0
    for p, w in pairs:
        acc += w
        if acc >= total / 2:
            return p
    return pairs[-1][0]


def next_close_utc(ts: pd.Timestamp) -> pd.Timestamp:
    """16:00 America/New_York on the next weekday after the print's New York date.

    Kalshi lists no session close. 16:00 ET is the daily snapshot used in
    src/06_mark_quality.py. Weekend prints roll to Monday.
    """
    day = ts.tz_convert(ET).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    close = datetime.combine(day, time(16, 0), tzinfo=ET)
    return pd.Timestamp(close).tz_convert("UTC")


def attach_categories(blocks: pd.DataFrame) -> pd.DataFrame:
    se = pd.read_csv(ROOT / "data" / "raw" / "series.csv")[["series_ticker", "category", "series_title"]]
    out = blocks.copy()
    out["series_ticker"] = out.ticker.map(kalshi.series_ticker_of)
    out = out.merge(se, on="series_ticker", how="left")
    out["is_sports"] = out.category.eq("Sports")
    out["paid_cheap_side"] = out.count_fp * out[["yes_price_dollars", "no_price_dollars"]].min(axis=1)
    out["paid_taker"] = np.where(
        out.taker_outcome_side.eq("yes"),
        out.count_fp * out.yes_price_dollars,
        np.where(out.taker_outcome_side.eq("no"), out.count_fp * out.no_price_dollars, np.nan),
    )
    out["notional_usd"] = out.count_fp
    return out


def block_window(b, block_ids: set[str]) -> dict:
    ts = int(b.ts)
    # 30 min before through 65 min after covers +1/+15/+60 with the 90s tolerance.
    cs = fetch_candles(b.ticker, ts - 30 * 60, ts + 65 * 60)
    bid, ask, how = screen_at(cs, ts)
    pre = pre_reference(cs, ts, b.ticker, block_ids)
    px = float(b.yes_price_dollars)
    row = {
        "trade_id": b.trade_id, "ticker": b.ticker, "created_time": str(b.created_time),
        "ts": ts, "count_fp": float(b.count_fp), "yes_price": px,
        "no_price": float(b.no_price_dollars), "taker_outcome_side": b.taker_outcome_side,
        "category": b.category, "series_title": b.series_title, "is_sports": bool(b.is_sports),
        "screen_bid": bid, "screen_ask": ask, "screen_source": how,
        "no_usable_quote": not quote_ok(bid, ask),
        "book_cross": book_cross(px, bid, ask),
        "outside_15m": outside_full_window(cs, ts, px, bid, ask),
        **pre,
    }
    gap, gap_src = signed_gap(px, pre["pre_mid"], b.taker_outcome_side)
    row["signed_gap"] = gap
    row["signed_gap_source"] = gap_src
    if pre["pre_mid"] is not None and gap_src == "taker_side_missing":
        cross = row["book_cross"]
        if cross == "through_offer":
            row["signed_gap"] = px - pre["pre_mid"]
            row["signed_gap_source"] = "inferred_through_offer"
        elif cross == "through_bid":
            row["signed_gap"] = pre["pre_mid"] - px
            row["signed_gap_source"] = "inferred_through_bid"
        elif cross == "inside":
            row["signed_gap_source"] = "inside_spread_unknown"
    for h, stale in ((1, 90), (15, 300), (60, 300)):
        m = mid_at(cs, ts, h * 60, max_stale_s=stale)
        row[f"mid_{h}"] = m["mid"]
        row[f"bid_{h}"] = m["bid"]
        row[f"ask_{h}"] = m["ask"]
        row[f"age_{h}"] = m["age_s"]
        row[f"retained_{h}"] = retained(pre["pre_mid"], m["mid"], px)
    row["class_60"] = classify(row["retained_60"])
    # Next weekday 16:00 ET. Separate short pull.
    close = next_close_utc(pd.Timestamp(b.created_time))
    close_ts = int(close.timestamp())
    cs2 = fetch_candles(b.ticker, close_ts - 300, close_ts + 90)
    m = mid_at(cs2, close_ts, 0, max_stale_s=300)
    # mid_at looks for a candle containing (close_ts-60)+60 = close_ts.
    row["next_close_utc"] = str(close)
    row["mid_next_close"] = m["mid"]
    row["bid_next_close"] = m["bid"]
    row["ask_next_close"] = m["ask"]
    row["retained_next_close"] = retained(pre["pre_mid"], m["mid"], px)
    row["n_candles_event"] = int(len(cs))
    return row


def baseline_moves(blocks: pd.DataFrame, block_ids: set[str], n_usable: int = 50) -> pd.DataFrame:
    """Same pre-mid and +60 mid move, at random minutes in the block markets, away from blocks."""
    rng = np.random.default_rng(RNG_SEED)
    eligible = []
    for ticker, g in blocks.groupby("ticker"):
        lo = int(g.ts.min()) - 24 * 3600
        hi = int(g.ts.max()) + 24 * 3600
        banned = []
        for ts in g.ts.astype(int):
            banned.append((ts - 60 * 60, ts + 60 * 60))
        # One candidate per 5 minutes keeps the draw uniform in time without a huge list.
        for minute in range(lo, hi, 300):
            if any(a <= minute <= b for a, b in banned):
                continue
            eligible.append((ticker, minute))
    if not eligible:
        return pd.DataFrame()
    order = rng.permutation(len(eligible))
    rows = []
    attempts = 0
    for idx in order:
        if sum(r["usable"] for r in rows) >= n_usable:
            break
        attempts += 1
        if attempts > max(400, n_usable * 8):
            break
        ticker, ts = eligible[idx]
        cs = fetch_candles(ticker, ts - 30 * 60, ts + 65 * 60)
        pre = pre_reference(cs, ts, ticker, block_ids, allow_vwap=False)
        post = mid_at(cs, ts, 60 * 60, max_stale_s=300)
        usable = pre["pre_mid"] is not None and post["mid"] is not None
        rows.append({
            "ticker": ticker, "ts": ts, "pre_mid": pre["pre_mid"], "pre_source": pre["pre_source"],
            "mid_60": post["mid"], "move": (None if not usable else post["mid"] - pre["pre_mid"]),
            "usable": usable,
        })
        print(f"  baseline {sum(r['usable'] for r in rows)}/{n_usable} attempts {attempts}", file=sys.stderr)
    out = pd.DataFrame(rows)
    out.attrs["attempts"] = attempts
    out.attrs["eligible_slots"] = len(eligible)
    return out


def ceiling_bin(qty: float) -> int | None:
    for n in WALK_SIZES:
        if qty <= n:
            return n
    return None


def slippage_proxy(blocks: pd.DataFrame, paths: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    depth = pd.read_csv(ROOT / "data" / "processed" / "orderbook_depth.csv")
    depth["snapshot_ts"] = pd.to_datetime(depth.snapshot_ts, utc=True)
    # The file can hold more than one snapshot. Keep the latest row per ticker.
    depth = depth.sort_values("snapshot_ts").groupby("ticker", as_index=False).tail(1)
    info = {
        "snapshot_min": str(depth.snapshot_ts.min()),
        "snapshot_max": str(depth.snapshot_ts.max()),
        "n_markets": int(depth.ticker.nunique()),
        "historical_depth": False,
    }
    by_ticker = depth.set_index("ticker")
    rows = []
    for p in paths.itertuples(index=False):
        qty = float(p.count_fp)
        bin_n = ceiling_bin(qty)
        side = "buy" if p.taker_outcome_side == "yes" else "sell" if p.taker_outcome_side == "no" else None
        gap_c = None if p.pre_mid is None else abs(p.yes_price - p.pre_mid) * 100
        rec = {
            "trade_id": p.trade_id, "ticker": p.ticker, "category": p.category,
            "count_fp": qty, "gap_cents": gap_c, "side": side, "bin": bin_n,
            "match": None, "slippage_c": None, "fill_frac": None, "cheaper": None, "note": "",
        }
        if side is None or bin_n is None:
            rec["note"] = "NOT AVAILABLE: block is larger than 1,000,000, the top of the 7 Nov curve" if bin_n is None else "NOT AVAILABLE: taker side missing"
            rows.append(rec)
            continue
        slip_col = f"{side}_{bin_n}_slippage_c"
        fill_col = f"{side}_{bin_n}_fill_frac"
        if p.ticker in by_ticker.index:
            src = by_ticker.loc[p.ticker]
            rec["match"] = "same_ticker"
            rec["slippage_c"] = f(src[slip_col]) if slip_col in src else None
            rec["fill_frac"] = f(src[fill_col]) if fill_col in src else None
        else:
            cat = depth[depth.category.eq(p.category)]
            full = cat[pd.to_numeric(cat[fill_col], errors="coerce") >= 1] if fill_col in cat.columns else cat.iloc[0:0]
            slips = pd.to_numeric(full[slip_col], errors="coerce").dropna() if slip_col in full.columns else pd.Series(dtype=float)
            if slips.empty:
                rec["match"] = "none"
                rec["note"] = "NOT AVAILABLE: ticker is not in the 7 Nov snapshot and no same-category book fully fills this size"
            else:
                rec["match"] = "category_median"
                rec["slippage_c"] = float(slips.median())
                rec["fill_frac"] = 1.0
                rec["note"] = f"category median of {len(slips)} books that fully fill a {bin_n:,.0f}-contract {side}"
        if rec["fill_frac"] is not None and rec["fill_frac"] < 1:
            rec["cheaper"] = None
            rec["note"] = (rec["note"] + "; " if rec["note"] else "") + "snapshot book does not fully fill this size bin"
        elif rec["slippage_c"] is not None and gap_c is not None:
            rec["cheaper"] = bool(gap_c < rec["slippage_c"])
        rows.append(rec)
    return pd.DataFrame(rows), info


def marks_for(paths: pd.DataFrame) -> pd.DataFrame:
    """Three point estimates at each back-test block, scored on the +60 mid.

    (a) book mid at the print.
    (b) size-and-recency weighted median of earlier block YES prices on that
        ticker. The print being scored is not in the median. The book's size
        is not stored, so the book is not an observation in this median.
        A ticker's first print has no earlier block, so (b) is missing.
    (c) same median of earlier prints that were inside the bid-ask for some
        minute of the prior 15. If none remain, the mark is the book.
    """
    names = {
        "KXFEDDECISION-26JUL-H25": "July Fed decision",
        "GOVPARTYTX-26-R": "Texas governor",
        "KXBRPRES-26-LULA": "Brazil president",
    }
    commodity = set(paths.loc[paths.category.eq("Commodities"), "ticker"])
    keep = set(names) | commodity
    sub = paths[paths.ticker.isin(keep)].copy()
    sub["market_name"] = sub.ticker.map(lambda t: names.get(t, "commodity hub"))
    rows = []
    for ticker, g in sub.groupby("ticker"):
        g = g.sort_values("ts")
        history = []  # (ts, px, qty, outside_15m)
        for r in g.itertuples(index=False):
            book = None
            if quote_ok(r.screen_bid, r.screen_ask):
                book = (float(r.screen_bid) + float(r.screen_ask)) / 2
            elif r.pre_mid is not None and r.pre_source == "median_minute_mid":
                book = float(r.pre_mid)
            def weights(items):
                px, w = [], []
                for ts_i, p, q, _flag in items:
                    age_min = (int(r.ts) - ts_i) / 60
                    px.append(p)
                    w.append(q * (0.5 ** (age_min / HALFLIFE_MIN)))
                return px, w
            # Score this print on earlier prints only. Putting the print into
            # its own mark makes a one-print market equal the print.
            mark_b = weighted_median(*weights(history))
            confirming = [h for h in history if h[3] == "inside"]
            if confirming:
                mark_c = weighted_median(*weights(confirming))
                mark_c_includes_book = False
            else:
                mark_c = book
                mark_c_includes_book = True
            history.append((int(r.ts), float(r.yes_price), float(r.count_fp), r.outside_15m))
            rows.append({
                "trade_id": r.trade_id, "ticker": ticker, "market_name": r.market_name,
                "series_title": r.series_title, "created_time": r.created_time,
                "book": book, "mark_b": mark_b, "mark_c": mark_c,
                "mark_c_is_book": mark_c_includes_book,
                "outside_15m": r.outside_15m, "mid_60": r.mid_60, "count_fp": r.count_fp,
                "err_a": None if book is None or r.mid_60 is None else abs(book - r.mid_60) * 100,
                "err_b": None if mark_b is None or r.mid_60 is None else abs(mark_b - r.mid_60) * 100,
                "err_c": None if mark_c is None or r.mid_60 is None else abs(mark_c - r.mid_60) * 100,
            })
    return pd.DataFrame(rows)


def _med(s: pd.Series):
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return None
    return float(s.median())


def _fmt(x, digits=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "NOT AVAILABLE"
    return f"{x:.{digits}f}"


def _word(n: int) -> str:
    words = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
    return words.get(int(n), str(int(n)))


def _counts(df: pd.DataFrame) -> dict:
    classified = df[df.class_60.notna()]
    return {
        "n": int(len(df)),
        "n_pre": int(df.pre_mid.notna().sum()),
        "n_60": int(df.mid_60.notna().sum()),
        "n_class": int(len(classified)),
        "reverted": int((classified.class_60 == "reverted").sum()),
        "partial": int((classified.class_60 == "partial").sum()),
        "persistent": int((classified.class_60 == "persistent").sum()),
        "med_ret_1": _med(df.retained_1),
        "med_ret_15": _med(df.retained_15),
        "med_ret_60": _med(df.retained_60),
        "med_ret_next": _med(df.retained_next_close),
        "n_next": int(df.mid_next_close.notna().sum()),
        "med_abs_move_60_c": _med((df.mid_60 - df.pre_mid).abs() * 100),
    }


def markdown_table(headers, rows) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join([line, sep, *body])


def build_report(paths, base, proxy, proxy_info, marks, blocks) -> str:
    first = blocks.created_time.min()
    last = blocks.created_time.max()
    duration = last - CANTOR
    before_lo = CANTOR - duration
    scan_files = sorted((ROOT / "data" / "raw").glob("block_trades_*.csv"))
    scan_note = ", ".join(p.name for p in scan_files)
    n_before_eq = int(((blocks.created_time >= before_lo) & (blocks.created_time < CANTOR)).sum())
    n_after_eq = int(((blocks.created_time >= CANTOR) & (blocks.created_time <= last)).sum())
    n_before = int((blocks.created_time < CANTOR).sum())
    n_after = int((blocks.created_time >= CANTOR).sum())
    months = blocks.groupby(blocks.created_time.dt.strftime("%Y-%m")).size()

    def cat_table(frame, label):
        g = frame.groupby(frame.category.fillna("UNKNOWN"), dropna=False)
        rows = []
        for cat, sub in g:
            rows.append((cat, int(len(sub)), f"{sub.notional_usd.sum():,.0f}", f"{sub.paid_taker.sum():,.0f}",
                         f"{sub.count_fp.min():,.0f}"))
        rows.sort(key=lambda r: -int(r[2].replace(",", "")))
        return rows

    lines = []
    a = lines.append
    a("# Block diagnostics")
    a("")
    a("These tables are written by `src/07_block_diagnostics.py` from the block tape, the 7 Nov 2026 depth snapshot, and candlesticks pulled for this run. A blank that the code could not fill is the words NOT AVAILABLE.")
    a("")
    a("## 1. Data availability")
    a("")
    a(f"- Block tape: {len(blocks)} prints, {blocks.ticker.nunique()} markets, {first} through {last}. Files: {scan_note}.")
    a("- Test 1 pre/post mids: 1-minute candlestick bid/ask. Usable minute = two-sided, ask above bid, spread under 50¢ (the rule in `src/03_block_vs_screen.py`). If that window has no usable minute, the pre-block reference is the VWAP of trades the API does not flag as blocks.")
    a(f"- Pre-block source mix: " + ", ".join(f"{k} {int(v)}" for k, v in paths.pre_source.value_counts(dropna=False).items()) + ".")
    a(f"- +60 min mid available for {int(paths.mid_60.notna().sum())} of {len(paths)}. Next weekday 16:00 ET mid available for {int(paths.mid_next_close.notna().sum())} of {len(paths)}.")
    a("- A horizon quote is the last usable minute ending at or up to 60 seconds after the target. It is kept only if that minute is at most 90 seconds old at +1 minute, and at most 5 minutes old at +15, +60, and the next 16:00 ET. A quieter book than that is NOT AVAILABLE at that horizon, not a carried-forward guess.")
    a("- Taker outcome side is present on every row of the tape, so the signed gap uses that side. It is not inferred from the book.")
    a(f"- Test 2 historical depth: NOT AVAILABLE: the repo has no order book at block time. `data/processed/orderbook_depth.csv` is a top-of-book-and-depth snapshot of {proxy_info['n_markets']} markets, timestamps {proxy_info['snapshot_min']} to {proxy_info['snapshot_max']}, depth capped at 100 levels by the script that built it. Candlesticks have the best bid and ask only.")
    a("- Test 3 book weight: NOT AVAILABLE: candlesticks do not carry size at the bid or ask, and the historical book is not stored. Design (b) is a weighted median of earlier block prices only. The print being scored is not included. Design (c) uses the book when no earlier print was inside the quote.")
    a(f"- Recency half-life is {HALFLIFE_MIN:.0f} minutes, Kalshi's reporting window. It is an assumption, not a fitted number.")
    a("")
    a("## 2. Tables")
    a("")
    a("### Test 1. Retained fraction of the block-minus-pre-mid gap")
    a("")
    a("Retained = (post mid − pre mid) / (block YES price − pre mid). Pre mid is the median usable 1-minute mid in the prior 30 minutes. Class at +60 min: reverted if retained < 25%, partial if 25% to 75% inclusive, persistent if retained > 75%. Negative retained counts as reverted.")
    a("")
    base_usable = base[base.usable] if len(base) else base
    base_med = _med(base_usable["move"].abs() * 100) if len(base_usable) else None
    attempts = int(base.attrs.get("attempts", len(base))) if len(base) else 0
    eligible = int(base.attrs.get("eligible_slots", 0)) if len(base) else 0

    def row_for(label, df):
        c = _counts(df)
        return [label, c["n"], c["n_class"], c["reverted"], c["partial"], c["persistent"],
                _fmt(None if c["med_ret_1"] is None else c["med_ret_1"] * 100),
                _fmt(None if c["med_ret_15"] is None else c["med_ret_15"] * 100),
                _fmt(None if c["med_ret_60"] is None else c["med_ret_60"] * 100),
                _fmt(None if c["med_ret_next"] is None else c["med_ret_next"] * 100),
                c["n_next"],
                _fmt(c["med_abs_move_60_c"])]

    headers = ["slice", "n", "n classified +60", "reverted", "partial", "persistent",
               "median retained +1 %", "+15 %", "+60 %", "next 16:00 ET %", "n next close",
               "median abs mid move +60, cents"]
    slices = [("all blocks", paths)]
    slices.append(("outside bid-ask at the print", paths[paths.book_cross.isin(["through_offer", "through_bid"])]))
    slices.append(("inside the spread at the print", paths[paths.book_cross.eq("inside")]))
    slices.append(("no usable quote at the print", paths[paths.no_usable_quote]))
    slices.append(("before 19 Aug 2026", paths[pd.to_datetime(paths.created_time, utc=True) < CANTOR]))
    slices.append(("on/after 19 Aug 2026", paths[pd.to_datetime(paths.created_time, utc=True) >= CANTOR]))
    for cat, sub in paths.groupby(paths.category.fillna("UNKNOWN")):
        slices.append((f"category: {cat}", sub))
    # Robustness: drop gaps under 1¢, where the ratio is a small denominator.
    wide = paths[(paths.yes_price - paths.pre_mid).abs() >= 0.01]
    slices.append(("|block − pre mid| ≥ 1¢", wide))
    a(markdown_table(headers, [row_for(lab, df) for lab, df in slices]))
    a("")
    base_abs = (base_usable["move"].abs() * 100) if len(base_usable) else pd.Series(dtype=float)
    base_zero = float((base_abs < 1e-9).mean()) if len(base_abs) else None
    base_p75 = float(base_abs.quantile(0.75)) if len(base_abs) else None
    a(f"Baseline: {len(base_usable)} usable random minutes out of {attempts} attempts, drawn from {eligible} five-minute slots in the same markets, seed {RNG_SEED}, excluding the 60 minutes on either side of a block on that ticker. Median |mid(t+60) − pre mid| = {_fmt(base_med)}¢. Share with no move: {_fmt(None if base_zero is None else base_zero*100, 0)}%. 75th percentile: {_fmt(base_p75)}¢. The baseline has no block price, so it has no retained fraction.")
    a("")
    disagree = paths[paths.book_cross.isin(["through_offer", "through_bid"])].copy()
    if len(disagree):
        # Taker-yes should be the offer side; taker-no should be the bid side.
        mismatch = (
            ((disagree.taker_outcome_side == "yes") & (disagree.book_cross == "through_bid"))
            | ((disagree.taker_outcome_side == "no") & (disagree.book_cross == "through_offer"))
        )
        a(f"Of {len(disagree)} prints outside the usable bid-ask, {int(mismatch.sum())} have a taker side that does not match the side of the YES book they crossed. The signed gap follows the taker side anyway. Median signed gap, all blocks with a pre mid: {_fmt(_med(paths.signed_gap) * 100 if _med(paths.signed_gap) is not None else None)}¢.")
    a("")
    a("### Test 2. Block gap versus the 7 Nov slippage curve (proxy)")
    a("")
    a("Historical depth at the print: NOT AVAILABLE. The comparison below is a proxy. Gap = |block YES price − pre mid| in cents. Slippage is the 7 Nov walk-the-book number, in cents versus that day's mid, on the taker's YES side (buy if the taker bought YES, sell if the taker bought NO). The size bin is the smallest published size at or above the block (25k, 100k, 250k, 1M). A block above 1M is not compared.")
    a("")
    comp = proxy[proxy.cheaper.notna()]
    same = comp[comp.match.eq("same_ticker")]
    cat = comp[comp.match.eq("category_median")]
    a(markdown_table(
        ["comparison", "n", "cheaper than the curve", "dearer than the curve", "median gap ¢", "median curve slippage ¢"],
        [
            ["same ticker, curve fully fills the bin", len(same), int((same.cheaper == True).sum()) if len(same) else 0,
             int((same.cheaper == False).sum()) if len(same) else 0, _fmt(_med(same.gap_cents)), _fmt(_med(same.slippage_c))],
            ["same category only, curve fully fills the bin", len(cat), int((cat.cheaper == True).sum()) if len(cat) else 0,
             int((cat.cheaper == False).sum()) if len(cat) else 0, _fmt(_med(cat.gap_cents)), _fmt(_med(cat.slippage_c))],
            ["no comparison", int(proxy.cheaper.isna().sum()), "—", "—", "—", "—"],
        ],
    ))
    a("")
    a("### Test 3. Mark versus the book mid 60 minutes later")
    a("")
    a("Back-test markets are the July Fed decision (`KXFEDDECISION-26JUL-H25`), Texas governor (`GOVPARTYTX-26-R`), Brazil (`KXBRPRES-26-LULA`), and every block market in the Commodities category. Mean absolute error is in cents, unweighted across prints that have both a mark and a +60 mid.")
    a("")
    a("Design (b) does not include the book, and it does not include the print being scored. Design (c) is that median of earlier prints that were inside the book, and it uses the book when none exist. It is not a blend. A size-weighted blend of the book and the blocks is NOT AVAILABLE.")
    a("")

    def mae(df, col):
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            return None, 0
        return float(s.mean()), int(len(s))

    mark_rows = []
    groups = [("all back-test prints", marks)] + [(name, sub) for name, sub in marks.groupby("market_name")]
    for ticker, sub in marks.groupby("ticker"):
        title = sub.series_title.iloc[0]
        groups.append((f"{title} ({ticker})", sub))
    # The market_name group already pools commodity hubs; the ticker group lists them.
    # Drop the duplicate pooled commodity label's double count by keeping both: pooled name and each ticker.
    seen = set()
    table_rows = []
    for label, sub in [("all back-test prints", marks)] + [(f"{n}", s) for n, s in marks.groupby(marks.market_name)]:
        ea, na = mae(sub, "err_a")
        eb, nb = mae(sub, "err_b")
        ec, nc = mae(sub, "err_c")
        table_rows.append([label, na, _fmt(ea), nb, _fmt(eb), nc, _fmt(ec)])
    for ticker, sub in marks.groupby("ticker"):
        ea, na = mae(sub, "err_a")
        eb, nb = mae(sub, "err_b")
        ec, nc = mae(sub, "err_c")
        if na == 0 and nb == 0 and nc == 0:
            continue
        label = f"{sub.series_title.iloc[0]} | {ticker}".replace("|", "\\|")
        table_rows.append([label, na, _fmt(ea), nb, _fmt(eb), nc, _fmt(ec)])
    a(markdown_table(
        ["slice", "n (a)", "MAE book ¢", "n (b)", "MAE earlier-blocks median ¢", "n (c)", "MAE inside-prints or book ¢"],
        table_rows,
    ))
    a("")
    a("### Test 4. Sample")
    a("")
    a(markdown_table(
        ["fact", "value"],
        [
            ["blocks", len(blocks)],
            ["markets", int(blocks.ticker.nunique())],
            ["first block (UTC)", str(first)],
            ["last block (UTC)", str(last)],
            ["notional, contracts × $1", f"${blocks.notional_usd.sum():,.2f}"],
            ["dollars paid, taker's price × contracts", f"${blocks.paid_taker.sum():,.2f}"],
            ["dollars paid, cheaper side × contracts (the column the rest of this repo calls premium_usd)", f"${blocks.paid_cheap_side.sum():,.2f}"],
            ["before 19 Aug 2026", n_before],
            ["on or after 19 Aug 2026", n_after],
            [f"equal window before 19 Aug ({before_lo.date()} to {CANTOR.date()}, open at the end)", n_before_eq],
            [f"equal window from 19 Aug through the last print ({CANTOR.date()} to {last.date()})", n_after_eq],
            ["sports prints", int(blocks.is_sports.sum())],
            ["sports minimum contracts observed", f"{blocks.loc[blocks.is_sports, 'count_fp'].min():,.2f}"],
            ["non-sports minimum contracts observed", f"{blocks.loc[~blocks.is_sports, 'count_fp'].min():,.2f}"],
            ["sports prints under 50,000 contracts", int(((blocks.is_sports) & (blocks.count_fp < 50_000)).sum())],
        ],
    ))
    a("")
    a("Blocks by month:")
    a("")
    a(markdown_table(["month", "n"], [(m, int(n)) for m, n in months.items()]))
    a("")
    a("By category, sports included. Dollars paid use the taker's price.")
    a("")
    a(markdown_table(["category", "n", "notional $", "taker paid $", "smallest print, contracts"], cat_table(blocks, "all")))
    a("")
    nonsports = blocks[~blocks.is_sports]
    a("By category, sports removed.")
    a("")
    a(markdown_table(["category", "n", "notional $", "taker paid $", "smallest print, contracts"], cat_table(nonsports, "ns")))
    a("")
    unquoted = paths[paths.no_usable_quote]
    a(f"No usable quote at the print (no bid/ask, crossed, or spread ≥ 50¢): {len(unquoted)} of {len(paths)}.")
    a("")
    if len(unquoted):
        a(markdown_table(
            ["ticker", "category", "time UTC", "bid", "ask", "YES price"],
            [[r.ticker, r.category, r.created_time, r.screen_bid, r.screen_ask, r.yes_price] for r in unquoted.itertuples(index=False)],
        ))
    a("")
    a("### July Fed meeting, recomputed")
    a("")
    fed = paths[paths.ticker.eq("KXFEDDECISION-26JUL-H25")].sort_values("ts")
    if fed.empty:
        a("NOT AVAILABLE: no July Fed block in the tape.")
    else:
        a(markdown_table(
            ["time UTC", "contracts", "YES price", "pre bid/ask (last usable minute)", "pre mid", "pre source",
             "screen at print", "+1 bid/ask", "+15 bid/ask", "+60 bid/ask", "retained +60"],
            [[
                r.created_time, f"{r.count_fp:,.0f}", f"{r.yes_price:.2f}",
                f"{r.pre_last_bid:.4f}/{r.pre_last_ask:.4f}" if pd.notna(r.pre_last_bid) else "NOT AVAILABLE",
                _fmt(r.pre_mid, 4), r.pre_source,
                f"{r.screen_bid}/{r.screen_ask}",
                f"{r.bid_1}/{r.ask_1}", f"{r.bid_15}/{r.ask_15}", f"{r.bid_60}/{r.ask_60}",
                _fmt(None if pd.isna(r.retained_60) else r.retained_60 * 100),
            ] for r in fed.itertuples(index=False)],
        ))
    a("")
    return "\n".join(lines), {
        "n_before_eq": n_before_eq, "n_after_eq": n_after_eq,
        "n_before": n_before, "n_after": n_after,
        "before_lo": str(before_lo), "duration_days": duration.total_seconds() / 86400,
        "base_med": base_med, "base_n": int(len(base_usable)), "base_attempts": attempts,
        "unquoted_n": int(len(unquoted)),
    }


def sentences(paths, base, proxy, marks, meta) -> str:
    c = _counts(paths)
    outside = paths[paths.book_cross.isin(["through_offer", "through_bid"])]
    co = _counts(outside)
    inside = _counts(paths[paths.book_cross.eq("inside")])
    wide = _counts(paths[(paths.yes_price - paths.pre_mid).abs() >= 0.01])
    base_med = meta["base_med"]
    block_move = c["med_abs_move_60_c"]

    def pct(part, whole):
        if not whole:
            return "NOT AVAILABLE"
        return f"{part} of {whole} ({100 * part / whole:.0f}%)"

    s1 = (
        f"At 60 minutes, {pct(c['reverted'], c['n_class'])} classified prints had reverted, "
        f"{c['partial']} were partial, and {c['persistent']} were persistent. "
        f"The median retained fraction was {_fmt(None if c['med_ret_1'] is None else c['med_ret_1']*100)}% at +1 min, "
        f"{_fmt(None if c['med_ret_15'] is None else c['med_ret_15']*100)}% at +15, and "
        f"{_fmt(None if c['med_ret_60'] is None else c['med_ret_60']*100)}% at +60. "
        f"Prints outside the bid-ask were {pct(co['reverted'], co['n_class'])} reverted at +60; "
        f"prints inside were {pct(inside['reverted'], inside['n_class'])} reverted."
    )
    conf1 = (
        f"The class counts use {c['n_class']} prints with a pre mid, a +60 mid, and a non-zero gap, out of {c['n']} blocks. "
        f"The median absolute book move at +60 is {_fmt(block_move)}¢ on the blocks and {_fmt(base_med)}¢ on {meta['base_n']} random minutes in the same markets."
    )
    wrong1 = (
        "A print can look reverted because the 30-minute median mid is not the mid at the handshake, because the public time is up to 15 minutes after the trade, or because a one-cent gap makes the ratio swing on a one-tick book move. "
        f"Restricted to gaps of at least 1¢, the +60 classes are {wide['reverted']} reverted, {wide['partial']} partial, {wide['persistent']} persistent, on {wide['n_class']} prints."
    )

    comp = proxy[proxy.cheaper.notna()]
    n_cheap = int((comp.cheaper == True).sum()) if len(comp) else 0
    n_dear = int((comp.cheaper == False).sum()) if len(comp) else 0
    s2 = (
        f"Of {len(comp)} blocks with a proxy slippage, {n_cheap} had a smaller |price − pre mid| than the 7 Nov curve and {n_dear} had a larger one. "
        f"{int(proxy.cheaper.isna().sum())} blocks have no comparison."
    )
    same_n = int((proxy.match == "same_ticker").sum())
    same_ok = int(((proxy.match == "same_ticker") & proxy.cheaper.notna()).sum())
    conf2 = (
        f"The proxy covers {len(comp)} of {len(proxy)} blocks. "
        f"Same-ticker snapshot rows: {same_n}, of which {same_ok} fully fill the size bin. "
        f"Category-median comparisons: {int((proxy.match=='category_median').sum())}."
    )
    wrong2 = (
        "The curve is one afternoon, 7 Nov 2026, not the book these trades actually lifted, and the size bin is the next published size up rather than the block's own size. "
        "A block can look cheap against a thin November book or expensive against a deep one that did not exist on the trade date."
    )

    def mae(col):
        s = pd.to_numeric(marks[col], errors="coerce").dropna()
        if s.empty:
            return None, 0
        return float(s.mean()), int(len(s))

    ea, na = mae("err_a")
    eb, nb = mae("err_b")
    ec, nc = mae("err_c")
    scored = {"book only": ea, "earlier-blocks median": eb, "inside-prints or book": ec}
    finite = {k: v for k, v in scored.items() if v is not None}
    if finite:
        winner = min(finite, key=finite.get)
        short = (
            f"The closest point estimate on the pooled back-test is {winner} at {_fmt(finite[winner])}¢ MAE. "
            f"Book only is {_fmt(ea)}¢ (n={na}), the earlier-blocks median is {_fmt(eb)}¢ (n={nb}), and inside-prints-or-book is {_fmt(ec)}¢ (n={nc})."
        )
        paired = marks[pd.to_numeric(marks["err_b"], errors="coerce").notna()]
        n_tx = int((paired.market_name == "Texas governor").sum()) if len(paired) else 0
        book_paired = float(pd.to_numeric(paired.err_a).mean()) if len(paired) else None
        blocks_paired = float(pd.to_numeric(paired.err_b).mean()) if len(paired) else None
        s3 = (
            f"The closest point estimate on the pooled back-test is {winner} at {_fmt(finite[winner])}¢ MAE. "
            f"Book only is {_fmt(ea)}¢ (n={na}). "
            f"The earlier-blocks median, which leaves out the print being scored, is {_fmt(eb)}¢ (n={nb}). "
            f"Inside-prints-or-book is {_fmt(ec)}¢ (n={nc}). "
            f"On the {nb} prints that have an earlier block, the book is {_fmt(book_paired)}¢ and the earlier-blocks median is {_fmt(blocks_paired)}¢. "
            f"{_word(n_tx).capitalize()} of those {_word(nb)} are the Texas governor market."
        )
    else:
        short = s3 = "NOT AVAILABLE: none of the three marks had a +60 mid to score."
    conf3 = ""
    wrong3 = (
        "Design (b) ignores the book, and design (c) uses the book when no earlier print was inside the quote. "
        "Sixty minutes is a short horizon, and several of these prints are the same event a minute apart, so the errors are not independent."
    )

    # Bottom line uses the class share and the MAE winner only.
    mostly = "NOT AVAILABLE"
    if c["n_class"]:
        if c["reverted"] > c["persistent"] + c["partial"]:
            mostly = "On this tape the gap mostly does not stay in the book: more prints revert than persist or partially stick."
        elif c["persistent"] > c["reverted"]:
            mostly = "On this tape more of the classified gap is still in the book an hour later than has reverted."
        else:
            mostly = "On this tape the hour-later book does not line up cleanly as either a revert or a persist."
    bullets = [
        f"{mostly} Classified at +60: {c['reverted']} reverted, {c['partial']} partial, {c['persistent']} persistent, out of {c['n_class']}.",
        f"Median retained fraction at +60 is {_fmt(None if c['med_ret_60'] is None else c['med_ret_60']*100)}%. Median |book move| is {_fmt(block_move)}¢ after a block and {_fmt(base_med)}¢ at {meta['base_n']} random times.",
        short,
        f"Against the 7 Nov curve, {n_cheap} comparable blocks were inside that curve's slippage and {n_dear} were outside it. This is not the cost of walking the book at the time of the trade.",
        "A mark that weights the book and the blocks together by size is NOT AVAILABLE: the historical book depth was not stored.",
    ]
    text = []
    text.append("## 3. Three sentences each")
    text.append("")
    text.append("**Test 1.** " + s1 + " " + conf1 + " " + wrong1)
    text.append("")
    text.append("**Test 2.** " + s2 + " " + conf2 + " " + wrong2)
    text.append("")
    text.append("**Test 3.** " + " ".join(p for p in (s3, conf3, wrong3) if p))
    text.append("")
    text.append("**Test 4.** The tape has "
                f"{c['n']} blocks. Dollars paid at the taker's price are not the same object as contracts times the cheaper side; both are in the table. "
                f"The equal-length windows are {meta['duration_days']:.1f} days. The before window opens on {meta['before_lo'][:10]}, after the scan has already started and before the first block, so it contains the same {meta['n_before_eq']} prints as the raw pre-19-Aug count, against {meta['n_after_eq']} from 19 Aug through the last print. "
                "Sports prints are in the category table. The smallest sports print in the tape is 40,000 contracts, and 2 sports prints are under 50,000, so this tape does not confirm a 50,000-contract sports minimum.")
    text.append("")
    text.append("## 4. Bottom line")
    text.append("")
    for b in bullets:
        text.append(f"- {b}")
    text.append("")
    text.append("## 5. Files")
    text.append("")
    text.append("- `src/07_block_diagnostics.py` — this script.")
    text.append("- `data/processed/block_paths.csv` — one row per block, mids, retained fractions, class.")
    text.append("- `data/processed/baseline_moves.csv` — the random-minute control.")
    text.append("- `data/processed/slippage_proxy.csv` — Test 2.")
    text.append("- `data/processed/mark_scores.csv` — Test 3.")
    text.append("- `data/processed/report.md` — this report.")
    text.append("- `data/cache/` — candlestick and VWAP responses, so a rerun does not refetch. Not committed.")
    text.append("")
    text.append("Rerun from inside `kalshi-cost-of-size`:")
    text.append("")
    text.append("```")
    text.append("python src/07_block_diagnostics.py")
    text.append("```")
    text.append("")
    return "\n".join(text)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = attach_categories(load_blocks())
    for col in ("yes_price_dollars", "no_price_dollars", "count_fp"):
        blocks[col] = pd.to_numeric(blocks[col], errors="coerce")
    block_ids = set(blocks.trade_id)
    print(f"{len(blocks)} blocks", file=sys.stderr)
    rows = []
    for i, b in blocks.iterrows():
        try:
            rows.append(block_window(b, block_ids))
        except Exception as e:
            rows.append({"trade_id": b.trade_id, "ticker": b.ticker, "error": str(e)[:300],
                         "created_time": str(b.created_time), "category": b.category,
                         "yes_price": f(b.yes_price_dollars), "count_fp": f(b.count_fp),
                         "pre_mid": None, "mid_60": None, "class_60": None, "no_usable_quote": True,
                         "book_cross": "no_usable_book", "outside_15m": "unknown"})
        print(f"  block {len(rows)}/{len(blocks)} {b.ticker}", file=sys.stderr)
    paths = pd.DataFrame(rows)
    paths.to_csv(OUT / "block_paths.csv", index=False)

    print("baseline", file=sys.stderr)
    base = baseline_moves(blocks, block_ids)
    base.to_csv(OUT / "baseline_moves.csv", index=False)

    proxy, proxy_info = slippage_proxy(blocks, paths)
    proxy.to_csv(OUT / "slippage_proxy.csv", index=False)

    marks = marks_for(paths)
    marks.to_csv(OUT / "mark_scores.csv", index=False)

    body, meta = build_report(paths, base, proxy, proxy_info, marks, blocks)
    report = body + "\n" + sentences(paths, base, proxy, marks, meta)
    (OUT / "report.md").write_text(report)
    print(OUT / "report.md", file=sys.stderr)


if __name__ == "__main__":
    main()
