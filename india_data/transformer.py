"""
FinRL Data Transformation Engine for Indian Equities.
Transforms raw single-stock historical series into multi-asset long format
satisfying the Phase 1 FinRL-X data contract.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd

from india_data.config import PROCESSED_DATA_DIR, REQUIRED_LONG_COLUMNS
from india_data.universe import to_canonical_symbol
from india_data.validator import validate_market_dataframe
from finrl_adapter.data_contract import validate_market_data


def to_finrl_format(
    data_map: Union[Dict[str, pd.DataFrame], List[pd.DataFrame], pd.DataFrame],
    validate: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Transform raw individual stock data into the long-format schema expected by FinRL adapters.

    Expected Schema:
        date | symbol | open | high | low | close | volume

    Args:
        data_map: One of:
            - Dictionary mapping canonical symbol -> DataFrame (OHLCV).
            - List of DataFrames (with 'symbol' or index).
            - Single DataFrame with 'symbol' column.
        validate: If True, validates data against both India validator and FinRL data contract.

    Returns:
        Dictionary adhering to FinRL data contract:
            {
                "prices": pd.DataFrame (long format),
                "features": pd.DataFrame (empty DataFrame for Phase 2)
            }
    """
    dfs_to_combine: List[pd.DataFrame] = []

    if isinstance(data_map, dict):
        for sym_key, df in data_map.items():
            if df is None or df.empty:
                continue
            canonical = to_canonical_symbol(sym_key)
            stock_df = df.copy()
            stock_df["symbol"] = canonical
            dfs_to_combine.append(stock_df)

    elif isinstance(data_map, list):
        for df in data_map:
            if df is None or df.empty:
                continue
            stock_df = df.copy()
            if "symbol" in stock_df.columns:
                stock_df["symbol"] = stock_df["symbol"].apply(to_canonical_symbol)
            dfs_to_combine.append(stock_df)

    elif isinstance(data_map, pd.DataFrame):
        if data_map.empty:
            raise ValueError("Input DataFrame is empty.")
        stock_df = data_map.copy()
        if "symbol" in stock_df.columns:
            stock_df["symbol"] = stock_df["symbol"].apply(to_canonical_symbol)
        dfs_to_combine.append(stock_df)

    else:
        raise TypeError(f"Unsupported data type for data_map: {type(data_map).__name__}")

    if not dfs_to_combine:
        raise ValueError("No valid price data provided to transform.")

    # Combine into unified DataFrame
    combined_df = pd.concat(dfs_to_combine, ignore_index=True)

    # Ensure required columns are present
    missing_cols = [col for col in REQUIRED_LONG_COLUMNS if col not in combined_df.columns]
    if missing_cols:
        raise ValueError(f"Combined data is missing required columns: {missing_cols}")

    # Reorder columns to standard long schema
    cols_order = REQUIRED_LONG_COLUMNS + [c for c in combined_df.columns if c not in REQUIRED_LONG_COLUMNS]
    combined_df = combined_df[cols_order].copy()

    # Format date as string 'YYYY-MM-DD'
    combined_df["date"] = pd.to_datetime(combined_df["date"]).dt.strftime("%Y-%m-%d")

    # Sort strictly by (date, symbol)
    combined_df = combined_df.sort_values(by=["date", "symbol"], ascending=[True, True]).reset_index(drop=True)

    # Drop any exact duplicate (date, symbol) records
    combined_df = combined_df.drop_duplicates(subset=["date", "symbol"], keep="last").reset_index(drop=True)

    contract_data = {
        "prices": combined_df,
        "features": pd.DataFrame(),  # Empty placeholder for Phase 2
    }

    if validate:
        # Validate through india_data validator
        validate_market_dataframe(combined_df, is_long_format=True, raise_on_error=True)
        # Validate through Phase 1 FinRL contract validator
        validate_market_data(contract_data)

    return contract_data


def save_processed_data(
    data: Dict[str, pd.DataFrame],
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Save transformed FinRL dataset to processed data directory as CSV.

    Args:
        data: FinRL data dictionary containing 'prices' DataFrame.
        output_path: Optional custom output file path (default: data/processed/prices.csv).

    Returns:
        Path of saved CSV file.
    """
    if "prices" not in data or not isinstance(data["prices"], pd.DataFrame):
        raise ValueError("Data dictionary must contain a 'prices' DataFrame.")

    target_file = Path(output_path) if output_path else (PROCESSED_DATA_DIR / "prices.csv")
    target_file.parent.mkdir(parents=True, exist_ok=True)

    data["prices"].to_csv(target_file, index=False)
    return target_file
