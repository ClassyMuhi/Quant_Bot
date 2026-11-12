"""
Unit tests for pipeline.market_pipeline module.
"""

from unittest.mock import MagicMock
from pathlib import Path
import pandas as pd
import pytest

from pipeline.market_pipeline import MarketPipeline
from pipeline.symbol_universe import SymbolUniverse, StockInfo
from finrl_adapter.data_contract import validate_market_data


@pytest.fixture
def test_pipeline_env(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Small 2-stock universe
    test_stocks = [
        StockInfo("RELIANCE", "Reliance Industries", "Energy", "Oil & Gas"),
        StockInfo("TCS", "Tata Consultancy Services", "IT", "Software"),
    ]
    universe = SymbolUniverse(stocks=test_stocks)

    mock_fetcher = MagicMock()

    # Mock historical data
    def mock_fetch_symbol(sym, **kwargs):
        dates = ["2026-01-01", "2026-01-02", "2026-01-05"]
        base = 2500.0 if sym == "RELIANCE" else 3500.0
        return pd.DataFrame([
            {
                "date": d,
                "symbol": sym,
                "open": base,
                "high": base + 20.0,
                "low": base - 10.0,
                "close": base + 10.0,
                "adj_close": base + 10.0,
                "volume": 50000,
            }
            for d in dates
        ])

    mock_fetcher.fetch_symbol.side_effect = mock_fetch_symbol

    # Mock incremental data
    def mock_fetch_incremental(sym, since_date, **kwargs):
        if since_date < "2026-01-06":
            base = 2500.0 if sym == "RELIANCE" else 3500.0
            return pd.DataFrame([
                {
                    "date": "2026-01-06",
                    "symbol": sym,
                    "open": base + 10.0,
                    "high": base + 30.0,
                    "low": base,
                    "close": base + 25.0,
                    "adj_close": base + 25.0,
                    "volume": 60000,
                }
            ])
        return pd.DataFrame()

    mock_fetcher.fetch_incremental.side_effect = mock_fetch_incremental

    pipeline = MarketPipeline(
        universe=universe,
        base_data_dir=data_dir,
        fetcher=mock_fetcher,
    )

    return pipeline, data_dir


def test_full_backfill(test_pipeline_env):
    pipeline, data_dir = test_pipeline_env
    summary = pipeline.run_full_backfill()

    assert "RELIANCE" in summary
    assert "TCS" in summary
    assert summary["RELIANCE"]["status"] == "success"
    assert summary["RELIANCE"]["gold_bars"] == 3
    assert summary["RELIANCE"]["latest_date"] == "2026-01-05"

    # Verify directory structure
    assert (data_dir / "bronze" / "RELIANCE.parquet").exists()
    assert (data_dir / "silver" / "RELIANCE.parquet").exists()
    assert (data_dir / "gold" / "RELIANCE.parquet").exists()
    assert (data_dir / "gold" / "TCS.parquet").exists()

    # Verify FinRL contract
    finrl_data = pipeline.get_finrl_dataset()
    assert "prices" in finrl_data and "features" in finrl_data
    assert validate_market_data(finrl_data) is True
    assert len(finrl_data["prices"]) == 6  # 3 days * 2 stocks


def test_incremental_update(test_pipeline_env):
    pipeline, data_dir = test_pipeline_env

    # 1. Run initial backfill
    pipeline.run_full_backfill()

    # 2. Run incremental update
    inc_summary = pipeline.run_incremental_update()

    assert inc_summary["RELIANCE"]["status"] == "updated"
    assert inc_summary["RELIANCE"]["new_bars"] == 1
    assert inc_summary["RELIANCE"]["latest_date"] == "2026-01-06"
    assert inc_summary["RELIANCE"]["total_silver_bars"] == 4

    # Verify no duplicates in silver/gold
    silver_df = pipeline.silver_transformer.read_silver_data("RELIANCE")
    assert len(silver_df) == 4
    assert list(silver_df["date"]) == ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]

