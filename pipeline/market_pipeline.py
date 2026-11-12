"""
Market Data Pipeline Orchestrator for Quant_Bot
Coordinates the Medallion Architecture data flow:
Yahoo Finance -> Bronze (Raw Parquet) -> Silver (Cleaned OHLCV) -> Gold (Engineered Features).
Supports configurable universes, full historical backfills, and idempotent incremental updates.
"""

from __future__ import annotations
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd

from .symbol_universe import SymbolUniverse
from .market_fetcher import MarketFetcher
from .bronze_writer import BronzeWriter
from .silver_transformer import SilverTransformer
from .gold_features import GoldFeatureGenerator

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class MarketPipeline:
    """
    End-to-end data pipeline orchestrator managing multi-stock market data ingestion,
    cleaning, and feature generation across Bronze, Silver, and Gold layers.
    """

    def __init__(
        self,
        universe: Optional[SymbolUniverse] = None,
        base_data_dir: Union[str, Path] = "data",
        fetcher: Optional[MarketFetcher] = None,
    ):
        self.universe = universe or SymbolUniverse()
        self.base_data_dir = Path(base_data_dir)

        # Initialize storage layers
        self.bronze_writer = BronzeWriter(bronze_dir=self.base_data_dir / "bronze")
        self.silver_transformer = SilverTransformer(
            silver_dir=self.base_data_dir / "silver",
            bronze_writer=self.bronze_writer,
        )
        self.gold_generator = GoldFeatureGenerator(
            gold_dir=self.base_data_dir / "gold",
            silver_transformer=self.silver_transformer,
        )
        self.fetcher = fetcher or MarketFetcher()

    def _resolve_symbols(self, symbols: Optional[List[str]] = None) -> List[str]:
        """Resolves target symbols from parameter or default universe."""
        if symbols:
            return [s.strip().upper() for s in symbols]
        return self.universe.get_symbols()

    def run_full_backfill(
        self,
        symbols: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: Optional[str] = "2y",
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes a complete backfill from scratch across all three layers:
        1. Fetches raw historical OHLCV from Yahoo Finance.
        2. Persists raw data into Bronze Parquet.
        3. Cleans, sanitizes, and standardizes into Silver Parquet.
        4. Calculates and persists model-ready features into Gold Parquet.

        Returns:
            Dictionary mapping symbol -> pipeline summary stats.
        """
        target_symbols = self._resolve_symbols(symbols)
        logger.info(f"Starting full historical backfill for {len(target_symbols)} symbols: {target_symbols}")

        summary: Dict[str, Dict[str, Any]] = {}

        for sym in target_symbols:
            logger.info(f"\n{'='*20} Processing {sym} (Backfill) {'='*20}")
            try:
                # 1. Fetch raw data
                raw_df = self.fetcher.fetch_symbol(
                    sym,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                )
                if raw_df.empty:
                    logger.warning(f"No raw data retrieved for {sym}. Skipping.")
                    summary[sym] = {"status": "failed", "reason": "No data returned from fetcher"}
                    continue

                # 2. Write to Bronze
                self.bronze_writer.write_symbol_data(sym, raw_df)

                # 3. Transform to Silver
                silver_df = self.silver_transformer.transform_symbol(sym, raw_df=raw_df)

                # 4. Generate Gold features
                gold_df = self.gold_generator.generate_symbol_features(sym, silver_df=silver_df)

                latest_date = self.bronze_writer.get_latest_date(sym)
                summary[sym] = {
                    "status": "success",
                    "bronze_bars": len(raw_df),
                    "silver_bars": len(silver_df),
                    "gold_bars": len(gold_df),
                    "latest_date": latest_date,
                }
                logger.info(f"[+] Completed {sym}: {len(gold_df)} feature rows. Latest Date: {latest_date}")

            except Exception as e:
                logger.error(f"Pipeline error processing {sym}: {e}", exc_info=True)
                summary[sym] = {"status": "error", "error": str(e)}

        return summary

    def run_incremental_update(
        self,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes an incremental update:
        1. Checks Bronze via DuckDB for the latest existing bar date.
        2. Fetches only newly created bars strictly after that date.
        3. Merges/deduplicates into Bronze.
        4. Re-cleans into Silver and re-computes Gold features.

        Returns:
            Dictionary mapping symbol -> incremental update stats.
        """
        target_symbols = self._resolve_symbols(symbols)
        logger.info(f"Starting incremental update for {len(target_symbols)} symbols: {target_symbols}")

        summary: Dict[str, Dict[str, Any]] = {}

        for sym in target_symbols:
            logger.info(f"\n{'='*20} Processing {sym} (Incremental) {'='*20}")
            try:
                latest_date = self.bronze_writer.get_latest_date(sym)

                if not latest_date:
                    logger.info(f"No existing Bronze data for {sym}. Falling back to full backfill.")
                    single_summary = self.run_full_backfill(symbols=[sym], period="1y")
                    summary[sym] = single_summary.get(sym, {"status": "failed"})
                    continue

                # Fetch incremental bars
                inc_df = self.fetcher.fetch_incremental(sym, since_date=latest_date)

                if inc_df.empty:
                    logger.info(f"[=] {sym} is already up-to-date as of {latest_date}.")
                    summary[sym] = {"status": "up_to_date", "latest_date": latest_date, "new_bars": 0}
                    continue

                # Write incremental to Bronze (automatically merges & deduplicates)
                self.bronze_writer.write_symbol_data(sym, inc_df)

                # Re-transform full dataset into Silver & Gold
                full_raw = self.bronze_writer.read_symbol_data(sym)
                silver_df = self.silver_transformer.transform_symbol(sym, raw_df=full_raw)
                gold_df = self.gold_generator.generate_symbol_features(sym, silver_df=silver_df)

                new_latest_date = self.bronze_writer.get_latest_date(sym)
                summary[sym] = {
                    "status": "updated",
                    "new_bars": len(inc_df),
                    "total_silver_bars": len(silver_df),
                    "latest_date": new_latest_date,
                }
                logger.info(f"[+] Updated {sym} with {len(inc_df)} new bars. Latest date: {new_latest_date}")

            except Exception as e:
                logger.error(f"Error during incremental update for {sym}: {e}", exc_info=True)
                summary[sym] = {"status": "error", "error": str(e)}

        return summary

    def get_finrl_dataset(self, symbols: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
        """
        Returns model-ready multi-stock dataset conforming to FinRL data contract:
        {"prices": prices_df, "features": features_df}
        """
        target_symbols = self._resolve_symbols(symbols)
        return self.gold_generator.to_finrl_dataset(target_symbols)


def main():
    """CLI entrypoint for Market Data Pipeline."""
    parser = argparse.ArgumentParser(description="Quant_Bot Multi-Stock Market Data Pipeline")
    parser.add_argument("--backfill", action="store_true", help="Run full historical backfill")
    parser.add_argument("--incremental", action="store_true", help="Run incremental daily update")
    parser.add_argument("--period", type=str, default="1y", help="Historical period (e.g. 1y, 2y, 5y)")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to process (default: all in universe)")

    args = parser.parse_args()
    pipeline = MarketPipeline()

    if args.backfill:
        print("[*] Launching Full Historical Backfill...")
        stats = pipeline.run_full_backfill(symbols=args.symbols, period=args.period)
        print("\nBackfill Summary:")
        for sym, stat in stats.items():
            print(f"  {sym:<12}: {stat}")
    elif args.incremental:
        print("[*] Launching Incremental Update...")
        stats = pipeline.run_incremental_update(symbols=args.symbols)
        print("\nIncremental Summary:")
        for sym, stat in stats.items():
            print(f"  {sym:<12}: {stat}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

