"""
Data Validation Engine for Indian Market Data.
Enforces data integrity, schema consistency, and pricing invariants.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

from india_data.config import REQUIRED_RAW_COLUMNS, REQUIRED_LONG_COLUMNS


class DataValidationError(Exception):
    """Custom exception raised when market data fails integrity checks."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


def validate_market_dataframe(
    df: pd.DataFrame,
    symbol: Optional[str] = None,
    is_long_format: bool = False,
    raise_on_error: bool = True,
) -> Dict[str, Any]:
    """
    Validate OHLCV market data against strict financial and structural rules.

    Validation Rules:
        1. Non-empty DataFrame.
        2. Required columns present ('date', 'open', 'high', 'low', 'close', 'volume', and 'symbol' if long format).
        3. Valid date format and chronologically sorted.
        4. No duplicate dates per symbol.
        5. OHLC and volume columns are numeric.
        6. Detection and reporting of missing values (NaNs).
        7. Financial integrity invariants:
           - close > 0
           - open > 0
           - high >= low
           - high >= open
           - high >= close
           - low <= open
           - low <= close
           - volume >= 0

    Args:
        df: Pandas DataFrame containing market data.
        symbol: Optional symbol identifier for targeted reporting.
        is_long_format: True if DataFrame contains multi-asset rows with a 'symbol' column.
        raise_on_error: If True, raises DataValidationError when critical issues are found.

    Returns:
        Dictionary with validation summary:
            {
                'is_valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'row_count': int,
                'date_range': (min_date, max_date),
                'missing_counts': Dict[str, int]
            }
    """
    errors: List[str] = []
    warnings: List[str] = []
    sym_tag = f"[{symbol}] " if symbol else ""

    if not isinstance(df, pd.DataFrame):
        msg = f"{sym_tag}Data must be a pandas DataFrame, got {type(df).__name__}."
        if raise_on_error:
            raise DataValidationError(msg, [msg])
        return {"is_valid": False, "errors": [msg], "warnings": [], "row_count": 0}

    if df.empty:
        msg = f"{sym_tag}DataFrame is empty."
        if raise_on_error:
            raise DataValidationError(msg, [msg])
        return {"is_valid": False, "errors": [msg], "warnings": [], "row_count": 0}

    # 1. Required Columns Check
    required_cols = REQUIRED_LONG_COLUMNS if is_long_format else REQUIRED_RAW_COLUMNS
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        errors.append(f"{sym_tag}Missing required columns: {missing_cols}")

    # If critical columns missing, return early
    if errors:
        if raise_on_error:
            raise DataValidationError(f"{sym_tag}Schema validation failed: {errors[0]}", errors)
        return {
            "is_valid": False,
            "errors": errors,
            "warnings": warnings,
            "row_count": len(df),
        }

    # 2. Date Column Validation
    # Ensure dates are parseable
    try:
        dates = pd.to_datetime(df["date"])
    except Exception as e:
        errors.append(f"{sym_tag}Failed to parse 'date' column as datetime: {e}")
        dates = None

    if dates is not None:
        # Check chronological sorting
        if not is_long_format:
            if not dates.is_monotonic_increasing:
                errors.append(f"{sym_tag}Dates are not in strictly ascending chronological order.")
            # Duplicate dates check (single asset)
            dups = df[df.duplicated(subset=["date"], keep=False)]
            if not dups.empty:
                errors.append(f"{sym_tag}Found {len(dups)} duplicate date rows: {dups['date'].tolist()[:5]}")
        else:
            # Multi-asset long format duplicate check
            dups = df[df.duplicated(subset=["date", "symbol"], keep=False)]
            if not dups.empty:
                errors.append(
                    f"{sym_tag}Found {len(dups)} duplicate (date, symbol) rows in multi-asset dataset."
                )

    # 3. Numeric Columns & Missing Values Check
    numeric_cols = ["open", "high", "low", "close", "volume"]
    missing_counts = {}
    for col in numeric_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            # Try to check if coercible
            non_numeric = df[pd.to_numeric(df[col], errors="coerce").isna()]
            if not non_numeric.empty:
                errors.append(f"{sym_tag}Column '{col}' contains non-numeric values ({len(non_numeric)} rows).")

        nan_count = int(df[col].isna().sum())
        missing_counts[col] = nan_count
        if nan_count > 0:
            errors.append(f"{sym_tag}Column '{col}' contains {nan_count} missing (NaN/null) values.")

    # 4. Financial Integrity Invariants (Price & Volume Sanity)
    # Only run invariant checks on rows without NaNs
    clean_df = df.dropna(subset=numeric_cols)
    if not clean_df.empty:
        # Non-positive prices
        neg_close = clean_df[clean_df["close"] <= 0]
        if not neg_close.empty:
            errors.append(f"{sym_tag}Found {len(neg_close)} rows with close <= 0.")

        neg_open = clean_df[clean_df["open"] <= 0]
        if not neg_open.empty:
            errors.append(f"{sym_tag}Found {len(neg_open)} rows with open <= 0.")

        # Negative volume
        neg_vol = clean_df[clean_df["volume"] < 0]
        if not neg_vol.empty:
            errors.append(f"{sym_tag}Found {len(neg_vol)} rows with volume < 0.")

        # High < Low
        invalid_hl = clean_df[clean_df["high"] < clean_df["low"]]
        if not invalid_hl.empty:
            errors.append(f"{sym_tag}Found {len(invalid_hl)} rows where High < Low.")

        # High < Open or High < Close
        invalid_ho = clean_df[clean_df["high"] < clean_df["open"]]
        if not invalid_ho.empty:
            errors.append(f"{sym_tag}Found {len(invalid_ho)} rows where High < Open.")

        invalid_hc = clean_df[clean_df["high"] < clean_df["close"]]
        if not invalid_hc.empty:
            errors.append(f"{sym_tag}Found {len(invalid_hc)} rows where High < Close.")

        # Low > Open or Low > Close
        invalid_lo = clean_df[clean_df["low"] > clean_df["open"]]
        if not invalid_lo.empty:
            errors.append(f"{sym_tag}Found {len(invalid_lo)} rows where Low > Open.")

        invalid_lc = clean_df[clean_df["low"] > clean_df["close"]]
        if not invalid_lc.empty:
            errors.append(f"{sym_tag}Found {len(invalid_lc)} rows where Low > Close.")

    # Compute Summary Info
    is_valid = len(errors) == 0
    date_range = (str(df["date"].min()), str(df["date"].max())) if "date" in df.columns else (None, None)

    summary = {
        "is_valid": is_valid,
        "symbol": symbol,
        "row_count": len(df),
        "date_range": date_range,
        "missing_counts": missing_counts,
        "errors": errors,
        "warnings": warnings,
    }

    if not is_valid and raise_on_error:
        error_summary = "; ".join(errors[:3])
        if len(errors) > 3:
            error_summary += f" (+{len(errors) - 3} more)"
        raise DataValidationError(f"{sym_tag}Data validation failed: {error_summary}", errors=errors)

    return summary
