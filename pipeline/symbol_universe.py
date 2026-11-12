"""
Symbol Universe Manager for Quant_Bot
Defines configurable Indian NSE stock universes with sector classifications
and Yahoo Finance ticker mappings (.NS).
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import pandas as pd


@dataclass(frozen=True)
class StockInfo:
    """Metadata describing a single equity instrument in the trading universe."""
    symbol: str  # NSE Trading Symbol, e.g. "RELIANCE"
    company_name: str
    sector: str
    industry: str
    exchange: str = "NSE"
    is_active: bool = True

    @property
    def yahoo_ticker(self) -> str:
        """Translates NSE symbol to Yahoo Finance ticker format."""
        return f"{self.symbol}.NS"


# Default diversified universe: 15 prominent liquid equities across 8 core Indian sectors
DEFAULT_NSE_UNIVERSE: List[StockInfo] = [
    # Banking & Financial Services
    StockInfo("HDFCBANK", "HDFC Bank Ltd.", "Financial Services", "Private Sector Bank"),
    StockInfo("ICICIBANK", "ICICI Bank Ltd.", "Financial Services", "Private Sector Bank"),
    StockInfo("SBIN", "State Bank of India", "Financial Services", "Public Sector Bank"),

    # Information Technology
    StockInfo("TCS", "Tata Consultancy Services Ltd.", "Information Technology", "IT Services & Consulting"),
    StockInfo("INFY", "Infosys Ltd.", "Information Technology", "IT Services & Consulting"),
    StockInfo("WIPRO", "Wipro Ltd.", "Information Technology", "IT Services & Consulting"),

    # Oil, Gas & Energy
    StockInfo("RELIANCE", "Reliance Industries Ltd.", "Energy", "Oil & Gas Refining & Marketing"),
    StockInfo("ONGC", "Oil and Natural Gas Corporation Ltd.", "Energy", "Oil & Gas Exploration & Production"),

    # Automobiles & Ancillaries
    StockInfo("TATAMOTORS", "Tata Motors Ltd.", "Automobile", "Commercial & Passenger Vehicles"),
    StockInfo("MARUTI", "Maruti Suzuki India Ltd.", "Automobile", "Passenger Cars & Utility Vehicles"),

    # FMCG & Consumer
    StockInfo("ITC", "ITC Ltd.", "Consumer Goods", "Diversified FMCG"),
    StockInfo("HINDUNILVR", "Hindustan Unilever Ltd.", "Consumer Goods", "FMCG - Household & Personal Care"),

    # Metals & Mining
    StockInfo("TATASTEEL", "Tata Steel Ltd.", "Metals & Mining", "Iron & Steel"),

    # Infrastructure & Construction
    StockInfo("LT", "Larsen & Toubro Ltd.", "Construction", "Engineering & Construction"),

    # Telecommunications
    StockInfo("BHARTIARTL", "Bharti Airtel Ltd.", "Telecommunication", "Telecom Services"),
]


class SymbolUniverse:
    """
    Manages the active universe of stocks for data fetching, transformation,
    and quantitative feature generation.
    """

    def __init__(self, stocks: Optional[List[StockInfo]] = None):
        self._stocks: Dict[str, StockInfo] = {}
        initial_stocks = stocks if stocks is not None else DEFAULT_NSE_UNIVERSE
        for stock in initial_stocks:
            self.add_stock(stock)

    def add_stock(self, stock: StockInfo) -> None:
        """Add or update a stock in the universe."""
        clean_symbol = stock.symbol.strip().upper()
        self._stocks[clean_symbol] = stock

    def get_stock(self, symbol: str) -> Optional[StockInfo]:
        """Retrieve stock metadata by NSE symbol."""
        return self._stocks.get(symbol.strip().upper())

    def get_symbols(self, active_only: bool = True) -> List[str]:
        """Return list of NSE symbols."""
        return [
            s.symbol for s in self._stocks.values()
            if not active_only or s.is_active
        ]

    def get_yahoo_tickers(self, active_only: bool = True) -> List[str]:
        """Return list of Yahoo Finance compatible tickers (e.g., 'RELIANCE.NS')."""
        return [
            s.yahoo_ticker for s in self._stocks.values()
            if not active_only or s.is_active
        ]

    @staticmethod
    def to_yahoo_ticker(symbol: str) -> str:
        """Convert a standard NSE symbol to Yahoo ticker."""
        sym = symbol.strip().upper()
        return sym if sym.endswith(".NS") else f"{sym}.NS"

    @staticmethod
    def from_yahoo_ticker(yahoo_ticker: str) -> str:
        """Convert a Yahoo ticker (e.g., 'RELIANCE.NS') back to standard NSE symbol."""
        clean = yahoo_ticker.strip().upper()
        return clean[:-3] if clean.endswith(".NS") else clean

    def get_by_sector(self, sector: str) -> List[StockInfo]:
        """Filter stocks by sector name (case-insensitive)."""
        target = sector.strip().lower()
        return [
            s for s in self._stocks.values()
            if s.sector.strip().lower() == target and s.is_active
        ]

    def get_sectors(self) -> List[str]:
        """Get unique sector names present in the active universe."""
        return sorted({s.sector for s in self._stocks.values() if s.is_active})

    def to_dataframe(self) -> pd.DataFrame:
        """Return active universe as a pandas DataFrame."""
        rows = [asdict(s) for s in self._stocks.values() if s.is_active]
        df = pd.DataFrame(rows)
        if not df.empty:
            df["yahoo_ticker"] = [s.yahoo_ticker for s in self._stocks.values() if s.is_active]
        return df

    def __len__(self) -> int:
        return len([s for s in self._stocks.values() if s.is_active])

    def __repr__(self) -> str:
        return f"<SymbolUniverse active_stocks={len(self)} sectors={len(self.get_sectors())}>"

