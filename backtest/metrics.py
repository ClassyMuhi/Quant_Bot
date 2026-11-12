"""
Performance & Risk Metrics for Quant_Bot Backtest Engine
Computes CAGR, Sharpe Ratio, Sortino Ratio, Maximum Drawdown, Win Rate,
Profit Factor, and Portfolio Turnover.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from .accounting import Trade


def compute_performance_metrics(
    equity_df: pd.DataFrame,
    trades: List[Trade],
    risk_free_rate: float = 0.06,  # Standard Indian 91-day T-Bill rate (~6%)
    trading_days_per_year: int = 252,
) -> Dict[str, Any]:
    """
    Computes standard quantitative performance metrics from equity curve and trades.

    Args:
        equity_df: DataFrame with ['date', 'total_equity', 'daily_return']
        trades: List of executed Trade objects
        risk_free_rate: Annualized risk-free benchmark rate (default 6.0%)
        trading_days_per_year: Annual trading sessions (default 252)

    Returns:
        Dictionary of formatted performance statistics.
    """
    if equity_df.empty or len(equity_df) < 2:
        return {
            "initial_equity": 0.0,
            "final_equity": 0.0,
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "annualized_volatility_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_duration_days": 0,
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "portfolio_turnover_pct": 0.0,
        }

    eq = equity_df["total_equity"].values
    initial_eq = float(eq[0])
    final_eq = float(eq[-1])
    n_days = len(eq)

    # 1. Total Return & CAGR
    total_return = (final_eq - initial_eq) / initial_eq
    years = n_days / float(trading_days_per_year)
    if years > 0 and final_eq > 0:
        cagr = (final_eq / initial_eq) ** (1.0 / years) - 1.0
    else:
        cagr = 0.0

    # 2. Daily returns & Volatility
    daily_returns = equity_df["daily_return"].iloc[1:].values  # Skip first day 0.0
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        daily_std = np.std(daily_returns, ddof=1)
        annualized_vol = daily_std * np.sqrt(trading_days_per_year)
    else:
        daily_std = 0.0
        annualized_vol = 0.0

    # 3. Sharpe Ratio
    daily_rf = risk_free_rate / float(trading_days_per_year)
    excess_returns = daily_returns - daily_rf
    if daily_std > 0:
        sharpe = (np.mean(excess_returns) / daily_std) * np.sqrt(trading_days_per_year)
    else:
        sharpe = 0.0

    # 4. Sortino Ratio (Downside deviation only)
    downside_returns = excess_returns[excess_returns < 0]
    if len(downside_returns) > 0:
        downside_std = np.sqrt(np.mean(downside_returns ** 2))
        sortino = ((np.mean(excess_returns) * trading_days_per_year) / (downside_std * np.sqrt(trading_days_per_year))) if downside_std > 0 else 0.0
    else:
        # If no down days exist, Sortino is exceptionally high for positive return
        sortino = 99.0 if np.mean(excess_returns) > 0 else 0.0

    # 5. Maximum Drawdown & Duration
    peak_series = np.maximum.accumulate(eq)
    drawdowns = (eq - peak_series) / peak_series
    max_dd = float(np.min(drawdowns))  # Negative number

    # Drawdown duration in trading days
    max_duration = 0
    current_duration = 0
    for dd in drawdowns:
        if dd < 0:
            current_duration += 1
            if current_duration > max_duration:
                max_duration = current_duration
        else:
            current_duration = 0

    # 6. Trade Analysis (Win Rate, Profit Factor)
    closed_trades = [t for t in trades if t.order_type == "SELL"]
    total_trades = len(trades)
    winning_trades = [t for t in closed_trades if t.realized_pnl > 0]
    losing_trades = [t for t in closed_trades if t.realized_pnl < 0]

    if closed_trades:
        win_rate = len(winning_trades) / float(len(closed_trades))
        gross_profit = sum(t.realized_pnl for t in winning_trades)
        gross_loss = abs(sum(t.realized_pnl for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    else:
        win_rate = 0.0
        profit_factor = 0.0

    # 7. Portfolio Turnover
    total_traded_volume = sum(t.gross_value for t in trades)
    avg_equity = float(np.mean(eq))
    turnover = (total_traded_volume / (2.0 * avg_equity)) if avg_equity > 0 else 0.0

    return {
        "initial_equity": round(initial_eq, 2),
        "final_equity": round(final_eq, 2),
        "total_return_pct": round(total_return * 100.0, 2),
        "cagr_pct": round(cagr * 100.0, 2),
        "annualized_volatility_pct": round(annualized_vol * 100.0, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "max_drawdown_duration_days": int(max_duration),
        "total_trades": total_trades,
        "closed_trades": len(closed_trades),
        "win_rate_pct": round(win_rate * 100.0, 2),
        "profit_factor": round(profit_factor, 2),
        "portfolio_turnover_pct": round(turnover * 100.0, 2),
    }
