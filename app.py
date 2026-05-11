"""Streamlit app: Kronos AI candlestick forecasting for crypto and stocks."""

from __future__ import annotations

import time
import uuid

import pandas as pd
import streamlit as st

from chart import build_forecast_chart
from data_fetcher import (
    DataFetchError,
    TickerNotFoundError,
    fetch_ohlcv,
    next_timestamps,
)
from forecaster import (
    ForecastError,
    ensure_kronos_repo,
    load_predictor,
    monte_carlo_forecast,
    summarize_forecast,
)
from rate_limiter import DEFAULT_LIMIT, check_limit, increment, remaining

PAGE_TITLE = "Kronos AI — Candlestick Forecast"
HISTORY_CANDLES = 500
FORECAST_CANDLES = 24
MONTE_CARLO_PATHS = 20

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
      .main .block-container {max-width: 1100px; padding-top: 2rem; padding-bottom: 2rem;}
      .stButton > button {
          background: linear-gradient(90deg, #f97316, #ea580c);
          color: white; border: none; border-radius: 10px;
          padding: 0.55rem 1.4rem; font-weight: 600; font-size: 1rem;
      }
      .stButton > button:hover {filter: brightness(1.08);}
      .metric-card {
          background: #ffffff; border: 1px solid #e5e7eb;
          border-radius: 12px; padding: 1rem 1.1rem;
          box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }
      .metric-label {font-size: 0.78rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em;}
      .metric-value {font-size: 1.45rem; font-weight: 700; color: #111827; margin-top: 0.25rem;}
      .metric-sub {font-size: 0.85rem; margin-top: 0.15rem;}
      .up {color: #16a34a;}
      .down {color: #dc2626;}
      @media (max-width: 700px) {
        .metric-value {font-size: 1.15rem;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())
if "last_result" not in st.session_state:
    st.session_state.last_result = None


# ---------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading Kronos model (first run only)…")
def get_predictor():
    ensure_kronos_repo()
    return load_predictor(device="cpu", max_context=512)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("📈 Kronos AI — Candlestick Forecasting")
st.caption(
    "Enter a ticker (crypto pair like `BTC/USDT` or stock like `AAPL`) and get a "
    "24-hour AI-generated price forecast powered by the open-source Kronos model."
)

left, right = st.columns([3, 1])
with left:
    ticker = st.text_input(
        "Ticker",
        placeholder="e.g. BTC/USDT or AAPL",
        label_visibility="collapsed",
    )
with right:
    run = st.button("Generate Forecast", use_container_width=True)

used_today = DEFAULT_LIMIT - remaining(st.session_state.user_id)
st.caption(f"Free tier: **{used_today}/{DEFAULT_LIMIT}** forecasts used today.")

# ---------------------------------------------------------------------------
# Forecast flow
# ---------------------------------------------------------------------------

def run_forecast(ticker: str) -> None:
    ticker = ticker.strip().upper()
    if not ticker:
        st.warning("Please enter a ticker symbol.")
        return

    allowed, used = check_limit(st.session_state.user_id)
    if not allowed:
        st.error("You've reached your 5 free forecasts for today. Come back tomorrow!")
        return

    try:
        with st.status("Fetching market data…", expanded=False) as status:
            try:
                history, asset_type = fetch_ohlcv(ticker, limit=HISTORY_CANDLES)
            except TickerNotFoundError:
                status.update(label="Ticker not found", state="error")
                st.error(
                    f"**{ticker}** doesn't seem to exist. "
                    "Double-check the spelling and try a real symbol — "
                    "for example `BTC/USDT`, `ETH/USDT` for crypto, or `AAPL`, `TSLA` for stocks."
                )
                return
            except DataFetchError as exc:
                status.update(label="Data fetch failed", state="error")
                st.error(f"Could not fetch data for **{ticker}**: {exc}")
                return
            status.update(
                label=f"Fetched {len(history)} {asset_type} candles. Loading model…",
                state="running",
            )

            try:
                predictor = get_predictor()
            except Exception as exc:  # noqa: BLE001
                status.update(label="Model load failed", state="error")
                st.error(f"Could not load the Kronos model: {exc}")
                return

            status.update(label=f"Running {MONTE_CARLO_PATHS} Monte Carlo paths…", state="running")
            progress = st.progress(0.0, text="0 / {} paths".format(MONTE_CARLO_PATHS))

            def _cb(done: int, total: int) -> None:
                progress.progress(done / total, text=f"{done} / {total} paths")

            future_ts = next_timestamps(history.index[-1], n=FORECAST_CANDLES)

            try:
                forecast = monte_carlo_forecast(
                    predictor=predictor,
                    df=history,
                    future_timestamps=future_ts,
                    n_paths=MONTE_CARLO_PATHS,
                    pred_len=FORECAST_CANDLES,
                    progress_callback=_cb,
                )
            except ForecastError as exc:
                status.update(label="Forecast failed", state="error")
                st.error(f"Forecast failed: {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                status.update(label="Forecast failed", state="error")
                st.error(f"Unexpected forecast error: {exc}")
                return

            progress.empty()
            status.update(label="Forecast complete ✓", state="complete")

    finally:
        pass

    # Record usage only after a successful forecast.
    increment(st.session_state.user_id)

    summary = summarize_forecast(history, forecast)
    st.session_state.last_result = {
        "ticker": ticker,
        "asset_type": asset_type,
        "history": history,
        "forecast": forecast,
        "summary": summary,
    }


if run:
    run_forecast(ticker)


# ---------------------------------------------------------------------------
# Render last result (persists across reruns within the session)
# ---------------------------------------------------------------------------

result = st.session_state.last_result
if result is not None:
    history = result["history"]
    forecast = result["forecast"]
    summary = result["summary"]
    ticker_label = result["ticker"]
    asset_type = result["asset_type"]

    fig = build_forecast_chart(
        history=history,
        forecast_mean=forecast["mean"],
        band=forecast["band"],
        ticker=ticker_label,
        history_window=100,
    )
    st.plotly_chart(fig, use_container_width=True)

    direction = summary["direction"]
    arrow = "▲" if direction == "up" else "▼"
    arrow_class = "up" if direction == "up" else "down"
    change_pct = summary["change_pct"]
    fmt = "{:,.4f}" if summary["current_price"] < 10 else "{:,.2f}"

    col1, col2, col3, col4 = st.columns(4)

    def _card(col, label: str, value: str, sub: str = "", sub_class: str = ""):
        sub_html = f'<div class="metric-sub {sub_class}">{sub}</div>' if sub else ""
        col.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-label">{label}</div>
              <div class="metric-value">{value}</div>
              {sub_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    last_candle_ts = history.index[-1]
    age = pd.Timestamp.utcnow() - last_candle_ts
    if age < pd.Timedelta(minutes=90):
        freshness = "live"
    elif age < pd.Timedelta(hours=6):
        freshness = f"{int(age.total_seconds() // 60)} min ago"
    elif age < pd.Timedelta(days=2):
        freshness = f"{int(age.total_seconds() // 3600)} h ago"
    else:
        freshness = f"{age.days} d ago"

    _card(col1, "Current Price", fmt.format(summary["current_price"]),
          sub=f"{asset_type.capitalize()} · {ticker_label} · {freshness}")
    _card(
        col2,
        "Forecast (24h)",
        fmt.format(summary["forecast_price"]),
        sub=f"{arrow} {change_pct:+.2f}%",
        sub_class=arrow_class,
    )
    _card(
        col3,
        "Direction",
        f"{arrow} {direction.upper()}",
        sub=f"Confidence: {summary['confidence_pct']:.0f}%",
        sub_class=arrow_class,
    )
    _card(
        col4,
        "Volatility outlook",
        summary["volatility_label"],
        sub=f"Avg range ≈ {summary['volatility_pct']:.2f}% / candle",
    )

    if forecast.get("errors"):
        with st.expander(f"{len(forecast['errors'])} sampling path(s) failed"):
            for err in forecast["errors"][:5]:
                st.code(err)
else:
    st.info(
        "Try a crypto pair like `BTC/USDT`, `ETH/USDT`, `SOL/USDT` "
        "or a stock ticker like `AAPL`, `TSLA`, `NVDA`."
    )
