"""
Market Data Fetcher for Indian NSE Equities
Uses Yahoo Finance (yfinance) to fetch historical and incremental OHLCV data.
Handles symbol mapping, network retries, and data normalization.
"""

from __future__ import annotations
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import yfinance as yf

from .symbol_universe import SymbolUniverse

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


STANDARD_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "adj_close", "volume"]


class MarketFetcher:
    """
    Fetches raw OHLCV market data for Indian NSE equities from Yahoo Finance.
    """

    def __init__(self, retry_count: int = 3, backoff_seconds: float = 2.0):
        self.retry_count = retry_count
        self.backoff_seconds = backoff_seconds

    def _normalize_yfinance_df(self, raw_df: pd.DataFrame, clean_symbol: str) -> pd.DataFrame:
        """
        Normalizes Yahoo Finance raw dataframe into standard schema:
        ['date', 'symbol', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
        """
        if raw_df is None or raw_df.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        df = raw_df.copy()

        # Handle MultiIndex columns (sometimes returned by yfinance download)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        # Reset index to turn DatetimeIndex into a column
        if "Date" in df.index.names or df.index.name == "Date" or isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()

        # Normalize column names to lowercase
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

        # Map common variations
        col_mapping = {
            "datetime": "date",
            "adj close": "adj_close",
            "adj_close": "adj_close",
        }
        df = df.rename(columns=col_mapping)

        if "date" not in df.columns:
            # First column is usually date if reset
            first_col = df.columns[0]
            df = df.rename(columns={first_col: "date"})

        # Format date as 'YYYY-MM-DD'
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        # Fallback for adj_close if missing
        if "adj_close" not in df.columns and "close" in df.columns:
            df["adj_close"] = df["close"]

        # Assign standard clean symbol (e.g., RELIANCE)
        df["symbol"] = clean_symbol.upper()

        # Ensure all standard columns exist
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = None

        df = df[STANDARD_COLUMNS].copy()

        # Numeric conversions
        numeric_cols = ["open", "high", "low", "close", "adj_close", "volume"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Drop rows where critical price columns are all NaN
        df = df.dropna(subset=["close"]).reset_index(drop=True)

        return df

    def fetch_symbol(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: Optional[str] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for a single symbol with retry logic.

        Args:
            symbol: Clean NSE symbol (e.g. 'RELIANCE') or Yahoo ticker ('RELIANCE.NS').
            start_date: Start date string 'YYYY-MM-DD' (optional).
            end_date: End date string 'YYYY-MM-DD' (optional).
            period: Yahoo finance period string, e.g. '1y', '2y', 'max' (used if start_date omitted).
            interval: Bar interval, default '1d'.

        Returns:
            Standardized DataFrame with ['date', 'symbol', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
        """
        clean_sym = SymbolUniverse.from_yahoo_ticker(symbol)
        yahoo_ticker = SymbolUniverse.to_yahoo_ticker(clean_sym)

        # Default period if no dates provided
        if not start_date and not period:
            period = "2y"

        for attempt in range(1, self.retry_count + 1):
            try:
                logger.info(f"Fetching {yahoo_ticker} (Attempt {attempt}/{self.retry_count})")
                ticker_obj = yf.Ticker(yahoo_ticker)

                if start_date:
                    hist = ticker_obj.history(start=start_date, end=end_date, interval=interval, auto_adjust=False)
                else:
                    hist = ticker_obj.history(period=period, interval=interval, auto_adjust=False)

                if hist.empty:
                    logger.warning(f"No market data returned for {yahoo_ticker}")
                    return pd.DataFrame(columns=STANDARD_COLUMNS)

                normalized = self._normalize_yfinance_df(hist, clean_sym)
                logger.info(f"Successfully fetched {len(normalized)} bars for {clean_sym}")
                return normalized

            except Exception as e:
                logger.warning(f"Error fetching {yahoo_ticker} on attempt {attempt}: {e}")
                if attempt < self.retry_count:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    logger.error(f"Failed to fetch market data for {clean_sym} after {self.retry_count} attempts.")
                    return pd.DataFrame(columns=STANDARD_COLUMNS)

        return pd.DataFrame(columns=STANDARD_COLUMNS)

    def fetch_multiple(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: Optional[str] = None,
        interval: str = "1d",
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV data for multiple symbols.

        Returns:
            Dictionary mapping clean_symbol -> standardized DataFrame.
        """
        results: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            clean_sym = SymbolUniverse.from_yahoo_ticker(sym)
            df = self.fetch_symbol(
                clean_sym,
                start_date=start_date,
                end_date=end_date,
                period=period,
                interval=interval,
            )
            if not df.empty:
                results[clean_sym] = df
            else:
                logger.warning(f"Empty dataset for {clean_sym}; skipped.")
        return results

    def fetch_incremental(
        self,
        symbol: str,
        since_date: str,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch data for bars strictly occurring after `since_date`.

        Args:
            symbol: Clean NSE symbol.
            since_date: 'YYYY-MM-DD' of the latest existing bar.
            end_date: Optional upper bound date.
        """
        since_dt = datetime.strptime(since_date, "%Y-%m-%d")
        next_day = (since_dt + timedelta(days=1)).strftime("%Y-%m-%d")

        today_str = datetime.now().strftime("%Y-%m-%d")
        if next_day > today_str:
            logger.info(f"{symbol} is already up to date ({since_date}).")
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        logger.info(f"Fetching incremental data for {symbol} from {next_day} to {end_date or 'latest'}")
        df = self.fetch_symbol(symbol, start_date=next_day, end_date=end_date)
        if not df.empty:
            df = df[df["date"] > since_date].reset_index(drop=True)
        return df

