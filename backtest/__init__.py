"""
Backtesting Engine Package for Quant_Bot
Provides event-driven historical simulation with zero look-ahead bias,
Indian statutory transaction costs and taxes, solvency-enforced accounting,
and benchmark comparative analysis.
"""

from .cost_model import (
    CostModel,
    TradeCost,
    IndianEquityCostModel,
    FlatPercentageCostModel,
    ZeroCostModel,
)
from .accounting import (
    Trade,
    Position,
    PortfolioAccount,
)
from .strategy import (
    SignalType,
    Signal,
    BacktestStrategy,
    SMACrossoverStrategy,
    RSIMeanReversionStrategy,
    FinRLStrategyAdapter,
)
from .metrics import (
    compute_performance_metrics,
)
from .engine import (
    BacktestEngine,
    BacktestResult,
)

__all__ = [
    "CostModel",
    "TradeCost",
    "IndianEquityCostModel",
    "FlatPercentageCostModel",
    "ZeroCostModel",
    "Trade",
    "Position",
    "PortfolioAccount",
    "SignalType",
    "Signal",
    "BacktestStrategy",
    "SMACrossoverStrategy",
    "RSIMeanReversionStrategy",
    "FinRLStrategyAdapter",
    "compute_performance_metrics",
    "BacktestEngine",
    "BacktestResult",
]

