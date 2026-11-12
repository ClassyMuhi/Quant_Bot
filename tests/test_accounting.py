"""
Unit tests for backtest.accounting module.
Verifies position tracking, cash accounting, solvency enforcement, and trade logging.
"""

import pytest
from backtest.accounting import Position, PortfolioAccount
from backtest.cost_model import ZeroCostModel, IndianEquityCostModel


def test_position_tracking():
    pos = Position(symbol="RELIANCE")

    # Buy 10 @ Rs. 100
    pos.update_on_buy(buy_qty=10, buy_price=100.0)
    assert pos.quantity == 10
    assert pos.average_cost == 100.0

    # Buy 10 @ Rs. 200 -> Average cost should be 150.0
    pos.update_on_buy(buy_qty=10, buy_price=200.0)
    assert pos.quantity == 20
    assert pos.average_cost == 150.0

    # Sell 10 @ Rs. 180 -> Realized PnL = (180 - 150) * 10 = 300.0
    pnl = pos.update_on_sell(sell_qty=10, sell_price=180.0)
    assert pnl == 300.0
    assert pos.quantity == 10
    assert pos.average_cost == 150.0

    # Sell remaining 10 @ Rs. 140 -> Realized PnL = (140 - 150) * 10 = -100.0
    pnl2 = pos.update_on_sell(sell_qty=10, sell_price=140.0)
    assert pnl2 == -100.0
    assert pos.quantity == 0
    assert pos.average_cost == 0.0


def test_portfolio_account_solvency():
    # Account with Rs. 10,000 cash
    account = PortfolioAccount(initial_cash=10000.0, cost_model=ZeroCostModel())

    # Try to buy 200 shares @ Rs. 100 (needs Rs. 20,000)
    # Solvency mechanism should scale down to 100 shares (10,000 // 100)
    trade = account.execute_order("2026-01-01", "TCS", "BUY", quantity=200, price=100.0)
    assert trade is not None
    assert trade.quantity == 100
    assert account.cash == 0.0
    assert account.get_total_equity({"TCS": 100.0}) == 10000.0


def test_portfolio_daily_snapshot():
    account = PortfolioAccount(initial_cash=50000.0, cost_model=ZeroCostModel())
    account.execute_order("2026-01-01", "INFY", "BUY", quantity=20, price=1000.0)

    # Cash: 30,000; Holdings: 20 INFY @ 1000 = 20,000 -> Total: 50,000
    snap1 = account.record_daily_snapshot("2026-01-01", {"INFY": 1000.0})
    assert snap1["total_equity"] == 50000.0

    # Next day price rises to 1100 -> Holdings: 22,000 -> Total: 52,000
    snap2 = account.record_daily_snapshot("2026-01-02", {"INFY": 1100.0})
    assert snap2["total_equity"] == 52000.0

    df = account.to_equity_dataframe()
    assert len(df) == 2
    assert "daily_return" in df.columns
    assert round(df["daily_return"].iloc[1], 4) == round((52000 - 50000) / 50000, 4)

