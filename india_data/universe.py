"""
Universe Definition & Symbol Mapping Adapter for Indian Equities.
Provides mappings between Canonical Symbols, Yahoo Finance Symbols, and MegaBull Instruments.
"""

from typing import Any, Dict, List, Optional, Union
import pandas as pd
from pathlib import Path

# -------------------------------------------------------------------------
# Initial Indian Equity Universe & Benchmark
# -------------------------------------------------------------------------

INDIAN_STOCKS: List[str] = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "LT",
    "BHARTIARTL",
    "AXISBANK",
]

BENCHMARK_INDEX: str = "^NSEI"

# Common index symbol aliases
INDEX_MAPPINGS: Dict[str, str] = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY 50": "^NSEI",
    "^NSEI": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "^NSEBANK": "^NSEBANK",
}


def to_yfinance_symbol(canonical_symbol: str) -> str:
    """
    Map a canonical Indian stock symbol or index to its Yahoo Finance query symbol.

    Examples:
        RELIANCE -> RELIANCE.NS
        TCS      -> TCS.NS
        NIFTY 50 -> ^NSEI
        ^NSEI    -> ^NSEI

    Args:
        canonical_symbol: Clean ticker symbol (e.g. 'RELIANCE', 'TCS', '^NSEI').

    Returns:
        Yahoo Finance ticker string with exchange suffix.
    """
    clean_sym = canonical_symbol.strip().upper()

    # Check index mappings first
    if clean_sym in INDEX_MAPPINGS:
        return INDEX_MAPPINGS[clean_sym]

    if clean_sym.startswith("^"):
        return clean_sym

    if clean_sym.endswith(".NS") or clean_sym.endswith(".BO"):
        return clean_sym

    return f"{clean_sym}.NS"


def to_canonical_symbol(yf_symbol: str) -> str:
    """
    Map a Yahoo Finance symbol back to its canonical Indian stock symbol.

    Examples:
        RELIANCE.NS -> RELIANCE
        TCS.NS      -> TCS
        ^NSEI       -> ^NSEI

    Args:
        yf_symbol: Yahoo Finance ticker (e.g. 'RELIANCE.NS', '^NSEI').

    Returns:
        Canonical symbol string without vendor suffix.
    """
    clean_sym = yf_symbol.strip().upper()

    if clean_sym == "^NSEI":
        return "^NSEI"

    for suffix in [".NS", ".BO"]:
        if clean_sym.endswith(suffix):
            return clean_sym[:-len(suffix)]

    return clean_sym


def get_yfinance_symbols(symbols: Optional[List[str]] = None) -> Dict[str, str]:
    """
    Generate mapping dictionary {canonical_symbol: yf_symbol} for a given list of symbols.
    Defaults to INDIAN_STOCKS if None.
    """
    symbol_list = symbols if symbols is not None else INDIAN_STOCKS
    return {sym: to_yfinance_symbol(sym) for sym in symbol_list}


# -------------------------------------------------------------------------
# MegaBull Symbol Mapping Adapter
# -------------------------------------------------------------------------

