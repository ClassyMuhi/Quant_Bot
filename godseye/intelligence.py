"""
Unified God's Eye Market Intelligence Engine
Coordinates RSS ingestion, entity extraction, sentiment classification,
Medallion event persistence, and look-ahead-safe event retrieval.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from godseye.collectors import RSSNewsCollector
from godseye.news_normalizer import NewsNormalizer
from godseye.event_classifier import EventClassifier
from godseye.event_store import EventStore

logger = logging.getLogger(__name__)


class GodsEyeIntelligence:
    """
    God's Eye Market Intelligence Coordinator.
    """

    def __init__(
        self,
        event_store: Optional[EventStore] = None,
        collector: Optional[RSSNewsCollector] = None,
        normalizer: Optional[NewsNormalizer] = None,
        classifier: Optional[EventClassifier] = None,
    ):
        self.store = event_store or EventStore()
        self.collector = collector or RSSNewsCollector()
        self.normalizer = normalizer or NewsNormalizer()
        self.classifier = classifier or EventClassifier()

    def collect_and_process(
        self,
        save_to_store: bool = True,
        batch_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Runs the full intelligence pipeline:
        1. Fetch raw news from Indian RSS feeds.
        2. Clean and identify affected NSE stocks & sectors.
        3. Classify sentiment, importance, and confidence.
        4. Save to Bronze, Silver, and update Gold features.
        """
        logger.info("God's Eye: Starting live news collection...")
        raw_items = self.collector.fetch_all()
        logger.info("God's Eye: Ingested %d raw items across RSS feeds.", len(raw_items))

        if not raw_items:
            return []

        # 1. Save to Bronze
        if save_to_store:
            self.store.save_bronze(raw_items, batch_name=batch_name)

        # 2. Normalize and Deduplicate
        normalized = self.normalizer.process_feed_items(raw_items)
        logger.info("God's Eye: Normalized into %d distinct unique events.", len(normalized))

        # 3. Classify Sentiment & Importance
        classified = self.classifier.classify_events(normalized)

        # 4. Save to Silver & update Gold
        if save_to_store and classified:
            self.store.save_silver(classified)
            logger.info("God's Eye: Persisted %d classified events to Silver.", len(classified))

        return classified

    def get_symbol_sentiment(
        self,
        symbol: str,
        as_of: Optional[datetime | str] = None,
        lookback_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Computes composite news sentiment for a given NSE symbol.
        Guarantees zero look-ahead bias if 'as_of' is provided.
        Returns:
            {
                "symbol": "RELIANCE",
                "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
                "score": float in [-1.0, 1.0],
                "confidence": float in [0.0, 1.0],
                "event_count": int,
                "latest_events": [...]
            }
        """
        as_of_dt = as_of or datetime.now(timezone.utc)
        events = self.store.get_events_up_to(as_of_datetime=as_of_dt, symbol=symbol, limit=20)

        if not events:
            return {
                "symbol": symbol.upper(),
                "sentiment": "NEUTRAL",
                "score": 0.0,
                "confidence": 0.0,
                "event_count": 0,
                "latest_events": [],
            }

        # Calculate weighted sentiment score
        # Impact = sent_score * (importance / 10.0) * confidence
        sent_map = {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}
        total_weight = 0.0
        weighted_sum = 0.0
        conf_sum = 0.0

        for e in events:
            val = sent_map.get(e["sentiment"].upper(), 0.0)
            imp = e["importance"]
            conf = e["confidence"]
            weight = (imp / 10.0) * conf

            weighted_sum += val * weight
            total_weight += weight
            conf_sum += conf

        avg_confidence = conf_sum / len(events)
        composite_score = (weighted_sum / total_weight) if total_weight > 0 else 0.0
        composite_score = max(-1.0, min(1.0, composite_score))

        if composite_score >= 0.2:
            sentiment_label = "BULLISH"
        elif composite_score <= -0.2:
            sentiment_label = "BEARISH"
        else:
            sentiment_label = "NEUTRAL"

        return {
            "symbol": symbol.upper(),
            "sentiment": sentiment_label,
            "score": round(composite_score, 4),
            "confidence": round(avg_confidence, 4),
            "event_count": len(events),
            "latest_events": events[:5],
        }

    def get_market_sentiment_summary(
        self,
        as_of: Optional[datetime | str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """
        Returns broad market intelligence summary across all stocks and macro events.
        """
        as_of_dt = as_of or datetime.now(timezone.utc)
        events = self.store.get_events_up_to(as_of_datetime=as_of_dt, symbol=None, limit=limit)

        bullish_count = sum(1 for e in events if e["sentiment"] == "BULLISH")
        bearish_count = sum(1 for e in events if e["sentiment"] == "BEARISH")
        neutral_count = sum(1 for e in events if e["sentiment"] == "NEUTRAL")

        return {
            "total_events": len(events),
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "neutral_count": neutral_count,
            "events": events,
        }

