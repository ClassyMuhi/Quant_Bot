"""
Backtesting Simulation Engine for Quant_Bot
Executes historical simulations with zero look-ahead bias, realistic Indian market friction,
solvency-enforced accounting, and benchmark comparison (Buy & Hold and NIFTY 50).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union, Tuple
import numpy as np
import pandas as pd

from .cost_model import CostModel, IndianEquityCostModel
from .accounting import PortfolioAccount
from .strategy import BacktestStrategy, Signal, SignalType
from .metrics import compute_performance_metrics

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Consolidated results of a backtest run."""
    strategy_name: str
    equity_df: pd.DataFrame
    trades_df: pd.DataFrame
    metrics: Dict[str, Any]
    buy_hold_equity_df: pd.DataFrame
    buy_hold_metrics: Dict[str, Any]
    benchmark_equity_df: Optional[pd.DataFrame] = None
    benchmark_metrics: Optional[Dict[str, Any]] = None

    def summary_table(self) -> pd.DataFrame:
        """Returns comparison table of Strategy vs Buy & Hold vs Benchmark."""
        data = {
            "Metric": [
                "Initial Capital (Rs)",
                "Final Capital (Rs)",
                "Total P&L (Rs)",
                "Realized P&L (Rs)",
                "Unrealized P&L (Rs)",
                "Total Return (%)",
                "CAGR (%)",
                "Annualized Volatility (%)",
                "Sharpe Ratio",
                "Sortino Ratio",
                "Max Drawdown (%)",
                "Max Drawdown (Days)",
                "Trading Days",
                "Short Period (<6M)",
                "Total Trades",
                "Win Rate (%)",
                "Profit Factor",
                "Portfolio Turnover (%)",
            ],
            self.strategy_name: [
                f"{self.metrics.get('initial_equity', 0):,.2f}",
                f"{self.metrics.get('final_equity', 0):,.2f}",
                f"{self.metrics.get('total_pnl', 0):,.2f}",
                f"{self.metrics.get('realized_pnl', 0):,.2f}",
                f"{self.metrics.get('unrealized_pnl', 0):,.2f}",
                f"{self.metrics.get('total_return_pct', 0):.2f}%",
                f"{self.metrics.get('cagr_pct', 0):.2f}%",
                f"{self.metrics.get('annualized_volatility_pct', 0):.2f}%",
                f"{self.metrics.get('sharpe_ratio', 0):.2f}",
                f"{self.metrics.get('sortino_ratio', 0):.2f}",
                f"{self.metrics.get('max_drawdown_pct', 0):.2f}%",
                f"{self.metrics.get('max_drawdown_duration_days', 0)}",
                f"{self.metrics.get('trading_days', 0)}",
                "YES (Warning)" if self.metrics.get("is_short_period") else "NO",
                f"{self.metrics.get('total_trades', 0)}",
                f"{self.metrics.get('win_rate_pct', 0):.2f}%",
                f"{self.metrics.get('profit_factor', 0):.2f}",
                f"{self.metrics.get('portfolio_turnover_pct', 0):.2f}%",
            ],
            "Buy & Hold (Universe)": [
                f"{self.buy_hold_metrics.get('initial_equity', 0):,.2f}",
                f"{self.buy_hold_metrics.get('final_equity', 0):,.2f}",
                f"{self.buy_hold_metrics.get('total_pnl', 0):,.2f}",
                f"{self.buy_hold_metrics.get('realized_pnl', 0):,.2f}",
                f"{self.buy_hold_metrics.get('unrealized_pnl', 0):,.2f}",
                f"{self.buy_hold_metrics.get('total_return_pct', 0):.2f}%",
                f"{self.buy_hold_metrics.get('cagr_pct', 0):.2f}%",
                f"{self.buy_hold_metrics.get('annualized_volatility_pct', 0):.2f}%",
                f"{self.buy_hold_metrics.get('sharpe_ratio', 0):.2f}",
                f"{self.buy_hold_metrics.get('sortino_ratio', 0):.2f}",
                f"{self.buy_hold_metrics.get('max_drawdown_pct', 0):.2f}%",
                f"{self.buy_hold_metrics.get('max_drawdown_duration_days', 0)}",
                f"{self.buy_hold_metrics.get('trading_days', 0)}",
                "YES (Warning)" if self.buy_hold_metrics.get("is_short_period") else "NO",
                f"{self.buy_hold_metrics.get('total_trades', 0)}",
                f"{self.buy_hold_metrics.get('win_rate_pct', 0):.2f}%",
                f"{self.buy_hold_metrics.get('profit_factor', 0):.2f}",
                f"{self.buy_hold_metrics.get('portfolio_turnover_pct', 0):.2f}%",
            ],
        }

        if self.benchmark_metrics:
            data["Benchmark (NIFTY)"] = [
                f"{self.benchmark_metrics.get('initial_equity', 0):,.2f}",
                f"{self.benchmark_metrics.get('final_equity', 0):,.2f}",
                f"{self.benchmark_metrics.get('total_pnl', 0):,.2f}",
                f"{self.benchmark_metrics.get('realized_pnl', 0):,.2f}",
                f"{self.benchmark_metrics.get('unrealized_pnl', 0):,.2f}",
                f"{self.benchmark_metrics.get('total_return_pct', 0):.2f}%",
                f"{self.benchmark_metrics.get('cagr_pct', 0):.2f}%",
                f"{self.benchmark_metrics.get('annualized_volatility_pct', 0):.2f}%",
                f"{self.benchmark_metrics.get('sharpe_ratio', 0):.2f}",
                f"{self.benchmark_metrics.get('sortino_ratio', 0):.2f}",
                f"{self.benchmark_metrics.get('max_drawdown_pct', 0):.2f}%",
                f"{self.benchmark_metrics.get('max_drawdown_duration_days', 0)}",
                f"{self.benchmark_metrics.get('trading_days', 0)}",
                "YES (Warning)" if self.benchmark_metrics.get("is_short_period") else "NO",
                "-",
                "-",
                "-",
                "-",
            ]

        return pd.DataFrame(data)

        return pd.DataFrame(data)