class MegaBullSymbolMapper:
    """
    Maps canonical symbols to MegaBull trading symbols and instrument tokens.

    Loads and searches MegaBull's tradable instruments list dynamically.
    Never hardcodes instrument tokens.
    """

    def __init__(
        self,
        instruments_df: Optional[pd.DataFrame] = None,
        instruments_csv_path: Optional[Union[str, Path]] = None,
        broker_client: Optional[Any] = None,
    ):
        """
        Initialize the symbol mapper.

        Args:
            instruments_df: Optional pre-loaded MegaBull instruments DataFrame.
            instruments_csv_path: Optional path to a saved MegaBull instruments CSV.
            broker_client: Optional MegaBull broker client instance to fetch instruments.
        """
        self._instruments_df: Optional[pd.DataFrame] = None

        if instruments_df is not None:
            self.load_instruments_dataframe(instruments_df)
        elif instruments_csv_path is not None:
            self.load_instruments_from_csv(instruments_csv_path)
        elif broker_client is not None:
            self.load_instruments_from_broker(broker_client)

    @property
    def instruments_df(self) -> Optional[pd.DataFrame]:
        return self._instruments_df

    def load_instruments_dataframe(self, df: pd.DataFrame) -> None:
        """Load instruments from a pandas DataFrame."""
        if not isinstance(df, pd.DataFrame):
            raise TypeError("instruments must be a pandas DataFrame.")
        self._instruments_df = df.copy()

    def load_instruments_from_csv(self, csv_path: Union[str, Path]) -> None:
        """Load instruments from a CSV file."""
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Instruments file not found: {path}")
        self._instruments_df = pd.read_csv(path)

    def load_instruments_from_broker(self, broker_client: Any) -> None:
        """Fetch instruments from an active MegaBull broker instance."""
        self._instruments_df = broker_client.get_instruments(as_dataframe=True)

    def get_trading_symbol(self, symbol: str) -> str:
        """
        Get MegaBull trading symbol for a canonical symbol.
        In Indian equity segment, canonical name maps directly to tradingSymbol (e.g. 'RELIANCE').
        """
        return to_canonical_symbol(symbol)

    def get_token(self, symbol: str, exchange: str = "NSE") -> Optional[int]:
        """
        Resolve MegaBull instrumentToken for a canonical symbol.

        Args:
            symbol: Canonical stock symbol (e.g. 'RELIANCE').
            exchange: Exchange segment (default: 'NSE').

        Returns:
            instrumentToken as integer, or None if not found.
        """
        if self._instruments_df is None or self._instruments_df.empty:
            raise ValueError(
                "MegaBull instruments data is not loaded. "
                "Provide instruments_df, instruments_csv_path, or broker_client."
            )

        canonical = to_canonical_symbol(symbol)
        df = self._instruments_df

        # Look for matching tradingSymbol
        matched = df[df["tradingSymbol"].astype(str).str.upper() == canonical]

        # Filter by exchange if available
        if "exchange" in matched.columns and exchange:
            exch_match = matched[matched["exchange"].astype(str).str.upper() == exchange.upper()]
            if not exch_match.empty:
                matched = exch_match

        if matched.empty:
            return None

        # Return instrumentToken
        token_col = "instrumentToken" if "instrumentToken" in matched.columns else "instrument_token"
        if token_col in matched.columns:
            token_val = matched.iloc[0][token_col]
            try:
                return int(token_val)
            except (ValueError, TypeError):
                return None

        return None

    def resolve(self, symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
        """
        Resolve complete symbol mapping for a given asset.

        Args:
            symbol: Canonical symbol or Yahoo Finance ticker.
            exchange: Target exchange (default: 'NSE').

        Returns:
            Dictionary containing:
                - canonical_symbol: e.g. 'RELIANCE'
                - yfinance_symbol: e.g. 'RELIANCE.NS'
                - megabull_symbol: e.g. 'RELIANCE'
                - instrument_token: integer token or None
        """
        canonical = to_canonical_symbol(symbol)
        yf_sym = to_yfinance_symbol(canonical)
        mb_sym = self.get_trading_symbol(canonical)

        token = None
        if self._instruments_df is not None and not self._instruments_df.empty:
            token = self.get_token(canonical, exchange=exchange)

        return {
            "canonical_symbol": canonical,
            "yfinance_symbol": yf_sym,
            "megabull_symbol": mb_sym,
            "instrument_token": token,
        }

    def batch_resolve(
        self,
        symbols: Optional[List[str]] = None,
        exchange: str = "NSE"
    ) -> pd.DataFrame:
        """
        Resolve symbol mappings for a list of symbols into a DataFrame.
        """
        target_symbols = symbols if symbols is not None else INDIAN_STOCKS
        rows = [self.resolve(sym, exchange=exchange) for sym in target_symbols]
        return pd.DataFrame(rows)
