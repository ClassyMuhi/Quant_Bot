"""
Scoring and Confluence Engine for Decision Engine
Combines multi-factor technical signals with God's Eye event intelligence.
Strictly enforces:
1. News sentiment cannot independently trigger an order (no trade without technical signal).
2. Neutral or low-confidence news has dampened influence.
3. Conflicting signals reduce overall confidence.
4. Confluence boosts confidence.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def compute_technical_score(indicators: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
    """
    Computes normalized technical score in [-1.0, 1.0] and raw technical confidence in [0.0, 1.0].
    
    Factors considered:
    1. RSI (14-day):
       - < 30: Oversold / reversal potential (+0.4)
       - 50 to 65: Bullish momentum zone (+0.4)
       - > 70: Overbought / exhaustion risk (-0.4)
       - 35 to 50: Bearish momentum zone (-0.3)
    2. Trend (SMA 20 vs SMA 50):
       - SMA 20 > SMA 50: Golden trend (+0.4)
       - SMA 20 < SMA 50: Death trend (-0.4)
    3. MACD:
       - MACD > Signal: Bullish crossover (+0.3)
       - MACD < Signal: Bearish crossover (-0.3)
    4. Momentum / Return (return_20d if available):
       - Positive return: (+0.2)
       - Negative return: (-0.2)

    Returns:
        (technical_score, technical_confidence, factor_breakdown)
    """
    rsi = float(indicators.get("rsi_14", 50.0))
    sma20 = float(indicators.get("sma_20", 0.0))
    sma50 = float(indicators.get("sma_50", 0.0))
    macd = float(indicators.get("macd", 0.0))
    macd_signal = float(indicators.get("macd_signal", 0.0))
    ret20 = float(indicators.get("return_20d", 0.0))

    components = {}

    # 1. RSI Factor
    if rsi < 30.0:
        rsi_score = 0.5  # Strong oversold bounce
        rsi_signal = "OVERSOLD_BULLISH"
    elif 50.0 <= rsi <= 68.0:
        rsi_score = 0.35  # Healthy bullish trend
        rsi_signal = "BULLISH_MOMENTUM"
    elif rsi > 70.0:
        rsi_score = -0.45  # Overbought pullback risk
        rsi_signal = "OVERBOUGHT_BEARISH"
    elif 30.0 <= rsi < 50.0:
        rsi_score = -0.35  # Bearish momentum
        rsi_signal = "BEARISH_MOMENTUM"
    else:
        rsi_score = 0.0
        rsi_signal = "NEUTRAL"

    components["rsi"] = {"value": rsi, "score": rsi_score, "signal": rsi_signal}

    # 2. Moving Average Trend Factor
    if sma20 > 0 and sma50 > 0:
        diff_pct = (sma20 - sma50) / sma50
        if diff_pct > 0.005:
            sma_score = 0.4
            sma_signal = "BULLISH_TREND"
        elif diff_pct < -0.005:
            sma_score = -0.4
            sma_signal = "BEARISH_TREND"
        else:
            sma_score = 0.0
            sma_signal = "NEUTRAL_TREND"
    else:
        sma_score = 0.0
        sma_signal = "UNKNOWN"

    components["trend"] = {"sma20": sma20, "sma50": sma50, "score": sma_score, "signal": sma_signal}

    # 3. MACD Factor
    macd_diff = macd - macd_signal
    if macd_diff > 0:
        macd_score = 0.3
        macd_signal_str = "BULLISH_CROSSOVER"
    elif macd_diff < 0:
        macd_score = -0.3
        macd_signal_str = "BEARISH_CROSSOVER"
    else:
        macd_score = 0.0
        macd_signal_str = "NEUTRAL"

    components["macd"] = {"macd": macd, "signal": macd_signal, "score": macd_score, "type": macd_signal_str}

    # 4. Momentum Factor
    if ret20 > 0.02:
        mom_score = 0.2
        mom_signal = "POSITIVE"
    elif ret20 < -0.02:
        mom_score = -0.2
        mom_signal = "NEGATIVE"
    else:
        mom_score = 0.0
        mom_signal = "FLAT"

    components["momentum"] = {"return_20d": ret20, "score": mom_score, "signal": mom_signal}

    # Weighted Composite Technical Score (Total max theoretical sum ~ 1.4, normalize to [-1, 1])
    raw_tech_score = (rsi_score * 0.35) + (sma_score * 0.35) + (macd_score * 0.20) + (mom_score * 0.10)
    # Scale slightly so clear alignment reaches >= 0.6
    scaled_tech_score = max(-1.0, min(1.0, raw_tech_score * 2.2))

    # Base technical confidence depends on agreement among indicators
    signs = [s > 0 for s in [rsi_score, sma_score, macd_score, mom_score] if abs(s) > 0.05]
    if not signs:
        tech_confidence = 0.4
    else:
        agreement = max(sum(signs), len(signs) - sum(signs)) / len(signs)
        tech_confidence = round(0.5 + 0.4 * agreement, 2)

    return round(scaled_tech_score, 4), tech_confidence, components


def evaluate_confluence(
    technical_score: float,
    technical_confidence: float,
    news_sentiment: Dict[str, Any],
    min_confidence_threshold: float = 0.50,
) -> Dict[str, Any]:
    """
    Combines technical score and God's Eye event intelligence according to strict rules:
    - Rule 1: News sentiment cannot independently trigger an order.
      If |technical_score| < 0.20, Decision is forced to HOLD.
    - Rule 2: Low-confidence / neutral news has minimal influence.
    - Rule 3: Conflicting signals (e.g. Bullish Tech vs Bearish News) penalize confidence by 50%.
    - Rule 4: Concordant signals boost confidence and conviction.

    Returns structured decision payload.
    """
    event_score = float(news_sentiment.get("score", 0.0))
    event_confidence = float(news_sentiment.get("confidence", 0.0))
    event_count = int(news_sentiment.get("event_count", 0))

    # 1. Base weights
    # Technical carries 75% baseline weight, News carries 25% weight when present
    if event_count == 0 or event_confidence < 0.2:
        effective_event_weight = 0.0
        tech_weight = 1.0
    else:
        effective_event_weight = 0.25 * event_confidence
        tech_weight = 1.0 - effective_event_weight

    raw_combined_score = (technical_score * tech_weight) + (event_score * effective_event_weight)
    raw_combined_score = max(-1.0, min(1.0, raw_combined_score))

    # 2. Check for Conflict vs Confluence
    is_conflict = False
    is_confluence = False
    final_confidence = technical_confidence

    if event_count > 0 and event_confidence >= 0.4:
        if (technical_score > 0.2 and event_score < -0.2) or (technical_score < -0.2 and event_score > 0.2):
            is_conflict = True
            # Halve confidence and dampen combined score
            final_confidence = round(final_confidence * 0.5, 2)
            raw_combined_score = round(raw_combined_score * 0.5, 4)
        elif (technical_score > 0.2 and event_score > 0.2) or (technical_score < -0.2 and event_score < -0.2):
            is_confluence = True
            # Boost confidence
            final_confidence = min(0.95, round(final_confidence + 0.15 * event_confidence, 2))

    # 3. Apply Fundamental Rule: News alone cannot trigger trade
    # If technical score is neutral (|tech_score| < 0.20), no trade can be initiated
    tech_is_neutral = abs(technical_score) < 0.20

    if tech_is_neutral:
        decision = "HOLD"
        reason_rule = "Technical indicators are neutral; news cannot independently initiate trade."
    elif final_confidence < min_confidence_threshold:
        decision = "HOLD"
        reason_rule = f"Confidence ({final_confidence:.2f}) below minimum required threshold ({min_confidence_threshold:.2f})."
    elif raw_combined_score >= 0.25:
        decision = "BUY"
        reason_rule = "Bullish technical confirmation supported or uncontradicted by event intelligence."
    elif raw_combined_score <= -0.25:
        decision = "SELL"
        reason_rule = "Bearish technical confirmation supported or uncontradicted by event intelligence."
    else:
        decision = "HOLD"
        reason_rule = "Combined score within neutral buffer band (-0.25 to +0.25)."

    # Technical signal label
    if technical_score >= 0.2:
        tech_signal_label = "BULLISH"
    elif technical_score <= -0.2:
        tech_signal_label = "BEARISH"
    else:
        tech_signal_label = "NEUTRAL"

    return {
        "decision": decision,
        "technical_signal": tech_signal_label,
        "technical_score": technical_score,
        "event_sentiment": news_sentiment.get("sentiment", "NEUTRAL"),
        "event_score": event_score,
        "event_confidence": event_confidence,
        "combined_score": round(raw_combined_score, 4),
        "confidence": final_confidence,
        "is_conflict": is_conflict,
        "is_confluence": is_confluence,
        "reason_rule": reason_rule,
    }

