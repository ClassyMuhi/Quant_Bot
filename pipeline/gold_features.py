"""
Gold Layer Feature Engineering for Quant_Bot
Generates model-ready technical, momentum, volatility, and volume features
from clean Silver OHLCV data. Supports per-symbol and multi-stock operations.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd

from .bronze_writer import read_parquet, write_parquet
from .silver_transformer import SilverTransformer

logger = logging.getLogger(__name__)


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Computes the Relative Strength Index (RSI) using exponential smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Where avg_loss is 0, RSI is 100; where both are 0, RSI is 50
    rsi = rsi.fillna(100.0)
    rsi.loc[(avg_gain == 0) & (avg_loss == 0)] = 50.0
    return rsi


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Computes the Average True Range (ATR)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


class GoldFeatureGenerator:
    """
    Computes financial, momentum, volatility, and trend features
    from Silver market data and persists them to Gold storage (data/gold).
    """

    def __init__(
        self,
        gold_dir: Union[str, Path] = "data/gold",
        silver_transformer: Optional[SilverTransformer] = None,
    ):
        self.gold_dir = Path(gold_dir)
        self.gold_dir.mkdir(parents=True, exist_ok=True)
        self.silver_transformer = silver_transformer or SilverTransformer()

    def _get_file_path(self, symbol: str) -> Path:
        """Standardized path for a symbol's Gold Parquet file."""
        return self.gold_dir / f"{symbol.strip().upper()}.parquet"

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates alpha and technical features for a single stock's clean OHLCV series.
        Expected input columns: ['date', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'adj_close']
        """
        if df.empty:
            return pd.DataFrame()

        data = df.sort_values(by="date").copy()

        # 1. Price Returns
        data["return_1d"] = data["close"].pct_change(1)
        data["log_return_1d"] = np.log(data["close"] / data["close"].shift(1))
        data["return_5d"] = data["close"].pct_change(5)
        data["return_20d"] = data["close"].pct_change(20)

        # 2. Moving Averages & Trend
        data["sma_10"] = data["close"].rolling(window=10, min_periods=1).mean()
        data["sma_20"] = data["close"].rolling(window=20, min_periods=1).mean()
        data["sma_50"] = data["close"].rolling(window=50, min_periods=1).mean()
        data["close_to_sma_20"] = (data["close"] / data["sma_20"]) - 1.0

        # Exponential Moving Averages & MACD
        data["ema_12"] = data["close"].ewm(span=12, adjust=False).mean()
        data["ema_26"] = data["close"].ewm(span=26, adjust=False).mean()
        data["macd"] = data["ema_12"] - data["ema_26"]
        data["macd_signal"] = data["macd"].ewm(span=9, adjust=False).mean()
        data["macd_hist"] = data["macd"] - data["macd_signal"]

        # 3. Momentum: RSI (14)
        data["rsi_14"] = compute_rsi(data["close"], period=14)

        # 4. Volatility & Risk
        # 20-day annualized rolling volatility (assuming 252 trading days)
        data["volatility_20d"] = data["return_1d"].rolling(window=20, min_periods=5).std() * np.sqrt(252)
        data["atr_14"] = compute_atr(data["high"], data["low"], data["close"], period=14)
        data["natr_14"] = (data["atr_14"] / data["close"]) * 100.0  # Normalized ATR (%)

        # 5. Volume Indicators
        data["volume_sma_20"] = data["volume"].rolling(window=20, min_periods=1).mean()
        data["volume_ratio_20"] = data["volume"] / data["volume_sma_20"].replace(0, np.nan)
        # Approximate Rolling VWAP (20-day)
        cum_vol = data["volume"].rolling(window=20, min_periods=1).sum()
        cum_vol_price = (data["close"] * data["volume"]).rolling(window=20, min_periods=1).sum()
        data["vwap_20"] = cum_vol_price / cum_vol.replace(0, np.nan)

        return data.reset_index(drop=True)

    def generate_symbol_features(
        self,
        symbol: str,
        silver_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Computes and saves Gold features for a given symbol.
        """
        clean_symbol = symbol.strip().upper()
        if silver_df is None or silver_df.empty:
            silver_df = self.silver_transformer.read_silver_data(clean_symbol)

        if silver_df.empty:
            logger.warning(f"No Silver data found for {clean_symbol}. Skipping gold feature generation.")
            return pd.DataFrame()

        gold_df = self.compute_features(silver_df)
        if not gold_df.empty:
            target_path = self._get_file_path(clean_symbol)
            write_parquet(gold_df, target_path)
            logger.info(f"Gold feature dataset saved for {clean_symbol}: {len(gold_df)} bars at {target_path}")

        return gold_df

    def generate_batch(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Compute Gold features across multiple symbols."""
        results: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            df = self.generate_symbol_features(sym)
            if not df.empty:
                results[sym] = df
        return results

    def read_gold_data(self, symbol: str) -> pd.DataFrame:
        """Read Gold features for a symbol."""
        target_path = self._get_file_path(symbol)
        if not target_path.exists():
            return pd.DataFrame()
        return read_parquet(target_path)

    def get_consolidated_features(self, symbols: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Consolidates Gold features across all requested symbols into a unified multi-stock DataFrame.
        """
        target_symbols = symbols if symbols is not None else self.list_available_symbols()
        dfs = []
        for sym in target_symbols:
            df = self.read_gold_data(sym)
            if not df.empty:
                dfs.append(df)

        if not dfs:
            return pd.DataFrame()

        consolidated = pd.concat(dfs, ignore_index=True)
        return consolidated.sort_values(by=["date", "symbol"]).reset_index(drop=True)

    def to_finrl_dataset(
        self,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Formats Gold data into the FinRL multi-stock data contract:
        {
            "prices": pd.DataFrame with ['date', 'symbol', 'close', ...],
            "features": pd.DataFrame with all computed technical indicators
        }
        """
        full_df = self.get_consolidated_features(symbols)
        if full_df.empty:
            return {"prices": pd.DataFrame(), "features": pd.DataFrame()}

        price_cols = ["date", "symbol", "open", "high", "low", "close", "adj_close", "volume"]
        prices_df = full_df[[c for c in price_cols if c in full_df.columns]].copy()
        features_df = full_df.copy()

        return {
            "prices": prices_df,
            "features": features_df,
        }

    def list_available_symbols(self) -> List[str]:
        """List symbols currently saved in Gold storage."""
        return sorted([p.stem for p in self.gold_dir.glob("*.parquet")])

