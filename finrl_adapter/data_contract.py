"""
Data Contract & Validation for FinRL Adapter
Defines and validates input data structures expected by FinRL strategies.
"""

from typing import Dict, List, Optional
import pandas as pd


REQUIRED_PRICE_COLUMNS = ["date", "symbol", "close"]
OPTIONAL_PRICE_COLUMNS = ["open", "high", "low", "volume", "adj_close"]


def validate_market_data(data: Dict[str, pd.DataFrame]) -> bool:
    """
    Validates that the input data dictionary satisfies the required FinRL data contract.

    Expected Structure:
        data = {
            'prices': pd.DataFrame with ['date', 'symbol', 'close', ...],
            'features': Optional[pd.DataFrame]
        }
    """
    if not isinstance(data, dict):
        raise TypeError("Input data must be a dictionary of DataFrames.")

    if "prices" not in data:
        raise ValueError("Data dictionary must contain a 'prices' DataFrame.")

    prices_df = data["prices"]
    if not isinstance(prices_df, pd.DataFrame):
        raise TypeError("'prices' must be a pandas DataFrame.")

    missing_cols = [col for col in REQUIRED_PRICE_COLUMNS if col not in prices_df.columns]
    if missing_cols:
        raise ValueError(f"'prices' DataFrame is missing required columns: {missing_cols}")

    return True
