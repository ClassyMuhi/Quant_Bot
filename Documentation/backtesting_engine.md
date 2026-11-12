# Backtesting Engine for Quant_Bot

## Overview

The **Backtesting Engine** is a modular, event-driven historical simulation framework for testing trading strategies on Indian NSE equities.

It allows quantitative researchers to test strategies against past market data (stored in our Gold-layer Parquet datasets) with **extreme realism**, including zero look-ahead bias, Indian statutory transaction taxes, slippage, and cash solvency accounting.

---

## Why We Built It (In Simple Words)

In algorithmic trading, backtesting without realistic constraints leads to "fool's gold" — strategies that appear wildly profitable on paper but lose money in real trading. 

Our engine prevents three common backtesting pitfalls:
1. **Look-Ahead Bias:** An algorithm cannot use information from the future. Signals generated from today's closing prices can only be executed tomorrow at the market open.
2. **Ignoring Indian Taxes & Friction:** Indian stock trading involves Brokerage, STT, Exchange fees, GST, Stamp Duty, and Slippage. These costs quickly eat into profits if not properly accounted for.
3. **Cash Solvency & Integer Shares:** You cannot spend money you don't have, and in the Indian stock market, you cannot buy fractional shares (e.g., 2.5 shares of Reliance).

---

## Engine Architecture

```
┌────────────────────────────────────────────────────────┐
│                   Input Market Data                    │
│     Gold Parquet Files (data/gold/{SYMBOL}.parquet)    │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   Backtest Strategy                    │
│   SMACrossover, RSIMeanReversion, or FinRL Adapter     │
│   Evaluates Day t Close -> Emits Signals for Day t+1   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│           BacktestEngine (Zero Look-Ahead Loop)        │
│   Executes at Day t+1 Open Price                       │
│   Applies IndianEquityCostModel (Brokerage, STT, Slip) │
│   Updates PortfolioAccount (Cash + Integer Holdings)   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Performance & Benchmark Metrics          │
│   CAGR, Sharpe, Sortino, Max Drawdown, Win Rate, Turn  │
│   Comparative Table vs Buy & Hold and NIFTY 50         │
└────────────────────────────────────────────────────────┘
```

---

## Core Modules Explained

### 1. Indian Cost & Slippage Model (`backtest/cost_model.py`)
Simulates the actual fee and tax structure of Indian discount brokerages (e.g. Zerodha, Groww):
* **Brokerage:** 0.03% capped at Rs. 20 per order.
* **STT (Securities Transaction Tax):** 0.1% on delivery (both Buy and Sell).
* **Exchange Turnover Charge:** 0.00325% (NSE).
* **GST:** 18% on (Brokerage + Exchange Turnover Charge).
* **SEBI Charges:** Rs. 10 per crore (0.0001%).
* **Stamp Duty:** 0.015% (charged on BUY orders only).
* **Slippage:** Configurable in basis points (default 5 bps = 0.05%). Buy orders slip higher; Sell orders slip lower.

### 2. Portfolio & Cash Accounting (`backtest/accounting.py`)
* **Solvency Protection:** An order cannot exceed available cash. If a buy order requests more shares than the cash balance can fund, the engine automatically scales down the quantity to the maximum affordable integer shares.
* **Integer Shares:** Realistically buys whole numbers of shares.
* **Trade Ledger:** Every trade records the execution price, base price, taxes/fees, net cash impact, and realized profit/loss.
* **Daily Equity Curve:** Tracks cash, invested market value, and total portfolio equity at the close of every trading day.

### 3. Strategy Interface & Signal Generation (`backtest/strategy.py`)
All strategies inherit from `BacktestStrategy`:
* Emits `Signal(symbol, date, signal_type, target_weight)` with types `BUY`, `SELL`, or `HOLD`.
* **Built-in Strategies:**
  * `SMACrossoverStrategy`: Classic trend-following (e.g. 10-day SMA crossing 20-day SMA).
  * `RSIMeanReversionStrategy`: Buys oversold (RSI < 30), sells overbought (RSI > 70).
  * `FinRLStrategyAdapter`: Directly takes any `FinRLBaseStrategy` from our FinRL adapter and runs it inside the backtesting engine!

