---
title: Kronos AI Candlestick Forecast
emoji: 📈
colorFrom: orange
colorTo: blue
sdk: streamlit
sdk_version: 1.39.0
app_file: app.py
pinned: false
license: mit
---

<div align="center">

# 📈 Kronos AI — Candlestick Forecasting

**A Streamlit web app that generates 24-hour AI candlestick forecasts for crypto pairs and stocks,
powered by the open-source [Kronos](https://github.com/shiyu-coder/Kronos) financial time-series model.**

<br/>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit" />
  <img src="https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white" alt="PyTorch" />
  <img src="https://img.shields.io/badge/Hugging%20Face-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" alt="Hugging Face" />
  <img src="https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white" alt="Plotly" />
  <img src="https://img.shields.io/badge/pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="pandas" />
  <img src="https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white" alt="NumPy" />
  <img src="https://img.shields.io/badge/Binance-F0B90B?style=for-the-badge&logo=binance&logoColor=black" alt="Binance API" />
  <img src="https://img.shields.io/badge/Yahoo%20Finance-6001D2?style=for-the-badge&logo=yahoo&logoColor=white" alt="Yahoo Finance" />
</p>

<p align="center">
  <a href="https://github.com/shiyu-coder/Kronos">
    <img src="https://img.shields.io/badge/Model-Kronos-9333ea?style=for-the-badge" alt="Kronos" />
  </a>
  <a href="https://huggingface.co/spaces">
    <img src="https://img.shields.io/badge/Deploy-Hugging%20Face%20Spaces-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" alt="Deploy to HF Spaces" />
  </a>
  <img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License" />
</p>

<br/>

<p align="center">
  <img src="./SysArchitecture.png" alt="System architecture diagram" width="900" />
</p>

<p align="center"><sub><i>System architecture — data sources, model pipeline, and UI layer.</i></sub></p>

</div>

---

## ✨ Features

- 🔎 **Auto-detection** of asset type from the ticker format.
- 🪙 **Crypto pairs** (e.g. `BTC/USDT`, `ETH/USDT`) via the **Binance** public REST API — no API key required.
- 📊 **Stocks** (e.g. `AAPL`, `TSLA`, `NVDA`) via **Yahoo Finance** (`yfinance`).
- 🧠 **Kronos** financial foundation model, loaded directly from Hugging Face Hub:
  - Tokenizer → [`NeoQuasar/Kronos-Tokenizer-base`](https://huggingface.co/NeoQuasar/Kronos-Tokenizer-base)
  - Model → [`NeoQuasar/Kronos-small`](https://huggingface.co/NeoQuasar/Kronos-small)
- 🎲 **Monte Carlo sampling** (N=20 paths) for probabilistic forecasts and a P10–P90 uncertainty cone.
- 📈 **Clean Plotly candlestick chart** — last 100 historical candles (blue) + 24 forecast candles (orange) + shaded uncertainty band.
- 📱 **Mobile-friendly** responsive layout.
- 🔒 **Built-in rate limit** — 5 free forecasts per user per day, resets at UTC midnight.
- ☁️ **One-click deploy** to Hugging Face Spaces (Streamlit SDK).
- 🚫 **No API keys** required from the user.

---

## 🖼️ How it works

```
┌─────────────┐    ┌────────────────┐    ┌────────────────────┐    ┌─────────────────┐
│   Ticker    │ →  │  Data fetcher  │ →  │  Kronos predictor  │ →  │  Plotly chart   │
│ BTC/USDT or │    │  Binance / yf  │    │  20 × MC samples   │    │  + uncertainty  │
│   AAPL …    │    │  500 × 1h OHLC │    │  pred_len = 24     │    │  band + metrics │
└─────────────┘    └────────────────┘    └────────────────────┘    └─────────────────┘
```

1. **Input** — user types a ticker and clicks *Generate Forecast*.
2. **Fetch** — `data_fetcher.py` pulls **500 candles of 1-hour OHLCV** from Binance (crypto) or yfinance (stocks).
3. **Forecast** — `forecaster.py` clones the Kronos repo if needed, loads tokenizer + model from Hugging Face,
   and runs **20 independent Monte Carlo paths** of `pred_len=24` candles.
4. **Aggregate** — paths are combined into a mean OHLC forecast and a 10th–90th percentile band on close price.
5. **Render** — `chart.py` builds the Plotly candlestick + uncertainty cone, and the UI displays headline metrics.

---

## 📊 Metrics shown

| Metric | Description |
| --- | --- |
| **Current price** | Last close from the historical series. |
| **Forecast (24h)** | Mean predicted close 24 candles ahead, with % change. |
| **Direction** | Up / down based on mean forecast vs. current price. |
| **Confidence** | Share of Monte Carlo paths that agree with the predicted direction. |
| **Volatility outlook** | Average forecasted high–low range relative to current price. |

---

## 📁 Project structure

```
finance-streamlit/
├── app.py             # Streamlit UI + orchestration
├── data_fetcher.py    # Binance + yfinance OHLCV fetching
├── forecaster.py      # Kronos repo bootstrap, model loading, Monte Carlo prediction
├── chart.py           # Plotly candlestick + uncertainty band
├── rate_limiter.py    # JSON-backed daily rate limit (5/day/user)
├── requirements.txt   # Pinned dependencies
├── README.md          # You are here
└── Kronos/            # Auto-cloned from github.com/shiyu-coder/Kronos on first run
```

The Kronos repository is cloned at startup into `./Kronos/` and added to `sys.path`,
so `from model import Kronos, KronosTokenizer, KronosPredictor` works identically on
local machines and on Hugging Face Spaces.

---

## 🚀 Run locally

> Requires **Python 3.10+**.

```bash
git clone <this-repo>
cd finance-streamlit

# Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows PowerShell

# Install pinned dependencies
pip install -r requirements.txt

# Launch the app
streamlit run app.py
```

Then open <http://localhost:8501>.

On **first run** the app will:

1. Clone the Kronos repo into `./Kronos/` (one-time).
2. Download tokenizer + model weights from Hugging Face Hub (cached afterwards by `huggingface_hub`).
3. Load the model on CPU. Thanks to `@st.cache_resource`, this happens only once per process.

Expect roughly **1–2 minutes per forecast** on a typical free-tier CPU
(20 Monte Carlo paths × 24-candle horizon).

---

## ☁️ Deploy to Hugging Face Spaces

This repo is **Spaces-ready** — the YAML frontmatter at the top of this README declares the Streamlit SDK.

1. Create a new **Space** with the **Streamlit** SDK.
2. Push all files in this directory to the Space repo (or use the web uploader).
3. The Space will:
   - Install dependencies from `requirements.txt`.
   - Clone the Kronos repo automatically on first request.
   - Serve `app.py`.

No secrets, environment variables, or API keys are required — Binance's public endpoints and `yfinance` work out of the box, and Hugging Face Hub downloads the model anonymously.

---

## 🛡️ Rate limit

| | Value |
| --- | --- |
| **Limit** | 5 forecasts / day / user |
| **Storage** | `.usage.json` keyed by per-session UUID |
| **Reset** | UTC midnight |
| **Tracking** | Streamlit session state + atomic JSON write |

When the limit is reached the UI shows:

> **You've reached your 5 free forecasts for today. Come back tomorrow!**

---

## 🧰 Tech stack

| Layer | Technology |
| --- | --- |
| Web UI | [Streamlit](https://streamlit.io/) |
| Charting | [Plotly](https://plotly.com/python/) |
| Model | [Kronos](https://github.com/shiyu-coder/Kronos) (PyTorch) |
| Model hub | [Hugging Face Hub](https://huggingface.co/) + [`transformers`](https://huggingface.co/docs/transformers) |
| Crypto data | [Binance public REST API](https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data) |
| Stock data | [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance) |
| Data ops | [pandas](https://pandas.pydata.org/) · [NumPy](https://numpy.org/) |
| Deploy target | [Hugging Face Spaces](https://huggingface.co/spaces) (Streamlit SDK) |

---

## ⚠️ Disclaimer

This app is for **educational and research purposes only**. The forecasts are
AI-generated approximations from a probabilistic model and **are not financial
advice**. Markets are noisy and any predictive model — Kronos included — can
and will be wrong. Do not make trading decisions based solely on this output.

---

## 📄 License

MIT — see headers in each source file. The Kronos model and tokenizer are
distributed under their own licenses on Hugging Face.
