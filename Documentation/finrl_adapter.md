# FinRL Adapter & Data Contract

## Overview

The `finrl_adapter/` package serves as the bridge between **Quant_Bot** and the **FinRL-Trading** quantitative architecture.

It defines standard rules for:
1. What input data every trading strategy must receive (**Data Contract**).
2. How trading strategies should be structured (**Strategy Base Class**).
3. How target stock weights are converted into realistic portfolio allocations with cash reserves (**Portfolio Allocator**).

---

## Core Modules in Simple Words

### 1. Data Contract (`data_contract.py`)
* **What it is:** A contract or rulebook that makes sure data given to trading strategies is valid and uniform.
* **Why we have it:** Prevents bugs where a strategy crashes halfway through backtesting because a column was missing or named incorrectly.
* **The Rule:**
  Every strategy expects a dictionary containing at least a `'prices'` table:
  ```python
  data = {
      "prices": pd.DataFrame,   # Must have: ['date', 'symbol', 'close']
      "features": pd.DataFrame  # Optional: technical indicators like RSI, SMA, etc.
  }
  ```
* **Validation Function:** `validate_market_data(data)` checks that the DataFrame contains all required columns and correct types.

---

### 2. Strategy Interface (`strategy.py`)
* **What it is:** The template that all trading strategies (rule-based, machine learning, or reinforcement learning) follow.
* **Key Components:**
  * `StrategyConfig`: Holds settings like max weight per stock (e.g. 20%), minimum weight, and cash reserve target.
  * `StrategyResult`: The standard answer produced by a strategy containing:
    * Strategy name
    * Target portfolio weights table (`symbol`, `weight`)
    * Execution metadata (timestamp, number of assets considered)
  * `FinRLBaseStrategy`: The parent class that custom strategies inherit from. Every strategy implements `generate_weights(data, target_date)`.

---

### 3. Portfolio Allocator (`portfolio_allocator.py`)
* **What it is:** The calculator that turns raw strategy weights into a realistic, actionable portfolio breakdown.
* **Why we have it:** Raw models might output numbers that don't add up to 100%, or they might try to put 90% into a single risky stock. The Allocator fixes this.
* **What it does:**
  1. Filters out zero or negative weights.
  2. Caps maximum weight per stock (e.g., no single stock can exceed 20%).
  3. Normalizes weights so total stock allocation does not exceed 100%.
  4. Automatically computes the remaining balance and assigns it to `CASH`.

#### Example:
If a strategy outputs:
* `RELIANCE`: 0.20 (20%)
* `TCS`: 0.15 (15%)
* `INFY`: 0.10 (10%)

The Allocator outputs:
```python
{
    "RELIANCE": 0.20,
    "TCS": 0.15,
    "INFY": 0.10,
    "CASH": 0.55   # 55% held safely in cash
}
```

---

## How to Test

Run the FinRL integration smoke test:
```bash
python -m pytest tests/test_finrl_integration.py
```
This tests synthetic multi-asset data generation, strategy weight generation, and portfolio cash allocation end-to-end.

