"""
Unit Tests for Decision Engine
Validates multi-factor scoring, news-only guardrails, conflict dampening,
confidence thresholds, and risk bounds.
"""

from datetime import datetime, timezone
import pytest
from decision_engine.scoring import compute_technical_score, evaluate_confluence
from decision_engine.risk_rules import calculate_entry_sl_target
from decision_engine.explanation import generate_explanation
from decision_engine.engine import DecisionEngine


def test_technical_scoring_bullish_and_bearish():
    bullish_indicators = {
        "rsi_14": 58.5,
        "sma_20": 2600.0,
        "sma_50": 2500.0,
        "macd": 15.0,
        "macd_signal": 10.0,
        "return_20d": 0.05,
        "volatility_20d": 0.18,
    }
    score, conf, components = compute_technical_score(bullish_indicators)
    assert score > 0.4
    assert conf >= 0.7
    assert components["rsi"]["signal"] == "BULLISH_MOMENTUM"
    assert components["trend"]["signal"] == "BULLISH_TREND"

    bearish_indicators = {
        "rsi_14": 38.0,
        "sma_20": 2400.0,
        "sma_50": 2550.0,
        "macd": -12.0,
        "macd_signal": -5.0,
        "return_20d": -0.06,
        "volatility_20d": 0.22,
    }
    b_score, b_conf, b_comp = compute_technical_score(bearish_indicators)
    assert b_score < -0.4
    assert b_comp["trend"]["signal"] == "BEARISH_TREND"


def test_rule_news_cannot_trigger_order_alone():
    """
    CRITICAL RULE: If technical indicators are neutral (|tech_score| < 0.2),
    news alone CANNOT trigger BUY or SELL, even with 100% bullish sentiment.
    """
    tech_score = 0.05  # Neutral technicals
    tech_conf = 0.60
    super_bullish_news = {
        "sentiment": "BULLISH",
        "score": 1.0,
        "confidence": 0.95,
        "event_count": 5,
    }

    result = evaluate_confluence(
        technical_score=tech_score,
        technical_confidence=tech_conf,
        news_sentiment=super_bullish_news,
        min_confidence_threshold=0.50,
    )

    assert result["decision"] == "HOLD"
    assert "news cannot independently" in result["reason_rule"].lower()


def test_conflicting_signals_dampen_confidence():
    """
    When technicals are Bullish but event intelligence is Bearish,
    confidence is penalized by 50% and score is dampened.
    """
    tech_score = 0.70
    tech_conf = 0.80
    bearish_news = {
        "sentiment": "BEARISH",
        "score": -0.80,
        "confidence": 0.85,
        "event_count": 3,
    }

    result = evaluate_confluence(
        technical_score=tech_score,
        technical_confidence=tech_conf,
        news_sentiment=bearish_news,
        min_confidence_threshold=0.50,
    )

    assert result["is_conflict"] is True
    assert result["confidence"] <= 0.45  # Halved from 0.80
    # Because confidence dropped below min threshold 0.50, decision must be HOLD
    assert result["decision"] == "HOLD"


def test_concordant_signals_boost_confidence():
    """
    When technicals and news agree (Bullish + Bullish), confidence is boosted.
    """
    tech_score = 0.65
    tech_conf = 0.75
    bullish_news = {
        "sentiment": "BULLISH",
        "score": 0.75,
        "confidence": 0.80,
        "event_count": 2,
    }

    result = evaluate_confluence(
        technical_score=tech_score,
        technical_confidence=tech_conf,
        news_sentiment=bullish_news,
        min_confidence_threshold=0.50,
    )

    assert result["is_confluence"] is True
    assert result["confidence"] > 0.75
    assert result["decision"] == "BUY"


def test_risk_rules_and_invariant_enforcement():
    indicators = {"volatility_20d": 0.20}
    current_price = 2500.0

    # BUY Setup: Stop-loss must be < Entry and Target > Entry
    entry, sl, tp, err = calculate_entry_sl_target("BUY", current_price, indicators)
    assert err is None
    assert sl < entry
    assert tp > entry
    assert round(abs(tp - entry) / abs(entry - sl), 1) == 2.0  # 1:2 R:R

    # SELL Setup: Stop-loss must be > Entry and Target < Entry
    s_entry, s_sl, s_tp, s_err = calculate_entry_sl_target("SELL", current_price, indicators)
    assert s_err is None
    assert s_sl > s_entry
    assert s_tp < s_entry

    # HOLD Setup
    h_entry, h_sl, h_tp, h_err = calculate_entry_sl_target("HOLD", current_price, indicators)
    assert h_entry is None


def test_decision_engine_stale_or_missing_data():
    engine = DecisionEngine()
    # Evaluating a non-existent symbol must safely return HOLD with explanation
    res = engine.evaluate("NONEXISTENT_SYMBOL_XYZ")
    assert res.decision == "HOLD"
    assert res.is_actionable is False
    assert "not found" in res.explanation.lower()

