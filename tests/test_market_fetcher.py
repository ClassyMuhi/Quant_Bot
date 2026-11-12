"""
Unit tests for pipeline.market_fetcher module.
"""

from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import pytest

from pipeline.market_fetcher import MarketFetcher, STANDARD_COLUMNS


@pytest.fixture
def mock_raw_yfinance_df():
    """Generates synthetic DataFrame mimicking yfinance.Ticker.history output."""
    dates = pd.date_range("2026-01-01", periods=5, freq="B")
    data = {
        "Open": [2500.0, 2520.0, 2510.0, 2540.0, 2530.0],
        "High": [2530.0, 2550.0, 2535.0, 2560.0, 2555.0],
        "Low": [2490.0, 2510.0, 2500.0, 2525.0, 2520.0],
        "Close": [2515.0, 2540.0, 2525.0, 2550.0, 2545.0],
        "Adj Close": [2515.0, 2540.0, 2525.0, 2550.0, 2545.0],
        "Volume": [100000, 120000, 95000, 140000, 110000],
    }
    df = pd.DataFrame(data, index=dates)
    df.index.name = "Date"
    return df


def test_normalize_yfinance_df(mock_raw_yfinance_df):
    fetcher = MarketFetcher()
    normalized = fetcher._normalize_yfinance_df(mock_raw_yfinance_df, "RELIANCE")

    assert list(normalized.columns) == STANDARD_COLUMNS
    assert len(normalized) == 5
    assert (normalized["symbol"] == "RELIANCE").all()
    assert normalized["date"].iloc[0] == "2026-01-01"
    assert normalized["close"].iloc[0] == 2515.0


def test_normalize_handles_multiindex(mock_raw_yfinance_df):
    # Simulate yfinance multi-index columns: ('Close', 'RELIANCE.NS')
    multi_cols = pd.MultiIndex.from_tuples([(c, "RELIANCE.NS") for c in mock_raw_yfinance_df.columns])
    df_multi = mock_raw_yfinance_df.copy()
    df_multi.columns = multi_cols

    fetcher = MarketFetcher()
    normalized = fetcher._normalize_yfinance_df(df_multi, "RELIANCE")
    assert list(normalized.columns) == STANDARD_COLUMNS
    assert len(normalized) == 5


@patch("pipeline.market_fetcher.yf.Ticker")
def test_fetch_symbol_mock(mock_ticker_cls, mock_raw_yfinance_df):
    mock_ticker_inst = MagicMock()
    mock_ticker_inst.history.return_value = mock_raw_yfinance_df
    mock_ticker_cls.return_value = mock_ticker_inst

    fetcher = MarketFetcher()
    df = fetcher.fetch_symbol("TCS", period="1y")

    mock_ticker_cls.assert_called_with("TCS.NS")
    assert not df.empty
    assert len(df) == 5
    assert (df["symbol"] == "TCS").all()


@patch("pipeline.market_fetcher.yf.Ticker")
def test_fetch_multiple(mock_ticker_cls, mock_raw_yfinance_df):
    mock_ticker_inst = MagicMock()
    mock_ticker_inst.history.return_value = mock_raw_yfinance_df
    mock_ticker_cls.return_value = mock_ticker_inst

    fetcher = MarketFetcher()
    result = fetcher.fetch_multiple(["INFY", "WIPRO"], period="6mo")

    assert "INFY" in result
    assert "WIPRO" in result
    assert len(result["INFY"]) == 5
    assert (result["INFY"]["symbol"] == "INFY").all()


@patch("pipeline.market_fetcher.yf.Ticker")
def test_fetch_incremental(mock_ticker_cls, mock_raw_yfinance_df):
    mock_ticker_inst = MagicMock()
    mock_ticker_inst.history.return_value = mock_raw_yfinance_df
    mock_ticker_cls.return_value = mock_ticker_inst

    fetcher = MarketFetcher()
    # Filter since 2026-01-02 -> should return rows after 2026-01-02
    inc_df = fetcher.fetch_incremental("RELIANCE", since_date="2026-01-02")
    assert (inc_df["date"] > "2026-01-02").all()

