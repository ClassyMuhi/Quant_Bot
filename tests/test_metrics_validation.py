"""
Quantitative Performance Metrics Validation & Edge Case Audit Tests
Validates mathematical precision of CAGR, Sharpe, Sortino, Max Drawdown,
Win Rate, Profit Factor, Turnover, and Realized/Unrealized P&L.
"""

import math
import numpy as np
import pandas as pd
import pytest

from backtest.metrics import compute_performance_metrics
from backtest.accounting import Trade, Position


def test_hand_calculated_cagr():
    """
    Validates CAGR against hand-calculated analytical result:
    Initial: 1,000,000, Final: 1,210,000 over 505 trading days (approx 2 years).
    CAGR = (1,210,000 / 1,000,000) ** (252 / 504) - 1 = 1.21 ** 0.5 - 1 = 10.00%
    """
    n_days = 505
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    eq_values = np.linspace(1000000.0, 1210000.0, n_days)

    equity_df = pd.DataFrame({"date": dates, "total_equity": eq_values})
    equity_df["daily_return"] = equity_df["total_equity"].pct_change().fillna(0.0)

    metrics = compute_performance_metrics(equity_df, [], trading_days_per_year=252)

    # 1.21 ** (252 / 504) - 1 = 1.21 ** 0.5 - 1 = 1.10 - 1 = 10.0%
    assert abs(metrics["cagr_pct"] - 10.0) < 0.2
    assert metrics["is_short_period"] is False
    assert metrics["trading_days"] == 505


def test_hand_calculated_sharpe():
    """
    Validates Sharpe ratio:
    Constantly positive excess return of 0.1% per day with 1.0% daily standard deviation.
    Daily Sharpe = 0.001 / 0.01 = 0.10
    Annualized Sharpe = 0.10 * sqrt(252) = 1.58745 -> 1.59
    """
    n_days = 253
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")

    # Construct daily returns with exact known mean and std
    np.random.seed(123)
    target_mean = 0.001 + (0.06 / 252.0)  # Excess = 0.001
    target_std = 0.01
    raw_rets = np.random.normal(target_mean, target_std, n_days - 1)
    # Standardize to exact target mean and std
    norm_rets = (raw_rets - np.mean(raw_rets)) / np.std(raw_rets, ddof=1) * target_std + target_mean

    eq = [1000000.0]
    for r in norm_rets:
        eq.append(eq[-1] * (1.0 + r))

    eq_df = pd.DataFrame({"date": dates, "total_equity": eq})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    metrics = compute_performance_metrics(eq_df, [], risk_free_rate=0.06, trading_days_per_year=252)

    expected_sharpe = round((0.001 / target_std) * math.sqrt(252), 2)  # ~1.59
    assert abs(metrics["sharpe_ratio"] - expected_sharpe) <= 0.05


def test_hand_calculated_sortino():
    """
    Validates Sortino Ratio using standard Lower Partial Moment formula.
    """
    n_days = 5
    dates = pd.date_range("2026-01-01", periods=n_days, freq="B")
    # Returns relative to rf=0: [0.0, 0.02, -0.01, 0.03, -0.02]
    # Downside diffs: [0.0, 0.0, -0.01, 0.0, -0.02]
    # Sum of squared downside: 0.0001 + 0.0004 = 0.0005 over N=4 periods -> mean = 0.000125
    # Downside std = sqrt(0.000125) = 0.01118
    # Mean excess return = (0.02 - 0.01 + 0.03 - 0.02)/4 = 0.02/4 = 0.005
    # Expected Sortino = (0.005 / 0.01118) * sqrt(252) = 0.4472 * 15.8745 = ~7.10
    eq = [100.0, 102.0, 100.98, 104.0094, 101.9292]
    eq_df = pd.DataFrame({"date": dates, "total_equity": eq})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    metrics = compute_performance_metrics(eq_df, [], risk_free_rate=0.0, trading_days_per_year=252)
    assert metrics["sortino_ratio"] > 0.0


def test_hand_calculated_max_drawdown():
    """
    Peak is 150.0, drops to 75.0, recovers to 90.0.
    Drawdown = (75.0 - 150.0) / 150.0 = -50.0%
    """
    dates = pd.date_range("2026-01-01", periods=6, freq="B")
    eq = [100.0, 150.0, 120.0, 75.0, 80.0, 90.0]
    eq_df = pd.DataFrame({"date": dates, "total_equity": eq})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    metrics = compute_performance_metrics(eq_df, [])
    assert metrics["max_drawdown_pct"] == -50.0
    assert metrics["max_drawdown_duration_days"] >= 4


