"""
Silver Layer Transformer for Quant_Bot
Cleans, validates, deduplicates, and standardizes raw Bronze market data.
Ensures strict compatibility with the FinRL data contract and quantitative engines.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd

from finrl_adapter.data_contract import validate_market_data
from .bronze_writer import BronzeWriter, read_parquet, write_parquet

logger = logging.getLogger(__name__)

SILVER_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "adj_close", "volume"]


class SilverTransformer:
    """
    Transforms raw Bronze market data into validated, clean Silver records (data/silver).
    Handles OHLC consistency, missing-value imputation, deduplication, and schema enforcement.
    """

    def __init__(
        self,
        silver_dir: Union[str, Path] = "data/silver",
        bronze_writer: Optional[BronzeWriter] = None,
    ):
        self.silver_dir = Path(silver_dir)
        self.silver_dir.mkdir(parents=True, exist_ok=True)
        self.bronze_writer = bronze_writer or BronzeWriter()

    def _get_file_path(self, symbol: str) -> Path:
        """Standardized path for a symbol's cleaned Silver Parquet file."""
        return self.silver_dir / f"{symbol.strip().upper()}.parquet"

    def clean_data(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Cleans and validates raw market data:
        1. Normalizes symbol and dates (YYYY-MM-DD).
        2. Deduplicates on 'date', keeping the latest row.
        3. Sorts chronologically.
        4. Fixes OHLC anomalies (High >= max(Open, Close), Low <= min(Open, Close)).
        5. Removes non-positive prices and invalid records.
        6. Imputes minor missing values using forward fill.
        """
        if df.empty:
            return pd.DataFrame(columns=SILVER_COLUMNS)

        clean_symbol = symbol.strip().upper()
        data = df.copy()

        # 1. Standardize date & symbol
        data["symbol"] = clean_symbol
        data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")

        # 2. Deduplicate by date
        data = data.drop_duplicates(subset=["date"], keep="last")

        # 3. Sort chronologically
        data = data.sort_values(by="date").reset_index(drop=True)

        # Ensure all numeric price columns exist
        for col in ["open", "high", "low", "close", "adj_close", "volume"]:
            if col not in data.columns:
                data[col] = np.nan
            else:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        # 4. Filter invalid prices: close and open must be strictly positive
        data = data[data["close"] > 0].reset_index(drop=True)
        if data.empty:
            return pd.DataFrame(columns=SILVER_COLUMNS)

        # Forward fill any missing open, high, low from close if needed
        data["open"] = data["open"].fillna(data["close"])
        data["adj_close"] = data["adj_close"].fillna(data["close"])
        data["volume"] = data["volume"].fillna(0).clip(lower=0)

        # 5. Sanitize High / Low logic:
        # High must be at least max(open, close)
        # Low must be at most min(open, close)
        max_oc = data[["open", "close"]].max(axis=1)
        min_oc = data[["open", "close"]].min(axis=1)

        data["high"] = data["high"].fillna(max_oc)
        data["low"] = data["low"].fillna(min_oc)

        data["high"] = np.maximum(data["high"], max_oc)
        data["low"] = np.minimum(data["low"], min_oc)
        # Ensure low is strictly positive
        data = data[data["low"] > 0].reset_index(drop=True)

        # 6. Format final columns
        data = data[SILVER_COLUMNS].reset_index(drop=True)

        # Verification against FinRL contract structure
        validate_market_data({"prices": data})

        return data

    def transform_symbol(
        self,
        symbol: str,
        raw_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Cleans data for a symbol (loaded from Bronze or passed directly)
        and writes it to Silver storage.
        """
        clean_symbol = symbol.strip().upper()
        if raw_df is None or raw_df.empty:
            raw_df = self.bronze_writer.read_symbol_data(clean_symbol)

        if raw_df.empty:
            logger.warning(f"No Bronze data found for {clean_symbol}. Skipping silver transformation.")
            return pd.DataFrame(columns=SILVER_COLUMNS)

        cleaned_df = self.clean_data(raw_df, clean_symbol)
        if not cleaned_df.empty:
            target_path = self._get_file_path(clean_symbol)
            write_parquet(cleaned_df, target_path)
            logger.info(f"Silver dataset saved for {clean_symbol}: {len(cleaned_df)} bars at {target_path}")

        return cleaned_df

    def transform_batch(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Transform multiple symbols from Bronze to Silver."""
        results: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            df = self.transform_symbol(sym)
            if not df.empty:
                results[sym] = df
        return results

    def read_silver_data(self, symbol: str) -> pd.DataFrame:
        """Read cleaned Parquet data for a symbol from Silver storage."""
        target_path = self._get_file_path(symbol)
        if not target_path.exists():
            return pd.DataFrame(columns=SILVER_COLUMNS)
        return read_parquet(target_path)

    def get_consolidated_prices(self, symbols: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Combines clean Silver data for all given symbols into a unified multi-stock DataFrame.
        Sorted by date, then symbol.
        """
        target_symbols = symbols if symbols is not None else self.list_available_symbols()
        dfs = []
        for sym in target_symbols:
            df = self.read_silver_data(sym)
            if not df.empty:
                dfs.append(df)

        if not dfs:
            return pd.DataFrame(columns=SILVER_COLUMNS)

        consolidated = pd.concat(dfs, ignore_index=True)
        consolidated = consolidated.sort_values(by=["date", "symbol"]).reset_index(drop=True)
        return consolidated

    def to_finrl_data_contract(self, symbols: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
        """
        Exports clean Silver data in the exact structure expected by FinRL adapters:
        {"prices": pd.DataFrame with ['date', 'symbol', 'close', ...]}
        """
        prices_df = self.get_consolidated_prices(symbols)
        dataset = {"prices": prices_df}
        if not prices_df.empty:
            validate_market_data(dataset)
        return dataset

    def list_available_symbols(self) -> List[str]:
        """List symbols currently saved in Silver storage."""
        return sorted([p.stem for p in self.silver_dir.glob("*.parquet")])
