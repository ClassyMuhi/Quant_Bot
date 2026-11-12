"""
Bronze Layer Writer for Quant_Bot
Stores raw, immutable market data in Parquet format.
Provides DuckDB querying capabilities and maintains ingestion audit trails.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


def write_parquet(df: pd.DataFrame, target_path: Union[str, Path]) -> None:
    """Save a Pandas DataFrame to Parquet using DuckDB engine."""
    path_str = Path(target_path).resolve().as_posix()
    # Execute copy statement
    conn = duckdb.connect(":memory:")
    conn.register("source_df", df)
    conn.execute(f"COPY source_df TO '{path_str}' (FORMAT PARQUET)")
    conn.close()


def read_parquet(target_path: Union[str, Path]) -> pd.DataFrame:
    """Read a Parquet file into a Pandas DataFrame using DuckDB."""
    path_str = Path(target_path).resolve().as_posix()
    return duckdb.query(f"SELECT * FROM read_parquet('{path_str}')").df()


class BronzeWriter:
    """
    Manages raw market data ingestion into the Bronze storage layer (data/bronze).
    Writes Parquet files per symbol and provides fast SQL querying via DuckDB.
    """

    def __init__(self, bronze_dir: Union[str, Path] = "data/bronze"):
        self.bronze_dir = Path(bronze_dir)
        self.bronze_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, symbol: str) -> Path:
        """Standardized path for a symbol's raw Parquet file."""
        return self.bronze_dir / f"{symbol.strip().upper()}.parquet"

    def write_symbol_data(
        self,
        symbol: str,
        df: pd.DataFrame,
        source: str = "yfinance",
    ) -> Path:
        """
        Write or append raw market data for a symbol.
        Adds metadata columns: '_ingested_at_utc' and '_source'.
        Deduplicates on 'date', keeping the most recent ingestion.
        """
        if df.empty:
            logger.warning(f"Empty dataframe provided for symbol '{symbol}'. Skipping write.")
            return self._get_file_path(symbol)

        clean_symbol = symbol.strip().upper()
        target_path = self._get_file_path(clean_symbol)

        data = df.copy()
        # Ingestion audit metadata
        now_utc = datetime.now(timezone.utc).isoformat()
        data["_ingested_at_utc"] = now_utc
        data["_source"] = source
        data["symbol"] = clean_symbol

        if target_path.exists():
            try:
                existing_df = read_parquet(target_path)
                combined = pd.concat([existing_df, data], ignore_index=True)
                # Deduplicate on date, keeping the newly ingested row
                combined = combined.drop_duplicates(subset=["date"], keep="last")
                combined = combined.sort_values(by="date").reset_index(drop=True)
                write_parquet(combined, target_path)
                logger.info(f"Updated Bronze Parquet for {clean_symbol}: {len(combined)} total bars at {target_path}")
                return target_path
            except Exception as e:
                logger.warning(f"Error reading existing bronze file for {clean_symbol}: {e}. Overwriting.")

        # If file doesn't exist or failed to load existing
        data = data.drop_duplicates(subset=["date"], keep="last")
        data = data.sort_values(by="date").reset_index(drop=True)
        write_parquet(data, target_path)
        logger.info(f"Created Bronze Parquet for {clean_symbol}: {len(data)} bars at {target_path}")
        return target_path

    def write_batch(
        self,
        batch_data: Dict[str, pd.DataFrame],
        source: str = "yfinance",
    ) -> Dict[str, Path]:
        """Write raw datasets for multiple symbols."""
        results: Dict[str, Path] = {}
        for sym, df in batch_data.items():
            path = self.write_symbol_data(sym, df, source=source)
            results[sym] = path
        return results

    def read_symbol_data(self, symbol: str) -> pd.DataFrame:
        """Read raw Parquet data for a symbol."""
        target_path = self._get_file_path(symbol)
        if not target_path.exists():
            return pd.DataFrame()
        return read_parquet(target_path)

    def get_latest_date(self, symbol: str) -> Optional[str]:
        """
        Uses DuckDB to query the latest available date in Bronze storage for a symbol.
        Returns 'YYYY-MM-DD' or None if symbol data doesn't exist.
        """
        target_path = self._get_file_path(symbol)
        if not target_path.exists():
            return None

        file_path_str = target_path.resolve().as_posix()
        query = f"SELECT MAX(date) AS max_date FROM read_parquet('{file_path_str}')"
        try:
            res = duckdb.query(query).df()
            if not res.empty and pd.notna(res["max_date"].iloc[0]):
                return str(res["max_date"].iloc[0])
        except Exception as e:
            logger.error(f"Error querying DuckDB for latest date of {symbol}: {e}")

        return None

    def query_duckdb(self, sql_query: str) -> pd.DataFrame:
        """
        Execute an arbitrary SQL query using DuckDB.
        Example: query_duckdb("SELECT * FROM read_parquet('data/bronze/*.parquet') WHERE close > 2000")
        """
        return duckdb.query(sql_query).df()

    def list_available_symbols(self) -> List[str]:
        """List symbols currently saved in Bronze storage."""
        return sorted([p.stem for p in self.bronze_dir.glob("*.parquet")])
