"""Pyth Pro symbology: which funding-rate and interest-rate feeds Pyth publishes today.

Source: GET https://pyth.dourolabs.app/v1/symbols?asset_type=<type>   (public, no key)
Docs:   https://docs.pyth.network/pro/symbology-reference
        asset_type `funding-rate` = "Funding rates of perpetual futures on exchanges such as Binance and Deribit";
        `interest-rate` = "Benchmark interest rates such as SOFR, and US Treasury prices and yields".

Writes data/raw/pyth/symbols_<type>.json and data/processed/a5_pyth_feeds.csv
Rerun: python src/13_fetch_pyth_catalog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json

import pandas as pd

from common import PROCESSED, RAW, get

OUT = RAW / "pyth"
OUT.mkdir(exist_ok=True)
TYPES = ["funding-rate", "interest-rate", "rates", "crypto", "equity"]


def main() -> None:
    rows = []
    for t in TYPES:
        try:
            d = get("https://pyth.dourolabs.app/v1/symbols", {"asset_type": t})
        except Exception as e:  # noqa: BLE001
            print(t, "error", e)
            continue
        (OUT / f"symbols_{t}.json").write_text(json.dumps(d))
        if t in ("crypto", "equity"):
            print(t, "feeds:", len(d), {s: sum(1 for x in d if x.get("state") == s) for s in set(x.get("state") for x in d)})
            continue
        for x in d:
            rows.append({"asset_type": t, "symbol": x.get("symbol"), "state": x.get("state"), "instrument_type": x.get("instrument_type"),
                         "interval": x.get("interval"), "min_publishers": x.get("min_publishers"), "min_channel": x.get("min_channel"),
                         "description": x.get("description"), "price_feed_id": x.get("price_feed_id")})
    df = pd.DataFrame(rows)
    df.to_csv(PROCESSED / "a5_pyth_feeds.csv", index=False)
    print(df[df.asset_type == "funding-rate"].to_string())
    ir = df[df.asset_type == "interest-rate"]
    print("interest-rate feeds:", len(ir), ir.state.value_counts().to_dict())
    print(ir[ir.state == "stable"].symbol.tolist())


if __name__ == "__main__":
    main()
