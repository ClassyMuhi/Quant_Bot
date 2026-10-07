"""
Unit and Component Tests for India Market Data Engine (india_data).
"""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from india_data import (
    INDIAN_STOCKS,
    BENCHMARK_INDEX,
    to_yfinance_symbol,
    to_canonical_symbol,
    get_yfinance_symbols,
    MegaBullSymbolMapper,
    validate_market_dataframe,
    DataValidationError,
    download_history,
    load_or_download,
    to_finrl_format,
    REQUIRED_RAW_COLUMNS,
    REQUIRED_LONG_COLUMNS,
)
from finrl_adapter.data_contract import validate_market_data


# -------------------------------------------------------------------------
# 1. Universe Configuration & Symbol Mapping Tests
# -------------------------------------------------------------------------

def test_universe_configuration():
    """Verify initial Indian universe and benchmark definitions."""
    assert len(INDIAN_STOCKS) == 10
    expected_stocks = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "ITC", "LT", "BHARTIARTL", "AXISBANK"
    ]
    for stock in expected_stocks:
        assert stock in INDIAN_STOCKS
    assert BENCHMARK_INDEX == "^NSEI"


def test_symbol_mappings():
    """Test mapping between canonical, Yahoo Finance, and index symbols."""
    # Canonical -> Yahoo
    assert to_yfinance_symbol("RELIANCE") == "RELIANCE.NS"
    assert to_yfinance_symbol("TCS") == "TCS.NS"
    assert to_yfinance_symbol("INFY") == "INFY.NS"
    assert to_yfinance_symbol("^NSEI") == "^NSEI"
    assert to_yfinance_symbol("NIFTY 50") == "^NSEI"
    assert to_yfinance_symbol("RELIANCE.NS") == "RELIANCE.NS"

    # Yahoo -> Canonical
    assert to_canonical_symbol("RELIANCE.NS") == "RELIANCE"
    assert to_canonical_symbol("TCS.NS") == "TCS"
    assert to_canonical_symbol("^NSEI") == "^NSEI"
    assert to_canonical_symbol("INFY") == "INFY"

    # Batch mappings
    mappings = get_yfinance_symbols(["RELIANCE", "TCS", "INFY"])
    assert mappings == {
        "RELIANCE": "RELIANCE.NS",
        "TCS": "TCS.NS",
        "INFY": "INFY.NS",
    }


# -------------------------------------------------------------------------
# 2. MegaBull Symbol Mapping Tests
# -------------------------------------------------------------------------

def test_megabull_symbol_mapper():
    """Test dynamic resolution of MegaBull instruments and tokens without hardcoding."""
    # Synthetic MegaBull instruments DataFrame simulating master tradable list
    sample_instruments = pd.DataFrame([
        {
            "instrumentToken": 738561,
            "tradingSymbol": "RELIANCE",
            "instrumentName": "RELIANCE INDUSTRIES LTD",
            "exchange": "NSE",
            "segment": "NSE_EQ",
        },
        {
            "instrumentToken": 2953217,
            "tradingSymbol": "TCS",
            "instrumentName": "TATA CONSULTANCY SERVICES",
            "exchange": "NSE",
            "segment": "NSE_EQ",
        },
        {
            "instrumentToken": 408065,
            "tradingSymbol": "INFY",
            "instrumentName": "INFOSYS LTD",
            "exchange": "NSE",
            "segment": "NSE_EQ",
        },
    ])

    mapper = MegaBullSymbolMapper(instruments_df=sample_instruments)

    # Token lookups
    assert mapper.get_token("RELIANCE") == 738561
    assert mapper.get_token("RELIANCE.NS") == 738561
    assert mapper.get_token("TCS") == 2953217
    assert mapper.get_token("INFY") == 408065
    assert mapper.get_token("UNKNOWN_STOCK") is None

    # Trading symbol resolution
    assert mapper.get_trading_symbol("RELIANCE.NS") == "RELIANCE"

    # Full resolution dict
    res = mapper.resolve("RELIANCE")
    assert res == {
        "canonical_symbol": "RELIANCE",
        "yfinance_symbol": "RELIANCE.NS",
        "megabull_symbol": "RELIANCE",
        "instrument_token": 738561,
    }

    # Batch resolution
    batch_df = mapper.batch_resolve(["RELIANCE", "TCS"])
    assert len(batch_df) == 2
    assert "instrument_token" in batch_df.columns
    assert list(batch_df["instrument_token"]) == [738561, 2953217]


# -------------------------------------------------------------------------
# 3. Data Validation Tests
# -------------------------------------------------------------------------

def create_valid_dummy_df():
    """Helper to generate valid single-stock OHLCV DataFrame."""
    return pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-05"],
        "open": [100.0, 102.0, 101.0],
        "high": [105.0, 106.0, 104.0],
        "low": [98.0, 100.0, 99.0],
        "close": [103.0, 104.0, 102.0],
        "volume": [10000, 15000, 12000],
    })


def test_validator_valid_data():
    """Verify that correctly formatted OHLCV data passes validation."""
    df = create_valid_dummy_df()
    summary = validate_market_dataframe(df, symbol="RELIANCE", raise_on_error=True)
    assert summary["is_valid"] is True
    assert summary["row_count"] == 3
    assert len(summary["errors"]) == 0


