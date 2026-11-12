"""
Unit tests for pipeline.gold_features module.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from pipeline.gold_features import GoldFeatureGenerator, compute_rsi, compute_atr
from pipeline.silver_transformer import SilverTransformer
from pipeline.bronze_writer import BronzeWriter
from finrl_adapter.data_contract import validate_market_data


def test_compute_rsi_monotonic():
    # Continual upward series -> RSI should approach 100
    up_prices = pd.Series([100 + i * 2 for i in range(30)])
    rsi_up = compute_rsi(up_prices, period=14)
    assert rsi_up.iloc[-1] > 90.0

    # Continual downward series -> RSI should approach 0
    down_prices = pd.Series([200 - i * 2 for i in range(30)])
    rsi_down = compute_rsi(down_prices, period=14)
    assert rsi_down.iloc[-1] < 10.0


def test_compute_atr_positive():
    high = pd.Series([105, 107, 106, 110, 108])
    low = pd.Series([95, 96, 98, 99, 97])
    close = pd.Series([100, 102, 101, 105, 103])
    atr = compute_atr(high, low, close, period=3)
    assert (atr.dropna() > 0).all()


@pytest.fixture
def sample_clean_ohlcv():
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    np.random.seed(42)
    base = 2000.0
    rows = []
    for d in dates:
        close = base + float(np.random.normal(0, 10))
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "symbol": "RELIANCE",
            "open": close - 5.0,
            "high": close + 10.0,
            "low": close - 10.0,
            "close": close,
            "adj_close": close,
            "volume": 100000,
        })
    return pd.DataFrame(rows)


def test_feature_generation_columns(sample_clean_ohlcv):
    generator = GoldFeatureGenerator()
    features_df = generator.compute_features(sample_clean_ohlcv)

    expected_cols = [
        "return_1d",
        "log_return_1d",
        "sma_10",
        "sma_20",
        "ema_12",
        "ema_26",
        "macd",
        "macd_signal",
        "rsi_14",
        "volatility_20d",
        "atr_14",
        "volume_sma_20",
        "volume_ratio_20",
        "vwap_20",
    ]
    for col in expected_cols:
        assert col in features_df.columns, f"Missing column: {col}"

    assert len(features_df) == 30
    assert (features_df["rsi_14"].dropna() >= 0).all() and (features_df["rsi_14"].dropna() <= 100).all()


def test_gold_persistence_and_finrl_export(tmp_path, sample_clean_ohlcv):
    gold_dir = tmp_path / "gold"
    silver_dir = tmp_path / "silver"
    gold_dir.mkdir()
    silver_dir.mkdir()

    # Save a mock silver file
    from pipeline.bronze_writer import write_parquet
    silver_file = silver_dir / "RELIANCE.parquet"
    write_parquet(sample_clean_ohlcv, silver_file)

    st = SilverTransformer(silver_dir=silver_dir)
    generator = GoldFeatureGenerator(gold_dir=gold_dir, silver_transformer=st)

    gold_df = generator.generate_symbol_features("RELIANCE")
    assert not gold_df.empty
    assert (gold_dir / "RELIANCE.parquet").exists()

    # Test FinRL dataset output
    dataset = generator.to_finrl_dataset(["RELIANCE"])
    assert "prices" in dataset and "features" in dataset
    assert validate_market_data(dataset) is True
    assert "rsi_14" in dataset["features"].columns

