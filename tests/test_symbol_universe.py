"""
Unit tests for pipeline.symbol_universe module.
"""

import pytest
import pandas as pd
from pipeline.symbol_universe import (
    SymbolUniverse,
    StockInfo,
    DEFAULT_NSE_UNIVERSE,
)


def test_default_universe_initialization():
    universe = SymbolUniverse()
    assert len(universe) >= 10
    symbols = universe.get_symbols()
    assert "RELIANCE" in symbols
    assert "TCS" in symbols
    assert "HDFCBANK" in symbols


def test_yahoo_ticker_conversion():
    assert SymbolUniverse.to_yahoo_ticker("RELIANCE") == "RELIANCE.NS"
    assert SymbolUniverse.to_yahoo_ticker("tcs") == "TCS.NS"
    assert SymbolUniverse.to_yahoo_ticker("INFY.NS") == "INFY.NS"

    assert SymbolUniverse.from_yahoo_ticker("RELIANCE.NS") == "RELIANCE"
    assert SymbolUniverse.from_yahoo_ticker("tcs.ns") == "TCS"
    assert SymbolUniverse.from_yahoo_ticker("INFY") == "INFY"


def test_sector_filtering():
    universe = SymbolUniverse()
    it_stocks = universe.get_by_sector("Information Technology")
    assert len(it_stocks) >= 2
    it_symbols = [s.symbol for s in it_stocks]
    assert "TCS" in it_symbols
    assert "INFY" in it_symbols

    sectors = universe.get_sectors()
    assert "Financial Services" in sectors
    assert "Energy" in sectors


def test_custom_stock_addition():
    custom_stock = StockInfo(
        symbol="BAJFINANCE",
        company_name="Bajaj Finance Ltd.",
        sector="Financial Services",
        industry="NBFC",
    )
    universe = SymbolUniverse(stocks=[custom_stock])
    assert len(universe) == 1
    assert universe.get_symbols() == ["BAJFINANCE"]
    assert universe.get_yahoo_tickers() == ["BAJFINANCE.NS"]
    assert universe.get_stock("bajfinance") == custom_stock


def test_to_dataframe():
    universe = SymbolUniverse()
    df = universe.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "symbol" in df.columns
    assert "sector" in df.columns
    assert "yahoo_ticker" in df.columns

