"""
FinRL-X Strategy Adapter
Defines the standard strategy interface, configuration, and result objects
compatible with FinRL-Trading's modern architecture.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import pandas as pd


@dataclass
class StrategyConfig:
    """
    Configuration parameters for a trading strategy.
    Matches FinRL-Trading StrategyConfig.
    """
    name: str = "BaseStrategy"
    max_weight_per_stock: float = 0.20
    min_weight_per_stock: float = 0.05
    cash_reserve: float = 0.10
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    """
    Standard output produced by a FinRL-Trading compatible strategy.
    Contains target weights and execution metadata.
    """
    strategy_name: str
    weights: pd.DataFrame  # DataFrame with columns: ['symbol', 'weight'] or ticker index
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FinRLBaseStrategy:
    """
    Base Strategy class adhering to FinRL-Trading's strategy abstraction.
    All custom strategies (Rule-based, ML, or DRL) subclass this interface.
    """

    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None
    ) -> StrategyResult:
        """
        Generate target portfolio weights given input market/feature data.

        Args:
            data: Dictionary containing dataframes (e.g. 'prices', 'fundamentals', 'features').
            target_date: Optional execution date string ('YYYY-MM-DD').

        Returns:
            StrategyResult with target weights and metadata.
        """
        raise NotImplementedError("Subclasses must implement generate_weights()")
