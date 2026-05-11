"""Kronos model loading and probabilistic OHLCV forecasting."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KRONOS_REPO_URL = "https://github.com/shiyu-coder/Kronos.git"
KRONOS_DIR_NAME = "Kronos"
TOKENIZER_REPO = "NeoQuasar/Kronos-Tokenizer-base"
MODEL_REPO = "NeoQuasar/Kronos-small"

PROJECT_ROOT = Path(__file__).resolve().parent
KRONOS_PATH = PROJECT_ROOT / KRONOS_DIR_NAME


class ForecastError(Exception):
    """Raised on prediction failures."""


def ensure_kronos_repo() -> Path:
    """Clone the Kronos repo into the project directory if missing."""
    if KRONOS_PATH.exists() and (KRONOS_PATH / "model").exists():
        return KRONOS_PATH
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", KRONOS_REPO_URL, str(KRONOS_PATH)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ForecastError(
            f"Failed to clone Kronos repo: {exc.stderr or exc.stdout}"
        ) from exc
    return KRONOS_PATH


def _register_kronos_path() -> None:
    """Add Kronos repo to sys.path so `from model import ...` works."""
    ensure_kronos_repo()
    kronos_str = str(KRONOS_PATH)
    if kronos_str not in sys.path:
        sys.path.insert(0, kronos_str)


def load_predictor(device: str = "cpu", max_context: int = 512):
    """Load tokenizer + model from HuggingFace and return a KronosPredictor."""
    _register_kronos_path()
    # Imported only after sys.path is updated.
    from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore

    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_REPO)
    model = Kronos.from_pretrained(MODEL_REPO)
    predictor = KronosPredictor(
        model=model,
        tokenizer=tokenizer,
        device=device,
        max_context=max_context,
    )
    return predictor


def _prepare_context(df: pd.DataFrame, max_context: int = 400) -> pd.DataFrame:
    """Trim and validate the input OHLCV DataFrame for Kronos."""
    needed = ["open", "high", "low", "close"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ForecastError(f"Input data missing columns: {missing}")

    if "volume" not in df.columns:
        df = df.copy()
        df["volume"] = 0.0
    if "amount" not in df.columns:
        df = df.copy()
        df["amount"] = df["close"] * df["volume"]

    df = df.dropna(subset=needed)
    if len(df) < 50:
        raise ForecastError(
            f"Not enough history to forecast (got {len(df)} candles, need ≥ 50)"
        )

    if len(df) > max_context:
        df = df.iloc[-max_context:]
    return df


def _single_path(
    predictor,
    context_df: pd.DataFrame,
    x_timestamp: pd.Series,
    y_timestamp: pd.Series,
    pred_len: int,
    temperature: float,
    top_p: float,
) -> pd.DataFrame:
    """Run one independent Kronos forecast path."""
    pred = predictor.predict(
        df=context_df[["open", "high", "low", "close", "volume", "amount"]],
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=temperature,
        top_p=top_p,
        sample_count=1,
        verbose=False,
    )
    return pred


def monte_carlo_forecast(
    predictor,
    df: pd.DataFrame,
    future_timestamps: pd.DatetimeIndex,
    n_paths: int = 20,
    pred_len: int = 24,
    temperature: float = 1.0,
    top_p: float = 0.9,
    max_context: int = 400,
    progress_callback=None,
) -> dict:
    """Run N independent Kronos forecasts and aggregate them.

    Returns a dict with:
      - paths: list of DataFrames (one per Monte Carlo sample)
      - mean: DataFrame of per-step mean OHLC
      - lower/upper: DataFrames of 10th/90th percentile bands on close price
      - timestamps: pd.DatetimeIndex of future steps
    """
    context = _prepare_context(df, max_context=max_context)

    # Build timestamp series Kronos expects.
    x_ts = pd.Series(context.index)
    y_ts = pd.Series(future_timestamps)

    paths: list[pd.DataFrame] = []
    errors: list[str] = []
    for i in range(n_paths):
        try:
            pred = _single_path(
                predictor=predictor,
                context_df=context,
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=pred_len,
                temperature=temperature,
                top_p=top_p,
            )
            pred.index = future_timestamps
            paths.append(pred)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        if progress_callback is not None:
            progress_callback(i + 1, n_paths)

    if not paths:
        raise ForecastError(
            "All Kronos sampling runs failed. Last error: "
            + (errors[-1] if errors else "unknown")
        )

    closes = np.stack([p["close"].to_numpy() for p in paths], axis=0)
    opens = np.stack([p["open"].to_numpy() for p in paths], axis=0)
    highs = np.stack([p["high"].to_numpy() for p in paths], axis=0)
    lows = np.stack([p["low"].to_numpy() for p in paths], axis=0)

    mean_df = pd.DataFrame(
        {
            "open": opens.mean(axis=0),
            "high": highs.mean(axis=0),
            "low": lows.mean(axis=0),
            "close": closes.mean(axis=0),
        },
        index=future_timestamps,
    )

    close_lower = np.percentile(closes, 10, axis=0)
    close_upper = np.percentile(closes, 90, axis=0)
    band = pd.DataFrame(
        {"lower": close_lower, "upper": close_upper},
        index=future_timestamps,
    )

    return {
        "paths": paths,
        "mean": mean_df,
        "band": band,
        "timestamps": future_timestamps,
        "errors": errors,
    }


def summarize_forecast(history_df: pd.DataFrame, forecast: dict) -> dict:
    """Compute headline metrics for the UI."""
    current_price = float(history_df["close"].iloc[-1])
    final_price = float(forecast["mean"]["close"].iloc[-1])
    change_pct = (final_price - current_price) / current_price * 100.0
    direction = "up" if final_price >= current_price else "down"

    # Confidence: how consistent the Monte Carlo paths agree on direction.
    paths_final = np.array([float(p["close"].iloc[-1]) for p in forecast["paths"]])
    if direction == "up":
        agreement = (paths_final >= current_price).mean()
    else:
        agreement = (paths_final < current_price).mean()
    confidence = float(agreement) * 100.0

    # Volatility outlook: average forecasted intra-candle range relative to price.
    mean_df = forecast["mean"]
    avg_range = float((mean_df["high"] - mean_df["low"]).mean())
    volatility = avg_range / current_price * 100.0

    if volatility < 1.0:
        vol_label = "Low"
    elif volatility < 3.0:
        vol_label = "Moderate"
    else:
        vol_label = "High"

    return {
        "current_price": current_price,
        "forecast_price": final_price,
        "change_pct": change_pct,
        "direction": direction,
        "confidence_pct": confidence,
        "volatility_pct": volatility,
        "volatility_label": vol_label,
    }
