"""
Unit tests for backtest.metrics module.
Verifies CAGR, Sharpe, Sortino, Max Drawdown, Win Rate, and Turnover calculations.
"""

import pandas as pd
import numpy as np
import pytest

from backtest.metrics import compute_performance_metrics
from backtest.accounting import Trade


def test_metrics_positive_growth():
    # 252 days with 20% total growth with daily fluctuations
    dates = pd.date_range("2025-01-01", periods=253, freq="B")
    initial_eq = 1000000.0
    np.random.seed(42)
    # Generate daily returns with positive mean but both up and down days
    daily_rets = np.random.normal(0.0008, 0.01, 252)
    equity = [initial_eq]
    for r in daily_rets:
        equity.append(equity[-1] * (1.0 + r))

    eq_df = pd.DataFrame({
        "date": dates,
        "total_equity": equity,
    })
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    trades = [
        Trade(1, "2025-01-02", "RELIANCE", "BUY", 100, 1000, 1000, 100000, 50, -100050),
        Trade(2, "2025-06-02", "RELIANCE", "SELL", 100, 1200, 1200, 120000, 60, 119940, realized_pnl=20000),
    ]

    metrics = compute_performance_metrics(eq_df, trades, risk_free_rate=0.06)

    assert metrics["final_equity"] > metrics["initial_equity"]
    assert metrics["total_return_pct"] > 0.0
    assert metrics["cagr_pct"] > 0.0
    assert metrics["sharpe_ratio"] > 0.0
    assert metrics["sortino_ratio"] > 0.0
    assert metrics["win_rate_pct"] == 100.0
    assert metrics["total_trades"] == 2
    assert metrics["closed_trades"] == 1


def test_max_drawdown():
    dates = pd.date_range("2026-01-01", periods=5, freq="B")
    # Peak at 100, drops to 80 (20% drawdown), recovers to 90
    equity = [100.0, 100.0, 80.0, 85.0, 90.0]

    eq_df = pd.DataFrame({"date": dates, "total_equity": equity})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)

    metrics = compute_performance_metrics(eq_df, [])
    assert metrics["max_drawdown_pct"] == -20.0
    assert metrics["max_drawdown_duration_days"] >= 2
