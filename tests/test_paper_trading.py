"""
Unit Tests for Paper Trading System
Validates dual-constraint position sizing, integer shares, cash solvency,
order validation & rejections (wrong side SL/TP, naked shorting, duplicates),
and ambiguous candle handling in position monitoring.
"""

import pytest
from pathlib import Path
from backtest.cost_model import IndianEquityCostModel
from paper_trading.position_sizer import PositionSizer
from paper_trading.portfolio import PaperPortfolio
from paper_trading.order_manager import OrderManager
from paper_trading.paper_broker import LocalPaperBroker, PaperExecutionGateway
from paper_trading.order_monitor import PositionMonitor


def test_dual_constraint_position_sizing():
    sizer = PositionSizer()
    # Scenario:
    # Investment = 100,000 INR
    # Risk percent = 2% -> Risk budget = 2,000 INR
    # Entry = 2,000 INR
    # Stop-Loss = 1,950 INR -> Risk per share = 50 INR
    # Target = 2,100 INR -> Reward per share = 100 INR (1:2 R:R)
    # Available cash = 200,000 INR
    #
    # Risk-based qty = 2,000 / 50 = 40 shares
    # Budget-based qty = 100,000 / 2,000 = 50 shares
    # Result quantity = min(40, 50) = 40 shares
    res = sizer.calculate_sizing(
        symbol="RELIANCE",
        side="BUY",
        investment_amount=100000.0,
        risk_percent=2.0,
        entry_price=2000.0,
        stop_loss_price=1950.0,
        target_price=2100.0,
        available_cash=200000.0,
    )

    assert res.is_valid is True
    assert res.quantity == 40
    assert isinstance(res.quantity, int)
    assert res.risk_budget == 2000.0
    assert res.risk_per_share == 50.0
    assert res.risk_to_reward_ratio == 2.0
    assert res.total_capital_required > 80000.0  # 40 * 2000 + taxes


def test_position_sizing_rejections():
    sizer = PositionSizer()

    # Case 1: Stop-loss on wrong side of entry for BUY (SL >= Entry)
    res_sl_bad = sizer.calculate_sizing(
        symbol="TCS",
        side="BUY",
        investment_amount=50000.0,
        risk_percent=1.0,
        entry_price=3500.0,
        stop_loss_price=3600.0,  # Wrong side!
        target_price=3800.0,
        available_cash=100000.0,
    )
    assert res_sl_bad.is_valid is False
    assert "strictly below entry" in res_sl_bad.error_message.lower()

    # Case 2: Target on wrong side of entry for BUY (Target <= Entry)
    res_tp_bad = sizer.calculate_sizing(
        symbol="TCS",
        side="BUY",
        investment_amount=50000.0,
        risk_percent=1.0,
        entry_price=3500.0,
        stop_loss_price=3400.0,
        target_price=3450.0,  # Wrong side!
        available_cash=100000.0,
    )
    assert res_tp_bad.is_valid is False
    assert "strictly above entry" in res_tp_bad.error_message.lower()

    # Case 3: Insufficient cash balance
    res_cash_low = sizer.calculate_sizing(
        symbol="TCS",
        side="BUY",
        investment_amount=100000.0,
        risk_percent=2.0,
        entry_price=3500.0,
        stop_loss_price=3400.0,
        target_price=3700.0,
        available_cash=1000.0,  # Not enough for even 1 share!
    )
    assert res_cash_low.is_valid is False
    assert "insufficient funds" in res_cash_low.error_message.lower()


