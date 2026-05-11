"""Plotly candlestick chart with historical + forecast + uncertainty band."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

HISTORY_COLOR_UP = "#2563eb"   # blue
HISTORY_COLOR_DOWN = "#1e3a8a"
FORECAST_COLOR_UP = "#f97316"  # orange
FORECAST_COLOR_DOWN = "#9a3412"
BAND_COLOR = "rgba(249, 115, 22, 0.18)"
LINE_COLOR = "rgba(249, 115, 22, 0.55)"


def build_forecast_chart(
    history: pd.DataFrame,
    forecast_mean: pd.DataFrame,
    band: pd.DataFrame,
    ticker: str,
    history_window: int = 100,
) -> go.Figure:
    """Return a Plotly figure with the historical + forecast candlesticks and band."""
    hist = history.iloc[-history_window:]

    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=hist.index,
            open=hist["open"],
            high=hist["high"],
            low=hist["low"],
            close=hist["close"],
            name="History",
            increasing_line_color=HISTORY_COLOR_UP,
            decreasing_line_color=HISTORY_COLOR_DOWN,
            increasing_fillcolor=HISTORY_COLOR_UP,
            decreasing_fillcolor=HISTORY_COLOR_DOWN,
        )
    )

    # Uncertainty band (10th–90th percentile of Monte Carlo close prices).
    fig.add_trace(
        go.Scatter(
            x=band.index,
            y=band["upper"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=band.index,
            y=band["lower"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=BAND_COLOR,
            name="Forecast band (P10–P90)",
            hoverinfo="skip",
        )
    )

    fig.add_trace(
        go.Candlestick(
            x=forecast_mean.index,
            open=forecast_mean["open"],
            high=forecast_mean["high"],
            low=forecast_mean["low"],
            close=forecast_mean["close"],
            name="Forecast",
            increasing_line_color=FORECAST_COLOR_UP,
            decreasing_line_color=FORECAST_COLOR_DOWN,
            increasing_fillcolor=FORECAST_COLOR_UP,
            decreasing_fillcolor=FORECAST_COLOR_DOWN,
        )
    )

    # Vertical "now" line at the boundary between history and forecast.
    boundary = hist.index[-1]
    fig.add_vline(
        x=boundary,
        line_width=1,
        line_dash="dot",
        line_color="rgba(120,120,120,0.6)",
    )

    fig.update_layout(
        title=dict(
            text=f"{ticker} — 24h Kronos Forecast",
            x=0.02,
            xanchor="left",
            font=dict(size=18),
        ),
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        margin=dict(l=10, r=10, t=50, b=10),
        height=520,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Price", tickformat=",.4f")
    fig.update_xaxes(title_text="Time (UTC)")
    return fig
