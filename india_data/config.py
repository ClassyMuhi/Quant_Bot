"""
Configuration parameters and constants for India Market Data Engine.
"""

from pathlib import Path

# Project Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Data Storage Directories
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DATA_DIR = DATA_DIR / "historical"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Default Market Data Settings
DEFAULT_PERIOD = "5y"
DEFAULT_BENCHMARK = "^NSEI"

# Required Schema Definitions
REQUIRED_RAW_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
REQUIRED_LONG_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]

# Ensure storage directories exist
HISTORICAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