def test_order_manager_rejections_and_naked_short_guard(tmp_path):
    account_file = tmp_path / "paper_acc.json"
    port = PaperPortfolio(account_file=account_file, initial_cash=50000.0)
    mgr = OrderManager(portfolio=port, allow_naked_shorting=False)

    # 1. Attempt to SELL when holding is 0 shares (Naked short selling attempt)
    order, err = mgr.validate_and_create_order(
        symbol="INFY",
        side="SELL",
        investment_amount=20000.0,
        risk_percent=2.0,
        entry_price=1500.0,
        stop_loss_price=1550.0,
        target_price=1400.0,
    )
    assert order is None
    assert "naked short selling rejected" in err.lower()

    # 2. Legitimate BUY order succeeds
    buy_order, buy_err = mgr.validate_and_create_order(
        symbol="INFY",
        side="BUY",
        investment_amount=30000.0,
        risk_percent=2.0,
        entry_price=1500.0,
        stop_loss_price=1450.0,
        target_price=1600.0,
    )
    assert buy_err is None
    assert buy_order is not None
    assert buy_order.quantity > 0
    assert buy_order.symbol == "INFY"

    # 3. Duplicate order detection (same order parameters immediately resubmitted)
    dup_order, dup_err = mgr.validate_and_create_order(
        symbol="INFY",
        side="BUY",
        investment_amount=30000.0,
        risk_percent=2.0,
        entry_price=1500.0,
        stop_loss_price=1450.0,
        target_price=1600.0,
    )
    assert dup_order is None
    assert "duplicate order detected" in dup_err.lower()


def test_paper_execution_and_accounting(tmp_path):
    account_file = tmp_path / "paper_acc.json"
    port = PaperPortfolio(account_file=account_file, initial_cash=100000.0)
    broker = LocalPaperBroker(portfolio=port, slippage_bps=0.0)

    # Buy 20 shares of RELIANCE at 2500
    mgr = OrderManager(portfolio=port)
    buy_order, _ = mgr.validate_and_create_order(
        symbol="RELIANCE",
        side="BUY",
        investment_amount=50000.0,
        risk_percent=2.0,
        entry_price=2500.0,
        stop_loss_price=2400.0,
        target_price=2700.0,
        requested_quantity=20,
    )

    filled_order, trade_rec = broker.execute_order(buy_order)
    assert filled_order.status == "FILLED"
    assert port.holdings["RELIANCE"]["quantity"] == 20
    assert port.cash < 50000.0  # Deducted 20 * 2500 + fees

    # Reload from disk to verify state persistence
    reloaded_port = PaperPortfolio(account_file=account_file)
    assert reloaded_port.holdings["RELIANCE"]["quantity"] == 20
    assert reloaded_port.cash == port.cash

    # Sell all 20 shares at 2600 (Profitable exit)
    sell_order, _ = mgr.validate_and_create_order(
        symbol="RELIANCE",
        side="SELL",
        investment_amount=52000.0,
        risk_percent=2.0,
        entry_price=2600.0,
        stop_loss_price=2650.0,
        target_price=2500.0,
        requested_quantity=20,
    )
    broker.execute_order(sell_order)
    assert "RELIANCE" not in port.holdings  # Position closed
    assert port.realized_pnl > 1800.0  # (2600 - 2500)*20 - both trade fees


def test_ambiguous_candle_detection(tmp_path):
    account_file = tmp_path / "paper_acc.json"
    port = PaperPortfolio(account_file=account_file, initial_cash=100000.0)
    broker = LocalPaperBroker(portfolio=port, slippage_bps=0.0)
    monitor = PositionMonitor(portfolio=port, broker=broker)

    # Open position with SL=2400 and Target=2600
    port.apply_trade(
        symbol="TCS",
        side="BUY",
        quantity=10,
        executed_price=2500.0,
        taxes_and_charges=15.0,
        sl_price=2400.0,
        target_price=2600.0,
    )

    # Bar where Low = 2380 (SL breached) and High = 2620 (Target breached) in the same bar!
    event = monitor.check_candle(
        symbol="TCS",
        high=2620.0,
        low=2380.0,
        close=2500.0,
        conservative_on_ambiguity=True,
    )

    assert event is not None
    assert "AMBIGUOUS" in event.trigger_type
    assert event.trigger_price == 2400.0  # Conservative risk management assumes SL was hit
    assert "TCS" not in port.holdings  # Position safely closed
    assert "Ambiguous candle" in event.warning

