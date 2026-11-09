"""Step 1: collect every block trade (is_block_trade=true) on Kalshi's public tape.

Kalshi's server aborts any trades scan that takes >10s, so a single
`is_block_trade=true` query over the full tape 504s. We walk backwards in
small time windows and shrink the window on timeout.

Output: data/raw/block_trades.csv
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kalshi  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "block_trades.csv"
FIELDS = ["trade_id", "ticker", "created_time", "count_fp", "yes_price_dollars", "no_price_dollars",
          "taker_outcome_side", "taker_book_side", "is_block_trade", "source"]


def scan(start_ts: int, end_ts: int, historical: bool, window_s: int = 12 * 3600, min_window_s: int = 3600):
    """Yield block trades in [start_ts, end_ts], walking backward from end_ts."""
    hi = end_ts
    window = window_s
    while hi > start_ts:
        lo = max(start_ts, hi - window)
        try:
            batch = list(kalshi.trades(min_ts=lo, max_ts=hi, is_block_trade=True, historical=historical, retries=2))
        except RuntimeError as e:
            if window > min_window_s:
                window = max(min_window_s, window // 2)
                print(f"  timeout on {lo}->{hi}; shrinking window to {window}s", file=sys.stderr)
                continue
            print(f"  giving up on {lo}->{hi}: {e}", file=sys.stderr)
            batch = []
        for t in batch:
            t["source"] = "historical" if historical else "live"
            yield t
        print(f"  {datetime.fromtimestamp(lo, timezone.utc):%Y-%m-%d %H:%M} -> "
              f"{datetime.fromtimestamp(hi, timezone.utc):%Y-%m-%d %H:%M}  {len(batch):4d} blocks "
              f"({'hist' if historical else 'live'})", file=sys.stderr)
        hi = lo
        # grow the window back slowly after a shrink
        if window < window_s:
            window = min(window_s, window * 2)
        time.sleep(0.2)


def main(days_back: int = 120, mode: str = "both", range_start: str | None = None, range_end: str | None = None):
    """mode: 'live' (cutoff -> now), 'historical' (now-days_back -> cutoff), or 'both'.
    Live and historical can be run as two parallel processes; outputs are suffixed by mode.
    For 'historical', an explicit YYYY-MM-DD range_start/range_end overrides days_back so
    several date ranges can be scanned in parallel."""
    cutoff = kalshi.get("/historical/cutoff")
    trades_cutoff = int(datetime.fromisoformat(cutoff["trades_created_ts"].replace("Z", "+00:00")).timestamp())
    now = int(time.time())
    start = now - days_back * 86400
    print(f"live tape from {cutoff['trades_created_ts']}; scanning back {days_back} days ({mode})", file=sys.stderr)

    jobs = []
    s = e = None
    if range_start:
        s = int(datetime.fromisoformat(range_start).replace(tzinfo=timezone.utc).timestamp())
        e = int(datetime.fromisoformat(range_end).replace(tzinfo=timezone.utc).timestamp()) if range_end else now
    if mode in ("live", "both"):
        jobs.append((max(s, trades_cutoff) if s else trades_cutoff, min(e, now) if e else now, False))
    if mode in ("historical", "both"):
        if s:
            jobs.append((s, min(e, trades_cutoff), True))
        else:
            jobs.append((start, trades_cutoff, True))

    suffix = mode if not range_start else f"{mode}_{range_start}_{range_end or 'cutoff'}"
    out = OUT if mode == "both" else OUT.with_name(f"block_trades_{suffix}.csv")
    seen: set[str] = set()
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for lo, hi, hist in jobs:
            for t in scan(lo, hi, historical=hist):
                if t["trade_id"] in seen:
                    continue
                seen.add(t["trade_id"])
                w.writerow(t)
                n += 1
                f.flush()
    print(f"wrote {n} block trades -> {out}", file=sys.stderr)


if __name__ == "__main__":
    # usage: 01_scan_block_trades.py [days_back] [live|historical|both] [range_start] [range_end]
    a = sys.argv[1:]
    main(int(a[0]) if len(a) > 0 else 120, a[1] if len(a) > 1 else "both",
         a[2] if len(a) > 2 else None, a[3] if len(a) > 3 else None)
