"""
Unit tests for backtest.cost_model module.
Verifies Indian equity delivery transaction costs, taxes, and slippage.
"""

import pytest
from backtest.cost_model import (
    IndianEquityCostModel,
    FlatPercentageCostModel,
    ZeroCostModel,
    TradeCost,
)


def test_indian_equity_cost_buy():
    # Buy 100 shares @ Rs. 1000
    model = IndianEquityCostModel(
        brokerage_pct=0.0003,
        brokerage_max_per_order=20.0,
        stt_pct=0.001,
        exchange_fee_pct=0.0000325,
        gst_pct=0.18,
        stamp_duty_pct=0.00015,
        slippage_bps=5.0,  # 5 bps = 0.05%
    )

    cost = model.calculate_cost("BUY", price=1000.0, quantity=100)

    # Base price: 1000.0, slippage: 1000 * 0.0005 = 0.50
    # Effective price: 1000.50
    assert cost.effective_price == 1000.50
    assert cost.gross_value == 100050.0

    # Brokerage: min(100050 * 0.0003, 20.0) = min(30.015, 20.0) = 20.0
    assert cost.brokerage == 20.0

    # STT: 100050 * 0.001 = 100.05
    assert cost.stt == 100.05

    # Stamp duty on BUY: 100050 * 0.00015 = 15.01
    assert cost.stamp_duty > 0.0

    # Net cash impact for BUY is negative (cash leaves portfolio)
    assert cost.net_cash_impact < 0
    assert abs(cost.net_cash_impact) > cost.gross_value


def test_indian_equity_cost_sell():
    model = IndianEquityCostModel(slippage_bps=10.0)
    cost = model.calculate_cost("SELL", price=2000.0, quantity=50)

    # SELL slips lower: 2000 - (2000 * 0.001) = 1998.0
    assert cost.effective_price == 1998.0
    # Stamp duty must be ZERO on SELL
    assert cost.stamp_duty == 0.0
    # STT must still apply on SELL (0.1%)
    assert cost.stt > 0.0

    # Net cash impact for SELL is positive (cash enters portfolio), but less than gross value due to taxes
    assert cost.net_cash_impact > 0
    assert cost.net_cash_impact < cost.gross_value


def test_zero_cost_model():
    model = ZeroCostModel()
    cost = model.calculate_cost("BUY", price=500.0, quantity=10)
    assert cost.effective_price == 500.0
    assert cost.total_cost == 0.0
    assert cost.net_cash_impact == -5000.0