def test_validator_missing_columns():
    """Verify validation fails when required columns are absent."""
    df = create_valid_dummy_df().drop(columns=["close"])
    with pytest.raises(DataValidationError) as exc_info:
        validate_market_dataframe(df, symbol="TEST", raise_on_error=True)
    assert "Missing required columns" in str(exc_info.value)


def test_validator_financial_invariants():
    """Verify validation catches pricing anomalies (e.g. High < Low, negative prices)."""
    # 1. High < Low
    bad_hl = create_valid_dummy_df()
    bad_hl.loc[0, "high"] = 90.0  # low is 98.0
    with pytest.raises(DataValidationError) as exc:
        validate_market_dataframe(bad_hl, raise_on_error=True)
    assert "High < Low" in str(exc.value)

    # 2. Negative price
    bad_neg = create_valid_dummy_df()
    bad_neg.loc[0, "close"] = -10.0
    with pytest.raises(DataValidationError) as exc:
        validate_market_dataframe(bad_neg, raise_on_error=True)
    assert "close <= 0" in str(exc.value)

    # 3. High < Open
    bad_ho = create_valid_dummy_df()
    bad_ho.loc[0, "high"] = 99.0  # open is 100.0
    with pytest.raises(DataValidationError) as exc:
        validate_market_dataframe(bad_ho, raise_on_error=True)
    assert "High < Open" in str(exc.value)


def test_validator_duplicate_dates():
    """Verify detection of duplicate dates."""
    dup_df = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-01", "2026-01-02"],
        "open": [100.0, 100.0, 102.0],
        "high": [105.0, 105.0, 106.0],
        "low": [98.0, 98.0, 100.0],
        "close": [103.0, 103.0, 104.0],
        "volume": [10000, 10000, 15000],
    })
    with pytest.raises(DataValidationError) as exc:
        validate_market_dataframe(dup_df, raise_on_error=True)
    assert "duplicate date rows" in str(exc.value)


def test_validator_missing_values():
    """Verify detection and reporting of NaNs."""
    nan_df = create_valid_dummy_df()
    nan_df.loc[1, "close"] = np.nan
    with pytest.raises(DataValidationError) as exc:
        validate_market_dataframe(nan_df, raise_on_error=True)
    assert "missing (NaN/null) values" in str(exc.value)


# -------------------------------------------------------------------------
# 4. Transformation & FinRL Contract Compatibility Tests
# -------------------------------------------------------------------------

def test_to_finrl_format():
    """Test multi-asset transformation into long-format FinRL data structure."""
    df_reliance = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02"],
        "open": [2500.0, 2520.0],
        "high": [2550.0, 2560.0],
        "low": [2490.0, 2510.0],
        "close": [2530.0, 2540.0],
        "volume": [50000, 60000],
    })

    df_tcs = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02"],
        "open": [3500.0, 3520.0],
        "high": [3550.0, 3560.0],
        "low": [3480.0, 3500.0],
        "close": [3530.0, 3540.0],
        "volume": [30000, 40000],
    })

    data_map = {
        "RELIANCE": df_reliance,
        "TCS.NS": df_tcs,  # Suffix should be stripped to canonical 'TCS'
    }

    finrl_data = to_finrl_format(data_map, validate=True)

    # Check contract structure
    assert isinstance(finrl_data, dict)
    assert "prices" in finrl_data
    assert "features" in finrl_data

    prices_df = finrl_data["prices"]
    assert isinstance(prices_df, pd.DataFrame)
    assert len(prices_df) == 4

    # Verify column schema
    for col in REQUIRED_LONG_COLUMNS:
        assert col in prices_df.columns

    # Verify canonical symbols
    symbols = set(prices_df["symbol"].unique())
    assert symbols == {"RELIANCE", "TCS"}
    assert "TCS.NS" not in symbols

    # Verify sorting by (date, symbol)
    expected_order = [
        ("2026-01-01", "RELIANCE"),
        ("2026-01-01", "TCS"),
        ("2026-01-02", "RELIANCE"),
        ("2026-01-02", "TCS"),
    ]
    actual_order = list(zip(prices_df["date"], prices_df["symbol"]))
    assert actual_order == expected_order

    # Validate against Phase 1 FinRL contract
    assert validate_market_data(finrl_data) is True


# -------------------------------------------------------------------------
# 5. Live Small Sample Ingestion Test
# -------------------------------------------------------------------------

def test_live_sample_ingestion(tmp_path):
    """Test historical downloading, caching, and transformation with a small sample (RELIANCE)."""
    # Use temporary directory for testing caching
    cache_dir = tmp_path / "historical"
    cache_dir.mkdir(parents=True, exist_ok=True)

    symbol = "RELIANCE"
    # Download / load 5 days of data
    df = load_or_download(symbol, period="5d", cache_dir=cache_dir, force_refresh=True)

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) >= 2
    for col in REQUIRED_RAW_COLUMNS:
        assert col in df.columns

    # Check cache file was created
    cached_file = cache_dir / f"{symbol}.csv"
    assert cached_file.exists()

    # Second call should load from cache
    cached_df = load_or_download(symbol, period="5d", cache_dir=cache_dir, force_refresh=False)
    assert len(cached_df) == len(df)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
