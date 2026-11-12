"""
Unit tests for pipeline.silver_transformer module.
"""

from pathlib import Path
import pandas as pd
import numpy as np
import pytest

from pipeline.bronze_writer import BronzeWriter
from pipeline.silver_transformer import SilverTransformer, SILVER_COLUMNS
from finrl_adapter.data_contract import validate_market_data


@pytest.fixture
def temp_dirs(tmp_path):
    bronze_dir = tmp_path / "bronze"
    silver_dir = tmp_path / "silver"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    silver_dir.mkdir(parents=True, exist_ok=True)
    return bronze_dir, silver_dir


def test_clean_data_anomalies_and_deduplication(temp_dirs):
    bronze_dir, silver_dir = temp_dirs
    transformer = SilverTransformer(silver_dir=silver_dir)

    dirty_data = pd.DataFrame([
        # Out-of-order date
        {
            "date": "2026-01-03",
            "symbol": "TCS",
            "open": 3500.0,
            "high": 3400.0,  # Anomaly: high is lower than open
            "low": 3550.0,   # Anomaly: low is higher than open
            "close": 3520.0,
            "adj_close": 3520.0,
            "volume": 50000,
        },
        # Earlier date
        {
            "date": "2026-01-01",
            "symbol": "TCS",
            "open": 3480.0,
            "high": 3510.0,
            "low": 3470.0,
            "close": 3500.0,
            "adj_close": 3500.0,
            "volume": 60000,
        },
        # Duplicate date of 2026-01-01 (should be replaced)
        {
            "date": "2026-01-01",
            "symbol": "TCS",
            "open": 3480.0,
            "high": 3515.0,
            "low": 3470.0,
            "close": 3505.0,
            "adj_close": 3505.0,
            "volume": 65000,
        },
        # Negative price row (should be dropped)
        {
            "date": "2026-01-02",
            "symbol": "TCS",
            "open": -100.0,
            "high": 100.0,
            "low": -200.0,
            "close": -50.0,
            "adj_close": -50.0,
            "volume": 1000,
        },
    ])

    cleaned = transformer.clean_data(dirty_data, "TCS")

    # Should have 2 rows (2026-01-01 deduplicated, 2026-01-03 fixed, 2026-01-02 dropped)
    assert len(cleaned) == 2
    assert list(cleaned["date"]) == ["2026-01-01", "2026-01-03"]

    # Verify deduplication kept the later duplicate
    row_01 = cleaned[cleaned["date"] == "2026-01-01"].iloc[0]
    assert row_01["close"] == 3505.0

    # Verify high >= max(open, close) and low <= min(open, close)
    row_03 = cleaned[cleaned["date"] == "2026-01-03"].iloc[0]
    assert row_03["high"] >= max(row_03["open"], row_03["close"])
    assert row_03["low"] <= min(row_03["open"], row_03["close"])


def test_transform_and_finrl_contract(temp_dirs):
    bronze_dir, silver_dir = temp_dirs
    bw = BronzeWriter(bronze_dir=bronze_dir)
    transformer = SilverTransformer(silver_dir=silver_dir, bronze_writer=bw)

    # Ingest 2 stocks into Bronze
    df_infy = pd.DataFrame([
        {"date": "2026-01-01", "symbol": "INFY", "open": 1500.0, "high": 1520.0, "low": 1490.0, "close": 1510.0, "adj_close": 1510.0, "volume": 10000},
        {"date": "2026-01-02", "symbol": "INFY", "open": 1510.0, "high": 1530.0, "low": 1500.0, "close": 1525.0, "adj_close": 1525.0, "volume": 12000},
    ])
    df_wipro = pd.DataFrame([
        {"date": "2026-01-01", "symbol": "WIPRO", "open": 450.0, "high": 460.0, "low": 445.0, "close": 455.0, "adj_close": 455.0, "volume": 20000},
        {"date": "2026-01-02", "symbol": "WIPRO", "open": 455.0, "high": 465.0, "low": 450.0, "close": 462.0, "adj_close": 462.0, "volume": 22000},
    ])

    bw.write_symbol_data("INFY", df_infy)
    bw.write_symbol_data("WIPRO", df_wipro)

    # Transform to Silver
    batch_res = transformer.transform_batch(["INFY", "WIPRO"])
    assert len(batch_res) == 2
    assert "INFY" in batch_res and "WIPRO" in batch_res

    # Test consolidated multi-stock data
    consolidated = transformer.get_consolidated_prices()
    assert len(consolidated) == 4
    assert set(consolidated["symbol"].unique()) == {"INFY", "WIPRO"}

    # Test FinRL data contract
    finrl_data = transformer.to_finrl_data_contract()
    assert "prices" in finrl_data
    assert validate_market_data(finrl_data) is True

