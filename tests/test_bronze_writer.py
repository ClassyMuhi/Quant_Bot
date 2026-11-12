"""
Unit tests for pipeline.bronze_writer module.
"""

from pathlib import Path
import pandas as pd
import pytest

from pipeline.bronze_writer import BronzeWriter


@pytest.fixture
def temp_bronze_dir(tmp_path):
    bronze_dir = tmp_path / "bronze"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    return bronze_dir


@pytest.fixture
def sample_market_df():
    return pd.DataFrame([
        {
            "date": "2026-01-01",
            "symbol": "RELIANCE",
            "open": 2500.0,
            "high": 2530.0,
            "low": 2490.0,
            "close": 2515.0,
            "adj_close": 2515.0,
            "volume": 100000,
        },
        {
            "date": "2026-01-02",
            "symbol": "RELIANCE",
            "open": 2520.0,
            "high": 2550.0,
            "low": 2510.0,
            "close": 2540.0,
            "adj_close": 2540.0,
            "volume": 120000,
        },
    ])


def test_write_and_read_symbol_data(temp_bronze_dir, sample_market_df):
    writer = BronzeWriter(bronze_dir=temp_bronze_dir)
    file_path = writer.write_symbol_data("RELIANCE", sample_market_df)

    assert file_path.exists()
    assert file_path.suffix == ".parquet"

    read_df = writer.read_symbol_data("RELIANCE")
    assert len(read_df) == 2
    assert "_ingested_at_utc" in read_df.columns
    assert "_source" in read_df.columns
    assert (read_df["symbol"] == "RELIANCE").all()


def test_incremental_append_and_deduplication(temp_bronze_dir, sample_market_df):
    writer = BronzeWriter(bronze_dir=temp_bronze_dir)
    writer.write_symbol_data("RELIANCE", sample_market_df)

    # New batch with one duplicate date and one new date
    new_data = pd.DataFrame([
        {
            "date": "2026-01-02",  # Duplicate date with updated volume
            "symbol": "RELIANCE",
            "open": 2520.0,
            "high": 2550.0,
            "low": 2510.0,
            "close": 2545.0,
            "adj_close": 2545.0,
            "volume": 130000,
        },
        {
            "date": "2026-01-05",  # New date
            "symbol": "RELIANCE",
            "open": 2545.0,
            "high": 2570.0,
            "low": 2530.0,
            "close": 2560.0,
            "adj_close": 2560.0,
            "volume": 150000,
        },
    ])

    writer.write_symbol_data("RELIANCE", new_data)
    read_df = writer.read_symbol_data("RELIANCE")

    # Should have 3 dates: 2026-01-01, 2026-01-02 (updated close 2545.0), 2026-01-05
    assert len(read_df) == 3
    assert list(read_df["date"]) == ["2026-01-01", "2026-01-02", "2026-01-05"]
    row_02 = read_df[read_df["date"] == "2026-01-02"].iloc[0]
    assert row_02["close"] == 2545.0


def test_duckdb_queries(temp_bronze_dir, sample_market_df):
    writer = BronzeWriter(bronze_dir=temp_bronze_dir)
    writer.write_symbol_data("RELIANCE", sample_market_df)

    latest_date = writer.get_latest_date("RELIANCE")
    assert latest_date == "2026-01-02"

    assert writer.get_latest_date("NONEXISTENT") is None

    # SQL query test
    query = f"SELECT count(*) as total_rows FROM read_parquet('{(temp_bronze_dir / 'RELIANCE.parquet').as_posix()}')"
    res = writer.query_duckdb(query)
    assert res["total_rows"].iloc[0] == 2

