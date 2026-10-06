"""
Portfolio Allocator
Converts raw strategy weights into clean portfolio target allocations
with explicit cash balances, position caps, and normalization.
"""

from typing import Dict, Optional
import pandas as pd


def compute_portfolio_allocation(
    weights_df: pd.DataFrame,
    symbol_col: str = "symbol",
    weight_col: str = "weight",
    cash_symbol: str = "CASH",
    max_weight_per_stock: Optional[float] = None,
) -> Dict[str, float]:
    """
    Normalizes stock weights and calculates the residual CASH allocation.

    Example Output:
        {
            "RELIANCE": 0.20,
            "TCS": 0.15,
            "INFY": 0.10,
            "CASH": 0.55
        }
    """
    if weights_df.empty:
        return {cash_symbol: 1.0}

    df = weights_df.copy()

    # Filter out non-positive weights
    df = df[df[weight_col] > 0]
    if df.empty:
        return {cash_symbol: 1.0}

    # Apply maximum weight cap per asset if specified
    if max_weight_per_stock:
        df[weight_col] = df[weight_col].clip(upper=max_weight_per_stock)

    # Calculate allocated stock weight
    total_stock_weight = float(df[weight_col].sum())

    # If sum > 1.0, normalize down to 1.0
    if total_stock_weight > 1.0:
        df[weight_col] = df[weight_col] / total_stock_weight
        total_stock_weight = 1.0

    allocations: Dict[str, float] = {}
    for _, row in df.iterrows():
        sym = str(row[symbol_col]).strip().upper()
        allocations[sym] = round(float(row[weight_col]), 4)

    # Assign residual weight to Cash
    cash_weight = max(0.0, 1.0 - total_stock_weight)
    allocations[cash_symbol] = round(cash_weight, 4)

    return allocations