### 4. Metrics Calculator (`backtest/metrics.py`)
Computes institutional-grade risk and return metrics:
* **Total Return (%) & CAGR (%):** Compound Annual Growth Rate normalized across the trading period.
* **Annualized Volatility (%):** Standard deviation of daily returns scaled by $\sqrt{252}$.
* **Sharpe Ratio:** Risk-adjusted return relative to the Indian 91-day T-Bill rate (default 6.0%).
* **Sortino Ratio:** Penalizes only downside volatility (down days).
* **Max Drawdown (%) & Duration (Days):** The worst peak-to-trough decline and the time spent recovering.
* **Win Rate (%) & Profit Factor:** Ratio of winning trades to total closed trades, and gross profits divided by gross losses.
* **Portfolio Turnover (%):** Measures trading activity and portfolio churn.

### 5. Backtest Orchestrator (`backtest/engine.py`)
Coordinates day-by-day execution:
* Aligns multi-stock trading calendars.
* Evaluates signals at Day $t$ Close and executes them on Day $t+1$ Open.
* Simultaneously benchmarks the strategy against:
  1. **Buy & Hold (Universe):** Buying equal slices of all universe stocks on Day 1 and holding throughout.
  2. **Benchmark (NIFTY 50):** Comparing against the NIFTY 50 index over the identical date range.
* Generates clean summary comparison tables via `result.summary_table()`.

---

## Zero Look-Ahead Bias Guarantee

To prevent looking into the future:
1. **Day $t$ Close:** After the market closes, the strategy inspects price and indicator data up to Day $t$ close. It generates buy or sell signals.
2. **Day $t+1$ Open:** The next morning, orders are sent to the simulated exchange and execute at Day $t+1$ Open price (plus or minus slippage and statutory taxes).
3. **Day $t+1$ Close:** Portfolio valuation is marked to market using Day $t+1$ Close price.

This guarantees that an algorithm never executes at the same close price it used to generate the signal.

---

## Assumptions and Limitations

1. **Daily Bar Resolution:** The backtest simulates daily bars (`1d`). Intraday price spikes, gaps, or intra-bar stop-losses that occur between the open and close are not modeled in daily mode.
2. **Market Impact:** For retail and standard quantitative order sizes, our 5–10 bps slippage model accurately reflects friction. For institutional orders exceeding 10% of daily volume, market impact models (e.g. Almgren-Chriss) would be needed.
3. **Short Selling:** The delivery cash segment on Indian exchanges (NSE/BSE) does not permit overnight short selling for cash equities without securities lending (SLB). Therefore, short signals liquidate positions rather than opening naked short positions.
4. **Corporate Actions:** Yahoo Finance data adjusts prices for stock splits and dividends (`adj_close`), but raw open/high/low may require corporate action synchronization if trading unadjusted historical series.

---

## Usage Example

```python
from pipeline.bronze_writer import read_parquet
from backtest import BacktestEngine, SMACrossoverStrategy, IndianEquityCostModel

# 1. Load Gold Parquet data for your stocks
reliance = read_parquet("data/gold/RELIANCE.parquet")
tcs = read_parquet("data/gold/TCS.parquet")
data = {"RELIANCE": reliance, "TCS": tcs}

# 2. Choose strategy and cost model
strategy = SMACrossoverStrategy(short_window=10, long_window=20)
cost_model = IndianEquityCostModel(slippage_bps=5.0)

# 3. Run backtest
engine = BacktestEngine(
    strategy=strategy,
    initial_capital=1000000.0,
    cost_model=cost_model,
)
result = engine.run(data)

# 4. View results
print(result.summary_table().to_string(index=False))
```

---

## Unit and Integration Tests

Run the full test suite with verbose output:
```bash
python -m pytest -v
```
All 34 unit and integration tests verify:
* Zero look-ahead bias ($t \to t+1$ execution)
* Indian equity cost model (brokerage cap, STT on buy/sell, stamp duty on buy only)
* Position accounting and cash solvency
* All quantitative risk and return metrics
* Strategy signal generation and FinRL adapter compatibility

