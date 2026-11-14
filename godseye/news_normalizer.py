"""
News Normalizer for God's Eye Market Intelligence
Maps unstructured financial news to NSE stock symbols and sectors,
normalizes publication timestamps, and detects duplicate/similar events.
"""

from __future__ import annotations
import re
from typing import Dict, List, Set, Tuple
from pipeline.symbol_universe import SymbolUniverse, DEFAULT_NSE_UNIVERSE

# Extended mapping of company variations & aliases to NSE symbols
COMPANY_NAME_ALIASES: Dict[str, str] = {
    "reliance": "RELIANCE",
    "ril": "RELIANCE",
    "reliance industries": "RELIANCE",
    "tcs": "TCS",
    "tata consultancy": "TCS",
    "infosys": "INFY",
    "infy": "INFY",
    "wipro": "WIPRO",
    "hdfc bank": "HDFCBANK",
    "hdfc": "HDFCBANK",
    "icici bank": "ICICIBANK",
    "icici": "ICICIBANK",
    "sbi": "SBIN",
    "state bank of india": "SBIN",
    "state bank": "SBIN",
    "bharti airtel": "BHARTIARTL",
    "airtel": "BHARTIARTL",
    "itc": "ITC",
    "hindustan unilever": "HINDUNILVR",
    "hul": "HINDUNILVR",
    "larsen & toubro": "LT",
    "l&t": "LT",
    "tata motors": "TATAMOTORS",
    "maruti suzuki": "MARUTI",
    "maruti": "MARUTI",
    "tata steel": "TATASTEEL",
    "ongc": "ONGC",
    "bajaj finance": "BAJFINANCE",
    "kotak mahindra": "KOTAKBANK",
    "kotak bank": "KOTAKBANK",
    "axis bank": "AXISBANK",
    "sun pharma": "SUNPHARMA",
}

# Sector identification patterns
SECTOR_KEYWORDS: Dict[str, List[str]] = {
    "Financial Services": ["bank", "nbfc", "lending", "credit", "repo rate", "rbi", "monetary policy", "interest rate", "npa"],
    "Information Technology": ["it", "tech", "software", "cloud", "saas", "ai", "consulting", "h1-b", "deal win"],
    "Energy": ["oil", "gas", "petroleum", "crude", "refinery", "brent", "opec", "energy", "power"],
    "Automobile": ["auto", "vehicle", "car", "ev", "passenger vehicle", "truck", "two-wheeler"],
    "Consumer Goods": ["fmcg", "consumer", "food", "beverage", "retail", "consumption", "rural demand"],
    "Metals & Mining": ["steel", "iron", "aluminum", "copper", "mining", "metal", "ore"],
    "Telecommunication": ["telecom", "5g", "spectrum", "tariff", "mobile subscriber", "broadband"],
    "Macro & Policy": ["gdp", "inflation", "cpi", "fiscal deficit", "budget", "finance ministry", "rupee", "sebi"],
}


class NewsNormalizer:
    """
    Cleans raw news items, identifies affected NSE equities & sectors,
    and eliminates redundant duplicate headlines.
    """

    def __init__(self, universe: Optional[SymbolUniverse] = None):
        self.universe = universe or SymbolUniverse()
        self.known_symbols = set(self.universe.get_symbols())
        # Compile symbol regex with word boundaries
        all_syms = sorted(list(self.known_symbols), key=len, reverse=True)
        sym_pattern = r"\b(" + "|".join(all_syms) + r")\b"
        self._symbol_regex = re.compile(sym_pattern, re.IGNORECASE)

    def extract_symbols_and_sectors(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Scans headline and description for mentioned NSE tickers, company aliases, and sector themes.
        """
        text_lower = text.lower()
        matched_symbols: Set[str] = set()

        # 1. Match direct ticker symbols (case-insensitive with word boundary)
        for match in self._symbol_regex.finditer(text):
            matched_symbols.add(match.group(0).upper())

        # 2. Match company name aliases
        for alias, sym in COMPANY_NAME_ALIASES.items():
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, text_lower):
                matched_symbols.add(sym)

        # 3. Match sectors based on matched stocks + general sector keywords
        matched_sectors: Set[str] = set()
        for sym in matched_symbols:
            stock_info = self.universe.get_stock(sym)
            if stock_info:
                matched_sectors.add(stock_info.sector)

        for sector, keywords in SECTOR_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                    matched_sectors.add(sector)
                    break

        return sorted(list(matched_symbols)), sorted(list(matched_sectors))

    @staticmethod
    def calculate_title_similarity(title1: str, title2: str) -> float:
        """Computes Jaccard similarity between two headline token sets."""
        tokens1 = set(re.findall(r"\w+", title1.lower()))
        tokens2 = set(re.findall(r"\w+", title2.lower()))
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        return len(intersection) / float(len(union))

    def deduplicate(
        self,
        news_items: List[Dict[str, Any]],
        similarity_threshold: float = 0.70,
    ) -> List[Dict[str, Any]]:
        """
        Removes identical articles and near-duplicate syndicated headlines.
        """
        deduped: List[Dict[str, Any]] = []
        for item in news_items:
            is_dup = False
            for existing in deduped:
                # 1. Same exact URL or ID
                if item.get("article_id") == existing.get("article_id") or (
                    item.get("url") and item.get("url") == existing.get("url")
                ):
                    is_dup = True
                    break
                # 2. Similar headline content
                sim = self.calculate_title_similarity(item.get("title", ""), existing.get("title", ""))
                if sim >= similarity_threshold:
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(item)

        return deduped

    def process_feed_items(
        self,
        raw_items: List[Dict[str, Any]],
        similarity_threshold: float = 0.70,
    ) -> List[Dict[str, Any]]:
        """
        Normalizes raw feed articles: identifies symbols & sectors,
        assigns event_id, and removes duplicate/syndicated stories.
        """
        enriched = []
        for item in raw_items:
            title = item.get("title", "")
            desc = item.get("description", "")
            combined_text = f"{title}. {desc}".strip()

            symbols, sectors = self.extract_symbols_and_sectors(combined_text)

            enriched.append({
                "event_id": item.get("article_id") or item.get("event_id") or str(hash(item.get("url", "") + title)),
                "title": title,
                "description": desc,
                "source": item.get("source", "Unknown"),
                "url": item.get("url", ""),
                "published_at": item.get("published_at", ""),
                "collected_at": item.get("collected_at", ""),
                "affected_symbols": symbols,
                "affected_sectors": sectors,
            })

        return self.deduplicate(enriched, similarity_threshold=similarity_threshold)
