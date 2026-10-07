"""
India Market Data Engine (india_data)
Provides ingestion, validation, MegaBull mapping, and FinRL transformation
for Indian equity and benchmark datasets.
"""

from india_data.config import (
    HISTORICAL_DATA_DIR,
    PROCESSED_DATA_DIR,
    DEFAULT_PERIOD,
    DEFAULT_BENCHMARK,
    REQUIRED_RAW_COLUMNS,
    REQUIRED_LONG_COLUMNS,
)
from india_data.universe import (
    INDIAN_STOCKS,
    BENCHMARK_INDEX,
    INDEX_MAPPINGS,
    to_yfinance_symbol,
    to_canonical_symbol,
    get_yfinance_symbols,
    MegaBullSymbolMapper,
)
from india_data.validator import (
    DataValidationError,
    validate_market_dataframe,
)
from india_data.loader import (
    DataDownloadError,
    download_history,
    load_history,
    save_history,
    load_or_download,
    load_universe,
)
from india_data.transformer import (
    to_finrl_format,
    save_processed_data,
)

__all__ = [
    # Config
    "HISTORICAL_DATA_DIR",
    "PROCESSED_DATA_DIR",
    "DEFAULT_PERIOD",
    "DEFAULT_BENCHMARK",
    "REQUIRED_RAW_COLUMNS",
    "REQUIRED_LONG_COLUMNS",
    # Universe & Mappings
    "INDIAN_STOCKS",
    "BENCHMARK_INDEX",
    "INDEX_MAPPINGS",
    "to_yfinance_symbol",
    "to_canonical_symbol",
    "get_yfinance_symbols",
    "MegaBullSymbolMapper",
    # Validator
    "DataValidationError",
    "validate_market_dataframe",
    # Loader
    "DataDownloadError",
    "download_history",
    "load_history",
    "save_history",
    "load_or_download",
    "load_universe",
    # Transformer
    "to_finrl_format",
    "save_processed_data",
]