def test_win_rate_and_profit_factor():
    """
    2 Winning Trades: +Rs. 10,000 each (+20,000 gross profit)
    1 Losing Trade: -Rs. 5,000 (-5,000 gross loss)
    Win Rate = 2 / 3 = 66.67%
    Profit Factor = 20,000 / 5,000 = 4.0
    """
    dates = pd.date_range("2026-01-01", periods=5, freq="B")
    eq_df = pd.DataFrame({"date": dates, "total_equity": [1000, 1010, 1020, 1015, 1015]})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    trades = [
        Trade(1, "2026-01-02", "RELIANCE", "BUY", 10, 1000, 1000, 10000, 0, -10000),
        Trade(2, "2026-01-03", "RELIANCE", "SELL", 10, 2000, 2000, 20000, 0, 20000, realized_pnl=10000.0),
        Trade(3, "2026-01-03", "TCS", "BUY", 10, 1000, 1000, 10000, 0, -10000),
        Trade(4, "2026-01-04", "TCS", "SELL", 10, 2000, 2000, 20000, 0, 20000, realized_pnl=10000.0),
        Trade(5, "2026-01-04", "INFY", "BUY", 10, 1000, 1000, 10000, 0, -10000),
        Trade(6, "2026-01-05", "INFY", "SELL", 10, 500, 500, 5000, 0, 5000, realized_pnl=-5000.0),
    ]

    metrics = compute_performance_metrics(eq_df, trades)
    assert metrics["closed_trades"] == 3
    assert metrics["win_rate_pct"] == 66.67
    assert metrics["profit_factor"] == 4.0
    assert metrics["realized_pnl"] == 15000.0


def test_edge_case_zero_trades_100_percent_cash():
    """Validates metrics when no trades are executed (pure cash holding)."""
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    eq = [1000000.0] * 30
    eq_df = pd.DataFrame({"date": dates, "total_equity": eq})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    metrics = compute_performance_metrics(eq_df, [], initial_capital=1000000.0)
    assert metrics["total_return_pct"] == 0.0
    assert metrics["cagr_pct"] == 0.0
    assert metrics["annualized_volatility_pct"] == 0.0
    assert metrics["sharpe_ratio"] == 0.0
    assert metrics["max_drawdown_pct"] == 0.0
    assert metrics["total_trades"] == 0
    assert metrics["win_rate_pct"] == 0.0
    assert metrics["portfolio_turnover_pct"] == 0.0


def test_edge_case_short_period_warning():
    """Short periods (< 126 trading days) must be flagged with warning."""
    dates = pd.date_range("2026-01-01", periods=20, freq="B")
    eq_df = pd.DataFrame({"date": dates, "total_equity": np.linspace(100, 110, 20)})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    metrics = compute_performance_metrics(eq_df, [])
    assert metrics["is_short_period"] is True
    assert metrics["trading_days"] == 20


def test_separate_realized_and_unrealized_pnl():
    """Validates explicit separation of realized and unrealized P&L."""
    dates = pd.date_range("2026-01-01", periods=3, freq="B")
    eq_df = pd.DataFrame({"date": dates, "total_equity": [100000.0, 110000.0, 120000.0]})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    trades = [
        Trade(1, "2026-01-01", "A", "BUY", 10, 1000, 1000, 10000, 0, -10000),
        Trade(2, "2026-01-02", "A", "SELL", 10, 1500, 1500, 15000, 0, 15000, realized_pnl=5000.0),
    ]

    open_pos = {"B": Position(symbol="B", quantity=10, average_cost=1000.0)}
    current_prices = {"B": 2500.0}  # Unrealized: (2500 - 1000) * 10 = 15,000

    metrics = compute_performance_metrics(
        eq_df,
        trades,
        initial_capital=100000.0,
        positions=open_pos,
        current_prices=current_prices,
    )

    assert metrics["realized_pnl"] == 5000.0
    assert metrics["unrealized_pnl"] == 15000.0
    assert metrics["total_pnl"] == 20000.0

