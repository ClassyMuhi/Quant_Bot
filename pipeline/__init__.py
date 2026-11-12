"""
Market Data Pipeline Package for Quant_Bot
Implements Medallion Architecture (Bronze -> Silver -> Gold)
for Indian NSE equities.
"""

from .symbol_universe import SymbolUniverse, StockInfo, DEFAULT_NSE_UNIVERSE
from .market_fetcher import MarketFetcher, STANDARD_COLUMNS
from .bronze_writer import BronzeWriter, read_parquet, write_parquet
from .silver_transformer import SilverTransformer, SILVER_COLUMNS
from .gold_features import GoldFeatureGenerator, compute_rsi, compute_atr
from .market_pipeline import MarketPipeline

__all__ = [
    "SymbolUniverse",
    "StockInfo",
    "DEFAULT_NSE_UNIVERSE",
    "MarketFetcher",
    "STANDARD_COLUMNS",
    "BronzeWriter",
    "read_parquet",
    "write_parquet",
    "SilverTransformer",
    "SILVER_COLUMNS",
    "GoldFeatureGenerator",
    "compute_rsi",
    "compute_atr",
    "MarketPipeline",
]
