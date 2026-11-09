"""Thin client for Kalshi's public (unauthenticated) Trade API v2.

Only read-only market-data endpoints are used. No API key is required.
Docs: https://docs.kalshi.com/api-reference
"""
from __future__ import annotations

import time
from typing import Iterator

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
_session = requests.Session()
_session.headers["User-Agent"] = "kalshi-cost-of-size/0.1"


def get(path: str, params: dict | None = None, retries: int = 5, timeout: int = 30) -> dict:
    """GET with retry/backoff. Kalshi returns 504 'context_deadline_exceeded' for
    scans that take >10s server-side; the caller is responsible for narrowing
    the query window when that happens repeatedly."""
    url = f"{BASE}{path}"
    delay = 1.0
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code in (502, 503, 504):
                last_err = RuntimeError(f"{r.status_code} {r.text[:120]}")
                time.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"GET {path} {params} failed: {last_err}")


def paginate(path: str, params: dict, key: str, limit: int = 1000, max_pages: int | None = None,
             retries: int = 5) -> Iterator[dict]:
    params = dict(params, limit=limit)
    cursor = ""
    pages = 0
    while True:
        if cursor:
            params["cursor"] = cursor
        d = get(path, params, retries=retries)
        for item in d.get(key, []):
            yield item
        cursor = d.get("cursor") or ""
        pages += 1
        if not cursor or (max_pages and pages >= max_pages):
            return


# --- Convenience wrappers ---------------------------------------------------

def trades(ticker: str | None = None, min_ts: int | None = None, max_ts: int | None = None,
           is_block_trade: bool | None = None, historical: bool = False, **kw) -> Iterator[dict]:
    params: dict = {}
    if ticker:
        params["ticker"] = ticker
    if min_ts is not None:
        params["min_ts"] = int(min_ts)
    if max_ts is not None:
        params["max_ts"] = int(max_ts)
    if is_block_trade is not None:
        params["is_block_trade"] = "true" if is_block_trade else "false"
    path = "/historical/trades" if historical else "/markets/trades"
    yield from paginate(path, params, "trades", **kw)


def market(ticker: str) -> dict:
    return get(f"/markets/{ticker}")["market"]


def markets(**params) -> Iterator[dict]:
    yield from paginate("/markets", params, "markets")


def series(series_ticker: str) -> dict:
    return get(f"/series/{series_ticker}")["series"]


def orderbook(ticker: str, depth: int = 100) -> dict:
    return get(f"/markets/{ticker}/orderbook", {"depth": depth})["orderbook"]


def candlesticks(series_ticker: str, ticker: str, start_ts: int, end_ts: int, period_interval: int = 1) -> list[dict]:
    d = get(f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            {"start_ts": int(start_ts), "end_ts": int(end_ts), "period_interval": period_interval})
    return d["candlesticks"]


def series_ticker_of(market_ticker: str) -> str:
    """Kalshi market tickers are SERIES-EVENT-STRIKE; the series is the first segment."""
    return market_ticker.split("-")[0]
