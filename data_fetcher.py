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


class DataFetchError(Exception):
    """Raised when OHLCV data cannot be retrieved."""


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
    """Fetch OHLCV from Binance public API. Returns DataFrame indexed by timestamp."""
    symbol = _normalize_crypto_symbol(ticker)
    params = {"symbol": symbol, "interval": interval, "limit": min(limit, BINANCE_MAX_LIMIT)}
    try:
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
    except requests.RequestException as exc:
        raise DataFetchError(f"Binance request failed: {exc}") from exc

    if resp.status_code == 400:
        raise DataFetchError(f"Invalid Binance symbol: {ticker}")
    if not resp.ok:
        raise DataFetchError(f"Binance API error {resp.status_code}: {resp.text[:200]}")

    rows = resp.json()
    if not rows:
        raise DataFetchError(f"No data returned for {ticker} on Binance")

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = df[col].astype(float)
    df["amount"] = df["quote_volume"]
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume", "amount"]]
    return df


def fetch_yfinance_ohlcv(ticker: str, limit: int = 500, interval: str = "1h") -> pd.DataFrame:
    """Fetch OHLCV from yfinance. 1h data is limited to ~730 days history."""
    ticker = ticker.strip().upper()
    # 1h interval requires period <= 730d. Use period long enough to cover `limit` trading hours.
    # Trading hours ~6.5/day → request generous window then trim to `limit`.
    days_needed = max(int(limit / 6 * 1.6), 30)
    days_needed = min(days_needed, 720)
    period = f"{days_needed}d"

    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise DataFetchError(f"yfinance request failed: {exc}") from exc

    if df is None or df.empty:
        raise DataFetchError(f"No data returned for {ticker} on yfinance")

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

    if len(df) > limit:
        df = df.iloc[-limit:]

    if df.empty:
        raise DataFetchError(f"No usable rows for {ticker}")
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
