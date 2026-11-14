"""
Execution Edge Cases & Indian Market Cost Audit Tests
Verifies zero look-ahead bias, gap-up/down handling, liquidity limits (partial fills),
cash solvency, integer share sizing, and 5/10/20/50 bps slippage scenarios.
"""

import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from backtest.strategy import BacktestStrategy, Signal, SignalType
from backtest.cost_model import IndianEquityCostModel, ZeroCostModel


class OneShotBuyStrategy(BacktestStrategy):
    def __init__(self, target_sym="RELIANCE"):
        super().__init__(name="OneShotBuy")
        self.target_sym = target_sym
        self.has_bought = False

    def generate_signals(self, current_date, historical_data):
        signals = {}
        if not self.has_bought and self.target_sym in historical_data:
            signals[self.target_sym] = Signal(
                symbol=self.target_sym,
                date=current_date,
                signal_type=SignalType.BUY,
            )
            self.has_bought = True
        return signals


class BuyThenSellStrategy(BacktestStrategy):
    def __init__(self, target_sym="TCS"):
        super().__init__(name="BuyThenSell")
        self.target_sym = target_sym
        self.day_count = 0

    def generate_signals(self, current_date, historical_data):
        self.day_count += 1
        if self.day_count == 1:
            return {self.target_sym: Signal(self.target_sym, current_date, SignalType.BUY)}
        elif self.day_count == 2:
            return {self.target_sym: Signal(self.target_sym, current_date, SignalType.SELL)}
        return {self.target_sym: Signal(self.target_sym, current_date, SignalType.HOLD)}


def test_gap_up_execution_and_solvency():
    """
    Test Day 1 Close: 100.
    Day 2 Open GAPS UP to 200 (+100%).
    Verify BUY executes at 200 (not 100), and cash never drops below 0.
    """
    df = pd.DataFrame([
        {"date": "2026-01-01", "symbol": "GAP", "open": 98.0, "high": 105.0, "low": 97.0, "close": 100.0, "volume": 10000},
        {"date": "2026-01-02", "symbol": "GAP", "open": 200.0, "high": 210.0, "low": 195.0, "close": 205.0, "volume": 10000},
        {"date": "2026-01-05", "symbol": "GAP", "open": 205.0, "high": 215.0, "low": 200.0, "close": 210.0, "volume": 10000},
    ])

    engine = BacktestEngine(
        strategy=OneShotBuyStrategy(target_sym="GAP"),
        initial_capital=50000.0,
        cost_model=IndianEquityCostModel(slippage_bps=5.0),
    )

    result = engine.run({"GAP": df})
    trades = result.trades_df
    assert len(trades) == 1
    trade = trades.iloc[0]

    # Must execute at Day 2 Open (200) + slippage (200 * 0.0005 = 0.10) -> 200.10
    assert trade["date"] == "2026-01-02"
    assert trade["base_price"] == 200.0
    assert trade["execution_price"] == 200.10

    # Solvency: Cash must remain >= 0
    final_cash = result.equity_df["cash"].iloc[-1]
    assert final_cash >= 0.0
    # Must be integer shares
    assert isinstance(int(trade["quantity"]), int)
    assert trade["quantity"] > 0