class BacktestEngine:
    """
    Modular, event-driven backtesting engine with strict elimination of look-ahead bias:
    Signals computed at end of day t execute on day t+1 at next available price (e.g. Open).
    """

    def __init__(
        self,
        strategy: BacktestStrategy,
        initial_capital: float = 1000000.0,
        cost_model: Optional[CostModel] = None,
        execution_price_col: str = "open",  # Execute at t+1 Open price
        valuation_price_col: str = "close", # Value portfolio at t Close price
        risk_free_rate: float = 0.06,       # 6% benchmark rate
        rebalance_cash_buffer: float = 0.02, # Keep 2% cash buffer to avoid over-allocation
        max_volume_participation_pct: Optional[float] = None, # Optional volume limit (e.g. 0.10 for 10% volume)
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.cost_model = cost_model or IndianEquityCostModel()
        self.execution_price_col = execution_price_col
        self.valuation_price_col = valuation_price_col
        self.risk_free_rate = risk_free_rate
        self.rebalance_cash_buffer = rebalance_cash_buffer
        self.max_volume_participation_pct = max_volume_participation_pct

    def _align_market_data(
        self,
        data: Dict[str, pd.DataFrame],
    ) -> Tuple[List[str], Dict[str, pd.DataFrame]]:
        """
        Sorts each symbol's data chronologically and extracts unified trading calendar dates.
        """
        cleaned_data: Dict[str, pd.DataFrame] = {}
        all_dates = set()

        for sym, df in data.items():
            if df.empty:
                continue
            d = df.copy()
            d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
            d = d.sort_values(by="date").reset_index(drop=True)
            cleaned_data[sym] = d
            all_dates.update(d["date"].unique())

        sorted_dates = sorted(list(all_dates))
        return sorted_dates, cleaned_data

    def run(
        self,
        data: Dict[str, pd.DataFrame],
        benchmark_df: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        """
        Executes backtest over provided dataset.

        Args:
            data: Mapping of symbol -> DataFrame containing at least ['date', 'open', 'close'].
            benchmark_df: Optional DataFrame for NIFTY benchmark with ['date', 'close'].
        """
        trading_dates, clean_data = self._align_market_data(data)
        if len(trading_dates) < 2:
            raise ValueError("Insufficient trading dates for backtesting (minimum 2 required).")

        account = PortfolioAccount(
            initial_cash=self.initial_capital,
            cost_model=self.cost_model,
        )

        symbols = list(clean_data.keys())
        pending_signals: Dict[str, Signal] = {}

        # Day-by-day simulation loop
        for i, date_str in enumerate(trading_dates):
            # 1. Day t+1: Execute pending signals generated on day t at today's execution price
            if pending_signals:
                self._execute_pending_signals(
                    account=account,
                    date=date_str,
                    signals=pending_signals,
                    market_data=clean_data,
                )
                pending_signals = {}

            # 2. End of Day: Mark-to-market portfolio snapshot using today's valuation price (close)
            today_close_prices: Dict[str, float] = {}
            for sym in symbols:
                sym_df = clean_data[sym]
                row = sym_df[sym_df["date"] == date_str]
                if not row.empty:
                    today_close_prices[sym] = float(row[self.valuation_price_col].iloc[0])

            account.record_daily_snapshot(date=date_str, current_prices=today_close_prices)

            # 3. Generate signals for tomorrow (t+1) using data strictly up to today (t)
            if i < len(trading_dates) - 1:
                # Slice historical data up to current date (zero look-ahead bias)
                history_slice: Dict[str, pd.DataFrame] = {}
                for sym, df in clean_data.items():
                    history_slice[sym] = df[df["date"] <= date_str].copy()

                pending_signals = self.strategy.generate_signals(
                    current_date=date_str,
                    historical_data=history_slice,
                )

        # Compute Strategy Metrics
        strategy_equity_df = account.to_equity_dataframe()
        trades_df = account.to_trades_dataframe()
        strategy_metrics = compute_performance_metrics(
            equity_df=strategy_equity_df,
            trades=account.trades,
            risk_free_rate=self.risk_free_rate,
            initial_capital=self.initial_capital,
            positions=account.positions,
            current_prices=today_close_prices,
        )

        # Compute Buy & Hold Benchmark of Universe
        buy_hold_equity_df, buy_hold_metrics = self._simulate_buy_and_hold(
            trading_dates=trading_dates,
            clean_data=clean_data,
        )

        # Compute External Benchmark (e.g. NIFTY 50) if supplied
        bench_equity_df, bench_metrics = None, None
        if benchmark_df is not None and not benchmark_df.empty:
            bench_equity_df, bench_metrics = self._evaluate_benchmark_series(
                trading_dates=trading_dates,
                benchmark_df=benchmark_df,
            )

        return BacktestResult(
            strategy_name=self.strategy.name,
            equity_df=strategy_equity_df,
            trades_df=trades_df,
            metrics=strategy_metrics,
            buy_hold_equity_df=buy_hold_equity_df,
            buy_hold_metrics=buy_hold_metrics,
            benchmark_equity_df=bench_equity_df,
            benchmark_metrics=bench_metrics,
        )

    def _execute_pending_signals(
        self,
        account: PortfolioAccount,
        date: str,
        signals: Dict[str, Signal],
        market_data: Dict[str, pd.DataFrame],
    ) -> None:
        """
        Executes orders according to signals:
        - First executes SELL orders to liberate cash.
        - Then executes BUY orders with available capital.
        - Enforces liquidity constraints if max_volume_participation_pct is set.
        """
        sell_orders = []
        buy_orders = []

        for sym, sig in signals.items():
            if sym not in market_data:
                continue
            sym_df = market_data[sym]
            row = sym_df[sym_df["date"] == date]
            if row.empty:
                continue

            exec_price = float(row[self.execution_price_col].iloc[0])
            if exec_price <= 0:
                continue

            if sig.signal_type == SignalType.SELL:
                sell_orders.append((sym, sig, exec_price, row))
            elif sig.signal_type == SignalType.BUY:
                buy_orders.append((sym, sig, exec_price, row))

        # 1. Execute SELLs first
        for sym, sig, price, row in sell_orders:
            pos = account.get_position(sym)
            if pos.quantity > 0:
                if sig.target_weight is not None and sig.target_weight > 0:
                    # Partial rebalance sell
                    current_equity = account.get_total_equity({sym: price})
                    target_value = current_equity * sig.target_weight
                    target_qty = int(target_value // price)
                    sell_qty = pos.quantity - target_qty
                else:
                    # Full liquidation
                    sell_qty = pos.quantity

                if sell_qty > 0:
                    # Apply volume constraint / partial fill if enabled
                    if self.max_volume_participation_pct is not None and "volume" in row.columns:
                        day_vol = float(row["volume"].iloc[0])
                        if day_vol > 0:
                            max_vol_fill = max(1, int(day_vol * self.max_volume_participation_pct))
                            sell_qty = min(sell_qty, max_vol_fill)
                    account.execute_order(date, sym, "SELL", sell_qty, price)

        # 2. Execute BUYs
        if buy_orders:
            for sym, sig, price, row in buy_orders:
                pos = account.get_position(sym)
                if sig.target_weight is not None:
                    # Continuous weight target
                    current_equity = account.get_total_equity({sym: price})
                    target_val = current_equity * sig.target_weight * (1.0 - self.rebalance_cash_buffer)
                    target_qty = int(target_val // price)
                    buy_qty = target_qty - pos.quantity
                else:
                    # Discrete BUY signal: allocate equal slice of available cash
                    slice_cash = account.cash / float(len(buy_orders))
                    buy_qty = int((slice_cash * (1.0 - self.rebalance_cash_buffer)) // price)

                if buy_qty > 0:
                    # Apply volume constraint / partial fill if enabled
                    if self.max_volume_participation_pct is not None and "volume" in row.columns:
                        day_vol = float(row["volume"].iloc[0])
                        if day_vol > 0:
                            max_vol_fill = max(1, int(day_vol * self.max_volume_participation_pct))
                            buy_qty = min(buy_qty, max_vol_fill)
                    account.execute_order(date, sym, "BUY", buy_qty, price)

    def _simulate_buy_and_hold(
        self,
        trading_dates: List[str],
        clean_data: Dict[str, pd.DataFrame],
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Simulates an equal-weight Buy & Hold benchmark over the stock universe.
        Purchased on Day 1 Open and held through Day N Close.
        """
        bh_account = PortfolioAccount(
            initial_cash=self.initial_capital,
            cost_model=self.cost_model,
        )

        first_date = trading_dates[0]
        symbols = list(clean_data.keys())
        alloc_per_sym = (self.initial_capital * 0.98) / float(len(symbols))

        # Day 1: Purchase equal weights of all universe stocks
        for sym in symbols:
            df = clean_data[sym]
            row = df[df["date"] == first_date]
            if not row.empty:
                open_price = float(row[self.execution_price_col].iloc[0])
                qty = int(alloc_per_sym // open_price)
                if qty > 0:
                    bh_account.execute_order(first_date, sym, "BUY", qty, open_price)

        # Mark-to-market daily
        for d in trading_dates:
            prices: Dict[str, float] = {}
            for sym in symbols:
                df = clean_data[sym]
                row = df[df["date"] == d]
                if not row.empty:
                    prices[sym] = float(row[self.valuation_price_col].iloc[0])
            bh_account.record_daily_snapshot(d, prices)

        bh_equity_df = bh_account.to_equity_dataframe()
        bh_metrics = compute_performance_metrics(
            equity_df=bh_equity_df,
            trades=bh_account.trades,
            risk_free_rate=self.risk_free_rate,
            initial_capital=self.initial_capital,
            positions=bh_account.positions,
            current_prices=prices,
        )
        return bh_equity_df, bh_metrics

    def _evaluate_benchmark_series(
        self,
        trading_dates: List[str],
        benchmark_df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Simulates a benchmark index (e.g. NIFTY 50) scaled to initial capital.
        """
        b_df = benchmark_df.copy()
        b_df["date"] = pd.to_datetime(b_df["date"]).dt.strftime("%Y-%m-%d")
        b_df = b_df.sort_values(by="date").reset_index(drop=True)

        # Filter to matching trading dates
        b_df = b_df[b_df["date"].isin(trading_dates)].reset_index(drop=True)
        if b_df.empty:
            return pd.DataFrame(), {}

        first_close = float(b_df["close"].iloc[0])
        b_df["total_equity"] = (b_df["close"] / first_close) * self.initial_capital
        b_df["daily_return"] = b_df["total_equity"].pct_change().fillna(0.0)

        metrics = compute_performance_metrics(
            equity_df=b_df,
            trades=[],
            risk_free_rate=self.risk_free_rate,
            initial_capital=self.initial_capital,
        )
        return b_df, metrics
        return b_df, metrics
