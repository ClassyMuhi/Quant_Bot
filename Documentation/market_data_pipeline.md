# Multi-Stock Market Data Pipeline (Medallion Architecture)

## Overview

The Market Data Pipeline automatically downloads, cleans, and prepares stock market data for Indian NSE stocks (such as RELIANCE, TCS, INFY, etc.).

Instead of dumping raw internet data straight into our trading strategies, we follow the **Medallion Architecture**, which organizes data into three simple stages:

```
[ Yahoo Finance ]
        │
        ▼
   1. BRONZE (Raw & Untouched)
        │
        ▼
   2. SILVER (Cleaned & Validated)
        │
        ▼
   3. GOLD   (Ready for AI & Trading Models)
```

---

## The Three Data Layers in Simple Words

### 1. Bronze Layer (Raw Storage)
* **What it is:** The "storage locker" for exact raw data downloaded from Yahoo Finance.
* **Why we have it:** If we ever find a bug in our cleaning logic or want to recalculate something from scratch, we never have to re-download months of data from the internet. We can always reprocess our Bronze files.
* **Storage format:** Stored as fast Parquet files in `data/bronze/{SYMBOL}.parquet`.
* **Extra details:** Every record is tagged with when it was downloaded (`_ingested_at_utc`) and where it came from (`_source="yfinance"`).

### 2. Silver Layer (Cleaned & Validated Data)
* **What it is:** The polished, high-quality version of the market data.
* **Why we have it:** Raw internet data often has problems (duplicate days, bad prices like zero or negative numbers, flipped High/Low prices, missing values). The Silver layer fixes all of these issues.
* **What gets cleaned:**
  * Removes duplicate records for the same day.
  * Sorts dates in chronological order.
  * Throws away invalid prices (e.g., negative prices).
  * Fixes High and Low prices so High is always the highest and Low is always the lowest.
  * Formats columns to match our FinRL standard (`date`, `symbol`, `open`, `high`, `low`, `close`, `adj_close`, `volume`).
* **Storage format:** Saved in `data/silver/{SYMBOL}.parquet`.

### 3. Gold Layer (Model-Ready Features)
* **What it is:** The final dataset enriched with mathematical indicators that trading algorithms and AI models need.
* **Why we have it:** An AI model cannot easily learn directly from raw stock prices alone. It needs technical indicators, percentage returns, and volatility measurements to make smart decisions.
* **Features computed:**
  * **Returns:** Daily percentage return, daily log return, 5-day return, 20-day return.
  * **Moving Averages:** 10-day, 20-day, and 50-day Simple Moving Averages (SMA), plus Exponential Moving Averages (EMA 12 and 26).
  * **Trend & Momentum:** MACD (Moving Average Convergence Divergence) and RSI (Relative Strength Index, 14-day).
  * **Volatility & Risk:** 20-day rolling annualized volatility, Average True Range (ATR 14).
  * **Volume Dynamics:** 20-day volume average, volume spike ratio, Volume Weighted Average Price (VWAP).
* **Storage format:** Saved in `data/gold/{SYMBOL}.parquet`.

---

## Pipeline Modules Explained

All modules live inside the `pipeline/` folder:

| Module | Purpose | Simple Explanation |
| :--- | :--- | :--- |
| `symbol_universe.py` | Configurable Stock List | Keeps track of all the stocks we want to trade across different Indian sectors (Banking, IT, Energy, Auto, FMCG, etc.). Automatically adds `.NS` to symbols so Yahoo Finance understands them (e.g., `RELIANCE` becomes `RELIANCE.NS`). |
| `market_fetcher.py` | Internet Downloader | Downloads price bars from Yahoo Finance. If an internet hiccup happens, it automatically retries with backoff instead of crashing. |
| `bronze_writer.py` | Raw Data Saver | Saves raw data to disk using Parquet. Uses DuckDB to quickly query files and check the latest date we have saved without loading everything into memory. |
| `silver_transformer.py` | Data Cleaner | Strips out bad data, fixes pricing anomalies, and guarantees that the data satisfies our FinRL contract. |
| `gold_features.py` | Feature Calculator | Takes the clean Silver data and calculates all mathematical features (RSI, ATR, moving averages, etc.). |
| `market_pipeline.py` | Conductor / Orchestrator | Coordinates the whole pipeline from end to end. Lets you run a complete backfill or a quick daily update with one simple command. |

---

## How Incremental Updates Work (No Duplicates)

When you run an update today, the pipeline does **not** re-download the entire history:
1. It asks DuckDB: *"What is the latest date we already have stored in Bronze for RELIANCE?"*
2. If the latest date is yesterday, it only asks Yahoo Finance for bars *after* yesterday.
3. If new bars exist, it merges them with the existing history, safely drops any overlapping dates, and refreshes the Silver and Gold files.
4. If the data is already up to date, it skips unnecessary downloads.

---

## How to Run It

### 1. From the Command Line (CLI)

* **Run a full historical backfill (e.g. 1 year of data for all stocks in the universe):**
  ```bash
  python -m pipeline.market_pipeline --backfill --period 1y
  ```

* **Run a backfill for specific stocks:**
  ```bash
  python -m pipeline.market_pipeline --backfill --symbols RELIANCE TCS INFY --period 6mo
  ```

* **Run daily incremental update (downloads only new missing days):**
  ```bash
  python -m pipeline.market_pipeline --incremental
  ```

### 2. In Python Code

```python
from pipeline.market_pipeline import MarketPipeline

# Initialize pipeline
pipeline = MarketPipeline()

# 1. Backfill or update data
pipeline.run_full_backfill(symbols=["RELIANCE", "TCS"], period="1y")

# 2. Get ready-to-use dataset for FinRL or trading models
dataset = pipeline.get_finrl_dataset(symbols=["RELIANCE", "TCS"])
prices_df = dataset["prices"]
features_df = dataset["features"]

print(prices_df.head())
print(features_df[["date", "symbol", "close", "rsi_14", "volatility_20d"]].tail())
```

---

## Unit Tests

Every component has dedicated unit tests inside the `tests/` folder:
* `tests/test_symbol_universe.py`: Tests stock lists and ticker translation.
* `tests/test_market_fetcher.py`: Tests network download logic and column standardization.
* `tests/test_bronze_writer.py`: Tests Parquet writing, metadata columns, and DuckDB queries.
* `tests/test_silver_transformer.py`: Tests data cleaning, duplicate removal, and FinRL validation.
* `tests/test_gold_features.py`: Tests indicator calculations (RSI, ATR, returns, volatility).
* `tests/test_market_pipeline.py`: Tests the full pipeline workflow and incremental updates.

Run all tests anytime with:
```bash
python -m pytest tests/
```