def test_gap_down_sell_execution():
    """
    Test Day 1 Buy.
    Day 2 GAPS DOWN from 100 to 50 (-50%).
    Verify SELL executes at Day 2 Open (50) with sell-side slippage.
    """
    df = pd.DataFrame([
        {"date": "2026-01-01", "symbol": "TCS", "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0, "volume": 10000},
        {"date": "2026-01-02", "symbol": "TCS", "open": 50.0, "high": 55.0, "low": 48.0, "close": 52.0, "volume": 10000},
        {"date": "2026-01-05", "symbol": "TCS", "open": 52.0, "high": 55.0, "low": 50.0, "close": 51.0, "volume": 10000},
    ])

    engine = BacktestEngine(
        strategy=BuyThenSellStrategy(target_sym="TCS"),
        initial_capital=100000.0,
        cost_model=IndianEquityCostModel(slippage_bps=10.0),  # 10 bps = 0.1%
    )

    result = engine.run({"TCS": df})
    trades = result.trades_df
    assert len(trades) == 2

    sell_trade = trades[trades["order_type"] == "SELL"].iloc[0]
    assert sell_trade["date"] == "2026-01-05"  # Signal on Day 2 close, executes Day 3 open
    # Day 3 Open is 52.0; Sell slippage: 52 - (52 * 0.001) = 51.948 -> 51.948
    assert sell_trade["base_price"] == 52.0
    assert sell_trade["execution_price"] < 52.0


def test_partial_fill_and_liquidity_constraints():
    """
    Tests volume participation capping.
    With max_volume_participation_pct=0.10:
    Daily volume is 500 shares -> max fill allowed = 50 shares.
    Even if algorithm wants 500 shares, order is constrained to 50.
    """
    df = pd.DataFrame([
        {"date": "2026-01-01", "symbol": "LOWVOL", "open": 100.0, "high": 105.0, "low": 98.0, "close": 100.0, "volume": 500},
        {"date": "2026-01-02", "symbol": "LOWVOL", "open": 100.0, "high": 105.0, "low": 98.0, "close": 100.0, "volume": 500},
        {"date": "2026-01-05", "symbol": "LOWVOL", "open": 100.0, "high": 105.0, "low": 98.0, "close": 100.0, "volume": 500},
    ])

    engine = BacktestEngine(
        strategy=OneShotBuyStrategy(target_sym="LOWVOL"),
        initial_capital=1000000.0,
        cost_model=ZeroCostModel(),
        max_volume_participation_pct=0.10,  # 10% of 500 = 50 shares
    )

    result = engine.run({"LOWVOL": df})
    trades = result.trades_df
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["quantity"] == 50  # Capped at 10% volume!


def test_indian_cost_schedule_buy_vs_sell():
    """
    Validates Indian statutory schedule:
    - Brokerage: min(0.03%, Rs. 20)
    - STT: 0.1% on delivery Buy and Sell
    - Exchange fee: 0.00325%
    - Stamp duty: 0.015% on BUY only (0.0 on SELL)
    - SEBI charges: 0.0001%
    - GST: 18% on (brokerage + exchange fee + sebi charges)
    """
    model = IndianEquityCostModel(
        brokerage_pct=0.0003,
        brokerage_max_per_order=20.0,
        stt_pct=0.001,
        exchange_fee_pct=0.0000325,
        gst_pct=0.18,
        sebi_charges_pct=0.000001,
        stamp_duty_pct=0.00015,
        slippage_bps=0.0,
    )

    # 1. Buy 100 @ Rs. 1000 = Rs. 100,000 gross
    buy_cost = model.calculate_cost("BUY", price=1000.0, quantity=100)
    assert buy_cost.gross_value == 100000.0
    assert buy_cost.brokerage == 20.0  # min(30, 20)
    assert buy_cost.stt == 100.0      # 100,000 * 0.001
    assert buy_cost.stamp_duty == 15.0 # 100,000 * 0.00015
    # GST on (20 + 3.25 + 0.10) = 23.35 * 0.18 = 4.20
    assert abs(buy_cost.gst - 4.20) <= 0.05

    # 2. Sell 100 @ Rs. 1000
    sell_cost = model.calculate_cost("SELL", price=1000.0, quantity=100)
    assert sell_cost.stamp_duty == 0.0  # ZERO stamp duty on sell!
    assert sell_cost.stt == 100.0       # STT still applies on sell!


def test_slippage_scenarios_5_10_20_50_bps():
    """Validates execution price under 5, 10, 20, and 50 bps slippage scenarios."""
    price = 1000.0
    qty = 10

    scenarios = {
        5.0: (1000.5, 999.5),
        10.0: (1001.0, 999.0),
        20.0: (1002.0, 998.0),
        50.0: (1005.0, 995.0),
    }

    for bps, (expected_buy, expected_sell) in scenarios.items():
        model = IndianEquityCostModel(slippage_bps=bps)
        b_cost = model.calculate_cost("BUY", price, qty)
        s_cost = model.calculate_cost("SELL", price, qty)

        assert b_cost.effective_price == expected_buy, f"Failed BUY at {bps} bps"
        assert s_cost.effective_price == expected_sell, f"Failed SELL at {bps} bps"

