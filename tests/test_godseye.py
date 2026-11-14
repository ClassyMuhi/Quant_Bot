"""
Unit Tests for God's Eye Market Intelligence System
"""

import json
from datetime import datetime, timezone, timedelta
import pytest
from pathlib import Path
from godseye.collectors import RSSNewsCollector
from godseye.news_normalizer import NewsNormalizer
from godseye.event_classifier import EventClassifier
from godseye.event_store import EventStore
from godseye.intelligence import GodsEyeIntelligence


def test_rss_news_collector_parsing():
    collector = RSSNewsCollector()
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>NSE Market News</title>
        <item>
          <title>Reliance Q3 Net Profit Surges 15% on Strong Oil and Retail Growth</title>
          <link>https://example.com/reliance-q3-profit</link>
          <description>Reliance Industries reported robust third-quarter earnings with gross revenues expanding.</description>
          <pubDate>Mon, 15 Jan 2024 10:30:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    items = collector.parse_rss_content(sample_xml, "Test Source")
    assert len(items) == 1
    assert "Reliance" in items[0]["title"]
    assert items[0]["source"] == "Test Source"
    assert "2024-01-15" in items[0]["published_at"]


def test_news_normalizer_symbol_and_sector():
    normalizer = NewsNormalizer()
    raw_item = {
        "title": "TCS signs multi-year deal worth $1B with UK insurer, boosting IT sector outlook",
        "description": "Tata Consultancy Services won a major digital transformation contract.",
        "url": "https://example.com/tcs-deal",
        "source": "Moneycontrol",
        "published_at": "2024-02-10T12:00:00+00:00",
    }
    processed = normalizer.process_feed_items([raw_item])
    assert len(processed) == 1
    event = processed[0]
    assert "TCS" in event["affected_symbols"]
    assert "Information Technology" in event["affected_sectors"]


def test_news_normalizer_deduplication():
    normalizer = NewsNormalizer()
    items = [
        {
            "title": "RBI keeps repo rate unchanged at 6.5 percent in monetary policy",
            "url": "https://example.com/rbi-1",
            "source": "ET",
            "published_at": "2024-02-08T09:00:00+00:00",
            "description": "RBI monetary policy committee keeps repo rate steady.",
        },
        {
            "title": "RBI leaves repo rate unchanged at 6.5% in latest monetary policy meeting",
            "url": "https://example.com/rbi-2",
            "source": "Livemint",
            "published_at": "2024-02-08T09:15:00+00:00",
            "description": "Reserve Bank of India maintained status quo on benchmark lending rates.",
        },
    ]
    # Deduplication should collapse nearly identical headlines
    deduped = normalizer.process_feed_items(items)
    assert len(deduped) == 1


def test_event_classifier_sentiment_and_importance():
    classifier = EventClassifier(use_llm_if_available=False)

    bullish_event = {
        "title": "Infosys reports record profit jump and raises full year revenue guidance",
        "description": "Net profit up 12% beat market estimates with strong deal wins.",
    }
    b_res = classifier.classify_single_event(bullish_event)
    assert b_res["sentiment"] == "BULLISH"
    assert b_res["importance"] >= 6
    assert b_res["confidence"] >= 0.7

    bearish_event = {
        "title": "SEBI slaps penalty on major bank as net loss widens and NPAs surge",
        "description": "Investigation into governance breaches led to heavy regulatory sanction.",
    }
    s_res = classifier.classify_single_event(bearish_event)
    assert s_res["sentiment"] == "BEARISH"
    assert s_res["importance"] >= 7


def test_event_store_and_zero_lookahead_leakage(tmp_path):
    store = EventStore(
        bronze_dir=tmp_path / "bronze",
        silver_dir=tmp_path / "silver",
        gold_dir=tmp_path / "gold",
    )

    events = [
        {
            "event_id": "ev_past",
            "title": "Reliance Q2 Profit surges",
            "description": "Solid performance in retail.",
            "source": "ET",
            "url": "https://example.com/p1",
            "published_at": "2024-01-10T10:00:00+00:00",
            "collected_at": "2024-01-10T10:05:00+00:00",
            "affected_symbols": ["RELIANCE"],
            "affected_sectors": ["Energy"],
            "sentiment": "BULLISH",
            "importance": 8,
            "confidence": 0.85,
        },
        {
            "event_id": "ev_future",
            "title": "Reliance profit slumps in surprise reversal",
            "description": "Margin compression hurts bottom line.",
            "source": "Livemint",
            "url": "https://example.com/p2",
            "published_at": "2024-01-20T14:00:00+00:00",
            "collected_at": "2024-01-20T14:05:00+00:00",
            "affected_symbols": ["RELIANCE"],
            "affected_sectors": ["Energy"],
            "sentiment": "BEARISH",
            "importance": 7,
            "confidence": 0.80,
        },
    ]

    store.save_silver(events)

    # Historical query at date 2024-01-15 MUST NOT see ev_future!
    as_of = "2024-01-15T23:59:59+00:00"
    visible_events = store.get_events_up_to(as_of, symbol="RELIANCE")

    assert len(visible_events) == 1
    assert visible_events[0]["event_id"] == "ev_past"
    assert visible_events[0]["sentiment"] == "BULLISH"

    # Query at later date 2024-01-25 sees both
    all_visible = store.get_events_up_to("2024-01-25T23:59:59+00:00", symbol="RELIANCE")
    assert len(all_visible) == 2

