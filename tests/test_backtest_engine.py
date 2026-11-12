"""
Integration and Unit tests for backtest.engine module.
Tests simulation execution, look-ahead bias prevention, FinRL adapter integration,
and benchmark comparative analysis.
"""

import pandas as pd
import numpy as np
import pytest

from backtest.engine import BacktestEngine, BacktestResult
from backtest.strategy import (
    SMACrossoverStrategy,
    RSIMeanReversionStrategy,
    FinRLStrategyAdapter,
    BacktestStrategy,
    Signal,
    SignalType,
)
from backtest.cost_model import ZeroCostModel, IndianEquityCostModel
from finrl_adapter import FinRLBaseStrategy, StrategyConfig, StrategyResult


class AlwaysBuyFirstDayStrategy(BacktestStrategy):
    """Test helper strategy that emits BUY on day 0, then HOLD."""
    def __init__(self):
        super().__init__(name="AlwaysBuyFirstDay")
        self.emitted = False

    def generate_signals(self, current_date, historical_data):
        signals = {}
        for sym in historical_data.keys():
            if not self.emitted:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.BUY)
            else:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.HOLD)
        self.emitted = True
        return signals


def test_zero_lookahead_bias():
    """
    Verifies that signals generated at the close of Day 0 execute strictly
    at Day 1 OPEN price, not Day 0 prices.
    """
    # 3-day market data
    df = pd.DataFrame([
        {"date": "2026-01-01", "symbol": "TEST", "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 1000},
        {"date": "2026-01-02", "symbol": "TEST", "open": 120.0, "high": 125.0, "low": 118.0, "close": 122.0, "volume": 1000},
        {"date": "2026-01-05", "symbol": "TEST", "open": 130.0, "high": 135.0, "low": 128.0, "close": 132.0, "volume": 1000},
    ])

    data = {"TEST": df}
    strategy = AlwaysBuyFirstDayStrategy()
    engine = BacktestEngine(
        strategy=strategy,
        initial_capital=100000.0,
        cost_model=ZeroCostModel(),
        execution_price_col="open",
        valuation_price_col="close",
    )

    result = engine.run(data)

    trades = result.trades_df
    assert len(trades) == 1
    trade = trades.iloc[0]

    # Signal was evaluated at Day 1 (2026-01-01) close.
    # Execution MUST happen on Day 2 (2026-01-02) at Day 2 OPEN (120.0), NOT Day 1 prices (100.0 or 102.0)!
    assert trade["date"] == "2026-01-02"
    assert trade["execution_price"] == 120.0


@pytest.fixture
def multi_stock_dataset():
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    np.random.seed(42)

    def make_stock_df(sym, base):
        rows = []
        p = base
        for d in dates:
            p += float(np.random.normal(1.0, 5.0))
            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "symbol": sym,
                "open": round(p - 2.0, 2),
                "high": round(p + 5.0, 2),
                "low": round(p - 5.0, 2),
                "close": round(p, 2),
                "volume": 50000,
            })
        return pd.DataFrame(rows)

    return {
        "RELIANCE": make_stock_df("RELIANCE", 2500.0),
        "TCS": make_stock_df("TCS", 3500.0),
    }


def test_sma_crossover_backtest(multi_stock_dataset):
    strategy = SMACrossoverStrategy(short_window=5, long_window=10)
    engine = BacktestEngine(
        strategy=strategy,
        initial_capital=500000.0,
        cost_model=IndianEquityCostModel(),
    )

    result = engine.run(multi_stock_dataset)

    assert isinstance(result, BacktestResult)
    assert not result.equity_df.empty
    assert "cagr_pct" in result.metrics
    assert "sharpe_ratio" in result.metrics
    assert "max_drawdown_pct" in result.metrics

    summary = result.summary_table()
    assert isinstance(summary, pd.DataFrame)
    assert "Metric" in summary.columns
    assert strategy.name in summary.columns
    assert "Buy & Hold (Universe)" in summary.columns


class DummyFinRLStrategy(FinRLBaseStrategy):
    """Simple FinRL strategy allocating 50% RELIANCE, 50% TCS."""
    def generate_weights(self, data, target_date=None):
        weights = pd.DataFrame([
            {"symbol": "RELIANCE", "weight": 0.40},
            {"symbol": "TCS", "weight": 0.40},
        ])
        return StrategyResult(strategy_name="DummyFinRL", weights=weights)


def test_finrl_strategy_adapter_backtest(multi_stock_dataset):
    finrl_strat = DummyFinRLStrategy(config=StrategyConfig(name="SimpleFiftyFifty"))
    adapter = FinRLStrategyAdapter(finrl_strat)

    engine = BacktestEngine(
        strategy=adapter,
        initial_capital=1000000.0,
        cost_model=IndianEquityCostModel(),
    )

    result = engine.run(multi_stock_dataset)
    assert not result.equity_df.empty
    assert len(result.trades_df) > 0
    assert result.metrics["final_equity"] > 0


def test_benchmark_comparison(multi_stock_dataset):
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    nifty_df = pd.DataFrame([
        {"date": d.strftime("%Y-%m-%d"), "close": 24000.0 + i * 15.0}
        for i, d in enumerate(dates)
    ])

    strategy = SMACrossoverStrategy(short_window=5, long_window=10)
    engine = BacktestEngine(strategy=strategy, initial_capital=1000000.0)

    result = engine.run(multi_stock_dataset, benchmark_df=nifty_df)
    assert result.benchmark_metrics is not None
    assert "total_return_pct" in result.benchmark_metrics
    summary = result.summary_table()
    assert "Benchmark (NIFTY)" in summary.columns

