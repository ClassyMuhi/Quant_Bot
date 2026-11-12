# MegaBull Paper Trading Broker Integration

## Overview

The `broker/megabull.py` module is a clean Python wrapper for the **MegaBull Paper Trading REST API**.

MegaBull is a simulated trading platform for Indian equities. It allows us to test order placement, position tracking, and portfolio rebalancing with virtual money without risking real capital.

---

## What It Does in Simple Words

Instead of manually writing HTTP requests in every file, the `MegaBull` class gives us simple Python methods:

### 1. Account & Balance
* `get_user_profile()`: Checks virtual money balance (total money, available cash, blocked funds in open orders) and account profile.

### 2. Market Watch & Instruments
* `get_marketwatch()`: Retrieves all symbols currently in the user's market watch along with live tick size, lot size, and last traded price.
* `get_instruments()`: Downloads the complete master list of all tradable NSE/BSE instruments as a pandas DataFrame.
* `get_marketwatch_quote(symbol)`: Looks up a specific stock (e.g. `RELIANCE`) in the market watch.

### 3. Order Execution
* `place_order(order_data)`: Submits buy or sell orders (Market, Limit, Stop-Loss).
* `modify_order(order_id, order_data)`: Edits quantity or price of an open order.
* `cancel_orders(order_ids)`: Cancels pending orders.
* `get_orders()`: Fetches open, executed, and cancelled orders.

### 4. Holdings & Positions
* `get_positions()`: Lists current intraday and active positions.
* `get_holdings()`: Lists long-term delivery holdings currently owned in the virtual portfolio.

### 5. Performance Reports
* `get_virtual_money_report(start_date, end_date)`: Historical virtual money ledger.
* `get_monthly_report(month, year)`: Monthly profit & loss statement.
* `get_daily_report(date_str)`: Daily trading breakdown.

---

## Authentication & Configuration

The client automatically loads your API key from the `.env` file at the root of the project:

```env
MEGABULL_API_KEY=your_megabull_api_key_here
```

To initialize the client in Python:
```python
from broker.megabull import MegaBull

# Automatically reads MEGABULL_API_KEY from .env
client = MegaBull()
profile = client.get_user_profile()
print(f"Available Virtual Money: Rs. {profile['virtualMoneyLeft']:,}")
```

---

## Verification Scripts

Two verification scripts test the broker integration:
1. `test_megabull.py`: Tests API key connection, user profile, holdings, and order retrieval.
2. `test_market_data.py`: Tests market watch inspection and downloads master tradable instruments.

Run with:
```bash
python test_megabull.py
python test_market_data.py
```

