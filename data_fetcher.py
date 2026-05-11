"""OHLCV data fetching for crypto (Binance) and stocks (yfinance)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone  #type: ignore

import pandas as pd #type: ignore
import requests #type: ignore
import yfinance as yf #type: ignore

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_MAX_LIMIT = 1000

CRYPTO_PATTERN = re.compile(r"^[A-Z0-9]{2,15}/[A-Z0-9]{2,10}$")

INTERVAL_TIMEDELTA = {
    "1m": pd.Timedelta("1m"),
    "5m": pd.Timedelta("5m"),
    "15m": pd.Timedelta("15m"),
    "1h": pd.Timedelta("1h"),
    "4h": pd.Timedelta("4h"),
    "1d": pd.Timedelta("1d"),
}


class DataFetchError(Exception):
    """Raised when OHLCV data cannot be retrieved."""


class TickerNotFoundError(DataFetchError):
    """Raised when the ticker symbol does not exist on the data source."""


def detect_asset_type(ticker: str) -> str:
    """Return 'crypto' if the ticker looks like a Binance pair, else 'stock'."""
    ticker = ticker.strip().upper()
    if CRYPTO_PATTERN.match(ticker):
        return "crypto"
    return "stock"


def _normalize_crypto_symbol(ticker: str) -> str:
    """Convert 'BTC/USDT' -> 'BTCUSDT' for Binance."""
    return ticker.strip().upper().replace("/", "").replace("-", "")


def fetch_binance_ohlcv(ticker: str, limit: int = 500, interval: str = "1h") -> pd.DataFrame:
    """Fetch OHLCV from Binance public API. Returns DataFrame indexed by timestamp.

    The currently forming candle (close_time in the future) is dropped so the
    series only contains fully closed candles — essential for correct forecasting.
    """
    symbol = _normalize_crypto_symbol(ticker)
    # Request one extra so we still have `limit` candles after dropping the open one.
    request_limit = min(limit + 1, BINANCE_MAX_LIMIT)
    params = {"symbol": symbol, "interval": interval, "limit": request_limit}
    try:
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
    except requests.RequestException as exc:
        raise DataFetchError(f"Binance request failed: {exc}") from exc

    if resp.status_code == 400:
        raise TickerNotFoundError(ticker)
    if not resp.ok:
        raise DataFetchError(f"Binance API error {resp.status_code}: {resp.text[:200]}")

    rows = resp.json()
    if not rows:
        raise TickerNotFoundError(ticker)

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_dt"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = df[col].astype(float)
    df["amount"] = df["quote_volume"]

    # Drop the currently forming candle: any row whose close_time is in the future.
    now = pd.Timestamp.utcnow()
    df = df[df["close_dt"] <= now]

    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume", "amount"]]
    df.index.name = "timestamp"

    if df.empty:
        raise DataFetchError(f"No closed candles available for {ticker} on Binance")

    if len(df) > limit:
        df = df.iloc[-limit:]
    return df


def _yf_session():
    """Browser-impersonating session that bypasses Yahoo's bot blocks.

    Yahoo Finance returns HTML (causing 'Expecting value: line 1 column 1' JSON
    errors) when called with plain Python requests. curl_cffi sends real Chrome
    TLS fingerprints, which yfinance happily uses if we pass the session in.
    """
    try:
        from curl_cffi import requests as cffi_requests
        return cffi_requests.Session(impersonate="chrome")
    except Exception:  # noqa: BLE001
        return None


def fetch_yfinance_ohlcv(ticker: str, limit: int = 500, interval: str = "1h") -> pd.DataFrame:
    """Fetch OHLCV from yfinance. 1h data is limited to ~730 days history."""
    ticker = ticker.strip().upper()
    # 1h interval requires period <= 730d. Use period long enough to cover `limit` trading hours.
    # Trading hours ~6.5/day → request generous window then trim to `limit`.
    days_needed = max(int(limit / 6 * 1.6), 30)
    days_needed = min(days_needed, 720)
    period = f"{days_needed}d"

    session = _yf_session()
    try:
        ticker_obj = yf.Ticker(ticker, session=session) if session is not None else yf.Ticker(ticker)
        df = ticker_obj.history(
            period=period,
            interval=interval,
            auto_adjust=False,
            prepost=False,   # exclude pre/post-market — those candles have unreliable prints
            actions=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise DataFetchError(f"yfinance request failed: {exc}") from exc

    if df is None or df.empty:
        raise TickerNotFoundError(ticker)

    # Flatten multi-index columns if present (newer yfinance versions).
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df = df.rename(
        columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }
    )
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        raise DataFetchError(f"yfinance returned unexpected columns: {list(df.columns)}")

    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df["amount"] = df["close"] * df["volume"]

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "timestamp"

    # Drop the currently forming candle: timestamp is the candle's open time,
    # so anything with open_time + interval > now is still in progress.
    step = INTERVAL_TIMEDELTA.get(interval, pd.Timedelta("1h"))
    now = pd.Timestamp.utcnow()
    df = df[df.index + step <= now]

    if df.empty:
        raise DataFetchError(f"No closed candles available for {ticker}")

    if len(df) > limit:
        df = df.iloc[-limit:]
    return df


def fetch_ohlcv(ticker: str, limit: int = 500) -> tuple[pd.DataFrame, str]:
    """Fetch OHLCV based on auto-detected asset type. Returns (df, asset_type)."""
    asset_type = detect_asset_type(ticker)
    if asset_type == "crypto":
        df = fetch_binance_ohlcv(ticker, limit=limit, interval="1h")
    else:
        df = fetch_yfinance_ohlcv(ticker, limit=limit, interval="1h")
    return df, asset_type


def next_timestamps(last_ts: pd.Timestamp, n: int, freq: str = "1h") -> pd.DatetimeIndex:
    """Generate `n` future timestamps starting one step after `last_ts`."""
    if last_ts.tzinfo is None:
        last_ts = last_ts.tz_localize("UTC")
    start = last_ts + pd.Timedelta(freq)
    return pd.date_range(start=start, periods=n, freq=freq)
