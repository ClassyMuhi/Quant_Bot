"""
Event Store for God's Eye Market Intelligence
Implements Medallion Architecture for financial news & market events:
- Bronze: Raw scraped/collected event payloads (JSON/Parquet)
- Silver: Cleaned, structured, classified events with metadata (Parquet)
- Gold: Aggregated symbol-level numerical event features for models & decisions (Parquet)

Enforces strict zero look-ahead bias: historical queries only access events
with published_at <= decision_timestamp.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_BRONZE_DIR = Path("data/news/bronze")
DEFAULT_SILVER_DIR = Path("data/news/silver")
DEFAULT_GOLD_DIR = Path("data/news/gold")


class EventStore:
    """
    Manages persistence and retrieval across Bronze, Silver, and Gold news event layers.
    """

    def __init__(
        self,
        bronze_dir: Optional[Path] = None,
        silver_dir: Optional[Path] = None,
        gold_dir: Optional[Path] = None,
    ):
        self.bronze_dir = Path(bronze_dir or DEFAULT_BRONZE_DIR)
        self.silver_dir = Path(silver_dir or DEFAULT_SILVER_DIR)
        self.gold_dir = Path(gold_dir or DEFAULT_GOLD_DIR)

        # Ensure directories exist
        for d in [self.bronze_dir, self.silver_dir, self.gold_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.silver_file = self.silver_dir / "events.parquet"
        self.gold_file = self.gold_dir / "news_features.parquet"

    # ---------------------------------------------------------
    # Bronze Layer: Raw Ingestion Persistence
    # ---------------------------------------------------------
    def save_bronze(self, raw_items: List[Dict[str, Any]], batch_name: Optional[str] = None) -> Path:
        """
        Saves raw ingested news payloads to Bronze storage.
        """
        if not raw_items:
            logger.info("No raw items to save in Bronze.")
            return self.bronze_dir

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        batch_id = batch_name or f"batch_{timestamp_str}"
        target_file = self.bronze_dir / f"{batch_id}.json"

        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(raw_items, f, indent=2, ensure_ascii=False)

        logger.info("Saved %d raw news records to Bronze: %s", len(raw_items), target_file)
        return target_file

    # ---------------------------------------------------------
    # Silver Layer: Cleaned, Deduplicated & Classified Events
    # ---------------------------------------------------------
    def save_silver(self, events: List[Dict[str, Any]]) -> Path:
        """
        Appends or upserts classified events into Silver Parquet table.
        Avoids duplicates based on event_id.
        Uses DuckDB to safely read and write Parquet without pyarrow DLL issues.
        """
        if not events:
            return self.silver_file

        # Format events into DataFrame with explicit schema
        records = []
        for e in events:
            # Flatten lists to comma-separated strings for Parquet compatibility
            symbols_str = ",".join(e.get("affected_symbols", []))
            sectors_str = ",".join(e.get("affected_sectors", []))

            records.append({
                "event_id": str(e.get("event_id", "")),
                "title": str(e.get("title", "")),
                "description": str(e.get("description", "")),
                "source": str(e.get("source", "")),
                "url": str(e.get("url", "")),
                "published_at": str(e.get("published_at", "")),
                "collected_at": str(e.get("collected_at", "")),
                "affected_symbols": symbols_str,
                "affected_sectors": sectors_str,
                "sentiment": str(e.get("sentiment", "NEUTRAL")).upper(),
                "importance": int(e.get("importance", 5)),
                "confidence": float(e.get("confidence", 0.5)),
            })

        new_df = pd.DataFrame(records)

        con = duckdb.connect()
        try:
            if self.silver_file.exists():
                # Read existing events, merge, and deduplicate on event_id
                old_df = con.execute(f"SELECT * FROM read_parquet('{self.silver_file.as_posix()}')").df()
                combined_df = pd.concat([old_df, new_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=["event_id"], keep="last")
            else:
                combined_df = new_df

            # Sort chronologically by published_at
            combined_df = combined_df.sort_values(by="published_at", ascending=True)

            # Register view in duckdb and export to parquet
            con.register("silver_view", combined_df)
            con.execute(f"COPY silver_view TO '{self.silver_file.as_posix()}' (FORMAT PARQUET)")
            logger.info("Saved %d total Silver events to %s", len(combined_df), self.silver_file)
        finally:
            con.close()

        # Update Gold aggregates automatically when Silver updates
        self.update_gold_features()
        return self.silver_file

    def get_silver_events(self) -> pd.DataFrame:
        """Loads all Silver events."""
        if not self.silver_file.exists():
            return pd.DataFrame(columns=[
                "event_id", "title", "description", "source", "url",
                "published_at", "collected_at", "affected_symbols",
                "affected_sectors", "sentiment", "importance", "confidence"
            ])
        con = duckdb.connect()
        try:
            return con.execute(f"SELECT * FROM read_parquet('{self.silver_file.as_posix()}') ORDER BY published_at ASC").df()
        finally:
            con.close()

    # ---------------------------------------------------------
    # Gold Layer: Symbol-Level Daily Aggregated Features
    # ---------------------------------------------------------
    def update_gold_features(self) -> Path:
        """
        Computes symbol-level numerical features from Silver events:
        - daily_sentiment_score: mean sentiment weighted by confidence and importance in [-1.0, 1.0]
        - event_count: number of events for the symbol on that day
        - max_importance: maximum event importance on that day (1-10)
        - avg_confidence: average confidence score
        """
        silver_df = self.get_silver_events()
        if silver_df.empty:
            return self.gold_file

        # Expand symbols: one row per (event, symbol)
        expanded_rows = []
        sentiment_map = {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}

        for _, row in silver_df.iterrows():
            symbols = [s.strip() for s in row["affected_symbols"].split(",") if s.strip()]
            if not symbols:
                # Macro event not tied to single symbol - can be assigned to 'MACRO' or 'NIFTY'
                symbols = ["MACRO"]

            pub_date = str(row["published_at"])[:10]  # YYYY-MM-DD
            sent_val = sentiment_map.get(str(row["sentiment"]).upper(), 0.0)
            imp = float(row["importance"])
            conf = float(row["confidence"])

            # Weighted impact = sent_val * (imp / 10.0) * conf
            impact = sent_val * (imp / 10.0) * conf

            for sym in symbols:
                expanded_rows.append({
                    "date": pub_date,
                    "symbol": sym,
                    "sentiment_value": sent_val,
                    "importance": imp,
                    "confidence": conf,
                    "impact": impact,
                    "published_at": row["published_at"],
                })

        if not expanded_rows:
            return self.gold_file

        exp_df = pd.DataFrame(expanded_rows)

        # Aggregate by date and symbol
        gold_df = exp_df.groupby(["date", "symbol"]).agg(
            sentiment_score=("impact", "mean"),
            raw_sentiment_mean=("sentiment_value", "mean"),
            event_count=("importance", "count"),
            max_importance=("importance", "max"),
            avg_confidence=("confidence", "mean")
        ).reset_index()

        # Clip sentiment_score into [-1.0, 1.0]
        gold_df["sentiment_score"] = gold_df["sentiment_score"].clip(-1.0, 1.0)
        gold_df = gold_df.sort_values(by=["date", "symbol"])

        con = duckdb.connect()
        try:
            con.register("gold_view", gold_df)
            con.execute(f"COPY gold_view TO '{self.gold_file.as_posix()}' (FORMAT PARQUET)")
            logger.info("Updated Gold news features: %d rows in %s", len(gold_df), self.gold_file)
        finally:
            con.close()

        return self.gold_file

    def get_gold_features(self, symbol: Optional[str] = None) -> pd.DataFrame:
        """Loads Gold news features, optionally filtered by symbol."""
        if not self.gold_file.exists():
            return pd.DataFrame(columns=[
                "date", "symbol", "sentiment_score", "raw_sentiment_mean",
                "event_count", "max_importance", "avg_confidence"
            ])
        con = duckdb.connect()
        try:
            if symbol:
                return con.execute(
                    f"SELECT * FROM read_parquet('{self.gold_file.as_posix()}') WHERE symbol = '{symbol}' ORDER BY date ASC"
                ).df()
            return con.execute(f"SELECT * FROM read_parquet('{self.gold_file.as_posix()}') ORDER BY date ASC, symbol ASC").df()
        finally:
            con.close()

    # ---------------------------------------------------------
    # Zero Look-Ahead Bias Historical Event Retrieval
    # ---------------------------------------------------------
    def get_events_up_to(
        self,
        as_of_datetime: datetime | str,
        symbol: Optional[str] = None,
        min_importance: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves historical events strictly published ON OR BEFORE as_of_datetime.
        Guarantees zero future information leakage during backtesting and live decision generation.
        """
        silver_df = self.get_silver_events()
        if silver_df.empty:
            return []

        # Parse as_of_datetime to ISO string
        if isinstance(as_of_datetime, datetime):
            if as_of_datetime.tzinfo is None:
                as_of_iso = as_of_datetime.replace(tzinfo=timezone.utc).isoformat()
            else:
                as_of_iso = as_of_datetime.astimezone(timezone.utc).isoformat()
        else:
            as_of_iso = str(as_of_datetime)
            # If string is just date YYYY-MM-DD, set to end of that day UTC
            if len(as_of_iso) == 10:
                as_of_iso = f"{as_of_iso}T23:59:59+00:00"

        # Filter strictly published_at <= as_of_iso
        filtered = silver_df[silver_df["published_at"] <= as_of_iso]
        filtered = filtered[filtered["importance"] >= min_importance]

        if symbol:
            symbol_upper = symbol.upper()
            filtered = filtered[filtered["affected_symbols"].apply(
                lambda s: symbol_upper in [item.strip() for item in s.split(",") if item.strip()]
            )]

        # Sort descending by published_at (most recent available first)
        filtered = filtered.sort_values(by="published_at", ascending=False).head(limit)

        results = []
        for _, row in filtered.iterrows():
            results.append({
                "event_id": row["event_id"],
                "title": row["title"],
                "description": row["description"],
                "source": row["source"],
                "url": row["url"],
                "published_at": row["published_at"],
                "collected_at": row["collected_at"],
                "affected_symbols": [s.strip() for s in row["affected_symbols"].split(",") if s.strip()],
                "affected_sectors": [s.strip() for s in row["affected_sectors"].split(",") if s.strip()],
                "sentiment": row["sentiment"],
                "importance": int(row["importance"]),
                "confidence": float(row["confidence"]),
            })
        return results

