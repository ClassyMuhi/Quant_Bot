"""
Historical Data Ingestion & Caching Engine for Indian Equities.
Fetches daily OHLCV from Yahoo Finance and maintains local CSV cache.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd
import yfinance as yf

from india_data.config import HISTORICAL_DATA_DIR, DEFAULT_PERIOD, REQUIRED_RAW_COLUMNS
from india_data.universe import (
    INDIAN_STOCKS,
    to_canonical_symbol,
    to_yfinance_symbol,
)
from india_data.validator import validate_market_dataframe, DataValidationError


class DataDownloadError(Exception):
    """Custom exception raised when historical market data download fails."""
    pass


def download_history(
    symbol: str,
    period: str = DEFAULT_PERIOD,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Download daily OHLCV market data for an Indian equity or benchmark from Yahoo Finance.

    Args:
        symbol: Canonical Indian symbol (e.g. 'RELIANCE') or Yahoo symbol ('RELIANCE.NS').
        period: Historical period string (e.g. '5y', '1y', 'max').
        start: Optional start date string ('YYYY-MM-DD').
        end: Optional end date string ('YYYY-MM-DD').

    Returns:
        Clean pandas DataFrame with columns: ['date', 'open', 'high', 'low', 'close', 'volume'].

    Raises:
        DataDownloadError: If download fails or returns empty data.
    """
    canonical_sym = to_canonical_symbol(symbol)
    yf_symbol = to_yfinance_symbol(canonical_sym)

    try:
        ticker = yf.Ticker(yf_symbol)
        if start or end:
            df = ticker.history(start=start, end=end, auto_adjust=False)
        else:
            df = ticker.history(period=period, auto_adjust=False)

    except Exception as e:
        raise DataDownloadError(f"Failed to fetch market data for {yf_symbol} ({canonical_sym}): {e}") from e

    if df is None or df.empty:
        raise DataDownloadError(
            f"No data returned for symbol '{yf_symbol}' (canonical: '{canonical_sym}'). "
            "Please verify the symbol name and date range."
        )

    # 1. Reset index and normalize date column
    df = df.reset_index()

    # Find the date column (typically 'Date' or 'Datetime')
    date_col = None
    for col in df.columns:
        if str(col).lower() in ["date", "datetime", "timestamp"]:
            date_col = col
            break

    if date_col is None:
        raise DataDownloadError(f"Unable to locate date column in downloaded data for {yf_symbol}.")

    # Convert to formatted 'YYYY-MM-DD' string
    df["date"] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")

    # 2. Normalize standard column names to lowercase
    rename_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename_map)

    # If 'close' is missing but 'Adj Close' is present, fallback
    if "close" not in df.columns and "adj_close" in df.columns:
        df["close"] = df["adj_close"]

    # 3. Ensure required raw columns exist
    for col in REQUIRED_RAW_COLUMNS:
        if col not in df.columns:
            raise DataDownloadError(f"Missing required column '{col}' from downloaded {yf_symbol} data.")

    # 4. Filter columns and reorder
    cols_to_keep = [col for col in REQUIRED_RAW_COLUMNS if col in df.columns]
    if "adj_close" in df.columns:
        cols_to_keep.append("adj_close")
    df = df[cols_to_keep].copy()

    # 5. Clean up data: ensure numeric types, sort chronologically, drop duplicate dates
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(by="date", ascending=True)
    df = df.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    return df


def load_history(
    symbol: str,
    cache_dir: Optional[Union[str, Path]] = None,
) -> Optional[pd.DataFrame]:
    """
    Load cached historical market data from local CSV if it exists.

    Args:
        symbol: Canonical Indian symbol (e.g. 'RELIANCE').
        cache_dir: Optional custom historical data directory.

    Returns:
        Pandas DataFrame if cache file exists, else None.
    """
    canonical_sym = to_canonical_symbol(symbol)
    target_dir = Path(cache_dir) if cache_dir else HISTORICAL_DATA_DIR
    cache_file = target_dir / f"{canonical_sym}.csv"

    if not cache_file.exists():
        return None

    try:
        df = pd.read_csv(cache_file)
        # Ensure date formatting
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df = df.sort_values(by="date", ascending=True).reset_index(drop=True)
        return df
    except Exception as e:
        raise IOError(f"Failed to read cached data from {cache_file}: {e}") from e


def save_history(
    symbol: str,
    df: pd.DataFrame,
    cache_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Save historical DataFrame to local CSV cache.

    Args:
        symbol: Canonical Indian symbol.
        df: Pandas DataFrame to save.
        cache_dir: Optional custom storage directory.

    Returns:
        Path to the saved CSV file.
    """
    canonical_sym = to_canonical_symbol(symbol)
    target_dir = Path(cache_dir) if cache_dir else HISTORICAL_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    cache_file = target_dir / f"{canonical_sym}.csv"
    df.to_csv(cache_file, index=False)
    return cache_file


def load_or_download(
    symbol: str,
    period: str = DEFAULT_PERIOD,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
    cache_dir: Optional[Union[str, Path]] = None,
    validate: bool = True,
) -> pd.DataFrame:
    """
    Load historical data from local CSV cache or download if missing / refresh requested.

    Behavior:
        IF local cache exists and not force_refresh:
            load it
        ELSE:
            download it
            validate it
            save it to data/historical/{symbol}.csv

    Args:
        symbol: Canonical symbol (e.g. 'RELIANCE') or Yahoo symbol ('RELIANCE.NS').
        period: Historical period (default: '5y').
        start: Optional start date ('YYYY-MM-DD').
        end: Optional end date ('YYYY-MM-DD').
        force_refresh: If True, bypass cache and re-download from source.
        cache_dir: Optional custom historical data directory.
        validate: If True, executes data validation checks.

    Returns:
        Clean, validated pandas DataFrame.
    """
    canonical_sym = to_canonical_symbol(symbol)

    # 1. Try loading from cache
    if not force_refresh:
        cached_df = load_history(canonical_sym, cache_dir=cache_dir)
        if cached_df is not None and not cached_df.empty:
            if validate:
                validate_market_dataframe(cached_df, symbol=canonical_sym, raise_on_error=True)
            return cached_df

    # 2. Download from Yahoo Finance
    df = download_history(canonical_sym, period=period, start=start, end=end)

    # 3. Validate
    if validate:
        validate_market_dataframe(df, symbol=canonical_sym, raise_on_error=True)

    # 4. Save to cache
    save_history(canonical_sym, df, cache_dir=cache_dir)

    return df


def load_universe(
    symbols: Optional[List[str]] = None,
    period: str = DEFAULT_PERIOD,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
    cache_dir: Optional[Union[str, Path]] = None,
    validate: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Load or download historical datasets for an entire universe of symbols.

    Args:
        symbols: List of canonical symbols. Defaults to INDIAN_STOCKS if None.
        period: Historical period (default: '5y').
        start: Optional start date.
        end: Optional end date.
        force_refresh: If True, re-downloads all symbols.
        cache_dir: Optional cache directory.
        validate: If True, validates each dataset.

    Returns:
        Dictionary mapping canonical_symbol -> pd.DataFrame.
    """
    target_symbols = symbols if symbols is not None else INDIAN_STOCKS
    result: Dict[str, pd.DataFrame] = {}

    for sym in target_symbols:
        canonical_sym = to_canonical_symbol(sym)
        df = load_or_download(
            canonical_sym,
            period=period,
            start=start,
            end=end,
            force_refresh=force_refresh,
            cache_dir=cache_dir,
            validate=validate,
        )
        result[canonical_sym] = df

    return result
