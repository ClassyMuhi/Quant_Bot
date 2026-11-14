"""
Signal Generator for Decision Engine
Extracts technical indicators from Gold market data and event intelligence
from God's Eye, validating data completeness and freshness.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "close", "rsi_14", "sma_20", "sma_50", "macd", "macd_signal", "volatility_20d"
]


class MarketDataFetcher:
    """
    Retrieves and inspects the latest technical indicator data from the Gold layer.
    """

    def __init__(self, gold_dir: Optional[Path] = None):
        self.gold_dir = Path(gold_dir or "data/gold")

    def get_latest_indicators(
        self,
        symbol: str,
        as_of: Optional[datetime | str] = None,
        max_stale_days: int = 7,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Loads the latest indicator record for symbol on or before as_of date.
        Returns: (indicator_dict, error_message)
        """
        parquet_path = self.gold_dir / f"{symbol.upper()}.parquet"
        if not parquet_path.exists():
            return None, f"Gold data file not found: {parquet_path}"

        con = duckdb.connect()
        try:
            query = f"SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
            if as_of:
                as_of_str = str(as_of)[:10]
                query += f" WHERE date <= '{as_of_str}'"
            query += " ORDER BY date DESC LIMIT 1"

            df = con.execute(query).df()
        except Exception as e:
            return None, f"Error reading Gold data for {symbol}: {e}"
        finally:
            con.close()

        if df.empty:
            return None, f"No market data available for {symbol} as of {as_of}"

        row = df.iloc[0].to_dict()

        # Check required columns
        for col in REQUIRED_COLUMNS:
            if col not in row or pd.isna(row[col]):
                return None, f"Missing or NaN required technical indicator: '{col}'"

        # Check staleness
        record_date_str = str(row["date"])[:10]
        try:
            record_date = datetime.strptime(record_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            if not as_of:
                days_diff = (now_dt - record_date).days
                if days_diff > max_stale_days:
                    return None, f"Market data is stale ({days_diff} days old, max allowed {max_stale_days})"
        except Exception:
            pass

        return row, None

