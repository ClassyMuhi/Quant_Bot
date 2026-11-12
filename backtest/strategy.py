"""
Strategy Interface & Built-In Signal Generators for Quant_Bot Backtest Engine
Supports discrete BUY / SELL / HOLD signals, continuous target weights,
and seamless compatibility with FinRLBaseStrategy.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import pandas as pd

from finrl_adapter.strategy import FinRLBaseStrategy, StrategyConfig


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    """Actionable signal emitted by a strategy for an individual symbol."""
    symbol: str
    date: str
    signal_type: SignalType
    target_weight: Optional[float] = None
    confidence: float = 1.0


class BacktestStrategy(ABC):
    """
    Abstract base class for all backtesting strategies.
    Receives market state at bar t and produces execution signals for bar t+1.
    """

    def __init__(self, name: str = "BaseStrategy"):
        self.name = name

    @abstractmethod
    def generate_signals(
        self,
        current_date: str,
        historical_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Signal]:
        """
        Evaluate market data up to current_date and emit signals.

        Args:
            current_date: Evaluation date string 'YYYY-MM-DD'.
            historical_data: Dictionary mapping symbol -> DataFrame of data available up to current_date.

        Returns:
            Dictionary mapping symbol -> Signal.
        """
        pass


class SMACrossoverStrategy(BacktestStrategy):
    """
    Moving Average Crossover Strategy:
    - BUY when short SMA crosses strictly above long SMA.
    - SELL when short SMA crosses strictly below long SMA.
    - HOLD otherwise.
    """

    def __init__(
        self,
        short_window: int = 10,
        long_window: int = 20,
        name: Optional[str] = None,
    ):
        strategy_name = name or f"SMA_Crossover_{short_window}_{long_window}"
        super().__init__(name=strategy_name)
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(
        self,
        current_date: str,
        historical_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Signal]:
        signals: Dict[str, Signal] = {}

        for sym, df in historical_data.items():
            if df.empty or len(df) < self.long_window + 1:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.HOLD)
                continue

            # Check if columns pre-exist (from Gold features) or compute
            short_col = f"sma_{self.short_window}"
            long_col = f"sma_{self.long_window}"

            if short_col in df.columns and long_col in df.columns:
                sma_short = df[short_col]
                sma_long = df[long_col]
            else:
                sma_short = df["close"].rolling(self.short_window).mean()
                sma_long = df["close"].rolling(self.long_window).mean()

            curr_short = sma_short.iloc[-1]
            curr_long = sma_long.iloc[-1]
            prev_short = sma_short.iloc[-2]
            prev_long = sma_long.iloc[-2]

            if pd.isna(curr_short) or pd.isna(curr_long) or pd.isna(prev_short) or pd.isna(prev_long):
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.HOLD)
                continue

            # Bullish crossover
            if prev_short <= prev_long and curr_short > curr_long:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.BUY)
            # Bearish crossover
            elif prev_short >= prev_long and curr_short < curr_long:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.SELL)
            else:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.HOLD)

        return signals


class RSIMeanReversionStrategy(BacktestStrategy):
    """
    RSI Mean Reversion Strategy:
    - BUY when RSI drops below oversold threshold (default 30).
    - SELL when RSI climbs above overbought threshold (default 70).
    - HOLD otherwise.
    """

    def __init__(
        self,
        rsi_lower: float = 30.0,
        rsi_upper: float = 70.0,
        period: int = 14,
        name: Optional[str] = None,
    ):
        strategy_name = name or f"RSI_MeanReversion_{int(rsi_lower)}_{int(rsi_upper)}"
        super().__init__(name=strategy_name)
        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.period = period

    def generate_signals(
        self,
        current_date: str,
        historical_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Signal]:
        signals: Dict[str, Signal] = {}

        for sym, df in historical_data.items():
            if df.empty or len(df) < self.period + 1:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.HOLD)
                continue

            rsi_val = df["rsi_14"].iloc[-1] if "rsi_14" in df.columns else None
            if rsi_val is None or pd.isna(rsi_val):
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.HOLD)
                continue

            if rsi_val <= self.rsi_lower:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.BUY)
            elif rsi_val >= self.rsi_upper:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.SELL)
            else:
                signals[sym] = Signal(symbol=sym, date=current_date, signal_type=SignalType.HOLD)

        return signals


class FinRLStrategyAdapter(BacktestStrategy):
    """
    Adapter enabling any FinRLBaseStrategy to run natively inside the Backtest Engine.
    Converts strategy target weights into BUY / SELL rebalancing signals.
    """

    def __init__(self, finrl_strategy: FinRLBaseStrategy, name: Optional[str] = None):
        strategy_name = name or f"FinRL_{finrl_strategy.config.name}"
        super().__init__(name=strategy_name)
        self.finrl_strategy = finrl_strategy

    def generate_signals(
        self,
        current_date: str,
        historical_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Signal]:
        # Consolidate historical prices into FinRL multi-stock data contract
        prices_list = []
        for sym, df in historical_data.items():
            if not df.empty:
                prices_list.append(df)

        if not prices_list:
            return {}

        prices_df = pd.concat(prices_list, ignore_index=True)
        data_packet = {"prices": prices_df}

        # Generate target weights from FinRL strategy
        res = self.finrl_strategy.generate_weights(data_packet, target_date=current_date)
        weights_df = res.weights

        signals: Dict[str, Signal] = {}
        for _, row in weights_df.iterrows():
            sym = str(row["symbol"]).strip().upper()
            w = float(row["weight"])

            if w > 0:
                sig_type = SignalType.BUY
            else:
                sig_type = SignalType.SELL

            signals[sym] = Signal(
                symbol=sym,
                date=current_date,
                signal_type=sig_type,
                target_weight=w,
            )

        return signals

